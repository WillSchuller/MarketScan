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


def test_includes_upcoming_same_day_event():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [_event("evt-1", "2026-09-16T18:00:00.000Z")],
            },
        )

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

    assert [e.event_id for e in events] == ["evt-1"]
    assert events[0].home_team == "Home Team"
    assert events[0].away_team == "Away Team"
    assert events[0].league == "NFL"


def test_excludes_event_already_started():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    _event("evt-started", "2026-09-16T08:00:00.000Z", started=True)
                ],
            },
        )

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

    assert events == []


def test_excludes_event_starting_tomorrow():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [_event("evt-tomorrow", "2026-09-17T18:00:00.000Z")],
            },
        )

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

    assert events == []


def test_excludes_event_that_started_earlier_today():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                # Not flagged started=true yet by the provider, but its start
                # time has already passed relative to "now" — must still be
                # rejected locally per the race-condition rule.
                "data": [_event("evt-past", "2026-09-16T08:00:00.000Z")],
            },
        )

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

    assert events == []


def test_follows_pagination_cursor():
    pages = [
        {
            "success": True,
            "data": [_event("evt-1", "2026-09-16T18:00:00.000Z")],
            "nextCursor": "page-2",
        },
        {
            "success": True,
            "data": [_event("evt-2", "2026-09-16T20:00:00.000Z")],
        },
    ]

    def handler(request):
        cursor = request.url.params.get("cursor")
        page = pages[1] if cursor == "page-2" else pages[0]
        return httpx.Response(200, json=page)

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

    assert [e.event_id for e in events] == ["evt-1", "evt-2"]


def test_skips_event_with_missing_fields():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {"eventID": "evt-broken", "status": {"started": False}},
                    _event("evt-ok", "2026-09-16T18:00:00.000Z"),
                ],
            },
        )

    with _client(handler) as client:
        events = list(
            get_todays_upcoming_events(
                SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
            )
        )

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
                    SETTINGS, WINDOW_START, WINDOW_END, client, now=NOW
                )
            )
