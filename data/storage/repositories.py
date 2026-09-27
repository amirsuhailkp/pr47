"""Repositories — the only place that translates between domain objects
(app/domain/*) and ORM rows (data/storage/models.py). Business logic never imports
SQLAlchemy directly.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.domain.market import Instrument
from app.domain.patterns import AlertRecord
from data.storage.database import session_scope
from data.storage.models import AlertRow, InstrumentRow, WatchlistEntryRow


class WatchlistRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, instrument: Instrument, notes: str | None = None, priority: int = 0) -> None:
        with session_scope(self._session_factory) as session:
            row = (
                session.query(InstrumentRow)
                .filter_by(symbol=instrument.symbol, exchange=instrument.exchange)
                .one_or_none()
            )
            if row is None:
                row = InstrumentRow(symbol=instrument.symbol, exchange=instrument.exchange)
                session.add(row)
                session.flush()

            session.add(
                WatchlistEntryRow(instrument_id=row.id, notes=notes, priority=priority, active=True)
            )

    def list_active(self) -> list[Instrument]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(WatchlistEntryRow)
                .filter_by(active=True)
                .join(InstrumentRow)
                .all()
            )
            return [
                Instrument(symbol=r.instrument.symbol, exchange=r.instrument.exchange) for r in rows
            ]

    def deactivate(self, instrument: Instrument) -> int:
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(WatchlistEntryRow)
                .join(InstrumentRow)
                .filter(
                    InstrumentRow.symbol == instrument.symbol,
                    InstrumentRow.exchange == instrument.exchange,
                    WatchlistEntryRow.active == True,  # noqa: E712
                )
                .all()
            )
            for row in rows:
                row.active = False
            return len(rows)


class AlertRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, alert: AlertRecord, body_text: str) -> int:
        with session_scope(self._session_factory) as session:
            row = AlertRow(
                dedup_key=alert.dedup_key,
                severity=alert.severity.value,
                symbol=alert.instrument.symbol,
                exchange=alert.instrument.exchange,
                title=alert.title,
                body=body_text,
                created_at=alert.created_at,
                delivered=False,
                delivery_attempts=0,
            )
            session.add(row)
            session.flush()
            return row.id

    def mark_delivered(self, alert_row_id: int) -> None:
        with session_scope(self._session_factory) as session:
            row = session.get(AlertRow, alert_row_id)
            if row is not None:
                row.delivered = True
                row.delivery_attempts += 1

    def record_delivery_failure(self, alert_row_id: int) -> None:
        with session_scope(self._session_factory) as session:
            row = session.get(AlertRow, alert_row_id)
            if row is not None:
                row.delivery_attempts += 1

    def recent(self, limit: int = 20) -> list[dict]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(AlertRow).order_by(AlertRow.created_at.desc()).limit(limit).all()
            )
            return [
                {
                    "symbol": r.symbol,
                    "severity": r.severity,
                    "title": r.title,
                    "delivered": r.delivered,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def for_symbol(self, symbol: str, limit: int = 20) -> list[dict]:
        """Alert history for one instrument, most recent first — powers the
        dashboard's per-stock page. `body` already contains any LLM commentary that
        was appended at alert time (app/orchestration/realtime_service.py), so this
        is read-only: it never calls an LLM itself."""
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(AlertRow)
                .filter_by(symbol=symbol)
                .order_by(AlertRow.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "severity": r.severity,
                    "title": r.title,
                    "body": r.body,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def undelivered(self) -> list[int]:
        with session_scope(self._session_factory) as session:
            rows = session.query(AlertRow.id).filter_by(delivered=False).all()
            return [r.id for r in rows]
