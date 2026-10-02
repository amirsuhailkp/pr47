"""On-demand hybrid ML + LLM stock analysis for the dashboard's "Analyze" button.

Deliberately on-demand, never called on page load (see dashboard/app.py's route) and
cached briefly per symbol — this is the one part of the dashboard that spends real LLM
tokens, and the dashboard runs on a public IP with no login, so an uncached automatic
call would let any visitor spend your Groq/Cerebras quota just by refreshing.

"Hybrid" here means three distinct, clearly-labeled things — never blended into one
made-up score, because app/domain/history.py and app/domain/llm.py are both explicit
that historical evidence and LLM output must never be collapsed into a single
predictive percentage:

  1. anomaly_z: a real, live-computed number. patterns/anomaly/detector.py's own
     per-symbol model, scored directly here so we see the value even when it's below
     that detector's alert threshold ("how many standard deviations is today's move
     from this stock's own recent typical day").
  2. historical: a real local backtest. Re-runs the exact same free pattern engine
     bar-by-bar over this stock's own already-fetched price history to find every past
     day its currently-confirmed pattern also fired, then looks at what actually
     happened next via the existing history/outcomes + history/statistics modules
     (sample size, median return, % positive/negative — with an automatic small-sample
     warning baked into those modules already). This is a live per-symbol backtest,
     not the offline dataset the ml_trainer subsystem builds separately (which needs a
     build-data run this VM likely hasn't done yet).
  3. llm_analysis: the LLM's qualitative read of both of the above plus recent news —
     possible scenarios and risks in plain language. The router already refuses any
     response using certainty language ("will go up", "guaranteed") — see
     intelligence/llm/validation.py — so this never reports a bare probability either.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.domain.history import HistoricalSetup, HistoricalSummary, OutcomeRecord
from app.domain.llm import LLMAnalysis
from app.domain.market import IndexSnapshot, Instrument, OHLCVBar
from app.domain.patterns import DetectedPattern
from data.providers.rss_news_provider import RssNewsProvider
from history.outcomes.calculator import compute_outcome
from history.statistics.summary import summarize
from intelligence.llm.evidence_builder import build_evidence
from intelligence.llm.router import LLMRouter
from market.analytics.context import MarketContext, build_context
from market.analytics.price_volume import build_snapshot
from market.strategies.profile import StrategyProfile
from ml.models.anomaly.model import AnomalyModel
from patterns.anomaly.detector import bar_features
from patterns.engine.base import PatternEngine

BACKTEST_HORIZONS = ("5d", "10d")
_MIN_WARMUP_BARS = 25  # matches dashboard/service.py's own "not enough history" floor
_ANOMALY_MIN_TRAINING_BARS = 30


async def _fetch_feed(url: str) -> str:
    """Minimal transport for RssNewsProvider — nothing in the live service wired one
    in yet (same gap as the LLM router had before scripts/run_service.py used it)."""
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _anomaly_zscore(bars: list[OHLCVBar]) -> tuple[float, list[tuple[str, float]]] | None:
    """Same scoring as patterns/anomaly/detector.py's detect_anomaly_event, but
    returns the raw number instead of gating it behind an alert threshold."""
    if len(bars) < _ANOMALY_MIN_TRAINING_BARS + 1:
        return None
    training_bars = bars[:-1]
    training_features = [
        bar_features(training_bars[i - 1].close, training_bars[i])
        for i in range(1, len(training_bars))
    ]
    if len(training_features) < _ANOMALY_MIN_TRAINING_BARS - 1:
        return None
    model = AnomalyModel.fit(training_features, ("bar_return_pct", "volume"))
    latest = bar_features(bars[-2].close, bars[-1])
    score = model.score(latest)
    return score.combined_z, list(score.top_contributors())


def _local_pattern_history(
    instrument: Instrument,
    bars: list[OHLCVBar],
    index_series: list[IndexSnapshot],
    family: str,
    pattern_engine: PatternEngine,
) -> HistoricalSummary | None:
    """Scans this stock's own history for earlier days `family` was confirmed, using
    an index snapshot per day (dashboard/service.py.fetch_index_series) so each day's
    MarketContext is reconstructed the same way the live pipeline would have seen it
    at the time — no lookahead into future index values."""
    max_horizon = max(int(h[:-1]) for h in BACKTEST_HORIZONS)
    outcomes_by_horizon: dict[str, list[OutcomeRecord]] = {h: [] for h in BACKTEST_HORIZONS}
    index_by_date = {s.timestamp.date(): s for s in index_series}

    for i in range(_MIN_WARMUP_BARS, len(bars) - max_horizon):
        window = bars[: i + 1]
        market_index_i = index_by_date.get(window[-1].timestamp.date())
        if market_index_i is None:
            continue
        try:
            snapshot_i = build_snapshot(window)
        except Exception:  # noqa: BLE001 — skip a malformed window, don't abort the scan
            continue
        context_i = build_context(
            stock_change_pct=snapshot_i.price_change_pct or 0.0, market_index=market_index_i,
            sector_index=None,
        )
        patterns_i = pattern_engine.run(instrument, snapshot_i, context_i, window[-1].timestamp)
        if not any(p.family.value == family and p.confirmed for p in patterns_i):
            continue

        setup = HistoricalSetup(
            instrument=instrument, timestamp=window[-1].timestamp, price=window[-1].close,
            volume=window[-1].volume, relative_volume=snapshot_i.relative_volume,
            volatility=None, trend=None, rsi=snapshot_i.rsi_14, vwap=snapshot_i.vwap,
            market_state=context_i.regime.value, sector_state=None, pattern=family,
            event_context=None, dataset_version="dashboard-local-backtest-v1",
        )
        forward_bars = bars[i + 1:]
        for horizon in BACKTEST_HORIZONS:
            outcome = compute_outcome(setup, forward_bars, horizon)
            if outcome is not None:
                outcomes_by_horizon[horizon].append(outcome)

    if sum(len(v) for v in outcomes_by_horizon.values()) == 0:
        return None
    return summarize(
        setup_criteria=f"{family} confirmed ({instrument.symbol}'s own history)",
        outcomes_by_horizon=outcomes_by_horizon,
    )


@dataclass
class HybridAnalysis:
    symbol: str
    computed_at: datetime
    anomaly_z: float | None
    anomaly_contributors: list[tuple[str, float]]
    historical: HistoricalSummary | None
    historical_family: str | None
    news_count: int
    llm_analysis: LLMAnalysis | None
    used_llm: bool
    error: str | None = None
    routing_events: list[dict] | None = None  # what each provider actually said — see below


async def run_analysis(
    instrument: Instrument,
    bars: list[OHLCVBar],
    index_series: list[IndexSnapshot],
    snapshot,
    context: MarketContext,
    patterns: list[DetectedPattern],
    pattern_engine: PatternEngine,
    llm_router: LLMRouter | None,
) -> HybridAnalysis:
    now = datetime.now(timezone.utc)
    anomaly = _anomaly_zscore(bars)
    anomaly_z, contributors = anomaly if anomaly else (None, [])

    confirmed = [p for p in patterns if p.confirmed]
    historical: HistoricalSummary | None = None
    family: str | None = None
    if confirmed:
        family = confirmed[0].family.value
        historical = _local_pattern_history(instrument, bars, index_series, family, pattern_engine)

    news: list[dict] = []
    try:
        news = await RssNewsProvider(_fetch_feed).get_news(instrument, now - timedelta(days=7))
    except Exception:  # noqa: BLE001 — a dead feed shouldn't block the rest of the analysis
        news = []

    if llm_router is None:
        return HybridAnalysis(
            instrument.symbol, now, anomaly_z, contributors, historical, family, len(news),
            None, False,
            error="No GROQ_API_KEYS/CEREBRAS_API_KEYS configured — showing the ML/historical "
                  "numbers only.",
        )

    risk_flags = [f"unusual move vs own history (z={anomaly_z:.2f})"] if anomaly_z and anomaly_z >= 2.5 else []
    evidence = build_evidence(
        instrument, snapshot, context, patterns, historical_summary=historical, news=news,
        risk_flags=risk_flags,
    )
    # LLMRouter.analyze() already records WHY each provider failed (bad key, rate
    # limit, validation error) in its failover_log — it was just never surfaced past
    # "all LLM providers were unavailable" before. Slice only what this call adds,
    # since the router instance is long-lived and its log keeps growing.
    log_start = len(llm_router.failover_log)
    try:
        analysis, used_llm = await llm_router.analyze("stock_analysis", evidence.to_payload())
    except Exception as exc:  # noqa: BLE001 — surface the failure, don't 500 the page
        return HybridAnalysis(
            instrument.symbol, now, anomaly_z, contributors, historical, family, len(news),
            None, False, error=f"LLM analysis failed: {exc}",
        )
    routing_events = [
        {"provider": e.provider_attempted, "outcome": e.outcome, "detail": e.detail}
        for e in llm_router.failover_log[log_start:]
    ]

    return HybridAnalysis(
        instrument.symbol, now, anomaly_z, contributors, historical, family, len(news),
        analysis, used_llm, routing_events=routing_events,
    )
