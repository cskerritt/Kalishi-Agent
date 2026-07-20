"""Tests for the weather fair-value model."""

from kalshi_agent.weather import _fair_yes, _market_date


def test_market_date_parsing():
    assert _market_date("KXHIGHLAX-26JUL20-T80") == "2026-07-20"
    assert _market_date("KXHIGHNY-26DEC01-B42.5") == "2026-12-01"
    assert _market_date("NODATE") is None


def test_greater_strike_far_below_forecast_is_near_certain():
    m = {"strike_type": "greater", "floor_strike": 70}
    assert _fair_yes(m, 85.0, 2.8) > 0.99


def test_greater_strike_far_above_forecast_is_near_zero():
    m = {"strike_type": "greater", "floor_strike": 80}
    # forecast 75, needs 81+: > 2 sigma away
    assert _fair_yes(m, 75.0, 2.8) < 0.05


def test_at_the_money_is_near_half():
    m = {"strike_type": "greater", "floor_strike": 75}
    # YES needs >= 75.5 with forecast 75.5
    assert abs(_fair_yes(m, 75.5, 2.8) - 0.5) < 0.01


def test_between_band_centered_on_forecast():
    m = {"strike_type": "between", "floor_strike": 74, "cap_strike": 76}
    p = _fair_yes(m, 75.0, 2.8)
    # 3-degree band around the forecast should be the modal bucket
    assert 0.3 < p < 0.5


def test_between_bands_sum_to_one_with_tails():
    sigma, fc = 2.8, 75.0
    tail_low = _fair_yes({"strike_type": "less", "cap_strike": 70}, fc, sigma)
    bands = sum(
        _fair_yes({"strike_type": "between", "floor_strike": f, "cap_strike": f + 1}, fc, sigma)
        for f in range(70, 80, 2)
    )
    tail_high = _fair_yes({"strike_type": "greater", "floor_strike": 79}, fc, sigma)
    assert abs(tail_low + bands + tail_high - 1.0) < 0.02


def test_unknown_strike_type_returns_none():
    assert _fair_yes({"strike_type": "custom"}, 75.0, 2.8) is None
