"""NSE market session engine.

Reusable by real-time ingestion, alerts, historical calculations, backtesting, reports
and scheduled jobs. Understands trading days vs weekends/holidays and the pre-open /
regular / post-close phases. Not every weekday is a trading day — holidays must be
supplied (from a maintained calendar, not assumed).
"""
from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PRE_OPEN_START = time(9, 0)
PRE_OPEN_END = time(9, 8)
REGULAR_START = time(9, 15)
REGULAR_END = time(15, 30)
POST_CLOSE_END = time(16, 0)


class SessionPhase(str, Enum):
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    REGULAR = "REGULAR"
    POST_CLOSE = "POST_CLOSE"


class NseSessionCalendar:
    """Holidays must be injected — this module does not hard-code a holiday list.

    In production, holidays are loaded from configuration/storage (an official NSE
    holiday calendar), refreshed at least yearly.
    """

    def __init__(self, holidays: set[date] | None = None) -> None:
        self._holidays = holidays or set()

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if d in self._holidays:
            return False
        return True

    def phase(self, ts: datetime) -> SessionPhase:
        if ts.tzinfo is None:
            raise ValueError("phase() requires a timezone-aware datetime")
        local = ts.astimezone(IST)
        if not self.is_trading_day(local.date()):
            return SessionPhase.CLOSED

        t = local.time()
        if PRE_OPEN_START <= t < PRE_OPEN_END:
            return SessionPhase.PRE_OPEN
        if REGULAR_START <= t <= REGULAR_END:
            return SessionPhase.REGULAR
        if REGULAR_END < t <= POST_CLOSE_END:
            return SessionPhase.POST_CLOSE
        return SessionPhase.CLOSED

    def is_market_open(self, ts: datetime) -> bool:
        return self.phase(ts) == SessionPhase.REGULAR
