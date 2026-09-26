from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import MarketSettings
from app.domain.market import IndexSnapshot
from data.providers.nse_universe_provider import NseUniverseProvider
from data.providers.yfinance_provider import YFinanceHistoricalProvider
from market.strategies.swing import SWING_PROFILE
from opportunity.discovery.engine import CandidateDiscoveryEngine
from opportunity.ranking.rank import rank_candidates

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

SAMPLE_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "MOVER,Mover Limited,EQ,25-AUG-2004,1,1,INE467B01029,1\n"
    "QUIET,Quiet Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
)


def _bars_for(symbol: str):
    if symbol == "MOVER":
        closes = [100 + i * 0.2 for i in range(59)] + [140.0]
        volumes = [200000] * 59 + [1200000]
    else:
        closes = [100.0 + (i % 3) * 0.1 for i in range(60)]
        volumes = [200000] * 60
    return [
        {"timestamp": BASE + timedelta(days=i), "open": c, "high": c * 1.01, "low": c * 0.99,
         "close": c, "volume": v}
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


@pytest.mark.asyncio
async def test_full_discovery_pipeline_universe_to_ranked_candidates():
    async def fetch_csv(url):
        return SAMPLE_CSV

    async def fetch_bars(symbol_yahoo, start, end, interval):
        return _bars_for(symbol_yahoo.replace(".NS", ""))

    universe_provider = NseUniverseProvider(fetch_csv)
    instruments = await universe_provider.get_universe()
    assert {i.symbol for i in instruments} == {"MOVER", "QUIET"}

    historical_provider = YFinanceHistoricalProvider(fetch_bars)
    engine = CandidateDiscoveryEngine(historical_provider, MarketSettings(MIN_HISTORY_DAYS=30))
    market_index = IndexSnapshot(
        code="NIFTY50", value=20000, change=100, change_pct=0.5,
        timestamp=BASE + timedelta(days=59), source="test",
    )

    result = await engine.discover(
        instruments, SWING_PROFILE, market_index, BASE + timedelta(days=59), BASE
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].instrument.symbol == "MOVER"

    ranked = rank_candidates(result.candidates)
    assert ranked[0].evidence.instrument.symbol == "MOVER"
    assert ranked[0].score.contributions["reason_count"] > 0
