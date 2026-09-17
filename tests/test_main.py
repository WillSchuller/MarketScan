from decimal import Decimal

from src.main import find_potential_matches, normalize_name
from src.models import Event, PredictionMarket
from datetime import datetime, timezone


def _event(home_team, away_team):
    return Event(
        event_id="evt-1",
        league="NFL",
        home_team=home_team,
        away_team=away_team,
        start_time_utc=datetime(2026, 9, 17, 23, 0, tzinfo=timezone.utc),
    )


def _market(event_ticker, title, ticker=None):
    return PredictionMarket(
        ticker=ticker or f"{event_ticker}-{title}",
        event_ticker=event_ticker,
        title=title,
        yes_bid=Decimal("0.5"),
        yes_ask=Decimal("0.5"),
        no_bid=Decimal("0.5"),
        no_ask=Decimal("0.5"),
    )


def test_normalize_name_collapses_whitespace_and_case():
    assert normalize_name("  Buffalo   Bills  ") == "buffalo bills"


def test_matches_when_both_teams_present_in_same_kalshi_event():
    event = _event(home_team="Buffalo Bills", away_team="Detroit Lions")
    markets = [
        _market("KXNFLGAME-26SEP17DETBUF", "Detroit wins"),
        _market("KXNFLGAME-26SEP17DETBUF", "Buffalo wins"),
    ]

    matches = find_potential_matches(event, markets)

    assert len(matches) == 2


def test_matches_kalshi_disambiguating_abbreviation():
    event = _event(home_team="Denver Broncos", away_team="Los Angeles Rams")
    markets = [
        _market("KXNFLGAME-26SEP27LARDEN", "Los Angeles R wins"),
        _market("KXNFLGAME-26SEP27LARDEN", "Denver wins"),
    ]

    matches = find_potential_matches(event, markets)

    assert len(matches) == 2


def test_no_match_when_only_one_team_present():
    event = _event(home_team="Buffalo Bills", away_team="Detroit Lions")
    markets = [
        # Same event_ticker family but the sibling market for the other team
        # in a *different* matchup is not enough on its own.
        _market("KXNFLGAME-26SEP27NYJDET", "Detroit wins"),
    ]

    assert find_potential_matches(event, markets) == []


def test_no_match_for_unrelated_game():
    event = _event(home_team="Buffalo Bills", away_team="Detroit Lions")
    markets = [
        _market("KXNFLGAME-26SEP27LACBUF", "Los Angeles C wins"),
        _market("KXNFLGAME-26SEP27LACBUF", "Buffalo wins"),
    ]

    assert find_potential_matches(event, markets) == []
