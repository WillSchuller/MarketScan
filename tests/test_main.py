from decimal import Decimal

from src.main import (
    _average_fair_probabilities,
    _devig_two_way,
    _expected_value,
    _implied_probability,
    find_potential_matches,
    find_prop_market,
    find_team_market,
    kalshi_game_ticker_suffix,
    moneyline_by_sportsbook,
    normalize_name,
    prop_odds_by_sportsbook,
)
from src.models import Event, PlayerPropMarket, PredictionMarket, SportsbookQuote
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


def _moneyline_quote(sportsbook, side, american_odds):
    return SportsbookQuote(
        event_id="evt-1",
        player_id=None,
        player_name=None,
        stat="points",
        period="game",
        side=side,
        bet_type="ml",
        line=None,
        sportsbook=sportsbook,
        american_odds=american_odds,
    )


def test_moneyline_by_sportsbook_groups_sides():
    quotes = [
        _moneyline_quote("draftkings", "home", -150),
        _moneyline_quote("draftkings", "away", 130),
        _moneyline_quote("fanduel", "away", 125),
    ]

    assert moneyline_by_sportsbook(quotes) == {
        "draftkings": {"home": -150, "away": 130},
        "fanduel": {"away": 125},
    }


def test_moneyline_by_sportsbook_ignores_player_props_and_spreads():
    prop_quote = SportsbookQuote(
        event_id="evt-1",
        player_id="SOME_PLAYER",
        player_name="Some Player",
        stat="points",
        period="game",
        side="home",
        bet_type="ml",
        line=None,
        sportsbook="draftkings",
        american_odds=-150,
    )
    spread_quote = SportsbookQuote(
        event_id="evt-1",
        player_id=None,
        player_name=None,
        stat="points",
        period="game",
        side="home",
        bet_type="sp",
        line=-3.5,
        sportsbook="draftkings",
        american_odds=-110,
    )

    assert moneyline_by_sportsbook([prop_quote, spread_quote]) == {}


def test_find_team_market_matches_by_name_containment():
    markets = [
        _market("KXNFLGAME-26SEP17DETBUF", "Detroit wins"),
        _market("KXNFLGAME-26SEP17DETBUF", "Buffalo wins"),
    ]

    assert find_team_market(markets, "Buffalo Bills").title == "Buffalo wins"
    assert find_team_market(markets, "Detroit Lions").title == "Detroit wins"
    assert find_team_market(markets, "Dallas Cowboys") is None


def test_kalshi_game_ticker_suffix_strips_league_game_prefix():
    matches = [
        _market("KXNFLGAME-26SEP17DETBUF", "Detroit wins"),
        _market("KXNFLGAME-26SEP17DETBUF", "Buffalo wins"),
    ]

    assert kalshi_game_ticker_suffix("NFL", matches) == "26SEP17DETBUF"


def test_kalshi_game_ticker_suffix_none_when_no_match_has_expected_prefix():
    matches = [_market("KXMLBGAME-26SEP17DETBUF", "Detroit wins")]

    assert kalshi_game_ticker_suffix("NFL", matches) is None


def _prop_quote(player_name, stat, side, line, sportsbook, american_odds, period="game"):
    return SportsbookQuote(
        event_id="evt-1",
        player_id=f"{player_name.upper()}_1_NFL",
        player_name=player_name,
        stat=stat,
        period=period,
        side=side,
        bet_type="ou",
        line=line,
        sportsbook=sportsbook,
        american_odds=american_odds,
    )


def test_prop_odds_by_sportsbook_groups_over_under_by_player_stat_line():
    quotes = [
        _prop_quote("Brock Purdy", "passing_yards", "over", 257.5, "fanduel", -113),
        _prop_quote("Brock Purdy", "passing_yards", "under", 257.5, "fanduel", -107),
        _prop_quote("Brock Purdy", "passing_yards", "over", 258.5, "draftkings", -110),
    ]

    grouped = prop_odds_by_sportsbook(quotes)

    assert grouped == {
        ("Brock Purdy", "passing_yards", 257.5): {"fanduel": {"over": -113, "under": -107}},
        ("Brock Purdy", "passing_yards", 258.5): {"draftkings": {"over": -110}},
    }


