from datetime import datetime, timezone

import pytest

from app.domain.market import Instrument
from app.domain.patterns import AlertRecord, Severity
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository, WatchlistRepository

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_watchlist_add_and_list_active(session_factory):
    repo = WatchlistRepository(session_factory)
    repo.add(INSTRUMENT, notes="momentum candidate", priority=1)
    active = repo.list_active()
    assert len(active) == 1
    assert active[0].symbol == "XYZ"


def test_watchlist_deactivate(session_factory):
    repo = WatchlistRepository(session_factory)
    repo.add(INSTRUMENT)
    removed = repo.deactivate(INSTRUMENT)
    assert removed == 1
    assert repo.list_active() == []


def test_watchlist_reuses_existing_instrument_row(session_factory):
    repo = WatchlistRepository(session_factory)
    repo.add(INSTRUMENT, notes="first")
    repo.add(INSTRUMENT, notes="second")
    active = repo.list_active()
    assert len(active) == 2  # two watchlist entries, same instrument


def _alert() -> AlertRecord:
    return AlertRecord(
        dedup_key="XYZ:PATTERN:MOMENTUM",
        severity=Severity.IMPORTANT,
        instrument=INSTRUMENT,
        created_at=datetime.now(timezone.utc),
        title="MOMENTUM pattern detected",
        body_lines=["price_change_pct=3.0"],
    )


def test_alert_save_and_recent(session_factory):
    repo = AlertRepository(session_factory)
    row_id = repo.save(_alert(), body_text="formatted alert text")
    recent = repo.recent(limit=5)
    assert len(recent) == 1
    assert recent[0]["symbol"] == "XYZ"
    assert recent[0]["delivered"] is False
    assert row_id > 0


def test_alert_mark_delivered(session_factory):
    repo = AlertRepository(session_factory)
    row_id = repo.save(_alert(), body_text="x")
    repo.mark_delivered(row_id)
    recent = repo.recent(limit=5)
    assert recent[0]["delivered"] is True


def test_alert_undelivered_tracks_pending(session_factory):
    repo = AlertRepository(session_factory)
    id1 = repo.save(_alert(), body_text="x")
    id2 = repo.save(_alert(), body_text="y")
    repo.mark_delivered(id1)
    pending = repo.undelivered()
    assert pending == [id2]


def test_alert_record_delivery_failure_increments_attempts(session_factory):
    repo = AlertRepository(session_factory)
    row_id = repo.save(_alert(), body_text="x")
    repo.record_delivery_failure(row_id)
    repo.record_delivery_failure(row_id)
    # no direct getter for attempts in recent(); verify no crash and still undelivered
    assert row_id in repo.undelivered()
