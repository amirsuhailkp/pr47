from datetime import datetime, timezone

from app.domain.history import HistoricalSetup, OutcomeRecord
from app.domain.market import Instrument
from history.statistics.summary import percentile, summarize, summarize_horizon

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


def _setup() -> HistoricalSetup:
    return HistoricalSetup(
        instrument=INSTRUMENT, timestamp=datetime.now(timezone.utc), price=100.0, volume=1000,
        relative_volume=1.5, volatility=0.02, trend="uptrend", rsi=60.0, vwap=99.0,
        market_state=None, sector_state=None, pattern="MOMENTUM", event_context=None,
        dataset_version="v1",
    )


def _outcome(return_pct: float, regime: str = "RISK_ON") -> OutcomeRecord:
    return OutcomeRecord(
        setup=_setup(), horizon="5d", return_pct=return_pct,
        max_favorable_excursion_pct=abs(return_pct) + 1, max_adverse_excursion_pct=-1.0,
        realized_volatility=1.0, market_regime_at_horizon=regime,
    )


def test_summarize_horizon_empty_reports_insufficient_evidence():
    summary = summarize_horizon("5d", [])
    assert summary.sample_size == 0
    assert "insufficient evidence" in summary.uncertainty_note.lower()


def test_summarize_horizon_small_sample_flagged():
    outcomes = [_outcome(1.0), _outcome(-2.0)]
    summary = summarize_horizon("5d", outcomes)
    assert summary.sample_size == 2
    assert "Small sample size" in summary.uncertainty_note


def test_summarize_horizon_large_sample_no_warning():
    outcomes = [_outcome(float(i % 5 - 2)) for i in range(40)]
    summary = summarize_horizon("5d", outcomes)
    assert summary.uncertainty_note == ""


def test_summarize_horizon_stats_correctness():
    outcomes = [_outcome(2.0), _outcome(-1.0), _outcome(4.0)]
    summary = summarize_horizon("5d", outcomes)
    assert summary.positive_frequency == 2 / 3
    assert summary.negative_frequency == 1 / 3
    assert summary.median_return_pct == 2.0
    assert round(summary.mean_return_pct, 4) == round((2.0 - 1.0 + 4.0) / 3, 4)


def test_regime_breakdown_counts_each_regime():
    outcomes = [_outcome(1.0, "RISK_ON"), _outcome(-1.0, "RISK_OFF"), _outcome(0.5, "RISK_ON")]
    summary = summarize_horizon("5d", outcomes)
    assert summary.regime_breakdown == {"RISK_ON": 2, "RISK_OFF": 1}


def test_summarize_never_collapses_to_one_number():
    outcomes_by_horizon = {"5d": [_outcome(1.0), _outcome(-1.0)], "10d": [_outcome(3.0)]}
    result = summarize("momentum breakout setup", outcomes_by_horizon)
    assert set(result.horizons.keys()) == {"5d", "10d"}
    assert len(result.horizons["5d"].return_distribution) == 2


def test_percentile_basic():
    dist = (1.0, 2.0, 3.0, 4.0, 5.0)
    assert percentile(dist, 0) == 1.0
    assert percentile(dist, 100) == 5.0
    assert percentile(dist, 50) == 3.0


def test_percentile_empty_is_none():
    assert percentile((), 50) is None