def test_prop_odds_by_sportsbook_ignores_non_game_period_and_missing_line():
    quotes = [
        _prop_quote("Brock Purdy", "passing_yards", "over", 150.5, "fanduel", -110, period="1h"),
        SportsbookQuote(
            event_id="evt-1",
            player_id="BROCK_PURDY_1_NFL",
            player_name="Brock Purdy",
            stat="touchdowns",
            period="game",
            side="yes",
            bet_type="yn",
            line=None,
            sportsbook="fanduel",
            american_odds=120,
        ),
    ]

    assert prop_odds_by_sportsbook(quotes) == {}


def _prop_market(player_name, stat, line):
    return PlayerPropMarket(
        ticker=f"KX-{player_name}-{line}",
        event_ticker="KXNFLPASSYDS-26SEP20MIASF",
        stat=stat,
        player_name=player_name,
        line=line,
        yes_bid=Decimal("0.45"),
        yes_ask=Decimal("0.47"),
        no_bid=Decimal("0.53"),
        no_ask=Decimal("0.55"),
    )


def test_find_prop_market_matches_player_stat_and_line_exactly():
    markets = [
        _prop_market("Brock Purdy", "passing_yards", 257.5),
        _prop_market("Brock Purdy", "passing_yards", 274.5),
    ]

    assert find_prop_market(markets, "Brock Purdy", "passing_yards", 257.5).line == 257.5
    assert find_prop_market(markets, "Brock Purdy", "passing_yards", 300.5) is None
    assert find_prop_market(markets, "Brock Purdy", "rushing_yards", 257.5) is None
    assert find_prop_market(markets, "Someone Else", "passing_yards", 257.5) is None


def test_implied_probability_matches_known_values():
    assert _implied_probability(-110) == Decimal(110) / Decimal(210)
    assert _implied_probability(150) == Decimal(100) / Decimal(250)


def test_devig_two_way_normalizes_to_sum_of_one():
    fair_a, fair_b = _devig_two_way(-110, -110)

    assert round(fair_a, 6) == Decimal("0.5")
    assert round(fair_b, 6) == Decimal("0.5")
    assert round(fair_a + fair_b, 6) == Decimal("1")


def test_devig_two_way_favorite_underdog():
    fair_favorite, fair_underdog = _devig_two_way(-200, 150)

    assert round(fair_favorite, 6) == Decimal("0.625")
    assert round(fair_underdog, 6) == Decimal("0.375")


def test_average_fair_probabilities_skips_sportsbook_missing_a_side():
    sides_by_sportsbook = {
        "book_a": {"over": -110, "under": -110},
        "book_b": {"over": -120, "under": 100},
        "book_c": {"over": -115},  # missing "under"; cannot be de-vigged
    }

    avg_over, avg_under = _average_fair_probabilities(sides_by_sportsbook, "over", "under")

    fair_a_over, fair_a_under = _devig_two_way(-110, -110)
    fair_b_over, fair_b_under = _devig_two_way(-120, 100)
    assert avg_over == (fair_a_over + fair_b_over) / 2
    assert avg_under == (fair_a_under + fair_b_under) / 2


def test_average_fair_probabilities_none_when_no_complete_sportsbook():
    sides_by_sportsbook = {"book_a": {"over": -110}}

    avg_over, avg_under = _average_fair_probabilities(sides_by_sportsbook, "over", "under")

    assert avg_over is None
    assert avg_under is None


def test_expected_value_positive_when_fair_probability_exceeds_price():
    assert _expected_value(Decimal("0.6"), Decimal("0.50")) == Decimal("0.2")


def test_expected_value_negative_when_price_exceeds_fair_probability():
    assert _expected_value(Decimal("0.4"), Decimal("0.50")) == Decimal("-0.2")


def test_expected_value_none_when_inputs_missing():
    assert _expected_value(None, Decimal("0.50")) is None
    assert _expected_value(Decimal("0.6"), None) is None
    assert _expected_value(Decimal("0.6"), Decimal("0")) is None
