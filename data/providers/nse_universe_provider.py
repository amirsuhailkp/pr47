"""NSE full equity list — free, official, no API key (docs §3, §20: the universe the
Candidate Discovery Engine scans, before any price/liquidity filtering).

This is the actual exchange-wide symbol list, not a hand-picked sample. SME stocks are
already excluded — they trade on NSE's separate SME/EMERGE platform, not in this file.
`SERIES` filters out trade-to-trade and other restricted series, keeping normal `EQ`
main-board equities.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Awaitable, Callable

from app.domain.market import Instrument

FetchCsv = Callable[[str], Awaitable[str]]
"""fetch_csv(url) -> raw CSV text."""

NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

DEFAULT_ALLOWED_SERIES = frozenset({"EQ"})


class NseUniverseError(Exception):
    pass


async def httpx_fetch_csv(url: str) -> str:
    """Production transport — NSE requires a browser-like User-Agent or it rejects
    the request. Not exercised in tests (nsearchives.nseindia.com isn't in this
    repo's test network allowlist); imports httpx lazily."""
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text


def parse_equity_csv(
    csv_text: str, allowed_series: frozenset[str] = DEFAULT_ALLOWED_SERIES
) -> list[Instrument]:
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise NseUniverseError("empty equity list response")

    header = [h.strip().upper() for h in rows[0]]
    try:
        symbol_idx = header.index("SYMBOL")
        series_idx = header.index("SERIES")
    except ValueError as exc:
        raise NseUniverseError(f"unexpected CSV header: {header}") from exc

    instruments: list[Instrument] = []
    for row in rows[1:]:
        if len(row) <= max(symbol_idx, series_idx):
            continue
        series = row[series_idx].strip()
        if series not in allowed_series:
            continue
        symbol = row[symbol_idx].strip()
        if not symbol:
            continue
        instruments.append(Instrument(symbol=symbol, exchange="NSE"))
    return instruments


class NseUniverseProvider:
    def __init__(
        self,
        fetch_csv: FetchCsv,
        url: str = NSE_EQUITY_LIST_URL,
        allowed_series: frozenset[str] = DEFAULT_ALLOWED_SERIES,
    ) -> None:
        self._fetch_csv = fetch_csv
        self._url = url
        self._allowed_series = allowed_series

    async def get_universe(self) -> list[Instrument]:
        try:
            csv_text = await self._fetch_csv(self._url)
        except Exception as exc:  # noqa: BLE001
            raise NseUniverseError(str(exc)) from exc
        return parse_equity_csv(csv_text, self._allowed_series)
