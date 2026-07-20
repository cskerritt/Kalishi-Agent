"""Bet journal: every live order is recorded with its thesis and model
snapshot, settlements are pulled from the exchange, and losses are flagged
for post-mortem so the model can be improved (see CLAUDE.md discipline).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from .client import KalshiAPIError, KalshiClient

JOURNAL_FILE = "journal.json"


def _load(path: str = JOURNAL_FILE) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _save(entries: list[dict[str, Any]], path: str = JOURNAL_FILE) -> None:
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)


def record_bet(
    ticker: str,
    side: str,
    count: int,
    price_cents: int,
    order_id: str,
    env: str,
    thesis: str = "",
    fair_cents: int | None = None,
    conviction: str = "",
    model_snapshot: dict[str, Any] | None = None,
    path: str = JOURNAL_FILE,
) -> None:
    entries = _load(path)
    entries.append({
        "placed_at": int(time.time()),
        "ticker": ticker,
        "side": side,
        "count": count,
        "price_cents": price_cents,
        "order_id": order_id,
        "env": env,
        "thesis": thesis,
        "fair_cents": fair_cents,
        "conviction": conviction,
        "model_snapshot": model_snapshot or {},
        "status": "open",          # open | won | lost | void
        "fill_count": None,        # set at settlement from fills
        "pnl_cents": None,
        "postmortem": None,        # written by the analyst after a loss
    })
    _save(entries, path)


def update_settlements(client: KalshiClient | None = None,
                       path: str = JOURNAL_FILE) -> list[dict[str, Any]]:
    """Check open journal entries against market results; returns entries
    that changed (each needs a post-mortem if lost)."""
    client = client or KalshiClient()
    entries = _load(path)
    changed = []
    for e in entries:
        if e["status"] != "open":
            continue
        try:
            m = client.get_market(e["ticker"]).get("market", {})
        except KalshiAPIError:
            continue
        result = m.get("result")  # "yes" | "no" | "" while unsettled
        if m.get("status") not in ("finalized", "settled") or result not in ("yes", "no"):
            continue
        fills = client.get_fills(ticker=e["ticker"]).get("fills", [])
        filled = sum(
            float(f.get("count_fp") or f.get("count") or 0)
            for f in fills
            if (f.get("side") or "") == e["side"]
        )
        e["fill_count"] = filled
        if filled == 0:
            e["status"] = "void"
            e["pnl_cents"] = 0
        else:
            won = result == e["side"]
            e["status"] = "won" if won else "lost"
            e["pnl_cents"] = round(
                filled * ((100 - e["price_cents"]) if won else -e["price_cents"])
            )
        e["settled_result"] = result
        e["settled_at"] = int(time.time())
        changed.append(e)
    _save(entries, path)
    return changed


def summarize(path: str = JOURNAL_FILE) -> dict[str, Any]:
    entries = _load(path)
    settled = [e for e in entries if e["status"] in ("won", "lost")]
    wins = [e for e in settled if e["status"] == "won"]
    return {
        "total_bets": len(entries),
        "open": sum(1 for e in entries if e["status"] == "open"),
        "void": sum(1 for e in entries if e["status"] == "void"),
        "settled": len(settled),
        "won": len(wins),
        "hit_rate": round(len(wins) / len(settled), 3) if settled else None,
        "pnl_cents": sum(e["pnl_cents"] or 0 for e in settled),
        "awaiting_postmortem": [
            e["ticker"] for e in entries
            if e["status"] == "lost" and not e.get("postmortem")
        ],
    }
