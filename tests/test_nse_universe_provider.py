import pytest

from data.providers.nse_universe_provider import (
    NseUniverseError,
    NseUniverseProvider,
    parse_equity_csv,
)

SAMPLE_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1,1,INE467B01029,1\n"
    "SOMEBE,Some BE Company Limited,BE,01-JAN-2000,10,1,INE000000001,10\n"
    "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
)


def test_parse_equity_csv_filters_to_eq_series_by_default():
    instruments = parse_equity_csv(SAMPLE_CSV)
    symbols = {i.symbol for i in instruments}
    assert symbols == {"TCS", "RELIANCE"}
    assert all(i.exchange == "NSE" for i in instruments)


def test_parse_equity_csv_can_allow_other_series():
    instruments = parse_equity_csv(SAMPLE_CSV, allowed_series=frozenset({"EQ", "BE"}))
    symbols = {i.symbol for i in instruments}
    assert symbols == {"TCS", "RELIANCE", "SOMEBE"}


def test_parse_equity_csv_raises_on_empty_input():
    with pytest.raises(NseUniverseError):
        parse_equity_csv("")


def test_parse_equity_csv_raises_on_missing_expected_columns():
    with pytest.raises(NseUniverseError):
        parse_equity_csv("A,B,C\n1,2,3\n")


@pytest.mark.asyncio
async def test_provider_get_universe_uses_injected_fetch():
    async def fetch_csv(url):
        assert "EQUITY_L.csv" in url
        return SAMPLE_CSV

    provider = NseUniverseProvider(fetch_csv)
    instruments = await provider.get_universe()
    assert len(instruments) == 2


@pytest.mark.asyncio
async def test_provider_wraps_fetch_failures():
    async def failing_fetch(url):
        raise ConnectionError("down")

    provider = NseUniverseProvider(failing_fetch)
    with pytest.raises(NseUniverseError):
        await provider.get_universe()
