"""Read-only web dashboard: watchlist overview + per-stock chart and current signals.

Run with: python -m scripts.run_dashboard  (see that file for the systemd unit note).

Design notes (see dashboard/service.py's module docstring for the fuller reasoning):
- Never calls the LLM router. Any "AI note" shown here comes from AlertRow.body,
  i.e. commentary an already-fired alert generated earlier — nothing is generated on
  page load, so a stranger refreshing this public page can't spend your LLM budget.
- Never writes to the alerts table or sends Telegram messages. It reads the same free
  detectors the real service uses, but doesn't route through AlertEngine, so viewing
  a stock here has zero side effects on the live service's cooldowns or alert history.
- No new background jobs, no caching layer, no auth — deliberately the smallest thing
  that shows real data, since you asked for this without over-engineering it. Add
  auth (see README note) before treating this as anything but a personal view.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from datetime import timedelta

from app.config.settings import get_settings
from app.domain.market import Instrument
from data.providers.nse_universe_provider import NseUniverseProvider, httpx_fetch_csv
from opportunity.discovery.engine import CandidateDiscoveryEngine
from opportunity.ranking.rank import rank_candidates
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository, WatchlistRepository
from intelligence.llm.build import build_llm_router_from_settings
from market.strategies.registry import get_strategy
from dashboard.analysis import HybridAnalysis, run_analysis
from dashboard.service import (
    INTERVAL_LOOKBACK_DAYS, build_pattern_engine, build_stock_view, build_watchlist_overview,
    fetch_chart_bars, fetch_index_series, fetch_index_snapshot,
)

app = FastAPI(title="DataBroker Dashboard")
templates = Jinja2Templates(directory="dashboard/templates")

_settings = get_settings()
_engine = create_db_engine(_settings.database.database_url)
init_db(_engine)
_alert_repo = AlertRepository(make_session_factory(_engine))
_watchlist_repo = WatchlistRepository(make_session_factory(_engine))
_provider = YFinanceHistoricalProvider(yfinance_fetch)
_profile = get_strategy("swing")  # dashboard always shows the daily/swing view for now
_llm_router = build_llm_router_from_settings(_settings.llm)  # None if no keys set — handled below
_pattern_engine = build_pattern_engine(_profile)

_ANALYSIS_CACHE_SECONDS = 900  # 15 min — protects your LLM quota from repeated clicks
_analysis_cache: dict[str, HybridAnalysis] = {}

_DISCOVER_CACHE_SECONDS = 1800  # 30 min — a scan is ~40 sequential yfinance calls; this
# keeps a visitor hammering "Scan" from hammering Yahoo on your behalf
_DISCOVER_DEFAULT_LIMIT = 40  # matches scripts/discover_candidates.py's own default
_discover_cache: dict | None = None  # {"computed_at": datetime, "ranked": [...]}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    env_symbols = set(_settings.market.watchlist())
    detailed = _watchlist_repo.list_active_detailed()
    db_symbols = {d["instrument"].symbol for d in detailed}
    priority_by_symbol = {d["instrument"].symbol: d["priority"] for d in detailed}
    symbols = sorted(env_symbols | db_symbols)
    rows = await build_watchlist_overview(symbols, _profile, _provider, _alert_repo)
    # dashboard-added (removable here) vs env-configured (.env is the source of truth,
    # so removal for those happens by editing .env, not from this page)
    rows_with_meta = [
        {
            "row": r, "removable": r.symbol in db_symbols and r.symbol not in env_symbols,
            "priority": priority_by_symbol.get(r.symbol, 0),
        }
        for r in rows
    ]
    rows_with_meta.sort(key=lambda m: (-m["priority"], m["row"].symbol))
    return templates.TemplateResponse(
        request, "index.html",
        {"rows_with_meta": rows_with_meta, "strategy": _profile.definition.name},
    )


@app.post("/watchlist/priority/{symbol}")
async def watchlist_priority(symbol: str, priority: int) -> JSONResponse:
    symbol = symbol.upper()
    priority = max(0, min(2, priority))  # 0=Normal, 1=High, 2=Top — clamp bad input
    _watchlist_repo.set_priority(Instrument(symbol=symbol, exchange="NSE"), priority)
    return JSONResponse({"symbol": symbol, "priority": priority})


@app.post("/watchlist/add/{symbol}")
async def watchlist_add(symbol: str) -> JSONResponse:
    """Adds to the DB-backed watchlist (data/storage/models.py's WatchlistEntryRow /
    WatchlistRepository — built a while ago, not used by anything until now).
    scripts/run_service.py now re-reads this table every poll cycle, so this takes
    effect on the live Telegram-alerting loop too, not just this dashboard — no .env
    edit or restart needed. It does not touch WATCHLIST_SYMBOLS in .env itself."""
    symbol = symbol.upper()
    _watchlist_repo.add(Instrument(symbol=symbol, exchange="NSE"))
    return JSONResponse({"symbol": symbol, "added": True})


@app.post("/watchlist/remove/{symbol}")
async def watchlist_remove(symbol: str) -> JSONResponse:
    symbol = symbol.upper()
    if symbol in set(_settings.market.watchlist()):
        return JSONResponse(
            {"error": f"{symbol} is set via WATCHLIST_SYMBOLS in .env — edit .env and restart "
                      "the service to remove it, the dashboard can't remove env-configured symbols."},
            status_code=400,
        )
    count = _watchlist_repo.deactivate(Instrument(symbol=symbol, exchange="NSE"))
    return JSONResponse({"symbol": symbol, "removed": count > 0})


@app.get("/stock/{symbol}", response_class=HTMLResponse)
async def stock_page(request: Request, symbol: str, interval: str = "1d") -> HTMLResponse:
    symbol = symbol.upper()
    if interval not in INTERVAL_LOOKBACK_DAYS:
        interval = "1d"

    error: str | None = None
    chart_error: str | None = None
    view = None
    chart_bars = []
    try:
        view = await build_stock_view(symbol, _profile, _provider, _alert_repo)
    except Exception as exc:  # noqa: BLE001 — show the error on the page, don't 500
        error = str(exc)

    # Signals/backtest always use the swing (daily) profile's own bars — only the
    # chart's timeframe changes here, so a "5m" zoomed-in view doesn't change what
    # the pattern/anomaly/backtest section is reasoning about. Kept as a separate
    # try/except: Yahoo not having intraday history for a symbol shouldn't blank out
    # signals that already loaded fine.
    if view is not None:
        try:
            chart_bars = view.bars if interval == "1d" else await fetch_chart_bars(symbol, interval, _provider)
        except Exception as exc:  # noqa: BLE001
            chart_error = f"Couldn't load {interval} data: {exc}"

    chart_data = None
    if chart_bars:
        label_fmt = "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M"
        chart_data = {
            "labels": [b.timestamp.strftime(label_fmt) for b in chart_bars],
            "ohlc": [{"o": b.open, "h": b.high, "l": b.low, "c": b.close} for b in chart_bars],
            "closes": [b.close for b in chart_bars],
            "volumes": [b.volume for b in chart_bars],
        }

    all_watched = set(_settings.market.watchlist()) | {i.symbol for i in _watchlist_repo.list_active()}
    return templates.TemplateResponse(
        request,
        "stock.html",
        {
            "symbol": symbol, "view": view, "error": error, "chart_data": chart_data,
            "chart_error": chart_error, "interval": interval,
            "intervals": list(INTERVAL_LOOKBACK_DAYS.keys()),
            "in_watchlist": symbol in all_watched,
        },
    )


@app.post("/stock/{symbol}/analyze")
async def analyze(symbol: str) -> JSONResponse:
    """On-demand only — never called by the page itself on load. See
    dashboard/analysis.py's module docstring for why (public URL, real LLM cost)."""
    symbol = symbol.upper()

    cached = _analysis_cache.get(symbol)
    if cached is not None and (datetime.now(timezone.utc) - cached.computed_at).total_seconds() < _ANALYSIS_CACHE_SECONDS:
        return JSONResponse(_serialize_analysis(cached, from_cache=True))

    try:
        view = await build_stock_view(symbol, _profile, _provider, _alert_repo)
        index_series = await fetch_index_series(_provider, _profile)
        instrument = Instrument(symbol=symbol, exchange="NSE")
        result = await run_analysis(
            instrument, view.bars, index_series, view.snapshot, view.context, view.raw_patterns,
            _pattern_engine, _llm_router,
        )
    except Exception as exc:  # noqa: BLE001 — the button should show an error, not crash
        return JSONResponse({"error": str(exc)}, status_code=500)

    _analysis_cache[symbol] = result
    return JSONResponse(_serialize_analysis(result, from_cache=False))


