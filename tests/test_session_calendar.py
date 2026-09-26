from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market.sessions.nse_calendar import IST, NseSessionCalendar, SessionPhase


def test_weekend_is_not_trading_day():
    cal = NseSessionCalendar()
    saturday = date(2026, 9, 19)
    assert cal.is_trading_day(saturday) is False


def test_weekday_is_trading_day_by_default():
    cal = NseSessionCalendar()
    monday = date(2026, 9, 21)
    assert cal.is_trading_day(monday) is True


def test_configured_holiday_overrides_weekday():
    holiday = date(2026, 10, 2)  # e.g. Gandhi Jayanti
    cal = NseSessionCalendar(holidays={holiday})
    assert cal.is_trading_day(holiday) is False


def test_regular_session_phase():
    cal = NseSessionCalendar()
    ts = datetime(2026, 9, 21, 10, 0, tzinfo=IST)
    assert cal.phase(ts) == SessionPhase.REGULAR
    assert cal.is_market_open(ts) is True


def test_closed_outside_session():
    cal = NseSessionCalendar()
    ts = datetime(2026, 9, 21, 20, 0, tzinfo=IST)
    assert cal.phase(ts) == SessionPhase.CLOSED
    assert cal.is_market_open(ts) is False


def test_phase_requires_timezone_aware_datetime():
    cal = NseSessionCalendar()
    naive = datetime(2026, 9, 21, 10, 0)
    with pytest.raises(ValueError):
        cal.phase(naive)


def test_phase_handles_non_ist_input():
    cal = NseSessionCalendar()
    utc_ts = datetime(2026, 9, 21, 4, 30, tzinfo=ZoneInfo("UTC"))  # 10:00 IST
    assert cal.phase(utc_ts) == SessionPhase.REGULAR
