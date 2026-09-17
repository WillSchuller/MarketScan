from datetime import datetime, timezone

import httpx
import pytest

from src.config import Settings
from src.sports_odds import get_todays_upcoming_events, parse_sportsbook_quotes

SETTINGS = Settings(
    sports_game_odds_api_key="fake-key",
    app_timezone="America/Chicago",
    kalshi_environment="production",
    kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
    league_ids="NFL,MLB",
)

WINDOW_START = datetime(2026, 9, 16, 5, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 17, 5, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
LEAGUE_IDS = "NFL,MLB"


def _event(event_id, starts_at, started=False, league="NFL"):
    return {
        "eventID": event_id,
        "leagueID": league,
        "teams": {
            "home": {"names": {"long": "Home Team"}},
            "away": {"names": {"long": "Away Team"}},
        },
        "status": {"started": started, "startsAt": starts_at},
    }


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetch(handler):
    with _client(handler) as client:
        return list(
            get_todays_upcoming_events(
                SETTINGS,
                WINDOW_START,
                WINDOW_END,
                client,
                league_ids=LEAGUE_IDS,
                now=NOW,
            )
        )


def test_sends_requested_league_ids():
    seen_params = {}

    def handler(request):
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"success": True, "data": []})

    _fetch(handler)

    assert seen_params["leagueID"] == LEAGUE_IDS


def test_includes_upcoming_same_day_events_across_leagues():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    _event("evt-nfl", "2026-09-16T18:00:00.000Z", league="NFL"),
                    _event("evt-mlb", "2026-09-16T19:00:00.000Z", league="MLB"),
                ],
            },
        )

    results = _fetch(handler)
    events = [event for event, _ in results]

    assert [e.event_id for e in events] == ["evt-nfl", "evt-mlb"]
    assert [e.league for e in events] == ["NFL", "MLB"]
    assert events[0].home_team == "Home Team"
    assert events[0].away_team == "Away Team"
    assert [raw["eventID"] for _, raw in results] == ["evt-nfl", "evt-mlb"]


def test_excludes_event_already_started():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    _event(
                        "evt-started",
                        "2026-09-16T08:00:00.000Z",
                        started=True,
                        league="MLB",
                    )
                ],
            },
        )

    assert _fetch(handler) == []


def test_excludes_event_starting_tomorrow():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    _event("evt-tomorrow", "2026-09-17T18:00:00.000Z", league="NFL")
                ],
            },
        )

    assert _fetch(handler) == []


def test_excludes_event_that_started_earlier_today():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                # Not flagged started=true yet by the provider, but its start
                # time has already passed relative to "now" — must still be
                # rejected locally per the race-condition rule.
                "data": [
                    _event("evt-past", "2026-09-16T08:00:00.000Z", league="MLB")
                ],
            },
        )

    assert _fetch(handler) == []


def test_follows_pagination_cursor_across_leagues():
    pages = [
        {
            "success": True,
            "data": [_event("evt-1", "2026-09-16T18:00:00.000Z", league="NFL")],
            "nextCursor": "page-2",
        },
        {
            "success": True,
            "data": [_event("evt-2", "2026-09-16T20:00:00.000Z", league="MLB")],
        },
    ]

    def handler(request):
        cursor = request.url.params.get("cursor")
        page = pages[1] if cursor == "page-2" else pages[0]
        return httpx.Response(200, json=page)

    events = [event for event, _ in _fetch(handler)]

    assert [e.event_id for e in events] == ["evt-1", "evt-2"]
    assert [e.league for e in events] == ["NFL", "MLB"]


def test_skips_event_with_missing_fields():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {"eventID": "evt-broken", "status": {"started": False}},
                    _event("evt-ok", "2026-09-16T18:00:00.000Z", league="MLB"),
                ],
            },
        )

    events = [event for event, _ in _fetch(handler)]

    assert [e.event_id for e in events] == ["evt-ok"]


def test_raises_on_api_error_response():
    def handler(request):
        return httpx.Response(
            400, json={"success": False, "error": "leagueID required"}
        )

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            list(
                get_todays_upcoming_events(
                    SETTINGS,
                    WINDOW_START,
                    WINDOW_END,
                    client,
                    league_ids=LEAGUE_IDS,
                    now=NOW,
                )
            )


def test_retries_after_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr("src.sports_odds.time.sleep", lambda seconds: None)
    calls = {"count": 0}

    def handler(request):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [_event("evt-1", "2026-09-16T18:00:00.000Z", league="NFL")],
            },
        )

    events = [event for event, _ in _fetch(handler)]

    assert calls["count"] == 2
    assert [e.event_id for e in events] == ["evt-1"]


def test_raises_after_exhausting_rate_limit_retries(monkeypatch):
    monkeypatch.setattr("src.sports_odds.time.sleep", lambda seconds: None)

    def handler(request):
        return httpx.Response(429)

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            list(
                get_todays_upcoming_events(
                    SETTINGS,
                    WINDOW_START,
                    WINDOW_END,
                    client,
                    league_ids=LEAGUE_IDS,
                    now=NOW,
                )
            )


