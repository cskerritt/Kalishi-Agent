"""Order-level and daily risk limits."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .config import Config

_DATA_DIR = os.environ.get(
    "KALSHI_DATA_DIR", os.path.join(os.path.dirname(__file__), "..")
)
_SPEND_FILE = os.path.join(_DATA_DIR, ".daily_spend.json")


@dataclass
class OrderIntent:
    ticker: str
    side: str          # "yes" | "no"
    action: str        # "buy" | "sell"
    count: int
    price_cents: int   # limit price (or estimated fill price for market orders)

    @property
    def cost_cents(self) -> int:
        return self.count * self.price_cents


class RiskViolation(Exception):
    pass


class RiskManager:
    """Enforces per-order cost, per-market position, and daily spend limits.

    Daily spend is tracked in a small local JSON file so it survives restarts.
    """

    def __init__(self, config: Config, spend_file: str = _SPEND_FILE):
        self.config = config
        self.spend_file = spend_file

    # ------------------------------------------------------------ daily spend

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _load_spend(self) -> dict:
        """Per-env daily spend: {"date": ..., "spent_cents": {"demo": N, "prod": N}}.
        Demo practice orders must not consume the real-money daily budget."""
        try:
            with open(self.spend_file) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if data.get("date") != self._today() or not isinstance(
            data.get("spent_cents"), dict
        ):
            data = {"date": self._today(), "spent_cents": {}}
        return data

    def daily_spent_cents(self) -> int:
        return self._load_spend()["spent_cents"].get(self.config.env, 0)

    def record_spend(self, cents: int) -> None:
        data = self._load_spend()
        env = self.config.env
        data["spent_cents"][env] = data["spent_cents"].get(env, 0) + cents
        with open(self.spend_file, "w") as f:
            json.dump(data, f)

    # ----------------------------------------------------------------- checks

    def check(self, intent: OrderIntent, current_position_count: int = 0) -> None:
        """Raise RiskViolation if the order breaks any limit. Sells are exempt
        from cost/spend limits (they reduce exposure)."""
        if intent.action == "sell":
            return

        if intent.cost_cents > self.config.max_order_cost_cents:
            raise RiskViolation(
                f"Order cost {intent.cost_cents}c exceeds MAX_ORDER_COST_CENTS "
                f"({self.config.max_order_cost_cents}c)"
            )
        if current_position_count + intent.count > self.config.max_position_contracts:
            raise RiskViolation(
                f"Position would reach {current_position_count + intent.count} contracts, "
                f"exceeding MAX_POSITION_CONTRACTS ({self.config.max_position_contracts})"
            )
        projected = self.daily_spent_cents() + intent.cost_cents
        if projected > self.config.max_daily_spend_cents:
            raise RiskViolation(
                f"Daily spend would reach {projected}c, exceeding MAX_DAILY_SPEND_CENTS "
                f"({self.config.max_daily_spend_cents}c)"
            )
