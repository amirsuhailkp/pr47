from datetime import datetime, timezone

import pytest

from app.domain.market import Instrument
from data.providers.rss_news_provider import (
    RssFetchError,
    RssNewsProvider,
    google_news_url,
    parse_rss_items,
)
from intelligence.research.news_synthesis import normalize_news_items

INSTRUMENT = Instrument(symbol="TCS", exchange="NSE")

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>TCS Q2 results announced</title>
  <link>https://example.com/a</link>
  <pubDate>Mon, 21 Sep 2026 10:00:00 GMT</pubDate>
  <description>Quarterly results summary.</description>
</item>
<item>
  <title>Unrelated notice</title>
  <link>https://example.com/b</link>
  <pubDate>Sun, 20 Sep 2026 09:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def test_parse_rss_items_extracts_expected_fields():
    items = parse_rss_items(SAMPLE_RSS, source="BSE", symbol="TCS")
    assert len(items) == 2
    assert items[0]["headline"] == "TCS Q2 results announced"
    assert items[0]["source"] == "BSE"
    assert items[0]["symbol"] == "TCS"
    assert items[0]["published_at"].tzinfo is not None


def test_parse_rss_items_skips_entries_without_title_or_date():
    xml = """<rss><channel><item><link>https://x</link></item></channel></rss>"""
    assert parse_rss_items(xml, source="BSE", symbol="TCS") == []


def test_parse_rss_items_raises_on_malformed_xml():
    with pytest.raises(RssFetchError):
        parse_rss_items("<not valid xml", source="BSE", symbol="TCS")


def test_google_news_url_is_symbol_scoped():
    url = google_news_url("TCS share")
    assert "TCS" in url
    assert url.startswith("https://news.google.com/rss/search")


@pytest.mark.asyncio
async def test_get_news_combines_both_feeds_and_filters_by_since():
    async def fetch_feed(url):
        return SAMPLE_RSS

    provider = RssNewsProvider(fetch_feed)
    since = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
    items = await provider.get_news(INSTRUMENT, since)
    # both feeds return the same 2-item fixture; only the item on/after `since` passes
    assert len(items) == 2  # one from each source (BSE + Google News), the older one filtered out
    assert all(i["headline"] == "TCS Q2 results announced" for i in items)


@pytest.mark.asyncio
async def test_get_news_tolerates_one_feed_failing():
    async def flaky_fetch(url):
        if "bseindia" in url:
            raise ConnectionError("BSE down")
        return SAMPLE_RSS

    provider = RssNewsProvider(flaky_fetch)
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    items = await provider.get_news(INSTRUMENT, since)
    assert len(items) == 2  # only Google News feed succeeded, both its items pass


@pytest.mark.asyncio
async def test_rss_output_feeds_directly_into_existing_normalizer_unchanged():
    """Confirms the provider's raw output shape matches what
    intelligence/research/news_synthesis.normalize_news_items already expects —
    no changes needed to that module to use this provider."""

    async def fetch_feed(url):
        return SAMPLE_RSS

    provider = RssNewsProvider(fetch_feed)
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    raw_items = await provider.get_news(INSTRUMENT, since)
    normalized = normalize_news_items(raw_items)
    assert len(normalized) == len(raw_items)
    assert all(isinstance(i["published_at"], str) for i in normalized)
