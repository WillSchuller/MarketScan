"""Minimal internal data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Event:
    event_id: str
    league: str
    home_team: str
    away_team: str
    start_time_utc: datetime


@dataclass(frozen=True)
class PredictionMarket:
    ticker: str
    event_ticker: str
    title: str
    yes_bid: Decimal | None
    yes_ask: Decimal | None
    no_bid: Decimal | None
    no_ask: Decimal | None
