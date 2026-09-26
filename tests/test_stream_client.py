import asyncio
from datetime import datetime, timezone

import pytest

from app.domain.market import Instrument, Quote
from app.domain.providers import MarketDataProvider
from data.ingestion.stream_client import ReconnectingStreamClient

INSTRUMENT = Instrument(symbol="XYZ", exchange="NSE")


class FlakyProvider(MarketDataProvider):
    """Fails once, then streams two quotes, then stops (raises StopAsyncIteration)."""

    def __init__(self) -> None:
        self.attempts = 0

    async def stream_quotes(self, instruments):
        self.attempts += 1
        if self.attempts == 1:
            raise ConnectionError("simulated drop")
        for i in range(2):
            yield Quote(
                instrument=INSTRUMENT,
                ltp=100.0 + i,
                bid=99.5,
                ask=100.5,
                timestamp=datetime.now(timezone.utc),
                source="test",
                ingestion_timestamp=datetime.now(timezone.utc),
            )
        raise StopAsyncIteration

    async def get_recent_bars(self, instrument, interval, count):
        return []

    async def health(self):
        return {"status": "OK"}


@pytest.mark.asyncio
async def test_stream_client_recovers_from_initial_failure_and_delivers_quotes():
    provider = FlakyProvider()
    client = ReconnectingStreamClient(
        provider, [INSTRUMENT], initial_backoff=0.01, max_backoff=0.05
    )
    received: list[Quote] = []

    async def drive():
        async for _ in client.run(lambda q: received.append(q)):
            if len(received) >= 2:
                return

    await asyncio.wait_for(drive(), timeout=2.0)

    assert provider.attempts == 2  # first attempt failed, second succeeded
    assert len(received) == 2
