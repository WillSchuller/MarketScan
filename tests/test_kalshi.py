from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from src.config import Settings
from src.kalshi import get_open_markets, get_player_prop_markets

SETTINGS = Settings(
    sports_game_odds_api_key="fake-key",
    app_timezone="America/Chicago",
    kalshi_environment="production",
    kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
    league_ids="NFL",
)

WINDOW_START = datetime(2026, 9, 17, 5, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc)


def _market(ticker, status="active", occurrence_datetime="2026-09-17T23:15:00Z", **overrides):
    market = {
        "ticker": ticker,
        "event_ticker": f"{ticker}-EVT",
        "title": "Some Team wins",
        "status": status,
        "occurrence_datetime": occurrence_datetime,
        "yes_bid_dollars": "0.4500",
        "yes_ask_dollars": "0.4700",
        "no_bid_dollars": "0.5300",
        "no_ask_dollars": "0.5500",
    }
    market.update(overrides)
    return market


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetch(handler, settings=SETTINGS):
    with _client(handler) as client:
        return list(
            get_open_markets(
                settings,
                client,
                league_ids=settings.league_ids,
                start_utc=WINDOW_START,
                end_utc=WINDOW_END,
            )
        )


def test_requests_open_status_for_leagues_game_series():
    seen_params = {}

    def handler(request):
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"markets": []})

    _fetch(handler)

    assert seen_params["status"] == "open"
    assert seen_params["series_ticker"] == "KXNFLGAME"


def test_queries_each_configured_league_series():
    settings = Settings(
        sports_game_odds_api_key="fake-key",
        app_timezone="America/Chicago",
        kalshi_environment="production",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        league_ids="NFL,MLB",
    )
    seen_series_tickers = []

    def handler(request):
        series_ticker = request.url.params["series_ticker"]
        seen_series_tickers.append(series_ticker)
        return httpx.Response(
            200, json={"markets": [_market(f"KXTEST-{series_ticker}")]}
        )

    markets = _fetch(handler, settings=settings)

    assert seen_series_tickers == ["KXNFLGAME", "KXMLBGAME"]
    assert [m.ticker for m in markets] == ["KXTEST-KXNFLGAME", "KXTEST-KXMLBGAME"]


def test_includes_open_market_with_yes_no_bid_ask():
    def handler(request):
        return httpx.Response(
            200, json={"markets": [_market("KXTEST-1")]}
        )

    markets = _fetch(handler)

    assert len(markets) == 1
    market = markets[0]
    assert market.ticker == "KXTEST-1"
    assert market.event_ticker == "KXTEST-1-EVT"
    assert market.yes_bid == Decimal("0.4500")
    assert market.yes_ask == Decimal("0.4700")
    assert market.no_bid == Decimal("0.5300")
    assert market.no_ask == Decimal("0.5500")


def test_excludes_market_not_actually_open():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "markets": [
                    _market("KXTEST-closed", status="determined"),
                    _market("KXTEST-open"),
                ]
            },
        )

    markets = _fetch(handler)

    assert [m.ticker for m in markets] == ["KXTEST-open"]


def test_excludes_market_for_a_different_days_game():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "markets": [
                    _market("KXTEST-today", occurrence_datetime="2026-09-17T23:15:00Z"),
                    _market("KXTEST-tomorrow", occurrence_datetime="2026-09-18T18:00:00Z"),
                    _market("KXTEST-yesterday", occurrence_datetime="2026-09-16T18:00:00Z"),
                ]
            },
        )

    markets = _fetch(handler)

    assert [m.ticker for m in markets] == ["KXTEST-today"]


def test_excludes_market_with_missing_occurrence_datetime():
    def handler(request):
        return httpx.Response(
            200,
            json={"markets": [_market("KXTEST-1", occurrence_datetime=None)]},
        )

    assert _fetch(handler) == []


def test_follows_cursor_pagination():
    pages = [
        {"markets": [_market("KXTEST-1")], "cursor": "page-2"},
        {"markets": [_market("KXTEST-2")]},
    ]

    def handler(request):
        cursor = request.url.params.get("cursor")
        page = pages[1] if cursor == "page-2" else pages[0]
        return httpx.Response(200, json=page)

    markets = _fetch(handler)

    assert [m.ticker for m in markets] == ["KXTEST-1", "KXTEST-2"]


def test_skips_market_with_missing_fields():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "markets": [
                    {"ticker": "KXTEST-broken", "status": "active"},
                    _market("KXTEST-ok"),
                ]
            },
        )

    markets = _fetch(handler)

    assert [m.ticker for m in markets] == ["KXTEST-ok"]


