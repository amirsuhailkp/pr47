from datetime import datetime, timezone

from app.domain.history import HistoricalSetup
from app.domain.market import Instrument
from history.similarity.matcher import find_similar

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _setup(rsi: float, rel_vol: float) -> HistoricalSetup:
    return HistoricalSetup(
        instrument=INSTRUMENT, timestamp=datetime.now(timezone.utc), price=100.0, volume=1000,
        relative_volume=rel_vol, volatility=0.02, trend="uptrend", rsi=rsi, vwap=99.0,
        market_state=None, sector_state=None, pattern="MOMENTUM", event_context=None,
        dataset_version="v1", features={"rsi": rsi, "relative_volume": rel_vol},
    )


def test_closest_match_ranked_first():
    query = {"rsi": 65.0, "relative_volume": 2.0}
    scales = {"rsi": 15.0, "relative_volume": 1.0}
    candidates = [
        _setup(rsi=66.0, rel_vol=2.1),   # very close
        _setup(rsi=30.0, rel_vol=0.5),   # far
        _setup(rsi=64.0, rel_vol=1.9),   # close
    ]
    matches = find_similar(query, candidates, scales, top_n=2)
    assert len(matches) == 2
    assert matches[0].distance <= matches[1].distance
    assert matches[0].setup.rsi in (66.0, 64.0)


def test_max_distance_filters_out_far_candidates():
    query = {"rsi": 65.0, "relative_volume": 2.0}
    scales = {"rsi": 15.0, "relative_volume": 1.0}
    candidates = [_setup(rsi=66.0, rel_vol=2.1), _setup(rsi=10.0, rel_vol=0.1)]
    matches = find_similar(query, candidates, scales, max_distance=0.5)
    assert len(matches) == 1


def test_no_shared_features_returns_empty():
    query = {"unrelated_feature": 1.0}
    scales = {"rsi": 15.0}
    candidates = [_setup(rsi=66.0, rel_vol=2.1)]
    assert find_similar(query, candidates, scales) == []
