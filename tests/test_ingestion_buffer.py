from datetime import datetime, timedelta, timezone

from app.domain.market import DataQuality, Instrument, Quote
from data.ingestion.buffer import IngestResult, TickIngestionBuffer

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _quote(ts: datetime, ingestion_ts: datetime | None = None) -> Quote:
    return Quote(
        instrument=INSTRUMENT,
        ltp=100.0,
        bid=99.5,
        ask=100.5,
        timestamp=ts,
        source="test",
        ingestion_timestamp=ingestion_ts or ts,
    )


def test_accepts_first_tick():
    buf = TickIngestionBuffer()
    now = datetime.now(timezone.utc)
    outcome = buf.ingest_quote(_quote(now), now)
    assert outcome.result == IngestResult.ACCEPTED


def test_duplicate_timestamp_rejected():
    buf = TickIngestionBuffer()
    now = datetime.now(timezone.utc)
    buf.ingest_quote(_quote(now), now)
    outcome = buf.ingest_quote(_quote(now), now)
    assert outcome.result == IngestResult.DUPLICATE


def test_out_of_order_tick_rejected():
    buf = TickIngestionBuffer()
    now = datetime.now(timezone.utc)
    buf.ingest_quote(_quote(now), now)
    older = now - timedelta(seconds=5)
    outcome = buf.ingest_quote(_quote(older), now)
    assert outcome.result == IngestResult.OUT_OF_ORDER


def test_stale_tick_flagged_not_dropped_silently():
    buf = TickIngestionBuffer(stale_after=timedelta(seconds=10))
    now = datetime.now(timezone.utc)
    old_tick_ts = now - timedelta(seconds=30)
    outcome = buf.ingest_quote(_quote(old_tick_ts), now)
    assert outcome.result == IngestResult.STALE
    assert outcome.quote is not None
    assert outcome.quote.data_quality == DataQuality.STALE


def test_feed_stale_when_no_recent_ticks():
    buf = TickIngestionBuffer()
    now = datetime.now(timezone.utc)
    buf.ingest_quote(_quote(now), now)
    later = now + timedelta(minutes=5)
    assert buf.is_feed_stale("NSE:XYZ", later, timedelta(minutes=1)) is True
    assert buf.is_feed_stale("NSE:XYZ", now, timedelta(minutes=1)) is False


def test_feed_stale_for_unknown_instrument():
    buf = TickIngestionBuffer()
    now = datetime.now(timezone.utc)
    assert buf.is_feed_stale("NSE:UNKNOWN", now, timedelta(minutes=1)) is True


def test_now_must_be_timezone_aware():
    import pytest

    buf = TickIngestionBuffer()
    with pytest.raises(ValueError):
        buf.ingest_quote(_quote(datetime.now(timezone.utc)), datetime.now())
