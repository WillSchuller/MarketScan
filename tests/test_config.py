import pytest

from src.config import load_settings


def test_load_settings_reads_required_values(monkeypatch):
    monkeypatch.setenv("SPORTS_GAME_ODDS_API_KEY", "fake-key")
    monkeypatch.setenv("APP_TIMEZONE", "America/New_York")
    monkeypatch.setenv("KALSHI_ENVIRONMENT", "demo")

    settings = load_settings()

    assert settings.sports_game_odds_api_key == "fake-key"
    assert settings.app_timezone == "America/New_York"
    assert settings.kalshi_environment == "demo"


def test_load_settings_uses_defaults(monkeypatch):
    monkeypatch.setenv("SPORTS_GAME_ODDS_API_KEY", "fake-key")
    monkeypatch.delenv("APP_TIMEZONE", raising=False)
    monkeypatch.delenv("KALSHI_ENVIRONMENT", raising=False)

    settings = load_settings()

    assert settings.app_timezone == "America/Chicago"
    assert settings.kalshi_environment == "production"


def test_load_settings_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("SPORTS_GAME_ODDS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SPORTS_GAME_ODDS_API_KEY is required"):
        load_settings()
