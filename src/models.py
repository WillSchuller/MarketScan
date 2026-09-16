"""Minimal internal data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    event_id: str
    league: str
    home_team: str
    away_team: str
    start_time_utc: datetime
