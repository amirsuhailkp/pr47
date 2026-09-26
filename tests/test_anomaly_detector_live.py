"""Proves patterns/anomaly/detector.py — the piece that finally puts ml/models/anomaly/
to real use in the live pipeline — actually functions: quiet on ordinary/insufficient
data, fires with a real severity and explainable signals on a genuine outlier bar.
"""
from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument, OHLCVBar
from app.domain.patterns import EventCategory, Severity
from patterns.anomaly.detector import AnomalyThresholds, detect_anomaly_event

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _bars(closes: list[float], volumes: list[int]) -> list[OHLCVBar]:
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
        out.append(
            OHLCVBar(
                instrument=INSTRUMENT, interval="1m", open=c, high=c * 1.01, low=c * 0.99,
                close=c, volume=v, timestamp=ts, source="test", ingestion_timestamp=ts,
            )
        )
    return out


def test_returns_none_with_insufficient_history():
    bars = _bars([100.0] * 10, [1000] * 10)
    as_of = bars[-1].timestamp
    assert detect_anomaly_event(INSTRUMENT, bars, as_of) is None


def test_stays_quiet_on_ordinary_flat_data():
    # Perfectly flat closes/volumes -> zero variance -> per_feature_z is empty for
    # bar_return_pct/volume (std=0 keys are skipped by AnomalyModel.score), so this
    # must never false-positive on genuinely boring data.
    bars = _bars([100.0] * 40, [1000] * 40)
    as_of = bars[-1].timestamp
    assert detect_anomaly_event(INSTRUMENT, bars, as_of) is None


def test_fires_on_a_genuine_outlier_bar():
    # 39 quiet bars with small realistic jitter, then one huge price+volume spike.
    closes = [100.0 + (0.05 if i % 2 == 0 else -0.05) for i in range(39)] + [130.0]
    volumes = [1000 + (10 if i % 2 == 0 else -10) for i in range(39)] + [50000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp

    event = detect_anomaly_event(INSTRUMENT, bars, as_of)

    assert event is not None
    assert event.category == EventCategory.TECHNICAL
    assert event.severity in (Severity.WATCH, Severity.IMPORTANT, Severity.CRITICAL)
    assert event.instrument == INSTRUMENT
    assert event.source_signals  # never an unexplained event (domain model enforces this too)
    assert "z-score" in event.source_signals[0] or "z=" in event.source_signals[0]


def test_thresholds_control_sensitivity():
    closes = [100.0 + (0.05 if i % 2 == 0 else -0.05) for i in range(39)] + [104.0]
    volumes = [1000] * 40
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp

    lenient = detect_anomaly_event(
        INSTRUMENT, bars, as_of,
        AnomalyThresholds(watch_z=100.0, important_z=100.0, critical_z=100.0),
    )
    assert lenient is None  # nothing clears an absurdly high bar on every tier

    strict = detect_anomaly_event(INSTRUMENT, bars, as_of, AnomalyThresholds(watch_z=0.01))
    assert strict is not None  # nearly everything clears an absurdly low bar
