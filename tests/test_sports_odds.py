from datetime import datetime, timezone

import httpx
import pytest

from src.config import Settings
from src.sports_odds import get_todays_upcoming_events

SETTINGS = Settings(
    sports_game_odds_api_key="fake-key",
    app_timezone="America/Chicago",
    kalshi_environment="production",
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

    events = _fetch(handler)

    assert [e.event_id for e in events] == ["evt-nfl", "evt-mlb"]
    assert [e.league for e in events] == ["NFL", "MLB"]
    assert events[0].home_team == "Home Team"
    assert events[0].away_team == "Away Team"


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

    events = _fetch(handler)

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

    events = _fetch(handler)

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