@app.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "discover.html",
        {"cache_minutes": _DISCOVER_CACHE_SECONDS // 60, "limit": _DISCOVER_DEFAULT_LIMIT},
    )


@app.post("/discover/scan")
async def discover_scan() -> JSONResponse:
    """On-demand, cached — see dashboard/templates/discover.html. Reuses
    opportunity/discovery/engine.py exactly as scripts/discover_candidates.py does;
    this doesn't add a new scoring/scanning approach, just a web front end on the
    existing one."""
    global _discover_cache
    now = datetime.now(timezone.utc)
    if _discover_cache is not None and (now - _discover_cache["computed_at"]).total_seconds() < _DISCOVER_CACHE_SECONDS:
        return JSONResponse(_serialize_discover(_discover_cache, from_cache=True))

    try:
        universe_provider = NseUniverseProvider(httpx_fetch_csv)
        universe = await universe_provider.get_universe()
        market_index = await fetch_index_snapshot(_provider, _profile)

        engine = CandidateDiscoveryEngine(_provider, _settings.market)
        start = now - timedelta(days=_profile.lookback_days)
        result = await engine.discover(
            universe, _profile, market_index, now, start, max_instruments=_DISCOVER_DEFAULT_LIMIT
        )
        ranked = rank_candidates(result.candidates)
    except Exception as exc:  # noqa: BLE001 — show the error, don't 500
        return JSONResponse({"error": str(exc)}, status_code=500)

    _discover_cache = {"computed_at": now, "ranked": ranked, "stats": result.stats}
    return JSONResponse(_serialize_discover(_discover_cache, from_cache=False))


