"""docs/ALERT_ARCHITECTURE.md / docs §48: 'If Telegram fails: queue alert, retry.'

A minimal in-memory retry queue. Durable persistence for pending deliveries across
process restarts is the AlertRepository's `undelivered()` query (data/storage) — this
queue handles in-process retry/backoff; a restart re-seeds it from that query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class PendingDelivery:
    alert_row_id: int
    payload: dict
    attempts: int = 0
    next_attempt_at: datetime | None = None


@dataclass
class DeliveryQueue:
    base_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 300.0
    max_attempts: int = 5
    _pending: dict[int, PendingDelivery] = field(default_factory=dict)

    def enqueue(self, alert_row_id: int, payload: dict) -> None:
        self._pending[alert_row_id] = PendingDelivery(alert_row_id=alert_row_id, payload=payload)

    def due(self, now: datetime) -> list[PendingDelivery]:
        return [
            d for d in self._pending.values()
            if d.next_attempt_at is None or d.next_attempt_at <= now
        ]

    def record_success(self, alert_row_id: int) -> None:
        self._pending.pop(alert_row_id, None)

    def record_failure(self, alert_row_id: int, now: datetime) -> bool:
        """Returns True if the item will be retried, False if it's given up (max
        attempts exhausted — the caller should surface this as a delivery failure)."""
        delivery = self._pending.get(alert_row_id)
        if delivery is None:
            return False
        delivery.attempts += 1
        if delivery.attempts >= self.max_attempts:
            self._pending.pop(alert_row_id, None)
            return False
        backoff = min(
            self.base_backoff_seconds * (2 ** (delivery.attempts - 1)), self.max_backoff_seconds
        )
        delivery.next_attempt_at = now + timedelta(seconds=backoff)
        return True

    def pending_count(self) -> int:
        return len(self._pending)
