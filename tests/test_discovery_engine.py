from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import MarketSettings
from app.domain.market import IndexSnapshot, Instrument
from data.providers.yfinance_provider import YFinanceHistoricalProvider
from market.strategies.swing import SWING_PROFILE
from opportunity.discovery.engine import CandidateDiscoveryEngine

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bars_for(symbol: str):
    if symbol == "GOOD":
        closes = [100 + i * 0.2 for i in range(59)] + [140.0]  # sharp final jump
        volumes = [200000] * 59 + [1200000]  # + volume spike
    elif symbol == "FLAT":
        closes = [100.0 + (i % 3) * 0.1 for i in range(60)]  # no real move
        volumes = [200000] * 60
    elif symbol == "SHORT":
        closes = [100.0] * 5
        volumes = [200000] * 5
    elif symbol == "EXPENSIVE":
        closes = [1000 + i * 2 for i in range(59)] + [1400.0]  # outside price band
        volumes = [200000] * 59 + [1200000]  # outside price band
    else:
        raise AssertionError(f"unexpected symbol {symbol}")
    return [
        {
            "timestamp": BASE + timedelta(days=i),
            "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


async def _fake_fetch(symbol_yahoo: str, start, end, interval):
    symbol = symbol_yahoo.replace(".NS", "")
    return _bars_for(symbol)


@pytest.fixture
def engine():
    provider = YFinanceHistoricalProvider(_fake_fetch)
    return CandidateDiscoveryEngine(provider, MarketSettings(MIN_HISTORY_DAYS=30))


@pytest.fixture
def market_index():
    return IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5,
        timestamp=BASE + timedelta(days=59), source="test",
    )


@pytest.mark.asyncio
async def test_discovery_finds_the_qualifying_candidate_and_skips_others(engine, market_index):
    instruments = [
        Instrument(symbol="GOOD", exchange="NSE"),
        Instrument(symbol="FLAT", exchange="NSE"),
        Instrument(symbol="SHORT", exchange="NSE"),
        Instrument(symbol="EXPENSIVE", exchange="NSE"),
    ]
    as_of = BASE + timedelta(days=59)
    start = BASE

    result = await engine.discover(instruments, SWING_PROFILE, market_index, as_of, start)

    assert result.stats.scanned == 4
    assert result.stats.insufficient_history == 1  # SHORT
    assert result.stats.failed_universe_filter == 1  # EXPENSIVE
    assert len(result.candidates) == 1
    assert result.candidates[0].instrument.symbol == "GOOD"
    assert len(result.candidates[0].reasons) > 0


@pytest.mark.asyncio
async def test_discovery_candidate_has_explainable_reasons(engine, market_index):
    instruments = [Instrument(symbol="GOOD", exchange="NSE")]
    as_of = BASE + timedelta(days=59)
    result = await engine.discover(instruments, SWING_PROFILE, market_index, as_of, BASE)
    candidate = result.candidates[0]
    assert all(isinstance(r, str) and r for r in candidate.reasons)


@pytest.mark.asyncio
async def test_discovery_respects_max_instruments(engine, market_index):
    instruments = [
        Instrument(symbol="GOOD", exchange="NSE"),
        Instrument(symbol="FLAT", exchange="NSE"),
    ]
    as_of = BASE + timedelta(days=59)
    result = await engine.discover(
        instruments, SWING_PROFILE, market_index, as_of, BASE, max_instruments=1
    )
    assert result.stats.scanned == 1


@pytest.mark.asyncio
async def test_discovery_counts_fetch_errors_without_stopping_scan():
    async def flaky_fetch(symbol_yahoo, start, end, interval):
        if "BAD" in symbol_yahoo:
            raise ConnectionError("no data")
        return _bars_for("GOOD")

    provider = YFinanceHistoricalProvider(flaky_fetch)
    engine = CandidateDiscoveryEngine(provider, MarketSettings(MIN_HISTORY_DAYS=30))
    instruments = [Instrument(symbol="BAD", exchange="NSE"), Instrument(symbol="GOOD2", exchange="NSE")]
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5,
        timestamp=BASE + timedelta(days=59), source="test",
    )
    result = await engine.discover(
        instruments, SWING_PROFILE, market_index, BASE + timedelta(days=59), BASE
    )
    assert result.stats.fetch_errors == 1
    assert len(result.candidates) == 1
