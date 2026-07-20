"""Weather-market edge scanner.

Compares Kalshi daily temperature ladders against NWS point forecasts
(api.weather.gov, free, no key). Fair probabilities come from a normal
forecast-error model: next-day NWS high-temperature forecasts have a mean
absolute error around 2°F (sigma ~= 2.8°F); same-day forecasts are tighter.

Only a screen: flags markets whose price deviates from model fair value by at
least `min_edge_cents`. Resolution stations matter — each series maps to the
exact station named in the market rules.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Any

import requests

from .client import KalshiClient
from .config import Config

# Kalshi temperature series -> (lat, lon) of the resolution station.
# Verify against rules_primary when adding a series: airport vs downtown
# stations differ by several degrees.
STATIONS = {
    "KXHIGHNY": (40.7789, -73.9692),     # Central Park, NYC
    "KXHIGHCHI": (41.7841, -87.7551),    # Chicago Midway
    "KXHIGHLAX": (33.9425, -118.4081),   # Los Angeles Intl
    "KXHIGHMIA": (25.7906, -80.3164),    # Miami Intl
    "KXHIGHAUS": (30.1945, -97.6699),    # Austin-Bergstrom
    "KXHIGHDEN": (39.8467, -104.6562),   # Denver Intl
    "KXHIGHPHIL": (39.8683, -75.2311),   # Philadelphia Intl
    "KXHIGHTPHX": (33.4278, -112.0037),  # Phoenix Sky Harbor
    "KXHIGHTSEA": (47.4444, -122.3139),  # Seattle-Tacoma
    "KXHIGHTSFO": (37.6197, -122.3647),  # San Francisco Intl
    "KXLOWTSFO": (37.6197, -122.3647),
}

# Forecast-error sigma (deg F) by forecast horizon in days.
SIGMA_BY_HORIZON = {0: 2.0, 1: 2.8, 2: 3.5}
DEFAULT_SIGMA = 4.5

_UA = {"User-Agent": "kalshi-agent-weather (github.com/cskerritt/Kalishi-Agent)"}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def nws_forecast(lat: float, lon: float) -> dict[str, list[dict[str, Any]]]:
    """Forecast periods for a point, keyed by kind.

    highs: [{date, temp_f, short}] from daytime periods.
    lows:  [{date, temp_f, short}] from overnight periods, attributed to the
           morning they end on (a market's daily low usually occurs pre-dawn).
    """
    meta = requests.get(
        f"https://api.weather.gov/points/{lat},{lon}", headers=_UA, timeout=20
    ).json()
    fc = requests.get(meta["properties"]["forecast"], headers=_UA, timeout=20).json()
    out: dict[str, list[dict[str, Any]]] = {"highs": [], "lows": []}
    for p in fc["properties"]["periods"]:
        entry = {"temp_f": p["temperature"], "short": p.get("shortForecast", "")}
        if p.get("isDaytime"):
            out["highs"].append({"date": p["startTime"][:10], **entry})
        else:
            out["lows"].append({"date": p["endTime"][:10], **entry})
    return out


def _market_date(ticker: str) -> str | None:
    """KXHIGHLAX-26JUL20-T80 -> 2026-07-20"""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})-", ticker)
    if not m:
        return None
    months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05",
              "JUN": "06", "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10",
              "NOV": "11", "DEC": "12"}
    yy, mon, dd = m.groups()
    return f"20{yy}-{months[mon]}-{dd}"


def _fair_yes(market: dict[str, Any], forecast_high: float, sigma: float) -> float | None:
    """P(market resolves YES) given forecast high and error sigma.

    Kalshi strike conventions: 'greater' = above floor_strike (so YES needs
    actual >= floor + 1 for integer strikes); 'between' = floor <= actual <= cap.
    Uses a continuity-corrected normal on whole degrees.
    """
    st = market.get("strike_type")
    floor = market.get("floor_strike")
    cap = market.get("cap_strike")
    if st == "greater" and floor is not None:
        return 1 - _norm_cdf((floor + 0.5 - forecast_high) / sigma)
    if st == "less" and cap is not None:
        return _norm_cdf((cap - 0.5 - forecast_high) / sigma)
    if st == "between" and floor is not None and cap is not None:
        hi = _norm_cdf((cap + 0.5 - forecast_high) / sigma)
        lo = _norm_cdf((floor - 0.5 - forecast_high) / sigma)
        return hi - lo
    return None


@dataclass
class WeatherEdge:
    ticker: str
    series: str
    date: str
    forecast_high: float
    short: str
    strike: str
    yes_bid: int | None
    yes_ask: int | None
    fair_cents: int
    side: str          # "yes" | "no"
    price_cents: int   # ask you'd pay
    edge_cents: int


def scan_weather(min_edge_cents: int = 8, horizon_days: int = 2) -> list[WeatherEdge]:
    client = KalshiClient(Config(env="prod"))
    forecasts: dict[str, dict[str, dict[str, Any]]] = {}
    edges: list[WeatherEdge] = []

    for series, (lat, lon) in STATIONS.items():
        markets = client.get_markets(
            series_ticker=series, status="open", limit=100
        ).get("markets", [])
        if not markets:
            continue
        kind = "lows" if series.startswith("KXLOW") else "highs"
        key = f"{lat},{lon}"
        if key not in forecasts:
            try:
                fc_all = nws_forecast(lat, lon)
                forecasts[key] = {
                    k: {f["date"]: f for f in periods} for k, periods in fc_all.items()
                }
            except Exception:
                continue

        for m in markets:
            date = _market_date(m["ticker"])
            fc = forecasts[key][kind].get(date) if date else None
            if not fc:
                continue
            horizon = (dt.date.fromisoformat(date) - dt.date.today()).days
            if horizon > horizon_days:
                continue
            sigma = SIGMA_BY_HORIZON.get(max(horizon, 0), DEFAULT_SIGMA)
            fair = _fair_yes(m, fc["temp_f"], sigma)
            if fair is None:
                continue
            fair_c = round(fair * 100)
            yes_ask, no_ask = m.get("yes_ask"), m.get("no_ask")
            best = None
            if yes_ask and 1 <= yes_ask <= 99 and fair_c - yes_ask >= min_edge_cents:
                best = ("yes", yes_ask, fair_c - yes_ask)
            if no_ask and 1 <= no_ask <= 99 and (100 - fair_c) - no_ask >= min_edge_cents:
                cand = ("no", no_ask, (100 - fair_c) - no_ask)
                if best is None or cand[2] > best[2]:
                    best = cand
            if best:
                strike = m.get("yes_sub_title") or m.get("subtitle") or ""
                edges.append(WeatherEdge(
                    ticker=m["ticker"], series=series, date=date,
                    forecast_high=fc["temp_f"], short=fc["short"], strike=strike,
                    yes_bid=m.get("yes_bid"), yes_ask=yes_ask, fair_cents=fair_c,
                    side=best[0], price_cents=best[1], edge_cents=best[2],
                ))

    edges.sort(key=lambda e: -e.edge_cents)
    return edges
