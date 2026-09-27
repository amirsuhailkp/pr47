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

from app.config.settings import get_settings
from app.domain.market import Instrument
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository
from intelligence.llm.build import build_llm_router_from_settings
from market.strategies.registry import get_strategy
from dashboard.analysis import HybridAnalysis, run_analysis
from dashboard.service import build_pattern_engine, build_stock_view, build_watchlist_overview, fetch_index_series

app = FastAPI(title="DataBroker Dashboard")
templates = Jinja2Templates(directory="dashboard/templates")

_settings = get_settings()
_engine = create_db_engine(_settings.database.database_url)
init_db(_engine)
_alert_repo = AlertRepository(make_session_factory(_engine))
_provider = YFinanceHistoricalProvider(yfinance_fetch)
_profile = get_strategy("swing")  # dashboard always shows the daily/swing view for now
_llm_router = build_llm_router_from_settings(_settings.llm)  # None if no keys set — handled below
_pattern_engine = build_pattern_engine(_profile)

_ANALYSIS_CACHE_SECONDS = 900  # 15 min — protects your LLM quota from repeated clicks
_analysis_cache: dict[str, HybridAnalysis] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    symbols = _settings.market.watchlist()
    rows = await build_watchlist_overview(symbols, _profile, _provider, _alert_repo)
    return templates.TemplateResponse(
        request, "index.html", {"rows": rows, "strategy": _profile.definition.name}
    )


@app.get("/stock/{symbol}", response_class=HTMLResponse)
async def stock_page(request: Request, symbol: str) -> HTMLResponse:
    symbol = symbol.upper()
    error: str | None = None
    view = None
    try:
        view = await build_stock_view(symbol, _profile, _provider, _alert_repo)
    except Exception as exc:  # noqa: BLE001 — show the error on the page, don't 500
        error = str(exc)

    chart_data = None
    if view is not None:
        chart_data = {
            "labels": [b.timestamp.strftime("%Y-%m-%d") for b in view.bars],
            "ohlc": [
                {"o": b.open, "h": b.high, "l": b.low, "c": b.close}
                for b in view.bars
            ],
            "closes": [b.close for b in view.bars],
            "volumes": [b.volume for b in view.bars],
        }

    return templates.TemplateResponse(
        request,
        "stock.html",
        {"symbol": symbol, "view": view, "error": error, "chart_data": chart_data},
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
