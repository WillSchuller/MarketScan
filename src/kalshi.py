"""Kalshi open prediction-market retrieval (public, read-only data)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation

import httpx

from src.config import Settings
from src.models import PredictionMarket

logger = logging.getLogger(__name__)

# Response `status` value for a currently tradeable market. Confirmed live:
# requesting ?status=open returns markets whose own `status` field is "active".
OPEN_STATUS = "active"


def get_open_markets(settings: Settings, client: httpx.Client) -> Iterator[PredictionMarket]:
    """Yield currently open Kalshi markets."""
    fetched = 0
    eligible = 0

    for raw_market in _fetch_markets(settings, client):
        fetched += 1

        market = _parse_market(raw_market)
        if market is None:
            continue

        eligible += 1
        yield market

    logger.info("Fetched %d Kalshi markets, %d open", fetched, eligible)


def _fetch_markets(settings: Settings, client: httpx.Client) -> Iterator[dict]:
    params: dict[str, str] = {"status": "open", "limit": "1000"}

    cursor: str | None = None
    while True:
        request_params = dict(params)
        if cursor:
            request_params["cursor"] = cursor

        response = client.get(f"{settings.kalshi_base_url}/markets", params=request_params)
        response.raise_for_status()
        payload = response.json()

        yield from payload.get("markets", [])

        cursor = payload.get("cursor")
        if not cursor:
            break


def _parse_market(raw_market: dict) -> PredictionMarket | None:
    try:
        # The status filter is applied server-side, but provider state can lag,
        # so re-check locally rather than trusting the request parameter alone.
        if raw_market["status"] != OPEN_STATUS:
            return None

        return PredictionMarket(
            ticker=raw_market["ticker"],
            event_ticker=raw_market["event_ticker"],
            title=raw_market.get("title") or raw_market.get("yes_sub_title", ""),
            yes_bid=_parse_price(raw_market.get("yes_bid_dollars")),
            yes_ask=_parse_price(raw_market.get("yes_ask_dollars")),
            no_bid=_parse_price(raw_market.get("no_bid_dollars")),
            no_ask=_parse_price(raw_market.get("no_ask_dollars")),
        )
    except (KeyError, TypeError):
        logger.warning(
            "Skipping market with unexpected shape: %s", raw_market.get("ticker")
        )
        return None


def _parse_price(raw_value: str | None) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None
