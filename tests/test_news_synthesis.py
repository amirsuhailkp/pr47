from datetime import datetime, timezone

from intelligence.research.news_synthesis import normalize_news_item, normalize_news_items

NOW = datetime.now(timezone.utc)


def test_valid_item_normalizes():
    raw = {
        "headline": "Company X reports record profit",
        "source": "Reuters",
        "published_at": NOW,
        "symbol": "XYZ",
        "url": "https://example.com/a",
    }
    result = normalize_news_item(raw)
    assert result is not None
    assert result["headline"] == raw["headline"]
    assert result["published_at"] == NOW.isoformat()


def test_item_missing_provenance_field_is_dropped():
    raw = {"headline": "Something happened", "symbol": "XYZ"}  # no source, no published_at
    assert normalize_news_item(raw) is None


def test_normalize_news_items_filters_out_invalid_entries():
    items = [
        {"headline": "A", "source": "S", "published_at": NOW, "symbol": "XYZ"},
        {"headline": "B"},  # invalid
    ]
    result = normalize_news_items(items)
    assert len(result) == 1
    assert result[0]["headline"] == "A"
