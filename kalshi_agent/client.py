"""Kalshi trade API v2 client with signed requests."""

from __future__ import annotations

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


class KalshiClient:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.config.validate_credentials()
        self._private_key = load_private_key(self.config.private_key_path)
        self._session = requests.Session()

    # ------------------------------------------------------------------ core

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        full_path = API_PREFIX + path
        headers = build_auth_headers(
            self.config.api_key_id, self._private_key, method, full_path
        )
        headers["Content-Type"] = "application/json"
        resp = self._session.request(
            method,
            self.config.base_url + full_path,
            params=params,
            json=json_body,
            headers=headers,
            timeout=30,
        )
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
        return self._request("GET", "/exchange/status")

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
        return self._request("GET", "/events", params=params)

    def get_markets(self, status: str | None = None, event_ticker: str | None = None,
                    series_ticker: str | None = None, tickers: str | None = None,
                    limit: int = 100, cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
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
        return self._request("GET", "/markets", params=params)

    def get_market(self, ticker: str) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})

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
        buy_max_cost_cents: int | None = None,
    ) -> dict[str, Any]:
        """Place an order. Prices are integer cents in [1, 99]."""
        if side not in ("yes", "no"):
            raise ValueError("side must be 'yes' or 'no'")
        if action not in ("buy", "sell"):
            raise ValueError("action must be 'buy' or 'sell'")
        if count < 1:
            raise ValueError("count must be >= 1")
        if order_type == "limit":
            if price_cents is None or not (1 <= price_cents <= 99):
                raise ValueError("limit orders require price_cents in [1, 99]")

        body: dict[str, Any] = {
            "ticker": ticker,
            "client_order_id": client_order_id or str(uuid.uuid4()),
            "side": side,
            "action": action,
            "count": count,
            "type": order_type,
        }
        if order_type == "limit" and price_cents is not None:
            body["yes_price" if side == "yes" else "no_price"] = price_cents
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts
        if buy_max_cost_cents is not None:
            body["buy_max_cost"] = buy_max_cost_cents
        return self._request("POST", "/portfolio/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/portfolio/orders/{order_id}")
