import pytest

from src.config import load_settings


def test_load_settings_reads_required_values(monkeypatch):
    monkeypatch.setenv("SPORTS_GAME_ODDS_API_KEY", "fake-key")
    monkeypatch.setenv("APP_TIMEZONE", "America/New_York")
    monkeypatch.setenv("KALSHI_ENVIRONMENT", "demo")
    monkeypatch.setenv("LEAGUE_IDS", "NFL,NBA")

    settings = load_settings()

    assert settings.sports_game_odds_api_key == "fake-key"
    assert settings.app_timezone == "America/New_York"
    assert settings.kalshi_environment == "demo"
    assert settings.kalshi_base_url == "https://demo-api.kalshi.co/trade-api/v2"
    assert settings.league_ids == "NFL,NBA"


def test_load_settings_uses_defaults(monkeypatch):
    monkeypatch.setenv("SPORTS_GAME_ODDS_API_KEY", "fake-key")
    monkeypatch.delenv("APP_TIMEZONE", raising=False)
    monkeypatch.delenv("KALSHI_ENVIRONMENT", raising=False)
    monkeypatch.delenv("LEAGUE_IDS", raising=False)

    settings = load_settings()

    assert settings.app_timezone == "America/Chicago"
    assert settings.kalshi_environment == "production"
    assert settings.kalshi_base_url == "https://api.elections.kalshi.com/trade-api/v2"
    assert settings.league_ids == "NFL,MLB,NHL"


def test_load_settings_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("SPORTS_GAME_ODDS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SPORTS_GAME_ODDS_API_KEY is required"):
        load_settings()


def test_load_settings_invalid_kalshi_environment_raises(monkeypatch):
    monkeypatch.setenv("SPORTS_GAME_ODDS_API_KEY", "fake-key")
    monkeypatch.setenv("KALSHI_ENVIRONMENT", "sandbox")

    with pytest.raises(RuntimeError, match="KALSHI_ENVIRONMENT must be one of"):
        load_settings()
