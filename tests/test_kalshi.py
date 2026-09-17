from decimal import Decimal

import httpx
import pytest

from src.config import Settings
from src.kalshi import get_open_markets

SETTINGS = Settings(
    sports_game_odds_api_key="fake-key",
    app_timezone="America/Chicago",
    kalshi_environment="production",
    kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
)


def _market(ticker, status="active", **overrides):
    market = {
        "ticker": ticker,
        "event_ticker": f"{ticker}-EVT",
        "title": "Some Team wins",
        "status": status,
        "yes_bid_dollars": "0.4500",
        "yes_ask_dollars": "0.4700",
        "no_bid_dollars": "0.5300",
        "no_ask_dollars": "0.5500",
    }
    market.update(overrides)
    return market


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetch(handler):
    with _client(handler) as client:
        return list(get_open_markets(SETTINGS, client))


def test_requests_open_status():
    seen_params = {}

    def handler(request):
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"markets": []})

    _fetch(handler)

    assert seen_params["status"] == "open"


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
            list(get_open_markets(SETTINGS, client))
