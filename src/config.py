"""Central application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    sports_game_odds_api_key: str
    app_timezone: str
    kalshi_environment: str


def load_settings() -> Settings:
    """Load required configuration, failing clearly if secrets are missing."""
    api_key = os.getenv("SPORTS_GAME_ODDS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SPORTS_GAME_ODDS_API_KEY is required. "
            "Create a local .env file using .env.example."
        )

    return Settings(
        sports_game_odds_api_key=api_key,
        app_timezone=os.getenv("APP_TIMEZONE", "America/Chicago"),
        kalshi_environment=os.getenv("KALSHI_ENVIRONMENT", "production"),
    )
