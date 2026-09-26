"""Provider interfaces. Business logic depends on these, never on a vendor SDK directly.

Concrete adapters live under data/providers/, intelligence/llm/, and alerts/telegram/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator

from app.domain.market import Instrument, OHLCVBar, Quote


class MarketDataProvider(ABC):
    """Real-time and reference market data."""

    @abstractmethod
    async def stream_quotes(self, instruments: list[Instrument]) -> AsyncIterator[Quote]:
        ...

    @abstractmethod
    async def get_recent_bars(
        self, instrument: Instrument, interval: str, count: int
    ) -> list[OHLCVBar]:
        ...

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        ...


class HistoricalDataProvider(ABC):
    """Bulk historical bar/price data for dataset construction and backtesting."""

    @abstractmethod
    async def get_bars(
        self, instrument: Instrument, interval: str, start: datetime, end: datetime
    ) -> list[OHLCVBar]:
        ...


class NewsProvider(ABC):
    @abstractmethod
    async def get_news(self, instrument: Instrument, since: datetime) -> list[dict[str, Any]]:
        ...


class CompanyDataProvider(ABC):
    @abstractmethod
    async def get_company_profile(self, instrument: Instrument) -> dict[str, Any]:
        ...


class LLMProvider(ABC):
    """A single LLM vendor/provider. See docs/LLM_ARCHITECTURE.md for routing/failover."""

    name: str

    @abstractmethod
    async def complete_structured(
        self, task_type: str, evidence: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        ...


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, payload: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        ...
