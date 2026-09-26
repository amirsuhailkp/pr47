from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument, OHLCVBar, VolumeStatistics
from market.analytics.price_volume import build_snapshot, price_change_pct, volume_acceleration


def _bars(closes: list[float], volumes: list[int]) -> list[OHLCVBar]:
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        ts = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i)
        out.append(
            OHLCVBar(
                instrument=Instrument(symbol="XYZ", exchange="NSE"),
                interval="1m",
                open=c,
                high=c * 1.01,
                low=c * 0.99,
                close=c,
                volume=v,
                timestamp=ts,
                source="test",
                ingestion_timestamp=ts,
            )
        )
    return out


def test_price_change_pct():
    bars = _bars([100, 105], [1000, 1000])
    assert round(price_change_pct(bars), 2) == 5.0


def test_volume_acceleration_needs_lookback_plus_one():
    assert volume_acceleration([100, 100, 100], lookback=5) is None
    accel = volume_acceleration([100, 100, 100, 100, 100, 500], lookback=5)
    assert accel == 5.0


def test_build_snapshot_smoke():
    closes = [100 + i for i in range(59)] + [200]  # sharp final jump clears prior resistance
    volumes = [1000] * 59 + [5000]
    bars = _bars(closes, volumes)
    vol_stats = VolumeStatistics(
        instrument=bars[-1].instrument,
        avg_volume=1000,
        relative_volume=5.0,
        volume_acceleration=5.0,
        as_of=bars[-1].timestamp,
    )
    snap = build_snapshot(bars, vol_stats)
    assert snap.price == closes[-1]
    assert snap.relative_volume == 5.0
    assert snap.sma_20 is not None
    assert snap.sma_50 is not None
    assert snap.rsi_14 == 100.0  # strictly increasing closes
    assert snap.breakout_distance_pct is not None and snap.breakout_distance_pct > 0