def _raw_event_with_odds(event_id, odds):
    return {
        "eventID": event_id,
        "players": {
            "SOME_PLAYER_1_NFL": {"playerID": "SOME_PLAYER_1_NFL", "name": "Some Player"},
        },
        "odds": odds,
    }


def _ou_odd(odd_id, side, *, book_odds_by_sportsbook):
    return {
        "oddID": odd_id,
        "statID": "passing_yards",
        "periodID": "game",
        "sideID": side,
        "betTypeID": "ou",
        "playerID": "SOME_PLAYER_1_NFL",
        "byBookmaker": {
            sportsbook: {
                "odds": odds,
                "overUnder": "249.5",
                "available": available,
            }
            for sportsbook, (odds, available) in book_odds_by_sportsbook.items()
        },
    }


def test_parses_over_under_quotes_from_two_sportsbooks_across_two_events():
    event_1 = _raw_event_with_odds(
        "evt-1",
        {
            "passing_yards-SOME_PLAYER_1_NFL-game-ou-over": _ou_odd(
                "passing_yards-SOME_PLAYER_1_NFL-game-ou-over",
                "over",
                book_odds_by_sportsbook={
                    "draftkings": ("-115", True),
                    "fanduel": ("-110", True),
                },
            ),
        },
    )
    event_2 = _raw_event_with_odds(
        "evt-2",
        {
            "passing_yards-SOME_PLAYER_1_NFL-game-ou-under": _ou_odd(
                "passing_yards-SOME_PLAYER_1_NFL-game-ou-under",
                "under",
                book_odds_by_sportsbook={
                    "draftkings": ("-105", True),
                    "fanduel": ("-120", True),
                },
            ),
        },
    )

    quotes_1 = list(parse_sportsbook_quotes(event_1))
    quotes_2 = list(parse_sportsbook_quotes(event_2))

    assert len(quotes_1) == 2
    assert {q.sportsbook for q in quotes_1} == {"draftkings", "fanduel"}
    assert all(q.event_id == "evt-1" for q in quotes_1)
    assert all(q.side == "over" for q in quotes_1)
    assert all(q.line == 249.5 for q in quotes_1)
    assert all(q.player_id == "SOME_PLAYER_1_NFL" for q in quotes_1)
    assert all(q.player_name == "Some Player" for q in quotes_1)

    draftkings_quote = next(q for q in quotes_1 if q.sportsbook == "draftkings")
    assert draftkings_quote.american_odds == -115

    assert len(quotes_2) == 2
    assert all(q.event_id == "evt-2" for q in quotes_2)
    assert all(q.side == "under" for q in quotes_2)


def test_discards_unavailable_bookmaker_quotes():
    event = _raw_event_with_odds(
        "evt-1",
        {
            "passing_yards-SOME_PLAYER_1_NFL-game-ou-over": _ou_odd(
                "passing_yards-SOME_PLAYER_1_NFL-game-ou-over",
                "over",
                book_odds_by_sportsbook={
                    "draftkings": ("-115", True),
                    "fanduel": ("-110", False),
                },
            ),
        },
    )

    quotes = list(parse_sportsbook_quotes(event))

    assert [q.sportsbook for q in quotes] == ["draftkings"]


def _moneyline_odd(odd_id, side, *, book_odds_by_sportsbook):
    return {
        "oddID": odd_id,
        "statID": "points",
        "periodID": "game",
        "sideID": side,
        "betTypeID": "ml",
        "byBookmaker": {
            sportsbook: {"odds": odds, "available": available}
            for sportsbook, (odds, available) in book_odds_by_sportsbook.items()
        },
    }


def test_parses_team_moneyline_quotes_with_no_player():
    event = _raw_event_with_odds(
        "evt-1",
        {
            "points-home-game-ml-home": _moneyline_odd(
                "points-home-game-ml-home",
                "home",
                book_odds_by_sportsbook={"draftkings": ("-150", True)},
            ),
            "points-away-game-ml-away": _moneyline_odd(
                "points-away-game-ml-away",
                "away",
                book_odds_by_sportsbook={"draftkings": ("+130", True)},
            ),
        },
    )

    quotes = list(parse_sportsbook_quotes(event))

    assert {(q.side, q.american_odds) for q in quotes} == {("home", -150), ("away", 130)}
    assert all(q.bet_type == "ml" for q in quotes)
    assert all(q.player_id is None for q in quotes)


def test_skips_odd_entry_with_missing_required_fields():
    event = _raw_event_with_odds(
        "evt-1",
        {
            "broken": {"oddID": "broken", "byBookmaker": {"draftkings": {"odds": "-110", "available": True}}},
        },
    )

    assert list(parse_sportsbook_quotes(event)) == []
