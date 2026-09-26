"""Historical/outcome domain models — see docs/DATA_MODEL.md §Historical objects.

Nothing here is reduced to a single predictive percentage: outcomes are stored per
horizon and summarized as distributions, never collapsed to one number.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market import Instrument


def _require_aware(ts: datetime, field_name: str) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware, got naive datetime")


@dataclass(frozen=True)
class DatasetManifest:
    """Required metadata for any stored historical dataset — docs/DATA_MODEL.md
    'datasets without a manifest are invalid and must not be used.'"""

    dataset_version: str
    source: str
    created_at: datetime
    date_range_start: datetime
    date_range_end: datetime
    universe_definition: str
    feature_schema: tuple[str, ...]
    label_definition: str
    configuration_snapshot: str  # serialized config used to build this dataset

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        _require_aware(self.date_range_start, "date_range_start")
        _require_aware(self.date_range_end, "date_range_end")
        if self.date_range_start > self.date_range_end:
            raise ValueError("date_range_start must not be after date_range_end")

    def content_hash(self) -> str:
        payload = {
            "dataset_version": self.dataset_version,
            "source": self.source,
            "date_range_start": self.date_range_start.isoformat(),
            "date_range_end": self.date_range_end.isoformat(),
            "universe_definition": self.universe_definition,
            "feature_schema": list(self.feature_schema),
            "label_definition": self.label_definition,
            "configuration_snapshot": self.configuration_snapshot,
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class HistoricalSetup:
    """One stored historical situation — enough to reproduce it (docs §21)."""

    instrument: Instrument
    timestamp: datetime
    price: float
    volume: int
    relative_volume: float | None
    volatility: float | None
    trend: str | None  # e.g. "uptrend", "downtrend", "sideways"
    rsi: float | None
    vwap: float | None
    market_state: str | None
    sector_state: str | None
    pattern: str | None
    event_context: str | None
    dataset_version: str
    features: dict[str, float] = field(default_factory=dict)  # for similarity search


@dataclass(frozen=True)
class OutcomeRecord:
    """Forward outcome for one HistoricalSetup at one horizon (docs §21)."""

    setup: HistoricalSetup
    horizon: str  # "5m" | "15m" | "30m" | "1h" | "1d" | "3d" | "5d" | "10d" | "20d"
    return_pct: float
    max_favorable_excursion_pct: float
    max_adverse_excursion_pct: float
    realized_volatility: float | None
    market_regime_at_horizon: str | None


@dataclass(frozen=True)
class HorizonSummary:
    horizon: str
    sample_size: int
    median_return_pct: float | None
    mean_return_pct: float | None
    positive_frequency: float | None
    negative_frequency: float | None
    return_distribution: tuple[float, ...]  # sorted returns, for percentile lookups
    mean_max_favorable_excursion_pct: float | None
    mean_max_adverse_excursion_pct: float | None
    return_volatility: float | None
    regime_breakdown: dict[str, int] = field(default_factory=dict)
    uncertainty_note: str = ""


@dataclass(frozen=True)
class HistoricalSummary:
    """Full multi-horizon outcome summary for a setup criteria — never a single
    predictive percentage (docs §21)."""

    setup_criteria: str
    sample_size: int
    horizons: dict[str, HorizonSummary] = field(default_factory=dict)