def _serialize_discover(cache: dict, from_cache: bool) -> dict:
    stats = cache["stats"]
    return {
        "from_cache": from_cache,
        "computed_at": cache["computed_at"].isoformat(),
        "stats": {
            "scanned": stats.scanned, "candidates_found": stats.candidates_found,
            "insufficient_history": stats.insufficient_history,
            "failed_universe_filter": stats.failed_universe_filter,
            "fetch_errors": stats.fetch_errors,
        },
        "candidates": [
            {
                "symbol": rc.evidence.instrument.symbol,
                "score": rc.score.total,
                "reasons": list(rc.evidence.reasons),
                "risks": list(rc.evidence.risks),
            }
            for rc in cache["ranked"][:20]
        ],
    }


def _serialize_analysis(a: HybridAnalysis, from_cache: bool) -> dict:
    llm = a.llm_analysis
    return {
        "from_cache": from_cache,
        "computed_at": a.computed_at.isoformat(),
        "anomaly_z": a.anomaly_z,
        "anomaly_contributors": a.anomaly_contributors,
        "historical_family": a.historical_family,
        "historical": (
            {
                "sample_size": a.historical.sample_size,
                "horizons": {
                    h: {
                        "sample_size": hs.sample_size,
                        "positive_frequency": hs.positive_frequency,
                        "negative_frequency": hs.negative_frequency,
                        "median_return_pct": hs.median_return_pct,
                        "mean_return_pct": hs.mean_return_pct,
                        "uncertainty_note": hs.uncertainty_note,
                    }
                    for h, hs in a.historical.horizons.items()
                },
            }
            if a.historical else None
        ),
        "news_count": a.news_count,
        "used_llm": a.used_llm,
        "error": a.error,
        "routing_events": a.routing_events or [],
        "llm": (
            {
                "summary": llm.summary,
                "observations": list(llm.observations),
                "possible_scenarios": list(llm.possible_scenarios),
                "risk_factors": list(llm.risk_factors),
                "invalidation_conditions": list(llm.invalidation_conditions),
                "uncertainty": list(llm.uncertainty),
                "missing_information": list(llm.missing_information),
            }
            if llm else None
        ),
    }
