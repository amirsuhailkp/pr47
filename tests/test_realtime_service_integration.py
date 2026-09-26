from datetime import datetime, timedelta, timezone

import pytest

from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from app.orchestration.pipeline import MonitoringPipeline
from app.orchestration.realtime_service import RealTimeService
from alerts.telegram.delivery_queue import DeliveryQueue
from alerts.telegram.notifier import TelegramNotifier
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _bars(closes, volumes):
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
        out.append(
            OHLCVBar(
                instrument=INSTRUMENT, interval="1m", open=c, high=c * 1.01, low=c * 0.99,
                close=c, volume=v, timestamp=ts, source="test", ingestion_timestamp=ts,
            )
        )
    return out


def _service(transport):
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)
    repo = AlertRepository(session_factory)
    notifier = TelegramNotifier(bot_token="tok", chat_id="1", transport=transport)
    return RealTimeService(
        pipeline=MonitoringPipeline(),
        alert_repository=repo,
        notifier=notifier,
        delivery_queue=DeliveryQueue(base_backoff_seconds=1.0),
    ), repo


@pytest.mark.asyncio
async def test_alert_persisted_and_delivered_on_success():
    async def transport(chat_id, body):
        return {"ok": True}

    service, repo = _service(transport)
    closes = [100 + i * 0.3 for i in range(59)] + [140.0]
    volumes = [1000] * 59 + [6000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5, timestamp=as_of, source="test"
    )

    row_ids = await service.handle_update(INSTRUMENT, bars, market_index, None, as_of)
    assert len(row_ids) > 0
    recent = repo.recent(limit=10)
    assert all(r["delivered"] for r in recent)


@pytest.mark.asyncio
async def test_alert_queued_and_retried_after_delivery_failure():
    attempts = {"count": 0}

    async def flaky_transport(chat_id, body):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return {"ok": False, "description": "temporary failure"}
        return {"ok": True}

    service, repo = _service(flaky_transport)
    closes = [100 + i * 0.3 for i in range(59)] + [140.0]
    volumes = [1000] * 59 + [6000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5, timestamp=as_of, source="test"
    )

    row_ids = await service.handle_update(INSTRUMENT, bars, market_index, None, as_of)
    assert service.delivery_queue.pending_count() == 1
    undelivered_before = repo.undelivered()
    assert row_ids[0] in undelivered_before

    # Retry after the backoff window — the flaky transport now succeeds.
    later = as_of + timedelta(seconds=5)
    await service.retry_pending_deliveries(later)

    assert service.delivery_queue.pending_count() == 0
    assert repo.undelivered() == []
