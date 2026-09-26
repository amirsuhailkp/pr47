"""Pattern, event and alert domain models — see docs/DATA_MODEL.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.domain.market import Instrument


def _require_aware(ts: datetime, field_name: str) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime")


class PatternFamily(str, Enum):
    MOMENTUM = "MOMENTUM"
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    # Future families (docs/PROJECT_PLAN.md Phase 2+/ spec §14): REVERSAL, BREAKDOWN,
    # MEAN_REVERSION, VOLATILITY_EXPANSION, GAP, RELATIVE_STRENGTH_DIVERGENCE,
    # EVENT_DRIVEN, ANOMALY.


class Severity(str, Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class EventCategory(str, Enum):
    PRICE = "PRICE"
    VOLUME = "VOLUME"
    TECHNICAL = "TECHNICAL"
    NEWS = "NEWS"
    MARKET = "MARKET"


@dataclass(frozen=True)
class DetectedPattern:
    family: PatternFamily
    instrument: Instrument
    timestamp: datetime
    supporting_evidence: list[str] = field(default_factory=list)
    confirmed: bool = False
    market_context_note: str | None = None
    sector_context_note: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")
        if not self.supporting_evidence:
            raise ValueError("DetectedPattern requires supporting_evidence — no unexplained patterns")


@dataclass(frozen=True)
class MarketEvent:
    category: EventCategory
    instrument: Instrument
    detected_at: datetime
    description: str
    severity: Severity
    source_signals: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_aware(self.detected_at, "detected_at")
        if not self.source_signals:
            raise ValueError("MarketEvent requires source_signals — no unexplained events")


@dataclass(frozen=True)
class AlertRecord:
    dedup_key: str
    severity: Severity
    instrument: Instrument
    created_at: datetime
    title: str
    body_lines: list[str]
    risks: list[str] = field(default_factory=list)
    cooldown_until: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if self.cooldown_until is not None:
            _require_aware(self.cooldown_until, "cooldown_until")
