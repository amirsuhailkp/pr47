"""Deduplication and cooldown for alerts.

An in-memory store for now (Phase 2). A durable store (the operational DB) replaces
this in a later pass without changing the interface below — see docs/DATA_MODEL.md
AlertRecord and docs/ALERT_ARCHITECTURE.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def build_dedup_key(instrument_symbol: str, category: str, family: str | None = None) -> str:
    parts = [instrument_symbol, category]
    if family:
        parts.append(family)
    return ":".join(parts)


class CooldownTracker:
    def __init__(self, cooldown_seconds: int) -> None:
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._last_fired: dict[str, datetime] = {}

    def is_in_cooldown(self, dedup_key: str, now: datetime) -> bool:
        last = self._last_fired.get(dedup_key)
        if last is None:
            return False
        return now - last < self._cooldown

    def record_fired(self, dedup_key: str, now: datetime) -> None:
        self._last_fired[dedup_key] = now

    def cooldown_until(self, dedup_key: str) -> datetime | None:
        last = self._last_fired.get(dedup_key)
        if last is None:
            return None
        return last + self._cooldown
