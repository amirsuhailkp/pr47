"""Deterministic monitoring pipeline for one instrument, one point in time.

This is the Phase 2 backbone of docs/ARCHITECTURE.md §3:
  bars -> analytics snapshot -> events + patterns -> alert engine -> formatted alerts

No LLM involved (that's Phase 4/intelligence/) — this must produce useful, explainable
Telegram-ready alerts entirely on its own, per docs/LLM_ARCHITECTURE.md's deterministic
fallback requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market import IndexSnapshot, Instrument, OHLCVBar, VolumeStatistics
from app.domain.patterns import AlertRecord
from alerts.deduplication.tracker import CooldownTracker
from alerts.engine.alert_engine import AlertEngine, classify_pattern_severity
from market.analytics.context import MarketContext, build_context
from market.analytics.price_volume import PriceVolumeSnapshot, build_snapshot
from market.strategies.profile import StrategyProfile
from patterns.breakout.detector import BreakoutDetector
from patterns.engine.base import PatternEngine
from patterns.engine.events import detect_all_events
from patterns.momentum.detector import MomentumDetector
from patterns.pullback.detector import PullbackDetector


def default_pattern_engine() -> PatternEngine:
    return PatternEngine([MomentumDetector(), BreakoutDetector(), PullbackDetector()])


def build_pipeline_from_profile(profile: StrategyProfile) -> "MonitoringPipeline":
    """Builds a MonitoringPipeline whose detectors and cooldown match the given
    strategy profile (docs §24 — a strategy's thresholds are part of its definition,
    not a separate hidden default)."""
    pattern_engine = PatternEngine(
        [
            MomentumDetector(profile.momentum_thresholds),
            BreakoutDetector(profile.breakout_thresholds),
            PullbackDetector(profile.pullback_thresholds),
        ]
    )
    alert_engine = AlertEngine(
        CooldownTracker(cooldown_seconds=profile.alert_cooldown_seconds),
        min_severity=profile.min_alert_severity,
    )
    return MonitoringPipeline(alert_engine=alert_engine, pattern_engine=pattern_engine)


@dataclass
class MonitoringPipeline:
    """Stateful only in its cooldown tracker — everything else per call is pure."""

    alert_engine: AlertEngine = field(
        default_factory=lambda: AlertEngine(CooldownTracker(cooldown_seconds=900))
    )
    pattern_engine: PatternEngine = field(default_factory=default_pattern_engine)

    def evaluate(
        self,
        instrument: Instrument,
        bars: list[OHLCVBar],
        market_index: IndexSnapshot,
        sector_index: IndexSnapshot | None,
        as_of: datetime,
        volume_stats: VolumeStatistics | None = None,
        market_volatility: float | None = None,
    ) -> list[AlertRecord]:
        snapshot: PriceVolumeSnapshot = build_snapshot(bars, volume_stats)
        context: MarketContext = build_context(
            stock_change_pct=snapshot.price_change_pct or 0.0,
            market_index=market_index,
            sector_index=sector_index,
            market_volatility=market_volatility,
        )

        alerts: list[AlertRecord] = []

        for event in detect_all_events(instrument, snapshot, context, as_of):
            alert = self.alert_engine.process_event(event, as_of)
            if alert is not None:
                alerts.append(alert)

        for pattern in self.pattern_engine.run(instrument, snapshot, context, as_of):
            severity = classify_pattern_severity(pattern)
            risks = [] if pattern.confirmed else ["pattern not confirmed by volume/market"]
            alert = self.alert_engine.process_pattern(pattern, severity, risks, as_of)
            if alert is not None:
                alerts.append(alert)

        return alerts
