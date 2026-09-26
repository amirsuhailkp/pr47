"""Train (and, if it earns it, promote) the anomaly model — by hand, or on a schedule.

    python -m scripts.train_anomaly_model
    python -m scripts.train_anomaly_model --lookback-days 1095 AAPL RELIANCE TCS

Uses only free historical bars (yfinance) and local arithmetic — no LLM calls, no
GROQ_API_KEYS/CEREBRAS_API_KEYS involved, so this never touches your token budget.

scripts/run_service.py also calls this on a schedule automatically (see its
RETRAIN_INTERVAL_DAYS setting) so a model deployed to Azure keeps improving without
anyone needing to log in and run it by hand.
"""
from __future__ import annotations

import argparse
import asyncio

from app.config.settings import get_settings
from data.providers.yfinance_provider import YFinanceHistoricalProvider, yfinance_fetch
from ml.training.anomaly_trainer_job import TrainingSkipped, run_training_job


async def main(symbols: list[str], lookback_days: int) -> None:
    provider = YFinanceHistoricalProvider(yfinance_fetch)
    print(f"Training anomaly model on {len(symbols)} symbol(s), {lookback_days} days of history...")
    try:
        model, manifest, validation = await run_training_job(
            provider, symbols, lookback_days=lookback_days
        )
    except TrainingSkipped as exc:
        print(f"Not promoted: {exc}")
        return

    print(f"Promoted {manifest.model_version} to production.")
    print(
        f"  {validation.metric_name}: model={validation.model_metric:.3f} "
        f"vs baseline={validation.baseline_metric:.3f} "
        f"(n={validation.sample_size}, leakage_tests_passed={validation.leakage_tests_passed})"
    )
    print(f"  trained on {manifest.training_data_description}")
    print("  saved to data/models/anomaly_production.json — scripts/run_service.py will load it on next start.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("symbols", nargs="*", help="defaults to WATCHLIST_SYMBOLS from .env")
    args = parser.parse_args()
    cli_symbols = args.symbols or get_settings().market.watchlist()
    asyncio.run(main(cli_symbols, args.lookback_days))
