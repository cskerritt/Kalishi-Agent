"""Kalshi trade API v2 client with signed requests."""

from __future__ import annotations

import time
import uuid
from typing import Any

import requests

from .auth import build_auth_headers, load_private_key
from .config import API_PREFIX, Config


class KalshiAPIError(Exception):
    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Kalshi API error {status_code}: {body}")


_DOLLAR_FIELDS = {
    "yes_bid_dollars": "yes_bid",
    "yes_ask_dollars": "yes_ask",
    "no_bid_dollars": "no_bid",
    "no_ask_dollars": "no_ask",
    "last_price_dollars": "last_price",
    "liquidity_dollars": "liquidity",
}
_FP_FIELDS = {
    "volume_fp": "volume",
    "volume_24h_fp": "volume_24h",
    "open_interest_fp": "open_interest",
}


def normalize_market(m: dict[str, Any]) -> dict[str, Any]:
    """Backfill legacy integer-cent fields from the newer *_dollars / *_fp strings.

    The API now returns prices as fixed-point dollar strings ("0.4500") and
    counts as fixed-point strings ("82.00"); the rest of the codebase works in
    integer cents and counts.
    """
    for src, dst in _DOLLAR_FIELDS.items():
        if m.get(dst) is None and m.get(src) is not None:
            m[dst] = round(float(m[src]) * 100)
    for src, dst in _FP_FIELDS.items():
        if m.get(dst) is None and m.get(src) is not None:
            m[dst] = int(float(m[src]))
    return m


class KalshiClient:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._private_key = None
        self._session = requests.Session()

    # ------------------------------------------------------------------ core

    def _ensure_key(self):
        if self._private_key is None:
            self.config.validate_credentials()
            self._private_key = load_private_key(self.config.private_key_path)
        return self._private_key

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        signed: bool = True,
    ) -> dict[str, Any]:
        full_path = API_PREFIX + path
        headers = {"Content-Type": "application/json"}
        if signed:
            headers.update(
                build_auth_headers(
                    self.config.api_key_id, self._ensure_key(), method, full_path
                )
            )
        for attempt in range(4):
            resp = self._session.request(
                method,
                self.config.base_url + full_path,
                params=params,
                json=json_body,
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 429:
                break
            time.sleep(1.5 * (attempt + 1))
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise KalshiAPIError(resp.status_code, body)
        if not resp.content:
            return {}
        return resp.json()

    # -------------------------------------------------------------- exchange

    def exchange_status(self) -> dict[str, Any]:
        return self._request("GET", "/exchange/status", signed=False)

    # --------------------------------------------------------------- markets

    def get_events(self, status: str | None = None, series_ticker: str | None = None,
                   limit: int = 100, cursor: str | None = None) -> dict[str, Any]:
        params = {"limit": limit}
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/events", params=params, signed=False)

    def get_markets(self, status: str | None = None, event_ticker: str | None = None,
                    series_ticker: str | None = None, tickers: str | None = None,
                    limit: int = 100, cursor: str | None = None,
                    min_close_ts: int | None = None,
                    max_close_ts: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if tickers:
            params["tickers"] = tickers
        if cursor:
            params["cursor"] = cursor
        data = self._request("GET", "/markets", params=params, signed=False)
        for m in data.get("markets", []):
            normalize_market(m)
        return data

    def get_market(self, ticker: str) -> dict[str, Any]:
        data = self._request("GET", f"/markets/{ticker}", signed=False)
        if "market" in data:
            normalize_market(data["market"])
        return data

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        return self._request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": depth}, signed=False
        )

    # ------------------------------------------------------------- portfolio

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/portfolio/balance")

    def get_positions(self, ticker: str | None = None, limit: int = 100) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return self._request("GET", "/portfolio/positions", params=params)

    def get_orders(self, ticker: str | None = None, status: str | None = None,
                   limit: int = 100) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        return self._request("GET", "/portfolio/orders", params=params)

    def get_fills(self, ticker: str | None = None, limit: int = 100) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return self._request("GET", "/portfolio/fills", params=params)

    # ----------------------------------------------------------------- orders

    def create_order(
        self,
        ticker: str,
        side: str,           # "yes" | "no"
        action: str,         # "buy" | "sell"
        count: int,
        order_type: str = "limit",   # "limit" | "market"
        price_cents: int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
    ) -> dict[str, Any]:
        """Place an order via the v2 endpoint. Prices are integer cents in [1, 99].

        The v2 API expresses every order on the YES leg as a bid or ask, so
        yes/no + buy/sell are mapped: NO orders become the mirrored YES order
        at (100 - price). "market" orders are sent as immediate-or-cancel at
        the most aggressive price.
        """
        if side not in ("yes", "no"):
            raise ValueError("side must be 'yes' or 'no'")
        if action not in ("buy", "sell"):
            raise ValueError("action must be 'buy' or 'sell'")
        if count < 1:
            raise ValueError("count must be >= 1")
        if order_type == "limit":
            if price_cents is None or not (1 <= price_cents <= 99):
                raise ValueError("limit orders require price_cents in [1, 99]")

        # Map to the YES leg: buying YES / selling NO takes the bid side;
        # selling YES / buying NO takes the ask side. NO prices mirror to 100-p.
        v2_side = "bid" if (side == "yes") == (action == "buy") else "ask"
        if order_type == "market":
            yes_price_cents = 99 if v2_side == "bid" else 1
            time_in_force = "immediate_or_cancel"
        else:
            yes_price_cents = price_cents if side == "yes" else 100 - price_cents
            time_in_force = "good_till_canceled"

        body: dict[str, Any] = {
            "ticker": ticker,
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "side": v2_side,
            "count": str(count),
            "price": f"{yes_price_cents / 100:.2f}",
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
        }
        if expiration_ts is not None:
            body["expiration_time"] = expiration_ts
        return self._request("POST", "/portfolio/events/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/portfolio/events/orders/{order_id}")
