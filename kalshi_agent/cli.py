"""Command-line interface for the Kalshi trading agent."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .client import KalshiAPIError, KalshiClient
from .config import Config
from .risk import OrderIntent, RiskManager, RiskViolation


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def _place(args, action: str) -> None:
    config = Config()
    client = KalshiClient(config)
    risk = RiskManager(config)
    intent = OrderIntent(args.ticker, args.side, action, args.count, args.price)

    positions = client.get_positions(ticker=args.ticker).get("market_positions", [])
    held = sum(abs(p.get("position", 0)) for p in positions)
    try:
        risk.check(intent, held)
    except RiskViolation as e:
        sys.exit(f"BLOCKED by risk limits: {e}")

    print(
        f"{action.upper()} {args.count} x {args.side.upper()} {args.ticker} "
        f"@ {args.price}c  (max cost ${intent.cost_cents / 100:.2f}, env={config.env})"
    )
    if not args.live:
        print("[DRY RUN] Order NOT sent. Re-run with --live to place it.")
        return
    result = client.create_order(
        ticker=args.ticker, side=args.side, action=action,
        count=args.count, order_type="limit", price_cents=args.price,
    )
    if action == "buy":
        risk.record_spend(intent.cost_cents)
    _print(result)


def _add_order_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("ticker", help="Market ticker, e.g. KXHIGHNY-25JUL21-B85")
    p.add_argument("--side", choices=["yes", "no"], required=True)
    p.add_argument("--count", type=int, required=True, help="Number of contracts")
    p.add_argument("--price", type=int, required=True, help="Limit price in cents (1-99)")
    p.add_argument("--live", action="store_true", help="Actually send the order")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="kalshi_agent", description="Kalshi trading agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Exchange status")
    sub.add_parser("balance", help="Account balance")
    sub.add_parser("positions", help="Open positions")

    p = sub.add_parser("orders", help="List orders")
    p.add_argument("--status", default=None, help="e.g. resting, executed, canceled")

    p = sub.add_parser("markets", help="List markets")
    p.add_argument("--status", default="open")
    p.add_argument("--series", default=None, help="Series ticker filter")
    p.add_argument("--event", default=None, help="Event ticker filter")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("market", help="Market detail + orderbook")
    p.add_argument("ticker")

    _add_order_args(sub.add_parser("buy", help="Buy contracts (limit order)"))
    _add_order_args(sub.add_parser("sell", help="Sell contracts (limit order)"))

    p = sub.add_parser("cancel", help="Cancel a resting order")
    p.add_argument("order_id")
    p.add_argument("--live", action="store_true")

    p = sub.add_parser("analyze", help="Ask Claude to analyze a market (no order placed)")
    p.add_argument("ticker")

    p = sub.add_parser(
        "scan", help="Snapshot liquid markets closing soon (prod prices) for review"
    )
    p.add_argument("--hours", type=float, default=36, help="Only markets closing within N hours")
    p.add_argument("--limit", type=int, default=25, help="Max candidates in the snapshot")
    p.add_argument("--series", default=None, help="Series ticker filter")
    p.add_argument("--min-volume", type=int, default=500, help="Minimum traded volume")
    p.add_argument("--out", default=None, help="Snapshot file (default .scan.json)")

    p = sub.add_parser("execute", help="Place numbered picks from a picks file")
    p.add_argument("numbers", type=int, nargs="+", help="Pick numbers to place")
    p.add_argument("--picks", default=None, help="Picks file (default picks.json)")
    p.add_argument("--live", action="store_true", help="Actually send the orders")

    p = sub.add_parser("run", help="Automated analyze-and-trade loop")
    p.add_argument("--series", default=None, help="Series ticker to scan")
    p.add_argument("--tickers", default=None, help="Comma-separated market tickers")
    p.add_argument("--interval", type=int, default=300, help="Seconds between cycles")
    p.add_argument("--count", type=int, default=10, help="Contracts per order")
    p.add_argument("--once", action="store_true", help="Run one cycle and exit")
    p.add_argument("--live", action="store_true", help="Actually place orders")

    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            _print(KalshiClient().exchange_status())
        elif args.command == "balance":
            _print(KalshiClient().get_balance())
        elif args.command == "positions":
            _print(KalshiClient().get_positions())
        elif args.command == "orders":
            _print(KalshiClient().get_orders(status=args.status))
        elif args.command == "markets":
            data = KalshiClient().get_markets(
                status=args.status, series_ticker=args.series,
                event_ticker=args.event, limit=args.limit,
            )
            for m in data.get("markets", []):
                print(
                    f"{m.get('ticker'):40s} yes {m.get('yes_bid')}/{m.get('yes_ask')}c  "
                    f"vol {m.get('volume')}  {m.get('title', '')[:60]}"
                )
        elif args.command == "market":
            client = KalshiClient()
            _print({
                "market": client.get_market(args.ticker),
                "orderbook": client.get_orderbook(args.ticker),
            })
        elif args.command == "buy":
            _place(args, "buy")
        elif args.command == "sell":
            _place(args, "sell")
        elif args.command == "cancel":
            if not args.live:
                print(f"[DRY RUN] Would cancel order {args.order_id}. Re-run with --live.")
            else:
                _print(KalshiClient().cancel_order(args.order_id))
        elif args.command == "analyze":
            from .analyst import ClaudeAnalyst
            market = KalshiClient().get_market(args.ticker).get("market", {})
            analysis = ClaudeAnalyst().analyze(market)
            _print({
                "ticker": args.ticker,
                "market_yes_ask": market.get("yes_ask"),
                "fair_yes_cents": analysis.fair_yes_cents,
                "confidence": analysis.confidence,
                "recommendation": analysis.recommendation,
                "reasoning": analysis.reasoning,
            })
        elif args.command == "scan":
            from .recommend import SCAN_FILE, scan_markets
            out = args.out or SCAN_FILE
            snapshot = scan_markets(
                hours=args.hours, limit=args.limit, series=args.series,
                min_volume=args.min_volume, out=out,
            )
            for i, m in enumerate(snapshot, 1):
                print(
                    f"{i:>3}. {m['ticker']:45s} yes {m['yes_bid']}/{m['yes_ask']}c  "
                    f"vol {m['volume']:>8}  closes {m['close_time']}  "
                    f"{(m.get('title') or '')[:50]}"
                )
            print(f"\n{len(snapshot)} candidate(s) written to {out}")
        elif args.command == "execute":
            from .recommend import PICKS_FILE, execute_picks
            execute_picks(args.numbers, picks_file=args.picks or PICKS_FILE, live=args.live)
        elif args.command == "run":
            from .agent import TradingAgent
            agent = TradingAgent(live=args.live, default_count=args.count)
            tickers = args.tickers.split(",") if args.tickers else None
            if args.once:
                agent.run_once(series_ticker=args.series, tickers=tickers)
            else:
                agent.run_forever(
                    series_ticker=args.series, tickers=tickers, interval_s=args.interval
                )
    except KalshiAPIError as e:
        sys.exit(str(e))
    except ValueError as e:
        sys.exit(f"Configuration error: {e}")


if __name__ == "__main__":
    main()
