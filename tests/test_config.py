"""Tests for env-scoped credential selection in Config."""

import pytest

from kalshi_agent.config import Config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "KALSHI_ENV",
        "KALSHI_API_KEY_ID",
        "KALSHI_PRIVATE_KEY_PATH",
        "KALSHI_DEMO_API_KEY_ID",
        "KALSHI_DEMO_PRIVATE_KEY_PATH",
        "KALSHI_PROD_API_KEY_ID",
        "KALSHI_PROD_PRIVATE_KEY_PATH",
    ):
        monkeypatch.delenv(var, raising=False)


def test_generic_credentials_used_when_no_scoped_vars(monkeypatch):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "generic-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/generic.pem")
    cfg = Config()
    assert cfg.api_key_id == "generic-id"
    assert cfg.private_key_path == "/generic.pem"


def test_env_scoped_credentials_override_generic(monkeypatch):
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "generic-id")
    monkeypatch.setenv("KALSHI_DEMO_API_KEY_ID", "demo-id")
    monkeypatch.setenv("KALSHI_DEMO_PRIVATE_KEY_PATH", "/demo.pem")
    monkeypatch.setenv("KALSHI_PROD_API_KEY_ID", "prod-id")
    cfg = Config()
    assert cfg.api_key_id == "demo-id"
    assert cfg.private_key_path == "/demo.pem"


def test_prod_scoped_credentials_selected_by_env(monkeypatch):
    monkeypatch.setenv("KALSHI_ENV", "prod")
    monkeypatch.setenv("KALSHI_DEMO_API_KEY_ID", "demo-id")
    monkeypatch.setenv("KALSHI_PROD_API_KEY_ID", "prod-id")
    monkeypatch.setenv("KALSHI_PROD_PRIVATE_KEY_PATH", "/prod.pem")
    cfg = Config()
    assert cfg.api_key_id == "prod-id"
    assert cfg.private_key_path == "/prod.pem"


def test_scoped_vars_ignored_for_other_env(monkeypatch):
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_PROD_API_KEY_ID", "prod-id")
    cfg = Config()
    assert cfg.api_key_id == ""
