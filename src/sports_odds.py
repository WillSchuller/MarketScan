"""SportsGameOdds event retrieval."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from src.config import Settings
from src.models import Event

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sportsgameodds.com/v2"


def get_todays_upcoming_events(
    settings: Settings,
    start_utc: datetime,
    end_utc: datetime,
    client: httpx.Client,
    league_ids: str | None = None,
    now: datetime | None = None,
) -> Iterator[Event]:
    """Yield today's not-yet-started events that currently have odds available."""
    current_time = now or datetime.now(timezone.utc)
    fetched = 0
    eligible = 0

    for raw_event in _fetch_events(settings, start_utc, end_utc, client, league_ids):
        fetched += 1

        event = _parse_event(raw_event)
        if event is None:
            continue

        if not (start_utc <= event.start_time_utc < end_utc):
            continue

        # Provider status can lag reality, so re-check the start time locally
        # even though the request already asked for started=false.
        if event.start_time_utc <= current_time:
            continue

        eligible += 1
        yield event

    logger.info("Fetched %d events, %d eligible for today", fetched, eligible)


def _fetch_events(
    settings: Settings,
    start_utc: datetime,
    end_utc: datetime,
    client: httpx.Client,
    league_ids: str | None,
) -> Iterator[dict]:
    params: dict[str, str] = {
        "oddsAvailable": "true",
        "started": "false",
        "startsAfter": start_utc.isoformat(),
        "startsBefore": end_utc.isoformat(),
        "limit": "50",
    }
    if league_ids:
        params["leagueID"] = league_ids

    cursor: str | None = None
    while True:
        request_params = dict(params)
        if cursor:
            request_params["cursor"] = cursor

        response = client.get(
            f"{BASE_URL}/events",
            headers={"x-api-key": settings.sports_game_odds_api_key},
            params=request_params,
        )
        response.raise_for_status()
        payload = response.json()

        if not payload.get("success", True):
            raise RuntimeError(f"SportsGameOdds request failed: {payload.get('error')}")

        yield from payload.get("data", [])

        cursor = payload.get("nextCursor")
        if not cursor:
            break


def _parse_event(raw_event: dict) -> Event | None:
    try:
        status = raw_event["status"]
        if status.get("started"):
            return None

        teams = raw_event["teams"]
        return Event(
            event_id=raw_event["eventID"],
            league=raw_event["leagueID"],
            home_team=teams["home"]["names"]["long"],
            away_team=teams["away"]["names"]["long"],
            start_time_utc=datetime.fromisoformat(
                status["startsAt"].replace("Z", "+00:00")
            ),
        )
    except (KeyError, TypeError):
        logger.warning(
            "Skipping event with unexpected shape: %s", raw_event.get("eventID")
        )
        return None
