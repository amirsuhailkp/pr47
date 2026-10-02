"""The actual 24/7 service loop — this did not exist before. scripts/run_local_test.py
and scripts/discover_candidates.py are both one-shot: run once, print, exit. This is
what you run to get continuous Telegram updates while the market is open.

Usage:
    python -m scripts.run_service                      # swing, WATCHLIST_SYMBOLS
    python -m scripts.run_service --strategy scalping

Design, matching the product vision (docs §1, "use LLMs for interpretation... not the
source of raw market truth") and the cost constraint you gave:
    - Every poll runs the free, local, deterministic + ML pipeline (patterns, events,
      the anomaly detector) on every symbol. This costs no API tokens at all — it's
      what makes checking every POLL_INTERVAL_SECONDS (default 300s) affordable.
    - The LLM is only ever called for a symbol where that free pipeline already
      decided something alert-worthy happened (see RealTimeService._append_llm_note).
      On an ordinary day where nothing fires, zero LLM calls are made, no matter how
      long the service runs.
    - Only checks the watchlist during NSE regular market hours (market/sessions/
      nse_calendar.py) — no point burning yfinance/IndianAPI calls overnight or on
      weekends. Known limitation: the holiday calendar isn't wired in yet (see
      NseSessionCalendar's docstring), so it will still poll on NSE holidays that
      fall on a weekday; add the official holiday list there when you have it.
    - Re-backfills the full lookback window every poll rather than only the newest
      bar(s) — simple and correct, at the cost of re-downloading data you already
      have. Fine at a 5-symbol watchlist and a 5-minute interval; revisit if you grow
      the watchlist a lot.

Stop with Ctrl+C.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from app.config.settings import get_settings
from app.domain.market import Instrument
from app.orchestration.pipeline import build_pipeline_from_profile
from app.orchestration.realtime_service import RealTimeService
from alerts.telegram.delivery_queue import DeliveryQueue
from alerts.telegram.notifier import TelegramNotifier
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from data.storage.database import create_db_engine, init_db, make_session_factory
from data.storage.repositories import AlertRepository, WatchlistRepository
from intelligence.llm.build import build_llm_router_from_settings
from market.sessions.nse_calendar import NseSessionCalendar
from market.strategies.profile import StrategyProfile
from market.strategies.registry import STRATEGIES, get_strategy
from ml.registry.persistence import days_since_last_attempt, load_production_anomaly_model
from ml.registry.persistence import record_retrain_attempt
from ml.training.anomaly_trainer_job import TrainingSkipped, run_training_job
from scripts.run_local_test import NIFTY_INDEX, _fetch_index_snapshot, _real_telegram_transport


async def _maybe_retrain(
    symbols: list[str], historical_provider: YFinanceHistoricalProvider, retrain_interval_days: int
) -> bool:
    """Runs the anomaly trainer if it's never run, or hasn't run in
    `retrain_interval_days` — so a deployment nobody is watching still keeps its
    model current. No LLM calls; failure here must never take the service down, so
    every error is caught and logged, not raised. Returns True only if a new model
    was actually promoted, so the caller knows to reload it into the live pipeline."""
    if retrain_interval_days <= 0:
        return False

    age_days = days_since_last_attempt()
    if age_days is not None and age_days < retrain_interval_days:
        return False

    # Record the attempt *before* training so a retrain that fails, hangs, or simply
    # never gets promoted still respects retrain_interval_days on the next cycle —
    # only successful promotion used to update anything on disk, so an
    # always-unpromoted model meant this ran on every single poll forever.
    record_retrain_attempt()

    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
          "retraining anomaly model (scheduled, local compute only, no LLM calls)...")
    try:
        _, manifest, validation = await run_training_job(historical_provider, symbols)
    except TrainingSkipped as exc:
        print(f"  not promoted: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 — never let a training hiccup stop alerts
        print(f"  retrain failed unexpectedly, keeping existing model: {exc}")
        return False

    print(f"  promoted {manifest.model_version} "
          f"({validation.metric_name}: {validation.model_metric:.3f} vs "
          f"baseline {validation.baseline_metric:.3f}) — pipeline will use it from the next check onward")
    return True


async def _poll_once(
    symbols: list[str],
    profile: StrategyProfile,
    service: RealTimeService,
    historical_provider: YFinanceHistoricalProvider,
) -> None:
    now = datetime.now(timezone.utc)
    market_index = await _fetch_index_snapshot(historical_provider, profile)

    for symbol in symbols:
        instrument = Instrument(symbol=symbol, exchange="NSE")
        start = now - timedelta(days=profile.lookback_days)
        try:
            bars = await historical_provider.get_bars(instrument, profile.bar_interval, start, now)
        except Exception as exc:  # noqa: BLE001 — one bad symbol shouldn't stop the loop
            print(f"  [{symbol}] backfill failed: {exc}")
            continue

        if len(bars) < 20:
            continue

        as_of = bars[-1].timestamp
        row_ids = await service.handle_update(instrument, bars, market_index, None, as_of)
        if row_ids:
            print(f"  [{symbol}] {len(row_ids)} alert(s) sent (row ids: {row_ids})")

    await service.retry_pending_deliveries(now)


async def main(symbols: list[str], profile: StrategyProfile) -> None:
    settings = get_settings()

    engine = create_db_engine(settings.database.database_url)
    init_db(engine)
    alert_repo = AlertRepository(make_session_factory(engine))
    watchlist_repo = WatchlistRepository(make_session_factory(engine))
    env_symbols = symbols  # the --symbols/.env list this process was started with

    historical_provider = YFinanceHistoricalProvider(yfinance_fetch)
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
    calendar = NseSessionCalendar()  # holidays not wired in yet — see module docstring

    print(f"DataBroker service starting — strategy={profile.definition.name}, "
          f"watchlist={symbols}, poll every {settings.alerts.poll_interval_seconds}s")
    print(
        "LLM enrichment: "
        + (f"ON ({', '.join(p.name for p in llm_router.providers)}), only on alerts that already fired"
           if llm_router else "OFF (no GROQ_API_KEYS/CEREBRAS_API_KEYS set — deterministic alerts only)")
    )
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            now = datetime.now(timezone.utc)

            # Re-resolve every cycle (not just once at startup) so a symbol added via
            # the dashboard's "Add to watchlist" button (WatchlistRepository.add —
            # built a while ago, never wired into this loop until now) gets picked up
            # on the very next poll, without restarting this service.
            try:
                db_symbols = [i.symbol for i in watchlist_repo.list_active()]
            except Exception as exc:  # noqa: BLE001 — a DB hiccup shouldn't stop alerting
                print(f"  watchlist DB lookup failed, using env/CLI list only: {exc}")
                db_symbols = []
            symbols = sorted(set(env_symbols) | set(db_symbols))

            retrained = await _maybe_retrain(
                symbols, historical_provider, settings.alerts.retrain_interval_days
            )
            if retrained:
                loaded = load_production_anomaly_model()
                service.pipeline.production_anomaly_model = loaded[0] if loaded else None

            if calendar.is_market_open(now):
                print(f"[{now.isoformat(timespec='seconds')}] market open — checking watchlist...")
                await _poll_once(symbols, profile, service, historical_provider)
            else:
                print(f"[{now.isoformat(timespec='seconds')}] market closed — waiting")
            await asyncio.sleep(settings.alerts.poll_interval_seconds)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping — pending deliveries have already been retried each cycle.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DataBroker as a 24/7 watchlist service.")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="swing")
    parser.add_argument("symbols", nargs="*", help="defaults to WATCHLIST_SYMBOLS from .env")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    cli_symbols = args.symbols or get_settings().market.watchlist()
    cli_profile = get_strategy(args.strategy)
    asyncio.run(main(cli_symbols, cli_profile))
