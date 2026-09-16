"""Local-calendar-day window calculation, converted to UTC."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


def get_today_utc_window(
    app_timezone: str, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return today's local calendar-day boundaries converted to UTC."""
    zone = ZoneInfo(app_timezone)

    if now is None:
        local_now = datetime.now(zone)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=zone)
    else:
        local_now = now.astimezone(zone)

    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)

    return start_local.astimezone(UTC), end_local.astimezone(UTC)
