"""RSS-based NewsProvider — BSE's official notices feed plus a per-symbol Google News
query, both free and keyless (docs/PROJECT_PLAN.md temporary-setup note).

Honesty about limitations, since these are read by whoever wires this in later:
- BSE's general notices feed (www.bseindia.com/data/xml/notices.xml) is exchange-wide
  and not filtered by company — Instrument has no company-name field to match against,
  only a ticker symbol, and BSE announcement titles are written by company name, not
  ticker. So BSE items here are tagged with the queried instrument but are NOT a
  reliable per-symbol filter. A real integration would use BSE's per-scrip
  announcement page/feed once its exact URL pattern is confirmed.
- The Google News query IS symbol-scoped (built into the search query itself), so
  those results are the more reliable per-instrument signal of the two.

Network access is behind an injectable `fetch_feed` transport, same pattern as the
other provider adapters, so this is unit-tested with fixed XML fixtures and no
network call.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree

from app.domain.market import Instrument
from app.domain.providers import NewsProvider

FetchFeed = Callable[[str], Awaitable[str]]
"""fetch_feed(url) -> raw RSS/XML text."""

BSE_NOTICES_FEED_URL = "https://www.bseindia.com/data/xml/notices.xml"


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"


class RssFetchError(Exception):
    pass


async def httpx_fetch_feed(url: str) -> str:
    """Production transport — a real GET for the feed XML. Not exercised in tests
    (bseindia.com / news.google.com aren't in this repo's test network allowlist);
    imports httpx lazily so the module stays importable without a live fetch."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text


def _parse_pubdate(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_rss_items(xml_text: str, source: str, symbol: str) -> list[dict[str, Any]]:
    """Parses standard RSS 2.0 <item> elements into the raw dict shape
    intelligence/research/news_synthesis.normalize_news_item expects — this module
    deliberately produces exactly that shape so no downstream code needs to change."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise RssFetchError(f"malformed RSS from {source}: {exc}") from exc

    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip() or None
        pub_date = _parse_pubdate(item.findtext("pubDate"))
        description = (item.findtext("description") or "").strip() or None
        if not title or pub_date is None:
            continue  # no traceable headline/date — skip rather than guess

        items.append(
            {
                "headline": re.sub(r"\s+", " ", title),
                "source": source,
                "published_at": pub_date,
                "symbol": symbol,
                "url": link,
                "summary": description,
            }
        )
    return items


class RssNewsProvider(NewsProvider):
    def __init__(
        self,
        fetch_feed: FetchFeed,
        bse_feed_url: str = BSE_NOTICES_FEED_URL,
        max_items_per_source: int = 20,
    ) -> None:
        self._fetch_feed = fetch_feed
        self._bse_feed_url = bse_feed_url
        self._max_items = max_items_per_source

    async def get_news(self, instrument: Instrument, since: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for url, source in (
            (self._bse_feed_url, "BSE"),
            (google_news_url(f"{instrument.symbol} share"), "Google News"),
        ):
            try:
                xml_text = await self._fetch_feed(url)
            except Exception:  # noqa: BLE001 — one feed failing shouldn't lose the other
                continue
            items = parse_rss_items(xml_text, source=source, symbol=instrument.symbol)
            items = [i for i in items if i["published_at"] >= since]
            results.extend(items[: self._max_items])

        return results
