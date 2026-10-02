"""Read-only analysis layer for the web dashboard.

Deliberately does NOT go through MonitoringPipeline.evaluate() / AlertEngine: those
persist alerts and send Telegram messages, which is correct for the 24/7 service loop
(scripts/run_service.py) but wrong here — a public dashboard page gets refreshed by
people just looking, and every refresh would otherwise (a) spam Telegram, (b) pollute
alert history, and (c) needlessly touch the cooldown tracker shared with the real
service if this ran in the same process. Instead this calls the same free detector
functions directly (patterns/engine/events.py, the pattern engine, the anomaly
detector) to get "what's true right now", without recording anything.

Also deliberately never calls the LLM router. This page can be hit by anyone with the
link (per your choice to run it on the public IP with no login) — calling
Groq/Cerebras on every page load would mean a stranger refreshing the page burns your
token budget. Any LLM commentary shown here is read from AlertRow.body, i.e. text an
already-fired, already-persisted alert generated earlier — never generated live.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config.settings import Settings
from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from data.providers.yfinance_provider import YFinanceHistoricalProvider
from data.storage.repositories import AlertRepository
from market.analytics.context import MarketContext, build_context
from market.analytics.price_volume import PriceVolumeSnapshot, build_snapshot
from market.strategies.profile import StrategyProfile
from ml.registry.persistence import load_production_anomaly_model
from patterns.anomaly.detector import AnomalyThresholds, detect_anomaly_event
from patterns.breakout.detector import BreakoutDetector
from patterns.engine.base import PatternEngine
from patterns.engine.events import detect_all_events
from patterns.momentum.detector import MomentumDetector
from patterns.pullback.detector import PullbackDetector

NIFTY_INDEX = Instrument(symbol="^NSEI", exchange="NSE")


@dataclass
class StockView:
    symbol: str
    bars: list[OHLCVBar]
    snapshot: PriceVolumeSnapshot
    context: MarketContext
    active_events: list[str]  # human-readable descriptions, current bar only
    active_patterns: list[dict]  # {family, confirmed, evidence} — for display
    raw_patterns: list  # list[DetectedPattern] — for analysis.py to reuse verbatim
    anomaly_note: str | None
    recent_alerts: list[dict]


async def _fetch_index_snapshot(
    provider: YFinanceHistoricalProvider, profile: StrategyProfile
) -> IndexSnapshot:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(profile.lookback_days, 2))
    bars = await provider.get_bars(NIFTY_INDEX, profile.bar_interval, start, end)
    if len(bars) < 2:
        raise RuntimeError("could not backfill enough NIFTY bars for market context")
    change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100.0
    return IndexSnapshot(
        code="NIFTY50", value=bars[-1].close, change=bars[-1].close - bars[-2].close,
        change_pct=change_pct, timestamp=bars[-1].timestamp, source="yfinance",
    )


fetch_index_snapshot = _fetch_index_snapshot  # public alias for dashboard/app.py's discover route


def _pattern_engine(profile: StrategyProfile) -> PatternEngine:
    return PatternEngine(
        [
            MomentumDetector(profile.momentum_thresholds),
            BreakoutDetector(profile.breakout_thresholds),
            PullbackDetector(profile.pullback_thresholds),
        ]
    )


# Public alias — dashboard/analysis.py's local backtest needs to build the identical
# engine so "was this pattern confirmed on that past day" uses the exact same logic
# the live chart/alerts use, not a second slightly-different implementation.
build_pattern_engine = _pattern_engine


async def fetch_index_series(
    provider: YFinanceHistoricalProvider, profile: StrategyProfile
) -> list[IndexSnapshot]:
    """Full NIFTY history over the same window as the stock's own bars, one snapshot
    per trading day — used by dashboard/analysis.py's local backtest to reconstruct
    what MarketContext looked like on each past day, so pattern confirmation there
    matches what the live pipeline would have said at the time (no lookahead)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=profile.lookback_days)
    bars = await provider.get_bars(NIFTY_INDEX, profile.bar_interval, start, end)
    snapshots = []
    for i in range(1, len(bars)):
        change_pct = (bars[i].close - bars[i - 1].close) / bars[i - 1].close * 100.0 if bars[i - 1].close else 0.0
        snapshots.append(
            IndexSnapshot(
                code="NIFTY50", value=bars[i].close, change=bars[i].close - bars[i - 1].close,
                change_pct=change_pct, timestamp=bars[i].timestamp, source="yfinance",
            )
        )
    return snapshots


INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "1d": 365, "1h": 59, "15m": 59, "5m": 59, "1m": 7,
}
"""Yahoo Finance limits how far back intraday intervals go (roughly 60 days for
5m/15m/1h, 7 days for 1m) — these are safe defaults per interval, not the strategy
profile's own lookback_days, which is tuned for daily swing analysis, not for
rendering a zoomable intraday chart."""


async def fetch_chart_bars(
    symbol: str, interval: str, provider: YFinanceHistoricalProvider
) -> list[OHLCVBar]:
    """Bars for the chart only, independent of the swing-profile pattern/anomaly
    analysis below — picking '5m' here just changes what you can see, not what
    the signals/backtest are based on."""
    if interval not in INTERVAL_LOOKBACK_DAYS:
        raise ValueError(f"unsupported chart interval: {interval}")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=INTERVAL_LOOKBACK_DAYS[interval])
    return await provider.get_bars(Instrument(symbol=symbol, exchange="NSE"), interval, start, now)


async def build_stock_view(
    symbol: str,
    profile: StrategyProfile,
    provider: YFinanceHistoricalProvider,
    alert_repo: AlertRepository,
) -> StockView:
    now = datetime.now(timezone.utc)
    instrument = Instrument(symbol=symbol, exchange="NSE")
    start = now - timedelta(days=profile.lookback_days)
    bars = await provider.get_bars(instrument, profile.bar_interval, start, now)
    if len(bars) < 20:
        raise ValueError(f"not enough history for {symbol} yet ({len(bars)} bars)")

    market_index = await _fetch_index_snapshot(provider, profile)
    snapshot = build_snapshot(bars)
    context = build_context(
        stock_change_pct=snapshot.price_change_pct or 0.0, market_index=market_index, sector_index=None
    )
    as_of = bars[-1].timestamp

    events = detect_all_events(instrument, snapshot, context, as_of)
    active_events = [e.description for e in events]

    patterns = _pattern_engine(profile).run(instrument, snapshot, context, as_of)
    active_patterns = [
        {"family": p.family.value, "confirmed": p.confirmed, "evidence": p.supporting_evidence}
        for p in patterns
    ]

    loaded = load_production_anomaly_model()
    production_model = loaded[0] if loaded is not None else None
    anomaly_event = detect_anomaly_event(instrument, bars, as_of, AnomalyThresholds(), production_model)
    anomaly_note = anomaly_event.description if anomaly_event is not None else None

    recent_alerts = alert_repo.for_symbol(symbol, limit=15)

    return StockView(
        symbol=symbol, bars=bars, snapshot=snapshot, context=context,
        active_events=active_events, active_patterns=active_patterns, raw_patterns=patterns,
        anomaly_note=anomaly_note, recent_alerts=recent_alerts,
    )


@dataclass
class WatchlistRow:
    symbol: str
    price: float
    change_pct: float | None
    last_alert_severity: str | None
    last_alert_at: datetime | None


async def build_watchlist_overview(
    symbols: list[str], profile: StrategyProfile, provider: YFinanceHistoricalProvider,
    alert_repo: AlertRepository,
) -> list[WatchlistRow]:
    rows: list[WatchlistRow] = []
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(profile.lookback_days, 5))
    for symbol in symbols:
        try:
            bars = await provider.get_bars(
                Instrument(symbol=symbol, exchange="NSE"), profile.bar_interval, start, now
            )
        except Exception:
            rows.append(WatchlistRow(symbol, 0.0, None, None, None))
            continue
        if len(bars) < 2:
            rows.append(WatchlistRow(symbol, bars[-1].close if bars else 0.0, None, None, None))
            continue
        change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100.0 if bars[-2].close else None
        history = alert_repo.for_symbol(symbol, limit=1)
        last = history[0] if history else None
        rows.append(
            WatchlistRow(
                symbol=symbol, price=bars[-1].close, change_pct=change_pct,
                last_alert_severity=last["severity"] if last else None,
                last_alert_at=last["created_at"] if last else None,
            )
        )
    return rows
