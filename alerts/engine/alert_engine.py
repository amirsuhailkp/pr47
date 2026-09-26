"""Alert engine — severity gate, dedup/cooldown, and assembly into AlertRecord.

Not every event or pattern reaches Telegram; only what clears the configured
minimum severity and isn't currently in cooldown for its dedup key.
"""
from __future__ import annotations

from datetime import datetime

from app.domain.market import Instrument
from app.domain.patterns import AlertRecord, DetectedPattern, MarketEvent, Severity
from alerts.deduplication.tracker import CooldownTracker, build_dedup_key

_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.WATCH: 1,
    Severity.IMPORTANT: 2,
    Severity.CRITICAL: 3,
}


class AlertEngine:
    def __init__(
        self,
        cooldown_tracker: CooldownTracker,
        min_severity: Severity = Severity.WATCH,
    ) -> None:
        self._cooldown = cooldown_tracker
        self._min_severity = min_severity

    def _passes_severity_gate(self, severity: Severity) -> bool:
        return _SEVERITY_ORDER[severity] >= _SEVERITY_ORDER[self._min_severity]

    def process_event(self, event: MarketEvent, now: datetime) -> AlertRecord | None:
        if not self._passes_severity_gate(event.severity):
            return None
        dedup_key = build_dedup_key(event.instrument.symbol, event.category.value)
        if self._cooldown.is_in_cooldown(dedup_key, now):
            return None

        self._cooldown.record_fired(dedup_key, now)
        return AlertRecord(
            dedup_key=dedup_key,
            severity=event.severity,
            instrument=event.instrument,
            created_at=now,
            title=event.description,
            body_lines=list(event.source_signals),
            cooldown_until=self._cooldown.cooldown_until(dedup_key),
        )

    def process_pattern(
        self,
        pattern: DetectedPattern,
        severity: Severity,
        risks: list[str],
        now: datetime,
    ) -> AlertRecord | None:
        if not self._passes_severity_gate(severity):
            return None
        dedup_key = build_dedup_key(
            pattern.instrument.symbol, "PATTERN", pattern.family.value
        )
        if self._cooldown.is_in_cooldown(dedup_key, now):
            return None

        self._cooldown.record_fired(dedup_key, now)
        return AlertRecord(
            dedup_key=dedup_key,
            severity=severity,
            instrument=pattern.instrument,
            created_at=now,
            title=f"{pattern.family.value} pattern detected",
            body_lines=list(pattern.supporting_evidence),
            risks=risks,
            cooldown_until=self._cooldown.cooldown_until(dedup_key),
        )


def classify_pattern_severity(pattern: DetectedPattern) -> Severity:
    """Confirmed patterns (market/volume-confirmed) are IMPORTANT; unconfirmed ones
    are only WATCH-worthy — surfaced, but flagged as lower confidence."""
    return Severity.IMPORTANT if pattern.confirmed else Severity.WATCH
