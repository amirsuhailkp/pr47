"""Manual end-to-end test run using the temporary free/keyless-or-cheap providers:

- Market data (live quote):     IndianAPI.in  (data/providers/indianapi_provider.py)
- Historical backfill (bars):   yfinance      (data/providers/yfinance_provider.py)
- News:                         BSE RSS + Google News RSS (data/providers/rss_news_provider.py)

This does NOT change any existing module — it only wires the provider adapters
(which implement the existing MarketDataProvider/HistoricalDataProvider/NewsProvider
interfaces) into the existing MonitoringPipeline / RealTimeService, now selectable by
strategy profile (market/strategies/: scalping vs swing — docs §24).

Usage:
    cp .env.example .env            # fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
                                     # INDIANAPI_API_KEY is optional (only used for the
                                     # live-quote printout; backfill/pipeline uses yfinance)
    pip install -r requirements.txt
    python -m scripts.run_local_test                              # swing, WATCHLIST_SYMBOLS from .env
    python -m scripts.run_local_test --strategy scalping           # scalping, same watchlist
    python -m scripts.run_local_test --strategy swing RELIANCE TCS # explicit symbols

What it does, per symbol (bar interval and thresholds come from the chosen strategy
profile — 5-minute bars + tight thresholds for scalping, daily bars + wider
confirmation for swing):
    1. Backfills bars via yfinance (free, no key) at the strategy's bar interval
    2. Backfills NIFTY 50 index bars at the same interval, for market context
    3. Runs the real MonitoringPipeline (Phase 2), configured for the chosen strategy
    4. Fetches recent news via BSE + Google News RSS (free, no key)
    5. Persists any resulting alerts to a local SQLite DB and attempts real Telegram
       delivery (queues + retries on failure, same as production)
    6. Prints a live quote from IndianAPI.in, if INDIANAPI_API_KEY is set

Note on scalping + yfinance: Yahoo only serves 5-minute data for roughly the last 60
days, and this is still REST-polled / backfilled data, not live intraday ticks — see
market/strategies/scalping.py's StrategyDefinition.limitations for the honest caveat.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from app.config.settings import get_settings
from app.domain.market import IndexSnapshot, Instrument
from app.orchestration.pipeline import build_pipeline_from_profile
from app.orchestration.realtime_service import RealTimeService
from alerts.telegram.delivery_queue import DeliveryQueue
from alerts.telegram.notifier import TelegramNotifier
from data.providers.indianapi_provider import (
    IndianApiMarketDataProvider,
    httpx_transport as indianapi_transport,
)
from data.providers.rss_news_provider import RssNewsProvider, httpx_fetch_feed
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository
from intelligence.llm.build import build_llm_router_from_settings
from intelligence.research.news_synthesis import normalize_news_items
from market.strategies.profile import StrategyProfile
from market.strategies.registry import STRATEGIES, get_strategy

NIFTY_INDEX = Instrument(symbol="^NSEI", exchange="NSE")


async def _fetch_index_snapshot(
    historical_provider: YFinanceHistoricalProvider, profile: StrategyProfile
) -> IndexSnapshot:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(profile.lookback_days, 2))
    bars = await historical_provider.get_bars(NIFTY_INDEX, profile.bar_interval, start, end)
    if len(bars) < 2:
        raise RuntimeError(
            f"could not backfill enough NIFTY bars at interval={profile.bar_interval} "
            "for market context"
        )
    change_pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100.0
    return IndexSnapshot(
        code="NIFTY50",
        value=bars[-1].close,
        change=bars[-1].close - bars[-2].close,
        change_pct=change_pct,
        timestamp=bars[-1].timestamp,
        source="yfinance",
    )


async def run_for_symbol(
    symbol: str,
    profile: StrategyProfile,
    service: RealTimeService,
    historical_provider: YFinanceHistoricalProvider,
    news_provider: RssNewsProvider,
    market_index: IndexSnapshot,
    live_quote_provider: IndianApiMarketDataProvider | None,
) -> None:
    instrument = Instrument(symbol=symbol, exchange="NSE")
    print(f"\n=== {symbol} ({profile.definition.name}) ===")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=profile.lookback_days)
    bars = await historical_provider.get_bars(instrument, profile.bar_interval, start, end)
    if len(bars) < 20:
        print(
            f"  not enough backfilled bars ({len(bars)}) at interval="
            f"{profile.bar_interval} — skipping"
        )
        return
    as_of = bars[-1].timestamp
    print(f"  backfilled {len(bars)} {profile.bar_interval} bars, latest close {bars[-1].close}")

    row_ids = await service.handle_update(instrument, bars, market_index, None, as_of)
    if row_ids:
        print(f"  {len(row_ids)} alert(s) generated and stored (row ids: {row_ids})")
    else:
        print("  no alerts for the current data")

    since = as_of - timedelta(days=7)
    try:
        raw_news = await news_provider.get_news(instrument, since)
        news = normalize_news_items(raw_news)
        print(f"  {len(news)} news item(s) in the last 7 days")
        for item in news[:3]:
            print(f"    - [{item['source']}] {item['headline']}")
    except Exception as exc:  # noqa: BLE001 — news is best-effort for this manual script
        print(f"  news fetch failed: {exc}")

    if live_quote_provider is not None:
        try:
            data = await indianapi_transport(  # one-off call, not the polling generator
                get_settings().providers.indianapi_api_key
            )("/stock", {"name": symbol})
            price = data.get("currentPrice", {})
            print(f"  live quote (IndianAPI.in): NSE={price.get('NSE')} BSE={price.get('BSE')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  live quote fetch failed: {exc}")


async def main(symbols: list[str], profile: StrategyProfile) -> None:
    settings = get_settings()

    engine = create_db_engine(settings.database.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    alert_repo = AlertRepository(session_factory)

    historical_provider = YFinanceHistoricalProvider(yfinance_fetch)
    news_provider = RssNewsProvider(httpx_fetch_feed)

    live_quote_provider = None
    if settings.providers.indianapi_api_key:
        live_quote_provider = IndianApiMarketDataProvider(
            indianapi_transport(settings.providers.indianapi_api_key)
        )

    notifier = TelegramNotifier(
        bot_token=settings.telegram.bot_token,
        chat_id=settings.telegram.chat_id,
        transport=_real_telegram_transport(settings.telegram.bot_token),
    )
    llm_router = build_llm_router_from_settings(settings.llm)
    service = RealTimeService(
        pipeline=build_pipeline_from_profile(profile),
        alert_repository=alert_repo,
        notifier=notifier,
        delivery_queue=DeliveryQueue(),
        llm_router=llm_router,
    )

    print(f"Strategy: {profile.definition.name}")
    print(
        "LLM enrichment: "
        + (f"ON ({', '.join(p.name for p in llm_router.providers)})" if llm_router else "OFF (no GROQ_API_KEYS/CEREBRAS_API_KEYS set — deterministic alerts only)")
    )
    print(f"Backfilling NIFTY 50 index context via yfinance ({profile.bar_interval} bars)...")
    market_index = await _fetch_index_snapshot(historical_provider, profile)
    print(f"NIFTY50 change: {market_index.change_pct:+.2f}%")

    for symbol in symbols:
        await run_for_symbol(
            symbol, profile, service, historical_provider, news_provider,
            market_index, live_quote_provider,
        )

    await service.retry_pending_deliveries(datetime.now(timezone.utc))
    print("\nDone. Recent alerts in the DB:")
    for row in alert_repo.recent(limit=10):
        print(f"  {row['created_at']} [{row['severity']}] {row['symbol']}: {row['title']} "
              f"(delivered={row['delivered']})")


def _real_telegram_transport(bot_token: str):
    async def transport(chat_id: str, body: dict) -> dict:
        import httpx

        if not bot_token:
            return {"ok": False, "description": "TELEGRAM_BOT_TOKEN not set — skipping send"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage", json=body
            )
            return response.json()

    return transport


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DataBroker's pipeline against free test data.")
    parser.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default="swing",
        help="which strategy profile to use (default: swing)",
    )
    parser.add_argument(
        "symbols", nargs="*",
        help="NSE symbols to check (default: WATCHLIST_SYMBOLS from .env)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    cli_symbols = args.symbols or get_settings().market.watchlist()
    cli_profile = get_strategy(args.strategy)
    asyncio.run(main(cli_symbols, cli_profile))
