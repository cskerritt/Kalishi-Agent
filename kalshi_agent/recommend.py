"""Scan-and-pick workflow.

`scan` snapshots liquid markets resolving soon (using prod's public market
data, where real prices live) into a JSON file an analyst — human or Claude —
can review. The analyst writes a numbered picks file, and `execute` places the
chosen picks on the active environment after the usual risk checks.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from .client import KalshiAPIError, KalshiClient
from .config import Config
from .risk import OrderIntent, RiskManager, RiskViolation

SCAN_FILE = ".scan.json"
PICKS_FILE = "picks.json"

_SNAPSHOT_FIELDS = (
    "ticker", "event_ticker", "title", "subtitle", "yes_sub_title",
    "rules_primary", "yes_bid", "yes_ask", "no_bid", "no_ask", "last_price",
    "volume", "volume_24h", "open_interest", "liquidity", "close_time",
    "expiration_time",
)


def scan_markets(
    hours: float = 36,
    limit: int = 25,
    series: str | None = None,
    min_volume: int = 500,
    out: str = SCAN_FILE,
) -> list[dict[str, Any]]:
    """Snapshot the most liquid open markets closing within `hours`."""
    client = KalshiClient(Config(env="prod"))
    now = int(time.time())
    markets: list[dict[str, Any]] = []
    cursor = None
    for _ in range(10):  # up to 10 pages of 200
        data = client.get_markets(
            status="open", series_ticker=series, limit=200, cursor=cursor,
            min_close_ts=now, max_close_ts=now + int(hours * 3600),
        )
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break

    liquid = [
        m for m in markets
        if (m.get("volume") or 0) >= min_volume
        and m.get("yes_bid") and m.get("yes_ask")
        and 1 <= m["yes_ask"] <= 99
    ]
    liquid.sort(key=lambda m: -(m.get("volume") or 0))
    snapshot = [{k: m.get(k) for k in _SNAPSHOT_FIELDS} for m in liquid[:limit]]

    with open(out, "w") as f:
        json.dump(
            {"generated_at": now, "hours": hours, "series": series,
             "scanned": len(markets), "candidates": snapshot},
            f, indent=2,
        )
    return snapshot


def execute_picks(
    numbers: list[int],
    picks_file: str = PICKS_FILE,
    live: bool = False,
) -> None:
    """Place the picks with the given numbers from a picks file.

    Picks file format:
      {"picks": [{"n": 1, "ticker": ..., "side": "yes"|"no", "count": int,
                  "price_cents": int, "rationale": str}, ...]}
    """
    config = Config()
    client = KalshiClient(config)
    risk = RiskManager(config)

    with open(picks_file) as f:
        picks = {p["n"]: p for p in json.load(f)["picks"]}

    unknown = [n for n in numbers if n not in picks]
    if unknown:
        sys.exit(f"No such pick(s): {unknown}. Available: {sorted(picks)}")

    for n in numbers:
        p = picks[n]
        intent = OrderIntent(p["ticker"], p["side"], "buy", p["count"], p["price_cents"])
        positions = client.get_positions(ticker=p["ticker"]).get("market_positions", [])
        held = sum(abs(pos.get("position", 0)) for pos in positions)
        try:
            risk.check(intent, held)
        except RiskViolation as e:
            print(f"#{n} BLOCKED by risk limits: {e}")
            continue

        print(
            f"#{n} BUY {p['count']} x {p['side'].upper()} {p['ticker']} "
            f"@ {p['price_cents']}c  (max cost ${intent.cost_cents / 100:.2f}, "
            f"env={config.env})"
        )
        if not live:
            print(f"#{n} [DRY RUN] Not sent. Re-run with --live to place it.")
            continue
        try:
            result = client.create_order(
                ticker=p["ticker"], side=p["side"], action="buy",
                count=p["count"], order_type="limit", price_cents=p["price_cents"],
            )
        except KalshiAPIError as e:
            print(f"#{n} FAILED: {e}")
            continue
        risk.record_spend(intent.cost_cents)
        print(f"#{n} placed: order_id={result.get('order_id')} "
              f"filled={result.get('fill_count')} resting={result.get('remaining_count')}")
