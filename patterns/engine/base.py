"""Extensible pattern engine.

Adding a new pattern family means implementing PatternDetector and registering it —
it must not require touching existing detectors or the engine itself (docs/PROJECT_PLAN.md
§14 "adding a new pattern should not require rewriting the entire system").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.market import Instrument
from app.domain.patterns import DetectedPattern
from market.analytics.context import MarketContext
from market.analytics.price_volume import PriceVolumeSnapshot


class PatternDetector(ABC):
    """One detector = one pattern family. Stateless, deterministic, explainable."""

    family_name: str

    @abstractmethod
    def detect(
        self,
        instrument: Instrument,
        snapshot: PriceVolumeSnapshot,
        context: MarketContext,
        as_of: datetime,
    ) -> DetectedPattern | None:
        """Return a DetectedPattern with non-empty supporting_evidence, or None."""


class PatternEngine:
    """Runs every registered detector against a snapshot and collects the matches."""

    def __init__(self, detectors: list[PatternDetector] | None = None) -> None:
        self._detectors: list[PatternDetector] = list(detectors or [])

    def register(self, detector: PatternDetector) -> None:
        self._detectors.append(detector)

    def run(
        self,
        instrument: Instrument,
        snapshot: PriceVolumeSnapshot,
        context: MarketContext,
        as_of: datetime,
    ) -> list[DetectedPattern]:
        results: list[DetectedPattern] = []
        for detector in self._detectors:
            pattern = detector.detect(instrument, snapshot, context, as_of)
            if pattern is not None:
                results.append(pattern)
        return results
