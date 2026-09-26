"""IndianAPI.in adapter for MarketDataProvider (docs/PROJECT_PLAN.md — temporary
testing setup before a broker account with true WebSocket streaming is wired in).

IndianAPI.in (https://stock.indianapi.in) is a REST API, not a WebSocket feed, so
`stream_quotes` here is a polling loop, not a true push stream. That's an explicit,
documented limitation of this adapter — swapping in a real broker's WebSocket-based
MarketDataProvider later requires no change to any caller, since both implement the
same interface.

Network access is abstracted behind an injectable `transport` (same pattern as
intelligence/llm/providers.py and alerts/telegram/notifier.py) so this is fully
unit-tested with no API key and no network call.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.domain.market import DataQuality, Instrument, OHLCVBar, Quote
from app.domain.providers import MarketDataProvider

Transport = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""transport(path, query_params) -> parsed JSON response body."""


class IndianApiError(Exception):
    pass


def httpx_transport(api_key: str, base_url: str = "https://stock.indianapi.in") -> Transport:
    """Production transport: a real GET against IndianAPI.in. Not exercised in tests
    (this repo's test network doesn't include stock.indianapi.in) — only imports
    httpx lazily so the module stays importable without it during testing."""

    async def _transport(path: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}{path}", params=params, headers={"x-api-key": api_key}
            )
            response.raise_for_status()
            return response.json()

    return _transport


class IndianApiMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        transport: Transport,
        poll_interval_seconds: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._transport = transport
        self._poll_interval = poll_interval_seconds
        self._clock = clock

    async def stream_quotes(self, instruments: list[Instrument]) -> AsyncIterator[Quote]:
        """Polls /stock?name=<symbol> for each instrument on a fixed interval. This
        is a documented stand-in for real push streaming — see module docstring."""
        while True:
            for instrument in instruments:
                try:
                    data = await self._transport("/stock", {"name": instrument.symbol})
                except Exception as exc:  # noqa: BLE001 — provider errors, never fabricate a quote
                    raise IndianApiError(str(exc)) from exc

                quote = self._parse_quote(instrument, data)
                if quote is not None:
                    yield quote
            await asyncio.sleep(self._poll_interval)

    def _parse_quote(self, instrument: Instrument, data: dict[str, Any]) -> Quote | None:
        current_price = data.get("currentPrice", {})
        price = current_price.get(instrument.exchange.upper()[:3])  # "NSE" or "BSE"
        if price is None:
            price = current_price.get("NSE") or current_price.get("BSE")
        if price is None:
            return None

        now = self._clock()
        return Quote(
            instrument=instrument,
            ltp=float(price),
            bid=None,
            ask=None,
            timestamp=now,
            source="indianapi",
            ingestion_timestamp=now,
            data_quality=DataQuality.OK,
        )

    async def get_recent_bars(
        self, instrument: Instrument, interval: str, count: int
    ) -> list[OHLCVBar]:
        period_map = {"1d": "1m", "5d": "6m", "1y": "1yr"}
        period = period_map.get(interval, "1m")
        try:
            data = await self._transport(
                "/historical_data",
                {"stock_name": instrument.symbol, "period": period, "filter": "price"},
            )
        except Exception as exc:  # noqa: BLE001
            raise IndianApiError(str(exc)) from exc

        bars: list[OHLCVBar] = []
        price_series = next(
            (d for d in data.get("datasets", []) if d.get("metric") == "Price"), None
        )
        if price_series is None:
            return []

        now = self._clock()
        for entry in price_series.get("values", [])[-count:]:
            date_str, close_str = entry[0], entry[1]
            close = float(close_str)
            ts = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            bars.append(
                OHLCVBar(
                    instrument=instrument,
                    interval=interval,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=0,  # IndianAPI's price dataset doesn't carry volume per-point
                    timestamp=ts,
                    source="indianapi",
                    ingestion_timestamp=now,
                )
            )
        return bars

    async def health(self) -> dict[str, Any]:
        try:
            await self._transport("/trending", {})
            return {"provider": "indianapi", "status": "OK"}
        except Exception as exc:  # noqa: BLE001
            return {"provider": "indianapi", "status": "DOWN", "detail": str(exc)}
