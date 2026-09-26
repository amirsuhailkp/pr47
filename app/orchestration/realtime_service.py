"""The real-time service (docs/ARCHITECTURE.md §5 / AZURE_DEPLOYMENT.md §1).

Ties together: MonitoringPipeline (Phase 2) -> AlertRepository (persist) ->
TelegramNotifier + DeliveryQueue (deliver, retry on failure). This is the concrete
wiring that closes the "real-time service" gap noted at the end of Phase 2/4.

Deliberately does not import Azure or any vendor SDK — it depends only on the
provider interfaces and repositories, per docs/ARCHITECTURE.md's provider isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market import IndexSnapshot, Instrument, OHLCVBar, VolumeStatistics
from app.orchestration.pipeline import MonitoringPipeline
from alerts.telegram.delivery_queue import DeliveryQueue
from alerts.telegram.formatter import format_alert
from alerts.telegram.notifier import TelegramNotifier, TelegramSendError
from data.storage.repositories import AlertRepository


@dataclass
class RealTimeService:
    pipeline: MonitoringPipeline
    alert_repository: AlertRepository
    notifier: TelegramNotifier
    delivery_queue: DeliveryQueue

    async def handle_update(
        self,
        instrument: Instrument,
        bars: list[OHLCVBar],
        market_index: IndexSnapshot,
        sector_index: IndexSnapshot | None,
        as_of: datetime,
        volume_stats: VolumeStatistics | None = None,
    ) -> list[int]:
        """Evaluates the pipeline for one instrument's latest bars, persists any
        resulting alerts, and attempts immediate delivery (queuing on failure).
        Returns the row ids of any alerts produced, for tests/observability."""
        alerts = self.pipeline.evaluate(
            instrument=instrument,
            bars=bars,
            market_index=market_index,
            sector_index=sector_index,
            as_of=as_of,
            volume_stats=volume_stats,
        )

        row_ids: list[int] = []
        for alert in alerts:
            text = format_alert(alert)
            row_id = self.alert_repository.save(alert, text)
            row_ids.append(row_id)
            await self._attempt_delivery(row_id, text, as_of)

        return row_ids

    async def _attempt_delivery(self, row_id: int, text: str, now: datetime) -> None:
        try:
            await self.notifier.send({"text": text})
        except TelegramSendError:
            self.delivery_queue.enqueue(row_id, {"text": text})
            self.alert_repository.record_delivery_failure(row_id)
            return
        self.alert_repository.mark_delivered(row_id)

    async def retry_pending_deliveries(self, now: datetime) -> None:
        """Called periodically to retry queued deliveries — docs §48 'queue alert,
        retry' rather than dropping a failed Telegram send."""
        for delivery in self.delivery_queue.due(now):
            try:
                await self.notifier.send(delivery.payload)
            except TelegramSendError:
                self.delivery_queue.record_failure(delivery.alert_row_id, now)
                self.alert_repository.record_delivery_failure(delivery.alert_row_id)
                continue
            self.delivery_queue.record_success(delivery.alert_row_id)
            self.alert_repository.mark_delivered(delivery.alert_row_id)
