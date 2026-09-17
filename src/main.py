"""Entry point: print today's eligible sporting events with market counts."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

import httpx

from src.config import load_settings
from src.kalshi import get_open_markets
from src.models import Event, PredictionMarket
from src.sports_odds import get_todays_upcoming_events, parse_sportsbook_quotes
from src.time_utils import get_today_utc_window

logger = logging.getLogger(__name__)


def normalize_name(value: str) -> str:
    """Lowercase, strip, and collapse whitespace for conservative name matching."""
    return " ".join(value.lower().strip().split())


def _team_phrase(market_title: str) -> str:
    """Kalshi's game markets are titled "{City} wins" (one market per team)."""
    return normalize_name(market_title).removesuffix(" wins")


def find_potential_matches(event: Event, markets: list[PredictionMarket]) -> list[PredictionMarket]:
    """Conservative match against one Kalshi game event's pair of team markets.

    Each Kalshi game market names only one team, so a single market can never
    name both sides of a SportsGameOdds event. Instead, require that among
    the markets sharing a Kalshi event_ticker, one names the home team and
    another names the away team, before treating any of them as a match.
    A false positive is worse than a missed match.

    Known limitation: this does not disambiguate by date, so a team playing
    a multi-game series this week can surface matches for other games in
    that series, not just today's. Kalshi's `close_time` on these markets
    was verified live to not reliably correspond to the game's actual start
    time (see CLAUDE.md's "Do Not Use Kalshi close_time as Game Start Time"),
    so it isn't used to narrow this further.
    """
    home = normalize_name(event.home_team)
    away = normalize_name(event.away_team)

    markets_by_event_ticker: dict[str, list[PredictionMarket]] = {}
    for market in markets:
        markets_by_event_ticker.setdefault(market.event_ticker, []).append(market)

    matches: list[PredictionMarket] = []
    for group in markets_by_event_ticker.values():
        phrases = [_team_phrase(m.title) for m in group]
        home_present = any(phrase and phrase in home for phrase in phrases)
        away_present = any(phrase and phrase in away for phrase in phrases)
        if home_present and away_present:
            matches.extend(group)

    return matches


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = load_settings()
    start_utc, end_utc = get_today_utc_window(settings.app_timezone)
    local_tz = ZoneInfo(settings.app_timezone)

    with httpx.Client(timeout=10.0) as client:
        todays_events = list(
            get_todays_upcoming_events(
                settings, start_utc, end_utc, client, league_ids=settings.league_ids
            )
        )
        markets = list(get_open_markets(settings, client, league_ids=settings.league_ids))

    print(f"Upcoming games today: {len(todays_events)}\n")

    for event, raw_event in todays_events:
        sportsbook_quotes = list(parse_sportsbook_quotes(raw_event))
        matches = find_potential_matches(event, markets)
        local_start = event.start_time_utc.astimezone(local_tz)

        print(event.league)
        print(f"{event.away_team} @ {event.home_team}")
        print(f"Start: {local_start.strftime('%I:%M %p %Z').lstrip('0')}")
        print(f"Sportsbook markets: {len(sportsbook_quotes)}")
        print(f"Kalshi matches: {len(matches)}")
        print()


if __name__ == "__main__":
    main()
