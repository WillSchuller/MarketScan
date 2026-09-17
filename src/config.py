"""Central application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Kalshi requires different base URLs per environment; keep the mapping here
# so no other module needs to know these hosts.
KALSHI_BASE_URLS = {
    "production": "https://api.elections.kalshi.com/trade-api/v2",
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
}


@dataclass(frozen=True)
class Settings:
    sports_game_odds_api_key: str
    app_timezone: str
    kalshi_environment: str
    kalshi_base_url: str
    league_ids: str


def load_settings() -> Settings:
    """Load required configuration, failing clearly if secrets are missing."""
    api_key = os.getenv("SPORTS_GAME_ODDS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SPORTS_GAME_ODDS_API_KEY is required. "
            "Create a local .env file using .env.example."
        )

    kalshi_environment = os.getenv("KALSHI_ENVIRONMENT", "production")
    kalshi_base_url = KALSHI_BASE_URLS.get(kalshi_environment)
    if kalshi_base_url is None:
        raise RuntimeError(
            f"KALSHI_ENVIRONMENT must be one of {sorted(KALSHI_BASE_URLS)}, "
            f"got {kalshi_environment!r}."
        )

    return Settings(
        sports_game_odds_api_key=api_key,
        app_timezone=os.getenv("APP_TIMEZONE", "America/Chicago"),
        kalshi_environment=kalshi_environment,
        kalshi_base_url=kalshi_base_url,
        # This subscription tier requires an explicit leagueID or eventID on
        # every /events request; there is no "all leagues" option available.
        league_ids=os.getenv("LEAGUE_IDS", "NFL,MLB"),
    )
