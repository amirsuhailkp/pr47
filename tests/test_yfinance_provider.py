from datetime import datetime, timezone

import pytest

from app.domain.market import Instrument
from data.providers.yfinance_provider import (
    YFinanceError,
    YFinanceHistoricalProvider,
    to_yahoo_symbol,
)

INSTRUMENT = Instrument(symbol="TCS", exchange="NSE")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 10, tzinfo=timezone.utc)


def test_to_yahoo_symbol_nse_suffix():
    assert to_yahoo_symbol(Instrument(symbol="TCS", exchange="NSE")) == "TCS.NS"


def test_to_yahoo_symbol_bse_suffix():
    assert to_yahoo_symbol(Instrument(symbol="TCS", exchange="BSE")) == "TCS.BO"


def test_to_yahoo_symbol_index_ticker_has_no_suffix():
    assert to_yahoo_symbol(Instrument(symbol="^NSEI", exchange="NSE")) == "^NSEI"


@pytest.mark.asyncio
async def test_get_bars_converts_raw_rows_to_ohlcv_bars():
    async def fetch_fn(symbol, start, end, interval):
        assert symbol == "TCS.NS"
        assert interval == "1d"
        return [
            {
                "timestamp": datetime(2026, 1, 2),
                "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 12345,
            }
        ]

    provider = YFinanceHistoricalProvider(fetch_fn)
    bars = await provider.get_bars(INSTRUMENT, "1d", START, END)
    assert len(bars) == 1
    assert bars[0].close == 104.0
    assert bars[0].timestamp.tzinfo is not None  # naive timestamps get UTC attached
    assert bars[0].source == "yfinance"


@pytest.mark.asyncio
async def test_get_bars_raises_on_unsupported_interval():
    provider = YFinanceHistoricalProvider(lambda *a: [])
    with pytest.raises(ValueError):
        await provider.get_bars(INSTRUMENT, "42d", START, END)


@pytest.mark.asyncio
async def test_get_bars_wraps_fetch_failures():
    async def failing_fetch(symbol, start, end, interval):
        raise ConnectionError("no internet")

    provider = YFinanceHistoricalProvider(failing_fetch)
    with pytest.raises(YFinanceError):
        await provider.get_bars(INSTRUMENT, "1d", START, END)
