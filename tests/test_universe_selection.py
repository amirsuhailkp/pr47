from app.config.settings import MarketSettings
from app.domain.market import Instrument
from market.universe.selection import UniverseCandidateStats, filter_universe, is_in_universe


def _settings() -> MarketSettings:
    return MarketSettings(
        MIN_PRICE=50,
        MAX_PRICE=300,
        MIN_AVG_TRADED_VALUE=5_000_000,
        EXCLUDE_SME=True,
        MIN_HISTORY_DAYS=250,
    )


def _stats(**overrides) -> UniverseCandidateStats:
    defaults = dict(
        instrument=Instrument(symbol="XYZ", exchange="NSE"),
        last_price=150.0,
        avg_traded_value=10_000_000.0,
        history_days_available=400,
        is_sme=False,
        has_reliable_data=True,
    )
    defaults.update(overrides)
    return UniverseCandidateStats(**defaults)


def test_qualifying_stock_is_in_universe():
    assert is_in_universe(_stats(), _settings()) is True


def test_price_outside_band_is_excluded():
    assert is_in_universe(_stats(last_price=400.0), _settings()) is False
    assert is_in_universe(_stats(last_price=10.0), _settings()) is False


def test_sme_excluded_when_configured():
    assert is_in_universe(_stats(is_sme=True), _settings()) is False


def test_unreliable_data_excluded():
    assert is_in_universe(_stats(has_reliable_data=False), _settings()) is False


def test_insufficient_history_excluded():
    assert is_in_universe(_stats(history_days_available=10), _settings()) is False


def test_low_liquidity_excluded():
    assert is_in_universe(_stats(avg_traded_value=1_000.0), _settings()) is False


def test_filter_universe_returns_only_qualifying_instruments():
    good = _stats()
    bad = _stats(instrument=Instrument(symbol="BAD", exchange="NSE"), is_sme=True)
    result = filter_universe([good, bad], _settings())
    assert result == [good.instrument]
