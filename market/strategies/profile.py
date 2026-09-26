"""StrategyProfile — the operational half of a strategy: what the descriptive
StrategyDefinition (app/domain/strategy.py) actually means in terms of bar interval,
pattern thresholds, and alert cadence. Kept separate from the definition so the
human-readable hypothesis/limitations text never silently drifts from what the code
actually does — changing a threshold means touching the profile, not prose.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.patterns import Severity
from app.domain.strategy import StrategyDefinition
from patterns.breakout.detector import BreakoutThresholds
from patterns.momentum.detector import MomentumThresholds
from patterns.pullback.detector import PullbackThresholds


@dataclass(frozen=True)
class StrategyProfile:
    definition: StrategyDefinition
    bar_interval: str  # e.g. "5m" for scalping, "1d" for swing
    lookback_days: int  # how much history to backfill before evaluating
    momentum_thresholds: MomentumThresholds
    breakout_thresholds: BreakoutThresholds
    pullback_thresholds: PullbackThresholds
    alert_cooldown_seconds: int
    min_alert_severity: Severity
