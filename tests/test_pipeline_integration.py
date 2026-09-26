from datetime import datetime, timedelta, timezone

from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from app.orchestration.pipeline import MonitoringPipeline
from alerts.telegram.formatter import format_alert

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


def test_pipeline_produces_explainable_alerts_without_any_llm():
    # A steady 59-bar climb, then a sharp final-bar jump with a volume spike —
    # should trip a PRICE event, a VOLUME event, and a BREAKOUT pattern.
    closes = [100 + i * 0.3 for i in range(59)] + [140.0]
    volumes = [1000] * 59 + [6000]
    bars = _bars(closes, volumes)
    as_of = bars[-1].timestamp

    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5, timestamp=as_of, source="test"
    )

    pipeline = MonitoringPipeline()
    alerts = pipeline.evaluate(
        instrument=INSTRUMENT,
        bars=bars,
        market_index=market_index,
        sector_index=None,
        as_of=as_of,
    )

    assert len(alerts) > 0
    # Every alert must be explainable: non-empty body and, if any risk exists, it's named.
    for alert in alerts:
        assert alert.body_lines or alert.title
        message = format_alert(alert)
        assert "guaranteed outcome" in message

    # Firing the same evaluation again immediately should be suppressed by cooldown.
    alerts_again = pipeline.evaluate(
        instrument=INSTRUMENT,
        bars=bars,
        market_index=market_index,
        sector_index=None,
        as_of=as_of + timedelta(seconds=1),
    )
    assert len(alerts_again) == 0
