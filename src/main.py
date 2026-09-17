"""Entry point: print today's eligible sporting events with market counts."""

from __future__ import annotations

import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from src.config import load_settings
from src.kalshi import get_open_markets
from src.models import Event, PredictionMarket, SportsbookQuote
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

    `markets` is expected to already be scoped to today's games (see
    get_open_markets), so this does not need its own date disambiguation.
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


def moneyline_by_sportsbook(
    sportsbook_quotes: list[SportsbookQuote],
) -> dict[str, dict[str, int]]:
    """Group each sportsbook's team (non-player) game moneyline odds by side.

    Both moneylines and spreads use statID "points", so betTypeID is required
    to isolate moneyline quotes specifically.
    """
    by_sportsbook: dict[str, dict[str, int]] = {}
    for quote in sportsbook_quotes:
        if (
            quote.player_id is not None
            or quote.bet_type != "ml"
            or quote.stat != "points"
            or quote.period != "game"
            or quote.side not in ("home", "away")
        ):
            continue
        by_sportsbook.setdefault(quote.sportsbook, {})[quote.side] = quote.american_odds

    return by_sportsbook


def find_team_market(
    matches: list[PredictionMarket], team_name: str
) -> PredictionMarket | None:
    """Pick the match (from an already-verified home/away pair) naming this team."""
    normalized_team = normalize_name(team_name)
    for market in matches:
        phrase = _team_phrase(market.title)
        if phrase and phrase in normalized_team:
            return market
    return None


def _format_american_odds(odds: int | None) -> str:
    return f"{odds:+d}" if odds is not None else "-"


def _format_kalshi_price(price: Decimal | None) -> str:
    return f"${price:.2f}" if price is not None else "-"


def _print_moneyline_comparison(
    event: Event,
    sportsbook_quotes: list[SportsbookQuote],
    matches: list[PredictionMarket],
) -> None:
    moneyline = moneyline_by_sportsbook(sportsbook_quotes)
    if not moneyline and not matches:
        return

    home_market = find_team_market(matches, event.home_team)
    away_market = find_team_market(matches, event.away_team)

    print(f"{'Moneyline':<18}{event.away_team:>16} {event.home_team:>16}")
    for sportsbook in sorted(moneyline):
        sides = moneyline[sportsbook]
        away_odds = _format_american_odds(sides.get("away"))
        home_odds = _format_american_odds(sides.get("home"))
        print(f"{sportsbook:<18}{away_odds:>16} {home_odds:>16}")

    if home_market or away_market:
        away_price = _format_kalshi_price(away_market.yes_ask if away_market else None)
        home_price = _format_kalshi_price(home_market.yes_ask if home_market else None)
        print(f"{'kalshi (yes ask)':<18}{away_price:>16} {home_price:>16}")


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
        markets = list(
            get_open_markets(
                settings,
                client,
                league_ids=settings.league_ids,
                start_utc=start_utc,
                end_utc=end_utc,
            )
        )

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
        if matches:
            _print_moneyline_comparison(event, sportsbook_quotes, matches)
        print()


if __name__ == "__main__":
    main()
