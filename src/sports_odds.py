"""SportsGameOdds event retrieval."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from src.config import Settings
from src.models import Event, SportsbookQuote

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sportsgameodds.com/v2"

# Small bounded retry on 429s so a rate-limit blip doesn't fail the whole
# scan; see CLAUDE.md's API Rate Limits guidance (backoff, not a retry
# framework, and never a parallel retry storm).
MAX_RATE_LIMIT_RETRIES = 5


def get_todays_upcoming_events(
    settings: Settings,
    start_utc: datetime,
    end_utc: datetime,
    client: httpx.Client,
    league_ids: str | None = None,
    now: datetime | None = None,
) -> Iterator[tuple[Event, dict]]:
    """Yield (event, raw_event) for today's not-yet-started events with odds available.

    The raw event is included alongside the normalized Event so callers can
    derive sportsbook quotes (see parse_sportsbook_quotes) without a second
    SportsGameOdds request.
    """
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
        yield event, raw_event

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

        payload = _get_with_retry(
            settings,
            client,
            f"{BASE_URL}/events",
            request_params,
        )

        if not payload.get("success", True):
            raise RuntimeError(f"SportsGameOdds request failed: {payload.get('error')}")

        yield from payload.get("data", [])

        cursor = payload.get("nextCursor")
        if not cursor:
            break


def _get_with_retry(
    settings: Settings, client: httpx.Client, url: str, params: dict[str, str]
) -> dict:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        response = client.get(
            url,
            headers={"x-api-key": settings.sports_game_odds_api_key},
            params=params,
        )

        if response.status_code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
            response.raise_for_status()
            return response.json()

        wait_seconds = _retry_after_seconds(response) or (2**attempt)
        logger.warning("SportsGameOdds rate limit hit, retrying in %.1fs", wait_seconds)
        time.sleep(wait_seconds)

    raise RuntimeError("unreachable")  # pragma: no cover


def _retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except ValueError:
        return None


def parse_sportsbook_quotes(raw_event: dict) -> Iterator[SportsbookQuote]:
    """Yield normalized, currently-available per-bookmaker quotes for one raw event."""
    event_id = raw_event.get("eventID")
    if not event_id:
        return

    players = raw_event.get("players", {})

    for raw_odd in raw_event.get("odds", {}).values():
        common_fields = _quote_common_fields(raw_odd, players)
        if common_fields is None:
            continue

        for sportsbook, book_data in raw_odd.get("byBookmaker", {}).items():
            # Stale/inactive lines must not be treated as currently tradeable.
            if not book_data.get("available"):
                continue

            american_odds = _parse_int(book_data.get("odds"))
            if american_odds is None:
                continue

            yield SportsbookQuote(
                event_id=event_id,
                sportsbook=sportsbook,
                american_odds=american_odds,
                line=_parse_line(book_data),
                **common_fields,
            )


def _quote_common_fields(raw_odd: dict, players: dict) -> dict | None:
    try:
        stat = raw_odd["statID"]
        period = raw_odd["periodID"]
        side = raw_odd["sideID"]
        bet_type = raw_odd["betTypeID"]
    except KeyError:
        return None

    player_id = raw_odd.get("playerID")
    player_name = players.get(player_id, {}).get("name") if player_id else None

    return {
        "player_id": player_id,
        "player_name": player_name,
        "stat": stat,
        "period": period,
        "side": side,
        "bet_type": bet_type,
    }


def _parse_int(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _parse_line(book_data: dict) -> float | None:
    raw_line = book_data.get("overUnder", book_data.get("spread"))
    if raw_line is None:
        return None
    try:
        return float(raw_line)
    except (TypeError, ValueError):
        return None


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
