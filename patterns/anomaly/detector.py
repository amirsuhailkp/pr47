"""ML anomaly detection, wired into the live pipeline — the ANOMALY family that
app/domain/patterns.py's PatternFamily comment already flagged as planned but never
built, and the reason ml/models/anomaly/ existed with no caller anywhere outside its
own tests.

Design choice: this fits a fresh AnomalyModel (ml/models/anomaly/model.py — the same
tested class, unmodified) on each symbol's own trailing bars, on every check, instead
of loading one offline-trained global model from the registry. That's deliberate, not
a shortcut dressed up as one:

- It's genuinely free to run continuously — no network call, pure arithmetic over
  bars you already backfilled for pattern/event detection.
- It adapts per symbol: a 3% move is unremarkable for a volatile small-cap but very
  unusual for a stable large-cap. A fixed global threshold (patterns/momentum,
  patterns/engine/events.py) can't tell the difference; this does, because it's
  scored against that stock's own recent behavior.
- The full offline training pipeline (ml/training/train_anomaly.py) needs labeled
  forward-return outcomes from history/outcomes — a real dataset that doesn't exist
  yet for this project. This online-fit approach is the honest interim: real ML,
  running for real, without inventing a training dataset that isn't there.

Swap in a registry-promoted model later (ml/registry/) without changing this module's
public function signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.market import Instrument, OHLCVBar
from app.domain.patterns import EventCategory, MarketEvent, Severity
from ml.models.anomaly.model import AnomalyModel

FEATURE_SCHEMA: tuple[str, ...] = ("bar_return_pct", "volume")


@dataclass(frozen=True)
class AnomalyThresholds:
    min_training_bars: int = 30
    """Below this many prior bars, there's not enough history to fit a meaningful
    per-symbol baseline — the detector stays quiet rather than guess."""
    watch_z: float = 2.5
    important_z: float = 3.5
    critical_z: float = 5.0


def bar_features(prev_close: float, bar: OHLCVBar) -> dict[str, float]:
    """Public so ml/training/anomaly_trainer_job.py builds training examples with the
    exact same feature definition the live detector scores against — a mismatch here
    would silently make a trained model meaningless at inference time."""
    bar_return_pct = ((bar.close - prev_close) / prev_close * 100.0) if prev_close else 0.0
    return {"bar_return_pct": bar_return_pct, "volume": float(bar.volume)}


def _severity_for(z: float, thresholds: AnomalyThresholds) -> Severity | None:
    if z >= thresholds.critical_z:
        return Severity.CRITICAL
    if z >= thresholds.important_z:
        return Severity.IMPORTANT
    if z >= thresholds.watch_z:
        return Severity.WATCH
    return None


def detect_anomaly_event(
    instrument: Instrument,
    bars: list[OHLCVBar],
    as_of: datetime,
    thresholds: AnomalyThresholds = AnomalyThresholds(),
    production_model: AnomalyModel | None = None,
) -> MarketEvent | None:
    """Scores the latest bar for anomalousness and returns a MarketEvent if the
    combined z-score clears `watch_z`. Returns None quietly (not an error) when there
    isn't enough history yet, or when nothing is unusual — this is a supplementary
    signal that should never be noisier than the deterministic detectors it sits
    alongside.

    `production_model` is the model ml/training/anomaly_trainer_job.py trained and
    validated offline against real historical outcomes, loaded via
    ml/registry/persistence.py once one has been trained and promoted. When given, it
    is used directly (only 2 bars needed, for the latest return/volume features) and
    is more statistically grounded than the fallback below. When None — no training
    has happened yet, or the trained model didn't beat its baseline — this falls back
    to fitting a fresh AnomalyModel on this call's own trailing bars, so the detector
    still works correctly with zero setup, just with a weaker (untested) baseline.
    """
    if production_model is not None:
        if len(bars) < 2:
            return None
        latest_features = bar_features(bars[-2].close, bars[-1])
        score = production_model.score(latest_features)
        return _event_from_score(instrument, score, as_of, thresholds)

    if len(bars) < thresholds.min_training_bars + 1:
        return None

    training_bars = bars[:-1]
    training_features = [
        bar_features(training_bars[i - 1].close, training_bars[i])
        for i in range(1, len(training_bars))
    ]
    if len(training_features) < thresholds.min_training_bars - 1:
        return None

    model = AnomalyModel.fit(training_features, FEATURE_SCHEMA)
    latest_features = bar_features(bars[-2].close, bars[-1])
    score = model.score(latest_features)
    return _event_from_score(instrument, score, as_of, thresholds)


def _event_from_score(
    instrument: Instrument, score, as_of: datetime, thresholds: AnomalyThresholds
) -> MarketEvent | None:
    severity = _severity_for(score.combined_z, thresholds)
    if severity is None:
        return None

    contributors = ", ".join(f"{name}={z:+.2f}" for name, z in score.top_contributors())
    return MarketEvent(
        category=EventCategory.TECHNICAL,
        instrument=instrument,
        detected_at=as_of,
        description=(
            f"ML anomaly: {instrument.symbol}'s latest bar is unusual versus its own "
            f"recent history (combined z-score={score.combined_z:.2f})"
        ),
        severity=severity,
        source_signals=[f"anomaly model z-scores: {contributors}"],
    )
