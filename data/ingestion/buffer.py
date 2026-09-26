"""Real-time ingestion buffer.

Pure, synchronous logic for the concerns docs/ARCHITECTURE.md §8 calls out: duplicate
messages, out-of-order messages, and stale data. Deliberately separated from the
actual WebSocket connection handling (see stream_client.py) so it can be unit tested
without a network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.market import DataQuality, Quote


class IngestResult:
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    STALE = "STALE"


@dataclass
class IngestOutcome:
    result: str
    quote: Quote | None


@dataclass
class _InstrumentState:
    last_timestamp: datetime | None = None
    last_ingestion_timestamp: datetime | None = None


@dataclass
class TickIngestionBuffer:
    """Tracks per-instrument last-seen timestamps to dedup and reorder-guard ticks,
    and flags data as stale once it's older than `stale_after` relative to `now`.
    """

    stale_after: timedelta = field(default_factory=lambda: timedelta(seconds=10))
    _state: dict[str, _InstrumentState] = field(default_factory=dict)

    def ingest_quote(self, quote: Quote, now: datetime) -> IngestOutcome:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        key = f"{quote.instrument.exchange}:{quote.instrument.symbol}"
        state = self._state.setdefault(key, _InstrumentState())

        # Staleness: how old is this tick relative to "now"?
        if now - quote.timestamp > self.stale_after:
            stale_quote = _with_quality(quote, DataQuality.STALE)
            return IngestOutcome(IngestResult.STALE, stale_quote)

        if state.last_timestamp is not None:
            if quote.timestamp == state.last_timestamp:
                return IngestOutcome(IngestResult.DUPLICATE, None)
            if quote.timestamp < state.last_timestamp:
                return IngestOutcome(IngestResult.OUT_OF_ORDER, None)

        state.last_timestamp = quote.timestamp
        state.last_ingestion_timestamp = now
        return IngestOutcome(IngestResult.ACCEPTED, quote)

    def is_feed_stale(self, instrument_key: str, now: datetime, max_silence: timedelta) -> bool:
        """True if we haven't accepted a tick for this instrument recently enough —
        used to mark the feed unhealthy rather than silently reusing an old quote."""
        state = self._state.get(instrument_key)
        if state is None or state.last_ingestion_timestamp is None:
            return True
        return now - state.last_ingestion_timestamp > max_silence


def _with_quality(quote: Quote, quality: DataQuality) -> Quote:
    return Quote(
        instrument=quote.instrument,
        ltp=quote.ltp,
        bid=quote.bid,
        ask=quote.ask,
        timestamp=quote.timestamp,
        source=quote.source,
        ingestion_timestamp=quote.ingestion_timestamp,
        data_quality=quality,
    )
