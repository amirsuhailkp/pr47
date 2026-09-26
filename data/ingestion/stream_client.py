"""Reconnecting real-time stream client.

Wraps a MarketDataProvider's stream_quotes() with reconnection, exponential backoff,
and heartbeat/staleness monitoring via TickIngestionBuffer. Provider errors never
propagate as fabricated data — on failure we retry the connection, we never invent a
quote (docs/ARCHITECTURE.md §8, §48).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument, Quote
from app.domain.providers import MarketDataProvider
from app.services.logging_setup import get_logger
from data.ingestion.buffer import IngestResult, TickIngestionBuffer

logger = get_logger(__name__)


class ReconnectingStreamClient:
    def __init__(
        self,
        provider: MarketDataProvider,
        instruments: list[Instrument],
        buffer: TickIngestionBuffer | None = None,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._instruments = instruments
        self._buffer = buffer or TickIngestionBuffer()
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def run(self, on_quote: Callable[[Quote], None]) -> AsyncIterator[None]:
        """Runs forever, reconnecting with exponential backoff on failure.

        Intended to be driven as a background task; callers can cancel it to stop.
        `on_quote` is called only for ACCEPTED ticks — duplicates, out-of-order and
        stale ticks are logged and dropped, never handed to analytics as current.
        """
        backoff = self._initial_backoff
        while True:
            try:
                self._connected = True
                async for quote in self._provider.stream_quotes(self._instruments):
                    now = self._clock()
                    outcome = self._buffer.ingest_quote(quote, now)
                    if outcome.result == IngestResult.ACCEPTED and outcome.quote is not None:
                        on_quote(outcome.quote)
                    elif outcome.result != IngestResult.ACCEPTED:
                        logger.info(
                            "tick_dropped",
                            result=outcome.result,
                            symbol=quote.instrument.symbol,
                        )
                    backoff = self._initial_backoff  # reset after any successful tick
                    yield
            except asyncio.CancelledError:
                self._connected = False
                raise
            except Exception as exc:  # noqa: BLE001 - provider errors must not crash the process
                self._connected = False
                logger.warning("stream_error", error=str(exc), backoff_seconds=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)

    def feed_is_stale(self, instrument: Instrument, max_silence: timedelta) -> bool:
        key = f"{instrument.exchange}:{instrument.symbol}"
        return self._buffer.is_feed_stale(key, self._clock(), max_silence)
