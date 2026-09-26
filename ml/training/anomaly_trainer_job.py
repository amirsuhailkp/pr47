"""The "AI trainer" you asked for — but note upfront: it does not call an LLM.

Training an AnomalyModel is fitting per-feature mean/std on historical price data and
checking the result against a baseline (ml/training/train_anomaly.py, unmodified —
built and tested, just never called by anything until this file). That is classical
statistics, not a language-model task, so this makes zero calls to Groq/Cerebras and
consumes zero LLM tokens no matter how often it runs. Your GROQ_API_KEYS/
CEREBRAS_API_KEYS and the pooling/failover in intelligence/llm/ are completely
untouched by this module.

Pulls historical bars directly from yfinance (same free provider everything else
uses) rather than waiting for live outcomes to accumulate — you don't have to run the
service for months before this has data to learn from; a couple of years of daily
history per watchlist symbol is enough for a first model today.

Promotion is never automatic on training completion (docs/ML_ARCHITECTURE.md,
ml/registry/registry.py): if the trained model doesn't beat BaselineAnomalyModel on a
held-out chronological slice, it is not promoted, and the live detector keeps using
its safe online-fit fallback — never a worse "trained" model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.market import Instrument, OHLCVBar
from app.domain.ml import ModelManifest, ValidationResult
from data.providers.yfinance_provider import YFinanceHistoricalProvider
from ml.models.anomaly.model import AnomalyModel
from ml.registry.persistence import save_production_anomaly_model
from ml.registry.registry import ModelRegistry, PromotionNotEligibleError
from ml.training.train_anomaly import TrainingExample, train_and_validate_anomaly_model
from patterns.anomaly.detector import FEATURE_SCHEMA, bar_features


def build_training_examples(bars: list[OHLCVBar], horizon_bars: int = 5) -> list[TrainingExample]:
    """One example per bar with enough history behind it (for features) and enough
    bars ahead of it (for the forward-return label). Labels come only from bars
    strictly after the feature bar, so there is no leakage into the features."""
    examples: list[TrainingExample] = []
    for i in range(1, len(bars) - horizon_bars):
        features = bar_features(bars[i - 1].close, bars[i])
        entry_close = bars[i].close
        forward_return_pct = (
            (bars[i + horizon_bars].close - entry_close) / entry_close * 100.0
            if entry_close
            else 0.0
        )
        examples.append(
            TrainingExample(
                timestamp=bars[i].timestamp,
                features=features,
                forward_return_pct=forward_return_pct,
            )
        )
    return examples


class TrainingSkipped(Exception):
    """Raised (and caught by the caller — scripts/train_anomaly_model.py or
    run_service.py's periodic check) when there simply isn't enough data yet, or the
    model didn't beat its baseline. Not promoting is the correct, expected outcome in
    that case, not a bug."""


async def run_training_job(
    historical_provider: YFinanceHistoricalProvider,
    symbols: list[str],
    lookback_days: int = 730,
    horizon_bars: int = 5,
    model_version: str | None = None,
) -> tuple[AnomalyModel, ModelManifest, ValidationResult]:
    """Pools training examples across every watchlist symbol (more chronological
    examples -> a more meaningful train/test split) and trains one shared anomaly
    model, rather than one per symbol — with only a handful of watchlist symbols,
    a per-symbol model wouldn't have enough held-out examples to validate honestly.

    Raises TrainingSkipped if there isn't enough pooled data, or if the trained model
    doesn't beat the baseline / fails the leakage check. Never returns a model that
    wasn't actually promotion-eligible.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)

    all_examples: list[TrainingExample] = []
    for symbol in symbols:
        instrument = Instrument(symbol=symbol, exchange="NSE")
        try:
            bars = await historical_provider.get_bars(instrument, "1d", start, now)
        except Exception as exc:  # noqa: BLE001 — one bad symbol shouldn't fail the job
            print(f"  [{symbol}] skipped for training: {exc}")
            continue
        all_examples.extend(build_training_examples(bars, horizon_bars))

    if len(all_examples) < 30:
        raise TrainingSkipped(
            f"only {len(all_examples)} pooled training examples across {len(symbols)} "
            "symbol(s) — need at least 30 for a meaningful chronological split. Add "
            "more watchlist symbols or a longer --lookback-days."
        )

    version = model_version or f"anomaly-{now.strftime('%Y%m%d-%H%M%S')}"
    model, manifest, validation = train_and_validate_anomaly_model(
        all_examples, FEATURE_SCHEMA, version
    )

    registry = ModelRegistry()
    registry.register(manifest, validation)
    try:
        registry.promote(manifest.task, manifest.model_version, now)
    except PromotionNotEligibleError as exc:
        raise TrainingSkipped(
            f"trained model ({validation.metric_name}: model={validation.model_metric:.3f} "
            f"vs baseline={validation.baseline_metric:.3f}, "
            f"leakage_tests_passed={validation.leakage_tests_passed}) did not beat its "
            "baseline — keeping the existing production model (or the online-fit "
            "fallback if none exists yet)."
        ) from exc

    save_production_anomaly_model(model, manifest, validation)
    return model, manifest, validation
