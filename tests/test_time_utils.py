from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.time_utils import get_today_utc_window

CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def test_middle_of_day():
    now = datetime(2024, 7, 15, 14, 30, tzinfo=CHICAGO)

    start_utc, end_utc = get_today_utc_window("America/Chicago", now=now)

    assert start_utc == datetime(2024, 7, 15, 5, 0, tzinfo=UTC)
    assert end_utc == datetime(2024, 7, 16, 5, 0, tzinfo=UTC)


def test_just_after_midnight():
    now = datetime(2024, 7, 15, 0, 0, 1, tzinfo=CHICAGO)

    start_utc, end_utc = get_today_utc_window("America/Chicago", now=now)

    assert start_utc == datetime(2024, 7, 15, 5, 0, tzinfo=UTC)
    assert end_utc == datetime(2024, 7, 16, 5, 0, tzinfo=UTC)


def test_just_before_midnight():
    now = datetime(2024, 7, 15, 23, 59, 59, tzinfo=CHICAGO)

    start_utc, end_utc = get_today_utc_window("America/Chicago", now=now)

    assert start_utc == datetime(2024, 7, 15, 5, 0, tzinfo=UTC)
    assert end_utc == datetime(2024, 7, 16, 5, 0, tzinfo=UTC)


def test_dst_spring_forward_produces_23_hour_day():
    # 2024-03-10: America/Chicago clocks jump from 02:00 CST to 03:00 CDT.
    now = datetime(2024, 3, 10, 12, 0, tzinfo=CHICAGO)

    start_utc, end_utc = get_today_utc_window("America/Chicago", now=now)

    assert start_utc == datetime(2024, 3, 10, 6, 0, tzinfo=UTC)
    assert end_utc == datetime(2024, 3, 11, 5, 0, tzinfo=UTC)
    assert end_utc - start_utc == timedelta(hours=23)


def test_dst_fall_back_produces_25_hour_day():
    # 2024-11-03: America/Chicago clocks fall back from 02:00 CDT to 01:00 CST.
    now = datetime(2024, 11, 3, 12, 0, tzinfo=CHICAGO)

    start_utc, end_utc = get_today_utc_window("America/Chicago", now=now)

    assert start_utc == datetime(2024, 11, 3, 5, 0, tzinfo=UTC)
    assert end_utc == datetime(2024, 11, 4, 6, 0, tzinfo=UTC)
    assert end_utc - start_utc == timedelta(hours=25)


def test_upper_boundary_is_exclusive():
    now = datetime(2024, 7, 15, 14, 30, tzinfo=CHICAGO)

    _, end_utc = get_today_utc_window("America/Chicago", now=now)
    just_before_end = end_utc - timedelta(microseconds=1)

    assert just_before_end < end_utc


def test_defaults_to_current_time_when_now_not_given():
    start_utc, end_utc = get_today_utc_window("America/Chicago")

    assert start_utc.tzinfo == UTC
    assert end_utc.tzinfo == UTC
    assert end_utc > start_utc
