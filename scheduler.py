"""Long-running scheduler for Railway.

Daily routine (all times America/New_York):
  08:11  weather scan  -> notify (+ auto-trade if AUTO_TRADE=true)
  14:07  sports drift  -> notify (+ auto-trade if AUTO_TRADE=true)
  20:19  settle + P&L  -> notify; flags losses needing post-mortem
  Mon 09:04  profit check vs target -> notify only when target reached

AUTO_TRADE (default false) gates ALL live order placement. When on, only
policy-passing picks are placed: net edge >= MIN_NET_EDGE, price <= 10c
(cheap defined-risk) or a threshold strike far from forecast, sized
AUTO_STAKE_CENTS per pick, max AUTO_MAX_PICKS_PER_DAY per day, always
within the RiskManager daily cap. Every placement is journaled.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import traceback
from zoneinfo import ZoneInfo

from kalshi_agent.client import KalshiClient
from kalshi_agent.config import Config
from kalshi_agent.edges import scan_edges
from kalshi_agent.journal import record_bet, summarize, update_settlements
from kalshi_agent.notify import notify
from kalshi_agent.risk import OrderIntent, RiskManager, RiskViolation

ET = ZoneInfo("America/New_York")

AUTO_TRADE = os.environ.get("AUTO_TRADE", "false").lower() == "true"
MIN_NET_EDGE = int(os.environ.get("MIN_NET_EDGE", "10"))
AUTO_STAKE_CENTS = int(os.environ.get("AUTO_STAKE_CENTS", "800"))   # $8 per pick
AUTO_MAX_PICKS_PER_DAY = int(os.environ.get("AUTO_MAX_PICKS_PER_DAY", "3"))
PROFIT_BASELINE = float(os.environ.get("PROFIT_BASELINE", "814.00"))
PROFIT_TARGET = float(os.environ.get("PROFIT_TARGET", "689.00"))

_auto_placed_today: dict[str, int] = {"date": "", "n": 0}


def _tradable(e) -> bool:
    """Conservative auto-trade filter: cheap defined-risk or far-from-forecast."""
    if e.net_edge_cents < MIN_NET_EDGE:
        return False
    if e.category == "weather":
        return e.price_cents <= 10  # cheap NWS-aligned tails/bands only
    if e.category == "sports":
        return 15 <= e.price_cents <= 85  # sane range, devig-backed
    return False


def _auto_trade(edges) -> list[str]:
    today = dt.datetime.now(ET).strftime("%Y-%m-%d")
    if _auto_placed_today["date"] != today:
        _auto_placed_today.update(date=today, n=0)
    placed = []
    config = Config()
    client = KalshiClient(config)
    risk = RiskManager(config)
    for e in edges:
        if _auto_placed_today["n"] >= AUTO_MAX_PICKS_PER_DAY:
            break
        if not _tradable(e):
            continue
        count = max(1, min(100, AUTO_STAKE_CENTS // e.price_cents))
        intent = OrderIntent(e.ticker, e.side, "buy", count, e.price_cents)
        try:
            positions = client.get_positions(ticker=e.ticker).get("market_positions", [])
            held = sum(abs(float(p.get("position_fp") or p.get("position") or 0))
                       for p in positions)
            if held:
                continue  # never add to an existing position automatically
            risk.check(intent, int(held))
            r = client.create_order(ticker=e.ticker, side=e.side, action="buy",
                                    count=count, order_type="limit",
                                    price_cents=e.price_cents)
            risk.record_spend(intent.cost_cents)
            record_bet(ticker=e.ticker, side=e.side, count=count,
                       price_cents=e.price_cents, order_id=r.get("order_id", ""),
                       env=config.env, thesis=f"[auto] {e.thesis}",
                       fair_cents=e.fair_cents, conviction="auto")
            _auto_placed_today["n"] += 1
            placed.append(f"{e.side.upper()} {count}x{e.ticker}@{e.price_cents}c")
        except RiskViolation as v:
            print(f"[auto] blocked: {v}", flush=True)
        except Exception as ex:
            print(f"[auto] failed {e.ticker}: {ex}", flush=True)
    return placed


def job_scan(label: str) -> None:
    edges = scan_edges(min_edge_cents=8)
    top = edges[:5]
    lines = [f"{e.category[:1]}|{e.ticker.split('-', 1)[1]} {e.side} @{e.price_cents}c "
             f"net{e.net_edge_cents:.0f}c" for e in top]
    placed = _auto_trade(edges) if AUTO_TRADE else []
    msg = f"{len(edges)} edge(s)."
    if lines:
        msg += " Top: " + "; ".join(lines[:3])
    msg += f" | auto-placed: {placed if placed else 'none' if AUTO_TRADE else 'off'}"
    notify(f"Kalshi {label} scan", msg[:900])


def job_settle() -> None:
    changed = update_settlements()
    s = summarize()
    wl = f"{s['won']}W-{s['settled'] - s['won']}L" if s["settled"] else "0 settled"
    msg = (f"{len(changed)} newly settled. Record {wl}, P&L ${s['pnl_cents'] / 100:+.2f}. "
           f"Open: {s['open']}.")
    if s["awaiting_postmortem"]:
        msg += f" POST-MORTEM NEEDED: {', '.join(s['awaiting_postmortem'][:4])}"
    notify("Kalshi settlement", msg[:900],
           priority="high" if s["awaiting_postmortem"] else "default")


def job_profit() -> None:
    c = KalshiClient()
    bal = c.get_balance()
    equity = float(bal.get("balance_dollars") or 0) + (bal.get("portfolio_value") or 0) / 100
    profit = equity - PROFIT_BASELINE
    print(f"[profit] equity=${equity:.2f} profit=${profit:+.2f}", flush=True)
    if profit >= PROFIT_TARGET:
        notify("Kalshi PROFIT TARGET",
               f"Equity ${equity:.2f} = ${profit:+.2f} vs baseline. Target +${PROFIT_TARGET:.0f} reached!",
               priority="urgent")


SCHEDULE = [  # (HH, MM, weekday-or-None, fn, label)
    (8, 11, None, lambda: job_scan("morning"), "morning-scan"),
    (14, 7, None, lambda: job_scan("afternoon"), "afternoon-scan"),
    (20, 19, None, job_settle, "settle"),
    (9, 4, 0, job_profit, "profit-check"),  # Mondays
]


def main() -> None:
    mode = "AUTO-TRADE ON" if AUTO_TRADE else "notify-only"
    notify("Kalshi agent up", f"Scheduler started ({mode}, env={Config().env}).")
    fired: set[str] = set()
    while True:
        now = dt.datetime.now(ET)
        for hh, mm, wd, fn, label in SCHEDULE:
            key = f"{now.date()}-{label}"
            if (now.hour, now.minute) == (hh, mm) and key not in fired \
                    and (wd is None or now.weekday() == wd):
                fired.add(key)
                print(f"[run] {label} @ {now:%H:%M %Z}", flush=True)
                try:
                    fn()
                except Exception:
                    traceback.print_exc()
                    notify("Kalshi job error", f"{label}: see logs", priority="high")
        if len(fired) > 500:
            fired = {k for k in fired if str(now.date()) in k}
        time.sleep(30)


if __name__ == "__main__":
    main()
