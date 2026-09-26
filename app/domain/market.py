"""Canonical, provider-independent market data models.

Every record that represents a market fact carries symbol, exchange, a timezone-aware
timestamp, source, ingestion_timestamp, and a data_quality flag. Consumers must check
data_quality before treating a record as current — see docs/DATA_MODEL.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DataQuality(str, Enum):
    OK = "OK"
    STALE = "STALE"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"


def _require_aware(ts: datetime, field_name: str) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime")


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    lot_size: int = 1
    is_active: bool = True


@dataclass(frozen=True)
class Quote:
    instrument: Instrument
    ltp: float
    bid: float | None
    ask: float | None
    timestamp: datetime
    source: str
    ingestion_timestamp: datetime
    data_quality: DataQuality = DataQuality.OK

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")
        _require_aware(self.ingestion_timestamp, "ingestion_timestamp")


@dataclass(frozen=True)
class Trade:
    instrument: Instrument
    price: float
    quantity: int
    timestamp: datetime
    source: str
    ingestion_timestamp: datetime

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")
        _require_aware(self.ingestion_timestamp, "ingestion_timestamp")


@dataclass(frozen=True)
class OHLCVBar:
    instrument: Instrument
    interval: str  # e.g. "1m", "5m", "1d"
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime  # bar start
    source: str
    ingestion_timestamp: datetime
    is_partial: bool = False
    data_quality: DataQuality = DataQuality.OK

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")
        _require_aware(self.ingestion_timestamp, "ingestion_timestamp")


@dataclass(frozen=True)
class VolumeStatistics:
    instrument: Instrument
    avg_volume: float
    relative_volume: float
    volume_acceleration: float
    as_of: datetime

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")


@dataclass(frozen=True)
class IndexSnapshot:
    code: str  # e.g. "NIFTY50", "NIFTY_IT"
    value: float
    change: float
    change_pct: float
    timestamp: datetime
    source: str

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")


@dataclass(frozen=True)
class CandidateEvidence:
    instrument: Instrument
    generated_at: datetime
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    historical_reference: str | None = None
    news_references: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_aware(self.generated_at, "generated_at")
        if not self.reasons:
            raise ValueError("CandidateEvidence requires at least one reason — no blind scoring")
