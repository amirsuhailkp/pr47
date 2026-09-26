from datetime import datetime, timezone

from app.domain.market import Instrument
from app.domain.patterns import AlertRecord, Severity
from alerts.telegram.formatter import format_alert


def test_format_alert_includes_disclaimer_and_risks():
    alert = AlertRecord(
        dedup_key="XYZ:PATTERN:BREAKOUT",
        severity=Severity.IMPORTANT,
        instrument=Instrument(symbol="XYZ", exchange="NSE"),
        created_at=datetime.now(timezone.utc),
        title="BREAKOUT pattern detected",
        body_lines=["breakout_distance_pct=1.20", "relative_volume=2.50x"],
        risks=["failed breakout", "declining volume"],
    )
    text = format_alert(alert)
    assert "XYZ — NSE" in text
    assert "BREAKOUT pattern detected" in text
    assert "failed breakout" in text
    assert "This is market analysis, not a guaranteed outcome." in text
