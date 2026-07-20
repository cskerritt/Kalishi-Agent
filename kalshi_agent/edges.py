"""Unified edge sweep: run every implemented fair-value model across the
exchange and rank all opportunities by net edge per day of capital lockup.

Models implemented so far (see RESEARCH.md for the roadmap):
- weather: NWS point-forecast model (weather.py)
- sports:  devigged sportsbook consensus via ESPN's public scoreboard API
           (MLB + WNBA moneylines; favorite's line in odds 'details')

Everything is fee-netted with the same feasible-edge policy.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

import requests

from .client import KalshiClient
from .config import Config
from .weather import scan_weather, taker_fee_cents

_ESPN = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUES = {
    "KXMLBGAME": ("baseball/mlb", {}),
    "KXWNBAGAME": ("basketball/wnba", {}),
}
# ESPN team abbreviation -> Kalshi ticker suffix, where they differ.
_TEAM_FIX = {"CHW": "CWS", "ARI": "AZ", "ATH": "ATH", "WSH": "WSH"}


@dataclass
class Edge:
    ticker: str
    category: str
    date: str
    side: str
    price_cents: int
    fair_cents: int
    net_edge_cents: float
    days: int
    edge_per_day: float
    thesis: str


def _ml_to_prob(ml: int) -> float:
    return (-ml) / (-ml + 100) if ml < 0 else 100 / (ml + 100)


# Score-margin sigma per league, for converting a point spread to a win prob
# when ESPN's 'details' is a spread (WNBA) rather than a moneyline (MLB).
_SPREAD_SIGMA = {"basketball/wnba": 10.5}


def _spread_to_prob(spread: float, league_path: str) -> float | None:
    import math
    sigma = _SPREAD_SIGMA.get(league_path)
    if sigma is None:
        return None
    return 0.5 * (1 + math.erf((spread / sigma) / math.sqrt(2)))


def _espn_fair_probs(league_path: str, yyyymmdd: str) -> dict[str, float]:
    """{'AWAY@HOME': devigged favorite win prob keyed by fav abbrev} ->
    returns {team_abbrev: fair win prob} per game using the favorite's line
    and a standard 4.2% two-way overround."""
    out: dict[str, float] = {}
    try:
        d = requests.get(f"{_ESPN}/{league_path}/scoreboard",
                         params={"dates": yyyymmdd}, timeout=20).json()
    except Exception:
        return out
    for ev in d.get("events", []):
        comp = ev["competitions"][0]
        teams = {c["homeAway"]: c["team"]["abbreviation"] for c in comp["competitors"]}
        odds = comp.get("odds")
        if not odds:
            continue
        details = odds[0].get("details", "")  # "TEX -175" (ML) or "MIN -10.5" (spread)
        m = re.match(r"([A-Z]+)\s+(-?\d+(?:\.\d+)?)", details or "")
        if not m:
            continue
        fav, line = m.group(1), float(m.group(2))
        if abs(line) >= 100:                      # moneyline
            fav_fair = _ml_to_prob(int(line)) / 1.042
        else:                                     # point spread
            p = _spread_to_prob(abs(line), league_path)
            if p is None:
                continue
            fav_fair = p
        dog = next((t for t in teams.values() if t != fav), None)
        out[_TEAM_FIX.get(fav, fav)] = fav_fair
        if dog:
            out[_TEAM_FIX.get(dog, dog)] = 1 - fav_fair
    return out


def _sports_edges(client: KalshiClient, min_edge_cents: int) -> list[Edge]:
    edges: list[Edge] = []
    today = dt.date.today()
    for series, (league, _) in _LEAGUES.items():
        markets = client.get_markets(
            series_ticker=series, status="open", limit=100
        ).get("markets", [])
        by_date: dict[str, list[dict[str, Any]]] = {}
        for m in markets:
            dm = re.search(r"-(\d{2}[A-Z]{3}\d{2})", m["ticker"])
            if dm:
                by_date.setdefault(dm.group(1), []).append(m)
        for datecode, ms in by_date.items():
            try:
                gdate = dt.datetime.strptime("20" + datecode, "%Y%b%d").date()
            except ValueError:
                continue
            if not (0 <= (gdate - today).days <= 2):
                continue
            fair = _espn_fair_probs(league, gdate.strftime("%Y%m%d"))
            if not fair:
                continue
            for m in ms:
                team = m["ticker"].rsplit("-", 1)[-1]
                p = fair.get(team)
                ask = m.get("yes_ask")
                if p is None or not ask or not (1 <= ask <= 99):
                    continue
                fair_c = round(p * 100)
                raw = fair_c - ask
                net = raw - taker_fee_cents(ask)
                if net >= min_edge_cents:
                    days = max((gdate - today).days, 1)
                    edges.append(Edge(
                        ticker=m["ticker"], category="sports",
                        date=gdate.isoformat(), side="yes", price_cents=ask,
                        fair_cents=fair_c, net_edge_cents=round(net, 2),
                        days=days, edge_per_day=round(net / days, 2),
                        thesis=f"{team} devig fair {fair_c}c vs ask {ask}c "
                               f"(ESPN consensus line)",
                    ))
    return edges


def scan_edges(min_edge_cents: int = 8) -> list[Edge]:
    client = KalshiClient(Config(env="prod"))
    edges: list[Edge] = []

    for w in scan_weather(min_edge_cents=min_edge_cents):
        edges.append(Edge(
            ticker=w.ticker, category="weather", date=w.date, side=w.side,
            price_cents=w.price_cents, fair_cents=(
                w.fair_cents if w.side == "yes" else 100 - w.fair_cents),
            net_edge_cents=w.net_edge_cents, days=w.days_to_resolution,
            edge_per_day=w.edge_per_day,
            thesis=f"NWS {w.forecast_high:.0f}F ({w.short[:24]}) vs strike "
                   f"'{w.strike}'",
        ))
    edges.extend(_sports_edges(client, min_edge_cents))
    edges.sort(key=lambda e: -e.edge_per_day)
    return edges
