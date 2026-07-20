import pytest

from kalshi_agent.config import Config
from kalshi_agent.risk import OrderIntent, RiskManager, RiskViolation


@pytest.fixture
def risk(tmp_path):
    config = Config()
    config.max_order_cost_cents = 1000
    config.max_position_contracts = 50
    config.max_daily_spend_cents = 2000
    return RiskManager(config, spend_file=str(tmp_path / "spend.json"))


def test_allows_small_buy(risk):
    risk.check(OrderIntent("T", "yes", "buy", 10, 50))  # 500c


def test_blocks_oversized_order(risk):
    with pytest.raises(RiskViolation, match="MAX_ORDER_COST_CENTS"):
        risk.check(OrderIntent("T", "yes", "buy", 30, 50))  # 1500c


def test_blocks_position_limit(risk):
    with pytest.raises(RiskViolation, match="MAX_POSITION_CONTRACTS"):
        risk.check(OrderIntent("T", "yes", "buy", 10, 50), current_position_count=45)


def test_blocks_daily_spend(risk):
    risk.record_spend(1600)
    with pytest.raises(RiskViolation, match="MAX_DAILY_SPEND_CENTS"):
        risk.check(OrderIntent("T", "yes", "buy", 10, 50))  # would reach 2100c


def test_sells_always_allowed(risk):
    risk.record_spend(2000)
    risk.check(OrderIntent("T", "yes", "sell", 99, 99))
