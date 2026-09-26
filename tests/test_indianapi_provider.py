from datetime import datetime, timezone

import pytest

from app.domain.market import Instrument
from data.providers.indianapi_provider import IndianApiError, IndianApiMarketDataProvider

INSTRUMENT = Instrument(symbol="TCS", exchange="NSE")
NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_stream_quotes_yields_parsed_quote_then_stops_on_cancel():
    async def transport(path, params):
        assert path == "/stock"
        assert params == {"name": "TCS"}
        return {"currentPrice": {"NSE": "4123.50", "BSE": "4122.00"}}

    provider = IndianApiMarketDataProvider(transport, poll_interval_seconds=0.01, clock=lambda: NOW)
    gen = provider.stream_quotes([INSTRUMENT])
    quote = await gen.__anext__()
    assert quote.ltp == 4123.50
    assert quote.instrument.symbol == "TCS"
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_quotes_falls_back_to_any_available_price():
    async def transport(path, params):
        return {"currentPrice": {"BSE": "100.0"}}  # NSE missing

    instrument = Instrument(symbol="XYZ", exchange="NSE")
    provider = IndianApiMarketDataProvider(transport, poll_interval_seconds=0.01, clock=lambda: NOW)
    gen = provider.stream_quotes([instrument])
    quote = await gen.__anext__()
    assert quote.ltp == 100.0
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_quotes_raises_indianapi_error_on_transport_failure():
    async def transport(path, params):
        raise ConnectionError("down")

    provider = IndianApiMarketDataProvider(transport, poll_interval_seconds=0.01, clock=lambda: NOW)
    gen = provider.stream_quotes([INSTRUMENT])
    with pytest.raises(IndianApiError):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_get_recent_bars_parses_price_dataset():
    async def transport(path, params):
        assert path == "/historical_data"
        return {
            "datasets": [
                {
                    "metric": "Price",
                    "values": [["2026-09-20", "100.0"], ["2026-09-21", "105.0"]],
                }
            ]
        }

    provider = IndianApiMarketDataProvider(transport, clock=lambda: NOW)
    bars = await provider.get_recent_bars(INSTRUMENT, "1d", count=2)
    assert len(bars) == 2
    assert bars[-1].close == 105.0


@pytest.mark.asyncio
async def test_get_recent_bars_returns_empty_without_price_dataset():
    async def transport(path, params):
        return {"datasets": []}

    provider = IndianApiMarketDataProvider(transport, clock=lambda: NOW)
    bars = await provider.get_recent_bars(INSTRUMENT, "1d", count=5)
    assert bars == []


@pytest.mark.asyncio
async def test_health_ok_when_transport_succeeds():
    async def transport(path, params):
        return {}

    provider = IndianApiMarketDataProvider(transport)
    health = await provider.health()
    assert health["status"] == "OK"


@pytest.mark.asyncio
async def test_health_down_when_transport_fails():
    async def transport(path, params):
        raise ConnectionError("down")

    provider = IndianApiMarketDataProvider(transport)
    health = await provider.health()
    assert health["status"] == "DOWN"
