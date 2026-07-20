"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

BASE_URLS = {
    "prod": "https://api.elections.kalshi.com",
    "demo": "https://demo-api.kalshi.co",
}
API_PREFIX = "/trade-api/v2"


@dataclass
class Config:
    api_key_id: str = field(default_factory=lambda: os.environ.get("KALSHI_API_KEY_ID", ""))
    private_key_path: str = field(
        default_factory=lambda: os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    )
    env: str = field(default_factory=lambda: os.environ.get("KALSHI_ENV", "demo"))
    max_order_cost_cents: int = field(
        default_factory=lambda: int(os.environ.get("MAX_ORDER_COST_CENTS", "2500"))
    )
    max_position_contracts: int = field(
        default_factory=lambda: int(os.environ.get("MAX_POSITION_CONTRACTS", "100"))
    )
    max_daily_spend_cents: int = field(
        default_factory=lambda: int(os.environ.get("MAX_DAILY_SPEND_CENTS", "10000"))
    )
    min_edge_cents: int = field(default_factory=lambda: int(os.environ.get("MIN_EDGE_CENTS", "10")))

    def __post_init__(self) -> None:
        # Env-scoped credentials (KALSHI_DEMO_API_KEY_ID / KALSHI_PROD_API_KEY_ID,
        # same for *_PRIVATE_KEY_PATH) override the generic ones, so demo and prod
        # keys can coexist in .env and KALSHI_ENV picks between them.
        prefix = f"KALSHI_{self.env.upper()}_"
        self.api_key_id = os.environ.get(prefix + "API_KEY_ID", self.api_key_id)
        self.private_key_path = os.environ.get(
            prefix + "PRIVATE_KEY_PATH", self.private_key_path
        )

    @property
    def base_url(self) -> str:
        try:
            return BASE_URLS[self.env]
        except KeyError:
            raise ValueError(f"KALSHI_ENV must be one of {sorted(BASE_URLS)}, got {self.env!r}")

    def validate_credentials(self) -> None:
        if not self.api_key_id:
            raise ValueError("KALSHI_API_KEY_ID is not set (see .env.example)")
        if not self.private_key_path:
            raise ValueError(
                "KALSHI_PRIVATE_KEY_PATH is not set. Kalshi API access requires the RSA "
                "private key downloaded when the API key was created (see .env.example)."
            )
        if not os.path.exists(self.private_key_path):
            raise ValueError(f"Private key file not found: {self.private_key_path}")
