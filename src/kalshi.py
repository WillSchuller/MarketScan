"""Kalshi open prediction-market retrieval (public, read-only data)."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from src.config import Settings
from src.models import PlayerPropMarket, PredictionMarket

logger = logging.getLogger(__name__)

# Response `status` value for a currently tradeable market. Confirmed live:
# requesting ?status=open returns markets whose own `status` field is "active".
OPEN_STATUS = "active"

# Small bounded retry on 429s; see CLAUDE.md's API Rate Limits guidance
# (backoff, not a retry framework, and never a parallel retry storm).
MAX_RATE_LIMIT_RETRIES = 5

# Kalshi's own game-winner market for a league lives in a predictable series,
# e.g. NFL -> KXNFLGAME (confirmed live via GET /series?category=Sports).
# Kalshi's full open-market catalog spans every category (elections, crypto,
# weather, ...) and runs into the hundreds of thousands of markets, so
# scoping the request to each league's game series avoids paginating all of
# it and filtering client-side.
SERIES_TICKER_TEMPLATE = "KX{league_id}GAME"

# Kalshi player-prop series tickers, confirmed live against Kalshi's own
# series list (GET /series?category=Sports) rather than guessed. Each maps
# a SportsGameOdds statID to the Kalshi series covering that same stat, for
# leagues this project currently supports. A stat with no entry here is
# simply never matched, per CLAUDE.md's "prefer NO MATCH" guidance.
PLAYER_PROP_SERIES: dict[str, dict[str, str]] = {
    "NFL": {
        "passing_yards": "KXNFLPASSYDS",
        "rushing_yards": "KXNFLRSHYDS",
        "receiving_yards": "KXNFLRECYDS",
        "passing_touchdowns": "KXNFLPASSTDS",
        "passing_completions": "KXNFLPASSCOMP",
        "passing_attempts": "KXNFLPASSATT",
        "passing_interceptions": "KXNFLPASSINT",
        "receiving_receptions": "KXNFLREC",
    },
    "MLB": {
        "batting_hits": "KXMLBHIT",
        "batting_homeRuns": "KXMLBHR",
        "batting_RBI": "KXMLBRBI",
        "batting_totalBases": "KXMLBTB",
        "batting_stolenBases": "KXMLBSB",
        "pitching_strikeouts": "KXMLBKS",
    },
    # SportsGameOdds' generic "points" stat is goals scored in hockey, and its
    # "goals+assists" is hockey points (confirmed live: SGO "points" over 0.5
    # lines up with Kalshi's "1+ goals" market for the same player).
    "NHL": {
        "points": "KXNHLGOAL",
        "goals+assists": "KXNHLPTS",
        "assists": "KXNHLAST",
        "goalie_saves": "KXNHLSAVE",
    },
}


def get_open_markets(
    settings: Settings,
    client: httpx.Client,
    league_ids: str,
    start_utc: datetime,
    end_utc: datetime,
) -> Iterator[PredictionMarket]:
    """Yield open Kalshi game markets for the given leagues' games today.

    Kalshi's `close_time` was verified live to not reliably correspond to a
    game's actual date (it can be offset by days), so this instead uses
    `occurrence_datetime` — Kalshi's expected-conclusion timestamp, which was
    verified live to track close to each game's real date/time — to scope
    results to [start_utc, end_utc), mirroring SportsGameOdds' same-day
    window. Without this, a team playing a multi-game series this week would
    surface matches for every game in the series, not just today's.
    """
    fetched = 0
    eligible = 0

    for league_id in _split_league_ids(league_ids):
        series_ticker = SERIES_TICKER_TEMPLATE.format(league_id=league_id)

        for raw_market in _fetch_markets(settings, client, series_ticker=series_ticker):
            fetched += 1

            occurrence = _parse_occurrence_datetime(raw_market)
            if occurrence is None or not (start_utc <= occurrence < end_utc):
                continue

            market = _parse_market(raw_market)
            if market is None:
                continue

            eligible += 1
            yield market

    logger.info("Fetched %d Kalshi markets, %d open today", fetched, eligible)


def _split_league_ids(league_ids: str) -> list[str]:
    return [league_id.strip() for league_id in league_ids.split(",") if league_id.strip()]


def _fetch_markets(settings: Settings, client: httpx.Client, **query: str) -> Iterator[dict]:
    params: dict[str, str] = {"status": "open", "limit": "1000", **query}

    cursor: str | None = None
    while True:
        request_params = dict(params)
        if cursor:
            request_params["cursor"] = cursor

        payload = _get_with_retry(client, f"{settings.kalshi_base_url}/markets", request_params)

        yield from payload.get("markets", [])

        cursor = payload.get("cursor")
        if not cursor:
            break


def get_player_prop_markets(
    settings: Settings,
    client: httpx.Client,
    league_id: str,
    game_ticker_suffix: str,
) -> Iterator[PlayerPropMarket]:
    """Yield open Kalshi player-prop markets for one already-matched game.

    Only call this once a game-level match already exists (see CLAUDE.md's
    API Efficiency guidance: query individual markets after a likely match,
    not speculatively). `game_ticker_suffix` is the per-game ticker segment
    shared across a Kalshi game's markets and its prop markets across every
    stat series, e.g. "26SEP20MIASF" for KXNFLGAME-26SEP20MIASF and
    KXNFLPASSYDS-26SEP20MIASF alike (confirmed live).
    """
    for stat_id, series_ticker in PLAYER_PROP_SERIES.get(league_id, {}).items():
        event_ticker = f"{series_ticker}-{game_ticker_suffix}"

        for raw_market in _fetch_markets(settings, client, event_ticker=event_ticker):
            market = _parse_player_prop_market(raw_market, stat_id)
            if market is not None:
                yield market


def _get_with_retry(client: httpx.Client, url: str, params: dict[str, str]) -> dict:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        response = client.get(url, params=params)

        if response.status_code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
            response.raise_for_status()
            return response.json()

        wait_seconds = _retry_after_seconds(response) or (2**attempt)
        logger.warning("Kalshi rate limit hit, retrying in %.1fs", wait_seconds)
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


def _parse_occurrence_datetime(raw_market: dict) -> datetime | None:
    raw_value = raw_market.get("occurrence_datetime")
    if raw_value is None:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _parse_market(raw_market: dict) -> PredictionMarket | None:
    try:
        # The status filter is applied server-side, but provider state can lag,
        # so re-check locally rather than trusting the request parameter alone.
        # Note: per CLAUDE.md, Kalshi's own status must never independently
        # establish game-start eligibility — that's SportsGameOdds' job, and
        # this function is only ever called for markets already scoped to an
        # already-eligible SportsGameOdds event's day.
        if raw_market["status"] != OPEN_STATUS:
            return None

        return PredictionMarket(
            ticker=raw_market["ticker"],
            event_ticker=raw_market["event_ticker"],
            title=raw_market.get("title") or raw_market.get("yes_sub_title", ""),
            yes_bid=_parse_price(raw_market.get("yes_bid_dollars")),
            yes_ask=_parse_price(raw_market.get("yes_ask_dollars")),
            no_bid=_parse_price(raw_market.get("no_bid_dollars")),
            no_ask=_parse_price(raw_market.get("no_ask_dollars")),
        )
    except (KeyError, TypeError):
        logger.warning(
            "Skipping market with unexpected shape: %s", raw_market.get("ticker")
        )
        return None


def _parse_price(raw_value: str | None) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None


def _parse_player_prop_market(raw_market: dict, stat_id: str) -> PlayerPropMarket | None:
    try:
        if raw_market["status"] != OPEN_STATUS:
            return None

        # Kalshi prop markets are threshold ladders titled e.g. "258+ passing
        # yards" with floor_strike=257.5; that floor_strike lines up exactly
        # with a sportsbook's over/under line (confirmed live), so it is the
        # matching key rather than the display threshold in the title.
        line = _parse_float(raw_market.get("floor_strike"))
        if line is None:
            return None

        player_name = raw_market.get("yes_sub_title", "").split(":")[0].strip()
        if not player_name:
            return None

        return PlayerPropMarket(
            ticker=raw_market["ticker"],
            event_ticker=raw_market["event_ticker"],
            stat=stat_id,
            player_name=player_name,
            line=line,
            yes_bid=_parse_price(raw_market.get("yes_bid_dollars")),
            yes_ask=_parse_price(raw_market.get("yes_ask_dollars")),
            no_bid=_parse_price(raw_market.get("no_bid_dollars")),
            no_ask=_parse_price(raw_market.get("no_ask_dollars")),
        )
    except (KeyError, TypeError):
        logger.warning(
            "Skipping player prop market with unexpected shape: %s", raw_market.get("ticker")
        )
        return None


def _parse_float(raw_value: object) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None
