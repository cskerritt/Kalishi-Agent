"""Automated analyze-and-trade loop.

For each open market in a series (or an explicit list of tickers), asks the
Claude analyst for a fair-probability estimate and places a limit order when the
edge over the current ask exceeds the configured threshold. Every order passes
through the RiskManager, and nothing is sent unless live=True.
"""

from __future__ import annotations

import logging
import time

from .analyst import Analysis, ClaudeAnalyst
from .client import KalshiClient
from .config import Config
from .risk import OrderIntent, RiskManager, RiskViolation

log = logging.getLogger("kalshi_agent")


class TradingAgent:
    def __init__(self, config: Config | None = None, live: bool = False,
                 default_count: int = 10):
        self.config = config or Config()
        self.client = KalshiClient(self.config)
        self.risk = RiskManager(self.config)
        self.analyst = ClaudeAnalyst()
        self.live = live
        self.default_count = default_count

    # ----------------------------------------------------------------- helpers

    def _position_count(self, ticker: str) -> int:
        positions = self.client.get_positions(ticker=ticker).get("market_positions", [])
        return sum(abs(p.get("position", 0)) for p in positions)

    def _decide(self, market: dict, analysis: Analysis) -> OrderIntent | None:
        """Turn an analysis into an order intent, or None."""
        if analysis.recommendation == "no_trade" or analysis.confidence == "low":
            return None

        ticker = market["ticker"]
        yes_ask = market.get("yes_ask") or 0
        no_ask = market.get("no_ask") or 0

        if analysis.recommendation == "buy_yes" and 0 < yes_ask < 100:
            edge = analysis.fair_yes_cents - yes_ask
            if edge >= self.config.min_edge_cents:
                return OrderIntent(ticker, "yes", "buy", self.default_count, yes_ask)
        elif analysis.recommendation == "buy_no" and 0 < no_ask < 100:
            edge = (100 - analysis.fair_yes_cents) - no_ask
            if edge >= self.config.min_edge_cents:
                return OrderIntent(ticker, "no", "buy", self.default_count, no_ask)
        return None

    def _execute(self, intent: OrderIntent) -> None:
        try:
            self.risk.check(intent, self._position_count(intent.ticker))
        except RiskViolation as e:
            log.warning("Risk check blocked %s: %s", intent.ticker, e)
            return

        if not self.live:
            log.info(
                "[DRY RUN] Would place: %s %s x%d %s @ %dc (cost %dc)",
                intent.action, intent.side, intent.count, intent.ticker,
                intent.price_cents, intent.cost_cents,
            )
            return

        result = self.client.create_order(
            ticker=intent.ticker,
            side=intent.side,
            action=intent.action,
            count=intent.count,
            order_type="limit",
            price_cents=intent.price_cents,
        )
        self.risk.record_spend(intent.cost_cents)
        order = result.get("order", result)
        log.info("Placed order %s: %s", order.get("order_id", "?"), order.get("status", "?"))

    # -------------------------------------------------------------------- run

    def run_once(self, series_ticker: str | None = None,
                 tickers: list[str] | None = None) -> None:
        if tickers:
            markets = [self.client.get_market(t).get("market", {}) for t in tickers]
        else:
            markets = self.client.get_markets(
                status="open", series_ticker=series_ticker, limit=25
            ).get("markets", [])

        log.info("Evaluating %d market(s)", len(markets))
        for market in markets:
            if not market:
                continue
            ticker = market.get("ticker", "?")
            try:
                analysis = self.analyst.analyze(market)
            except Exception as e:
                log.error("Analysis failed for %s: %s", ticker, e)
                continue
            log.info(
                "%s: fair=%dc market_yes_ask=%sc conf=%s rec=%s — %s",
                ticker, analysis.fair_yes_cents, market.get("yes_ask"),
                analysis.confidence, analysis.recommendation,
                analysis.reasoning[:140],
            )
            intent = self._decide(market, analysis)
            if intent:
                self._execute(intent)

    def run_forever(self, series_ticker: str | None = None,
                    tickers: list[str] | None = None, interval_s: int = 300) -> None:
        mode = "LIVE" if self.live else "DRY RUN"
        log.info("Starting trading loop (%s, env=%s, every %ds)", mode, self.config.env, interval_s)
        while True:
            try:
                self.run_once(series_ticker=series_ticker, tickers=tickers)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.error("Cycle failed: %s", e)
            time.sleep(interval_s)