def test_raises_on_http_error():
    def handler(request):
        return httpx.Response(500, json={"error": "internal"})

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            list(
                get_open_markets(
                    SETTINGS,
                    client,
                    league_ids=SETTINGS.league_ids,
                    start_utc=WINDOW_START,
                    end_utc=WINDOW_END,
                )
            )


def _prop_market(ticker, event_ticker, yes_sub_title, floor_strike, status="active"):
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "yes_sub_title": yes_sub_title,
        "floor_strike": floor_strike,
        "status": status,
        "yes_bid_dollars": "0.4500",
        "yes_ask_dollars": "0.4700",
        "no_bid_dollars": "0.5300",
        "no_ask_dollars": "0.5500",
    }


def test_player_props_query_each_mapped_stat_series_for_the_game():
    seen_event_tickers = []

    def handler(request):
        event_ticker = request.url.params["event_ticker"]
        seen_event_tickers.append(event_ticker)
        return httpx.Response(200, json={"markets": []})

    with _client(handler) as client:
        list(get_player_prop_markets(SETTINGS, client, "NFL", "26SEP20MIASF"))

    assert seen_event_tickers == [
        f"{series}-26SEP20MIASF"
        for series in [
            "KXNFLPASSYDS",
            "KXNFLRSHYDS",
            "KXNFLRECYDS",
            "KXNFLPASSTDS",
            "KXNFLPASSCOMP",
            "KXNFLPASSATT",
            "KXNFLPASSINT",
            "KXNFLREC",
        ]
    ]


def test_player_props_parses_line_and_player_name():
    def handler(request):
        if request.url.params["event_ticker"] == "KXNFLPASSYDS-26SEP20MIASF":
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _prop_market(
                            "KXNFLPASSYDS-26SEP20MIASF-SFBPURDY13-350",
                            "KXNFLPASSYDS-26SEP20MIASF",
                            "Brock Purdy: 350+",
                            349.5,
                        )
                    ]
                },
            )
        return httpx.Response(200, json={"markets": []})

    with _client(handler) as client:
        markets = list(get_player_prop_markets(SETTINGS, client, "NFL", "26SEP20MIASF"))

    passing_yards = [m for m in markets if m.stat == "passing_yards"]
    assert len(passing_yards) == 1
    market = passing_yards[0]
    assert market.player_name == "Brock Purdy"
    assert market.line == 349.5
    assert market.yes_ask == Decimal("0.4700")


def test_player_props_skips_closed_market_and_missing_floor_strike():
    def handler(request):
        if request.url.params["event_ticker"] == "KXNFLPASSYDS-26SEP20MIASF":
            market = _prop_market(
                "KXNFLPASSYDS-26SEP20MIASF-CLOSED",
                "KXNFLPASSYDS-26SEP20MIASF",
                "Someone: 100+",
                99.5,
                status="determined",
            )
            no_strike = _prop_market(
                "KXNFLPASSYDS-26SEP20MIASF-NOSTRIKE",
                "KXNFLPASSYDS-26SEP20MIASF",
                "Someone Else: 100+",
                None,
            )
            return httpx.Response(200, json={"markets": [market, no_strike]})
        return httpx.Response(200, json={"markets": []})

    with _client(handler) as client:
        markets = list(get_player_prop_markets(SETTINGS, client, "NFL", "26SEP20MIASF"))

    assert markets == []


def test_player_props_empty_for_unmapped_league():
    def handler(request):
        raise AssertionError("should not request markets for an unmapped league")

    with _client(handler) as client:
        markets = list(get_player_prop_markets(SETTINGS, client, "NHL", "26SEP20ABCXYZ"))

    assert markets == []


def test_retries_after_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr("src.kalshi.time.sleep", lambda seconds: None)
    calls = {"count": 0}

    def handler(request):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"markets": [_market("KXTEST-1")]})

    markets = _fetch(handler)

    assert calls["count"] == 2
    assert [m.ticker for m in markets] == ["KXTEST-1"]


def test_raises_after_exhausting_rate_limit_retries(monkeypatch):
    monkeypatch.setattr("src.kalshi.time.sleep", lambda seconds: None)

    def handler(request):
        return httpx.Response(429)

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            list(
                get_open_markets(
                    SETTINGS,
                    client,
                    league_ids=SETTINGS.league_ids,
                    start_utc=WINDOW_START,
                    end_utc=WINDOW_END,
                )
            )
