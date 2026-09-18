"""Entry point: print today's eligible sporting events with market counts."""

from __future__ import annotations

import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from src.config import load_settings
from src.kalshi import SERIES_TICKER_TEMPLATE, get_open_markets, get_player_prop_markets
from src.models import Event, PlayerPropMarket, PredictionMarket, SportsbookQuote
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


def kalshi_game_ticker_suffix(league: str, matches: list[PredictionMarket]) -> str | None:
    """Extract the per-game ticker suffix shared with that game's prop markets.

    e.g. event_ticker "KXNFLGAME-26SEP20MIASF" -> "26SEP20MIASF", which is
    also the suffix on that same game's KXNFLPASSYDS-26SEP20MIASF etc.
    (confirmed live; see get_player_prop_markets).
    """
    prefix = f"{SERIES_TICKER_TEMPLATE.format(league_id=league)}-"
    for market in matches:
        if market.event_ticker.startswith(prefix):
            return market.event_ticker.removeprefix(prefix)
    return None


def prop_odds_by_sportsbook(
    sportsbook_quotes: list[SportsbookQuote],
) -> dict[tuple[str, str, float], dict[str, dict[str, int]]]:
    """Group each sportsbook's game-period player-prop odds by (player, stat, line)."""
    by_prop: dict[tuple[str, str, float], dict[str, dict[str, int]]] = {}
    for quote in sportsbook_quotes:
        if (
            quote.player_id is None
            or quote.bet_type != "ou"
            or quote.period != "game"
            or quote.side not in ("over", "under")
            or quote.line is None
        ):
            continue
        key = (quote.player_name or "", quote.stat, quote.line)
        by_prop.setdefault(key, {}).setdefault(quote.sportsbook, {})[quote.side] = quote.american_odds

    return by_prop


def find_prop_market(
    prop_markets: list[PlayerPropMarket], player_name: str, stat: str, line: float
) -> PlayerPropMarket | None:
    """Conservative exact match: same player, same stat, same line."""
    normalized_player = normalize_name(player_name)
    for market in prop_markets:
        if (
            market.stat == stat
            and market.line == line
            and normalize_name(market.player_name) == normalized_player
        ):
            return market
    return None


def _implied_probability(odds: int) -> Decimal:
    """Convert American odds to raw, vig-inclusive implied probability."""
    if odds > 0:
        return Decimal(100) / Decimal(odds + 100)
    return Decimal(-odds) / Decimal(-odds + 100)


def _devig_two_way(odds_a: int, odds_b: int) -> tuple[Decimal, Decimal]:
    """Remove the vig from one sportsbook's two-way market.

    Normalizes the pair's implied probabilities (which sum to more than 1
    because of the sportsbook's hold) so they sum to exactly 1.
    """
    prob_a = _implied_probability(odds_a)
    prob_b = _implied_probability(odds_b)
    total = prob_a + prob_b
    return prob_a / total, prob_b / total


def _average_fair_probabilities(
    sides_by_sportsbook: dict[str, dict[str, int]], side_a: str, side_b: str
) -> tuple[Decimal | None, Decimal | None]:
    """Average de-vigged fair probabilities for each side across sportsbooks quoting both.

    A sportsbook missing either side of the market cannot be de-vigged and is
    skipped rather than guessed at.
    """
    fair_a: list[Decimal] = []
    fair_b: list[Decimal] = []
    for sides in sides_by_sportsbook.values():
        if side_a in sides and side_b in sides:
            prob_a, prob_b = _devig_two_way(sides[side_a], sides[side_b])
            fair_a.append(prob_a)
            fair_b.append(prob_b)

    avg_a = sum(fair_a) / len(fair_a) if fair_a else None
    avg_b = sum(fair_b) / len(fair_b) if fair_b else None
    return avg_a, avg_b


def _expected_value(fair_probability: Decimal | None, price: Decimal | None) -> Decimal | None:
    """Expected value per $1 risked, using the sportsbook consensus as fair value."""
    if fair_probability is None or price is None or price == 0:
        return None
    return (fair_probability - price) / price


def _format_american_odds(odds: int | None) -> str:
    return f"{odds:+d}" if odds is not None else "-"


def _format_kalshi_price(price: Decimal | None) -> str:
    return f"${price:.2f}" if price is not None else "-"


def _format_kalshi_price_with_ev(price: Decimal | None, ev: Decimal | None) -> str:
    if price is None:
        return "-"
    if ev is None:
        return _format_kalshi_price(price)
    return f"{_format_kalshi_price(price)} ({ev:+.1%} EV)"


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

    print(f"{'Moneyline':<18}{event.away_team:>22} {event.home_team:>22}")
    for sportsbook in sorted(moneyline):
        sides = moneyline[sportsbook]
        away_odds = _format_american_odds(sides.get("away"))
        home_odds = _format_american_odds(sides.get("home"))
        print(f"{sportsbook:<18}{away_odds:>22} {home_odds:>22}")

    if home_market or away_market:
        away_price = away_market.yes_ask if away_market else None
        home_price = home_market.yes_ask if home_market else None
        # Consensus fair value comes from de-vigging and averaging the same
        # sportsbook moneylines shown above, not from Kalshi itself.
        avg_away_fair, avg_home_fair = _average_fair_probabilities(moneyline, "away", "home")
        away_display = _format_kalshi_price_with_ev(
            away_price, _expected_value(avg_away_fair, away_price)
        )
        home_display = _format_kalshi_price_with_ev(
            home_price, _expected_value(avg_home_fair, home_price)
        )
        print(f"{'kalshi (yes ask)':<18}{away_display:>22} {home_display:>22}")


def _print_prop_comparisons(
    sportsbook_quotes: list[SportsbookQuote],
    prop_markets: list[PlayerPropMarket],
) -> None:
    by_prop = prop_odds_by_sportsbook(sportsbook_quotes)
    if not by_prop or not prop_markets:
        return

    for (player_name, stat, line), sportsbooks in sorted(by_prop.items()):
        market = find_prop_market(prop_markets, player_name, stat, line)
        if market is None:
            continue

        print(f"\n{player_name} {stat} {line}")
        print(f"{'':<18}{'Over':>22} {'Under':>22}")
        for sportsbook in sorted(sportsbooks):
            sides = sportsbooks[sportsbook]
            over_odds = _format_american_odds(sides.get("over"))
            under_odds = _format_american_odds(sides.get("under"))
            print(f"{sportsbook:<18}{over_odds:>22} {under_odds:>22}")

        # Kalshi player-prop markets are threshold ladders where "yes" means
        # the stat lands over the line (see kalshi.py), matching Over/Under.
        avg_over_fair, avg_under_fair = _average_fair_probabilities(sportsbooks, "over", "under")
        over_display = _format_kalshi_price_with_ev(
            market.yes_ask, _expected_value(avg_over_fair, market.yes_ask)
        )
        under_display = _format_kalshi_price_with_ev(
            market.no_ask, _expected_value(avg_under_fair, market.no_ask)
        )
        print(f"{'kalshi (ask)':<18}{over_display:>22} {under_display:>22}")


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

                # Only fetch player-prop markets once a game-level match already
                # exists (see CLAUDE.md's API Efficiency guidance).
                game_suffix = kalshi_game_ticker_suffix(event.league, matches)
                if game_suffix:
                    prop_markets = list(
                        get_player_prop_markets(settings, client, event.league, game_suffix)
                    )
                    _print_prop_comparisons(sportsbook_quotes, prop_markets)
            print()


if __name__ == "__main__":
    main()
