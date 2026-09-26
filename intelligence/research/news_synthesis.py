"""News synthesis for the LLM evidence payload.

docs §33: "Never let an LLM invent news." This module doesn't summarize or interpret
news content itself (that's the LLM's job, working from what's passed here) — it only
normalizes provider-supplied news items into the shape StructuredEvidence expects,
and filters out anything missing the fields needed to prove provenance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


REQUIRED_FIELDS = ("headline", "source", "published_at", "symbol")


def normalize_news_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Returns a normalized item, or None if it's missing required provenance fields
    — an item with no traceable source must never reach the LLM as 'news'."""
    if not all(raw.get(f) for f in REQUIRED_FIELDS):
        return None

    published_at = raw["published_at"]
    if isinstance(published_at, datetime):
        published_at = published_at.isoformat()

    return {
        "headline": raw["headline"],
        "source": raw["source"],
        "published_at": published_at,
        "symbol": raw["symbol"],
        "url": raw.get("url"),
        "summary": raw.get("summary"),
    }


def normalize_news_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in (normalize_news_item(r) for r in raw_items) if item is not None]
