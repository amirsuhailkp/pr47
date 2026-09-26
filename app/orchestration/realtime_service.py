"""The real-time service (docs/ARCHITECTURE.md §5 / AZURE_DEPLOYMENT.md §1).

Ties together: MonitoringPipeline (Phase 2, deterministic + ML) -> optional LLM
one-line enrichment (Phase 4/intelligence/) -> AlertRepository (persist) ->
TelegramNotifier + DeliveryQueue (deliver, retry on failure). This is the concrete
wiring that closes the "real-time service" gap noted at the end of Phase 2/4 — and,
until now, also the reason GROQ_API_KEYS/CEREBRAS_API_KEYS were never actually called:
intelligence/llm/router.py existed and was tested, but nothing here ever invoked it.

LLM cost control (docs' "use LLMs for interpretation... not the source of raw market
truth", and the 24/7-without-burning-tokens requirement): the router is only ever
called for an alert the deterministic pipeline + ML anomaly detector already decided
was worth sending. It is never called on a routine "nothing happened" check — that's
exactly what the free pattern/event/anomaly detectors in the pipeline are for. When it
is called, only one short line (`LLMAnalysis.summary`) is appended to the existing
deterministic message — never the full structured analysis — so an update stays a
short update, not an AI report.

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
from intelligence.llm.evidence_builder import build_evidence
from intelligence.llm.router import LLMRouter
from market.analytics.context import build_context
from market.analytics.price_volume import build_snapshot

_LLM_SUMMARY_MAX_CHARS = 220
"""Hard cap on the appended AI line — this is an update, not a report."""


@dataclass
class RealTimeService:
    pipeline: MonitoringPipeline
    alert_repository: AlertRepository
    notifier: TelegramNotifier
    delivery_queue: DeliveryQueue
    llm_router: LLMRouter | None = None
    """None means no GROQ_API_KEYS/CEREBRAS_API_KEYS configured — alerts are sent with
    their deterministic text only, exactly as before. This keeps the service usable
    with zero LLM cost, per the product vision's "LLM for interpretation, not the
    source of truth"."""

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
            if self.llm_router is not None:
                text = await self._append_llm_note(
                    instrument, bars, market_index, sector_index, as_of, volume_stats, text
                )
            row_id = self.alert_repository.save(alert, text)
            row_ids.append(row_id)
            await self._attempt_delivery(row_id, text, as_of)

        return row_ids

    async def _append_llm_note(
        self,
        instrument: Instrument,
        bars: list[OHLCVBar],
        market_index: IndexSnapshot,
        sector_index: IndexSnapshot | None,
        as_of: datetime,
        volume_stats: VolumeStatistics | None,
        text: str,
    ) -> str:
        """Best-effort: an LLM hiccup must never block a Telegram delivery that the
        deterministic pipeline already earned. Recomputes the snapshot/context/pattern
        objects the pipeline just used internally — cheap, pure, no I/O — since
        `evaluate()` intentionally still returns only `list[AlertRecord]` so every
        existing caller keeps working unchanged."""
        try:
            snapshot = build_snapshot(bars, volume_stats)
            context = build_context(
                stock_change_pct=snapshot.price_change_pct or 0.0,
                market_index=market_index,
                sector_index=sector_index,
            )
            patterns = self.pipeline.pattern_engine.run(instrument, snapshot, context, as_of)
            evidence = build_evidence(instrument, snapshot, context, patterns)

            analysis, used_llm = await self.llm_router.analyze(
                "alert_summary", evidence.to_payload()
            )
            if not used_llm or not analysis.summary:
                return text  # every provider failed -> deterministic fallback; the
                # alert text above is already the deterministic explanation, so
                # appending the fallback's echo of it would just be noise.

            summary = analysis.summary.strip()
            if len(summary) > _LLM_SUMMARY_MAX_CHARS:
                summary = summary[: _LLM_SUMMARY_MAX_CHARS - 1].rstrip() + "\u2026"
            return f"{text}\n\n\U0001f916 {summary}"
        except Exception:  # noqa: BLE001 — never let LLM enrichment block delivery
            return text

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
