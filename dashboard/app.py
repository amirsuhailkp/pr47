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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config.settings import get_settings
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository
from market.strategies.registry import get_strategy
from dashboard.service import build_stock_view, build_watchlist_overview

app = FastAPI(title="DataBroker Dashboard")
templates = Jinja2Templates(directory="dashboard/templates")

_settings = get_settings()
_engine = create_db_engine(_settings.database.database_url)
init_db(_engine)
_alert_repo = AlertRepository(make_session_factory(_engine))
_provider = YFinanceHistoricalProvider(yfinance_fetch)
_profile = get_strategy("swing")  # dashboard always shows the daily/swing view for now


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
            "closes": [b.close for b in view.bars],
            "volumes": [b.volume for b in view.bars],
        }

    return templates.TemplateResponse(
        request,
        "stock.html",
        {"symbol": symbol, "view": view, "error": error, "chart_data": chart_data},
    )
