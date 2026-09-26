from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument
from app.domain.patterns import EventCategory, MarketEvent, Severity
from alerts.deduplication.tracker import CooldownTracker, build_dedup_key
from alerts.engine.alert_engine import AlertEngine, classify_pattern_severity
from app.domain.patterns import DetectedPattern, PatternFamily

NOW = datetime.now(timezone.utc)
INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _event(severity: Severity) -> MarketEvent:
    return MarketEvent(
        category=EventCategory.PRICE,
        instrument=INSTRUMENT,
        detected_at=NOW,
        description="Rapid price increase",
        severity=severity,
        source_signals=["price_change_pct=4.0"],
    )


def test_cooldown_tracker_blocks_within_window():
    tracker = CooldownTracker(cooldown_seconds=60)
    key = build_dedup_key("XYZ", "PRICE")
    assert tracker.is_in_cooldown(key, NOW) is False
    tracker.record_fired(key, NOW)
    assert tracker.is_in_cooldown(key, NOW + timedelta(seconds=30)) is True
    assert tracker.is_in_cooldown(key, NOW + timedelta(seconds=61)) is False


def test_alert_engine_severity_gate():
    engine = AlertEngine(CooldownTracker(60), min_severity=Severity.IMPORTANT)
    assert engine.process_event(_event(Severity.WATCH), NOW) is None
    alert = engine.process_event(_event(Severity.IMPORTANT), NOW)
    assert alert is not None
    assert alert.severity == Severity.IMPORTANT


def test_alert_engine_dedup_suppresses_repeat_within_cooldown():
    engine = AlertEngine(CooldownTracker(60), min_severity=Severity.WATCH)
    first = engine.process_event(_event(Severity.WATCH), NOW)
    assert first is not None
    second = engine.process_event(_event(Severity.WATCH), NOW + timedelta(seconds=10))
    assert second is None
    third = engine.process_event(_event(Severity.WATCH), NOW + timedelta(seconds=61))
    assert third is not None


def test_classify_pattern_severity():
    confirmed = DetectedPattern(
        family=PatternFamily.MOMENTUM, instrument=INSTRUMENT, timestamp=NOW,
        supporting_evidence=["x"], confirmed=True,
    )
    unconfirmed = DetectedPattern(
        family=PatternFamily.MOMENTUM, instrument=INSTRUMENT, timestamp=NOW,
        supporting_evidence=["x"], confirmed=False,
    )
    assert classify_pattern_severity(confirmed) == Severity.IMPORTANT
    assert classify_pattern_severity(unconfirmed) == Severity.WATCH


def test_alert_engine_process_pattern_includes_risks():
    engine = AlertEngine(CooldownTracker(60), min_severity=Severity.WATCH)
    pattern = DetectedPattern(
        family=PatternFamily.BREAKOUT, instrument=INSTRUMENT, timestamp=NOW,
        supporting_evidence=["breakout_distance_pct=1.0"], confirmed=False,
    )
    alert = engine.process_pattern(
        pattern, Severity.WATCH, risks=["low volume confirmation"], now=NOW
    )
    assert alert is not None
    assert alert.risks == ["low volume confirmation"]
