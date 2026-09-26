"""yfinance-backed HistoricalDataProvider — free, no API key, used for backfilling
history/ datasets during testing (docs/PROJECT_PLAN.md temporary-setup note).

yfinance is synchronous and blocking, so the real fetch function runs it in a thread
via asyncio.to_thread. As with the other provider adapters, the actual data fetch is
behind an injectable `fetch_fn` so this is unit-tested without network access or the
yfinance package needing to succeed against a live Yahoo endpoint.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.domain.market import Instrument, OHLCVBar
from app.domain.providers import HistoricalDataProvider

FetchFn = Callable[[str, datetime, datetime, str], Awaitable[list[dict[str, Any]]]]
"""fetch_fn(yahoo_symbol, start, end, yf_interval) -> list of raw bar dicts with
keys: timestamp (datetime), open, high, low, close, volume."""


class YFinanceError(Exception):
    pass


_INTERVAL_TO_YF = {"1d": "1d", "1h": "60m", "15m": "15m", "5m": "5m", "1m": "1m"}


def to_yahoo_symbol(instrument: Instrument) -> str:
    if instrument.symbol.startswith("^"):
        return instrument.symbol  # index tickers (e.g. ^NSEI) have no exchange suffix on Yahoo
    suffix = ".NS" if instrument.exchange.upper() == "NSE" else ".BO"
    return f"{instrument.symbol}{suffix}"


async def yfinance_fetch(
    yahoo_symbol: str, start: datetime, end: datetime, yf_interval: str
) -> list[dict[str, Any]]:
    """Production fetch function — wraps the blocking yfinance call in a thread.
    Not exercised in tests (Yahoo Finance's endpoint isn't in this repo's test
    network allowlist); only imports yfinance lazily so the module stays importable
    without it installed."""

    def _blocking_fetch() -> list[dict[str, Any]]:
        import yfinance as yf

        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(start=start, end=end, interval=yf_interval)
        return [
            {
                "timestamp": index.to_pydatetime(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
            for index, row in df.iterrows()
        ]

    return await asyncio.to_thread(_blocking_fetch)


class YFinanceHistoricalProvider(HistoricalDataProvider):
    def __init__(self, fetch_fn: FetchFn = yfinance_fetch) -> None:
        self._fetch_fn = fetch_fn

    async def get_bars(
        self, instrument: Instrument, interval: str, start: datetime, end: datetime
    ) -> list[OHLCVBar]:
        yf_interval = _INTERVAL_TO_YF.get(interval)
        if yf_interval is None:
            raise ValueError(f"unsupported interval for yfinance: {interval}")

        yahoo_symbol = to_yahoo_symbol(instrument)
        try:
            raw_bars = await self._fetch_fn(yahoo_symbol, start, end, yf_interval)
        except Exception as exc:  # noqa: BLE001
            raise YFinanceError(str(exc)) from exc

        now = datetime.now(timezone.utc)
        bars: list[OHLCVBar] = []
        for raw in raw_bars:
            ts = raw["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                OHLCVBar(
                    instrument=instrument,
                    interval=interval,
                    open=raw["open"],
                    high=raw["high"],
                    low=raw["low"],
                    close=raw["close"],
                    volume=raw["volume"],
                    timestamp=ts,
                    source="yfinance",
                    ingestion_timestamp=now,
                )
            )
        return bars
