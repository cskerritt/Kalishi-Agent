"""Claude-powered market analysis.

Given a Kalshi market's metadata and current prices, asks Claude to estimate a
fair probability for YES and returns a structured recommendation. Requires
ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import anthropic

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "fair_yes_probability": {
            "type": "number",
            "description": "Estimated probability (0-1) that the market resolves YES",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "How confident the estimate is given available information",
        },
        "reasoning": {"type": "string", "description": "Brief reasoning for the estimate"},
        "recommendation": {
            "type": "string",
            "enum": ["buy_yes", "buy_no", "no_trade"],
            "description": "Suggested action given the estimate vs the current market price",
        },
    },
    "required": ["fair_yes_probability", "confidence", "reasoning", "recommendation"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a careful prediction-market analyst evaluating Kalshi event contracts. "
    "Estimate the probability the market resolves YES based only on the market's rules, "
    "title, and general knowledge. Be honest about uncertainty: if you lack current "
    "information the market depends on (live scores, today's weather, breaking news), "
    "say so, use 'low' confidence, and recommend no_trade. Only recommend a trade when "
    "your estimate differs meaningfully from the market price AND your confidence "
    "supports it. Prices are in cents; a YES price of 45 implies a 45% market-implied "
    "probability."
)


@dataclass
class Analysis:
    fair_yes_probability: float
    confidence: str
    reasoning: str
    recommendation: str

    @property
    def fair_yes_cents(self) -> int:
        return round(self.fair_yes_probability * 100)


class ClaudeAnalyst:
    def __init__(self, model: str = "claude-opus-4-8"):
        self._client = anthropic.Anthropic()
        self._model = model

    def analyze(self, market: dict[str, Any]) -> Analysis:
        summary = {
            "ticker": market.get("ticker"),
            "title": market.get("title"),
            "subtitle": market.get("subtitle"),
            "rules_primary": market.get("rules_primary"),
            "yes_bid": market.get("yes_bid"),
            "yes_ask": market.get("yes_ask"),
            "no_bid": market.get("no_bid"),
            "no_ask": market.get("no_ask"),
            "last_price": market.get("last_price"),
            "volume": market.get("volume"),
            "open_interest": market.get("open_interest"),
            "close_time": market.get("close_time"),
            "expiration_time": market.get("expiration_time"),
        }
        response = self._client.messages.create(
            model=self._model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyze this Kalshi market and estimate the fair YES probability:\n\n"
                        + json.dumps(summary, indent=2, default=str)
                    ),
                }
            ],
        )
        if response.stop_reason == "refusal":
            return Analysis(0.5, "low", "Model declined to analyze this market.", "no_trade")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return Analysis(
            fair_yes_probability=data["fair_yes_probability"],
            confidence=data["confidence"],
            reasoning=data["reasoning"],
            recommendation=data["recommendation"],
        )
