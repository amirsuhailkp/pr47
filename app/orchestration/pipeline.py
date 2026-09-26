"""Deterministic + ML monitoring pipeline for one instrument, one point in time.

This is the Phase 2 backbone of docs/ARCHITECTURE.md §3:
  bars -> analytics snapshot -> events + patterns + ML anomaly -> alert engine ->
  formatted alerts

Still no LLM involved (that's Phase 4/intelligence/, invoked separately in
app/orchestration/realtime_service.py only for alerts this layer already produced) —
this must produce useful, explainable Telegram-ready alerts entirely on its own, per
docs/LLM_ARCHITECTURE.md's deterministic fallback requirement. The ML anomaly detector
(patterns/anomaly/detector.py) is part of that "on its own" guarantee: it's a local
z-score model, not a network call, so it costs nothing to run on every check.
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
from ml.models.anomaly.model import AnomalyModel
from ml.registry.persistence import load_production_anomaly_model
from patterns.anomaly.detector import AnomalyThresholds, detect_anomaly_event
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
    not a separate hidden default).

    Also loads a trained, promoted anomaly model from disk if
    scripts/train_anomaly_model.py has produced one (ml/registry/persistence.py) —
    silently falls back to the online-fit detector if none exists yet."""
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
    loaded = load_production_anomaly_model()
    production_anomaly_model = loaded[0] if loaded is not None else None
    return MonitoringPipeline(
        alert_engine=alert_engine,
        pattern_engine=pattern_engine,
        production_anomaly_model=production_anomaly_model,
    )


@dataclass
class MonitoringPipeline:
    """Stateful only in its cooldown tracker — everything else per call is pure."""

    alert_engine: AlertEngine = field(
        default_factory=lambda: AlertEngine(CooldownTracker(cooldown_seconds=900))
    )
    pattern_engine: PatternEngine = field(default_factory=default_pattern_engine)
    anomaly_thresholds: AnomalyThresholds = field(default_factory=AnomalyThresholds)
    production_anomaly_model: AnomalyModel | None = None
    """An AnomalyModel loaded via ml/registry/persistence.py once
    scripts/train_anomaly_model.py has trained and promoted one. None (the default)
    means: no training has happened yet, so detect_anomaly_event() falls back to
    fitting fresh on each call's own trailing bars — see that function's docstring."""

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

        anomaly_event = detect_anomaly_event(
            instrument, bars, as_of, self.anomaly_thresholds, self.production_anomaly_model
        )
        if anomaly_event is not None:
            alert = self.alert_engine.process_event(anomaly_event, as_of)
            if alert is not None:
                alerts.append(alert)

        for pattern in self.pattern_engine.run(instrument, snapshot, context, as_of):
            severity = classify_pattern_severity(pattern)
            risks = [] if pattern.confirmed else ["pattern not confirmed by volume/market"]
            alert = self.alert_engine.process_pattern(pattern, severity, risks, as_of)
            if alert is not None:
                alerts.append(alert)

        return alerts
