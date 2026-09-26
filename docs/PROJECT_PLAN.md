# DataBroker — Project Plan

This is a from-scratch project. It does not reuse or migrate the prior `data` repository's
architecture; only general ideas may carry over where they are still technically sound.

## Development rules

1. Keep modules small; avoid giant files.
2. No circular dependencies.
3. Typed interfaces at every provider boundary; dependency injection for externals.
4. Business logic stays independent of vendor SDKs.
5. Configuration is explicit — no hard-coded thresholds like the ₹50/₹300 universe bounds.
6. Failures are observable, not swallowed.
7. Core calculations (indicators, patterns, historical stats) are deterministic and reproducible.
8. LLM functionality is always optional; the system is fully functional without it.
9. No hidden global state, no magic numbers.
10. Tests are written alongside functionality, not after.
11. **No giant `agent.py`.** Market data, ML, LLM, Telegram, database and news stay in separate
    services. An orchestration layer may coordinate them but must not absorb their logic.
12. **No blind scoring.** Any ranking must expose the reasons behind it (see ALERT_ARCHITECTURE.md
    and DATA_MODEL.md `CandidateEvidence`).
13. **No false certainty.** Outputs describe evidence, scenarios, risk and uncertainty — never a
    guaranteed direction.

## Phases

Each phase must be stable — tests passing, run locally, manually verified — before the next
phase starts. Phase 6 is not touched while Phase 1 is unstable.

### Phase 1 — Foundation
- Repository structure (this scaffold)
- Configuration system (`app/config`, `.env` / `.env.example`)
- Canonical domain models (`app/domain`)
- Operational database + migrations
- Market universe definition (configurable price/liquidity bounds)
- Market session engine (NSE calendar, IST-aware)
- Provider interfaces (no concrete vendor logic yet beyond a minimal Telegram ping)
- Azure runtime skeleton (four services stubbed)
- Basic structured logging
- `/status` health check (skeleton)

### Phase 2 — Real-time market intelligence ✅ (scaffolded, deterministic path complete)
- ✅ Real-time ingestion buffer — dedup, out-of-order, staleness (`data/ingestion/buffer.py`)
- ✅ Reconnecting stream client — backoff, never fabricates data on failure (`data/ingestion/stream_client.py`)
- ✅ Core indicators — SMA/EMA, RSI, ATR, VWAP, rolling return, drawdown, breakout distance (`market/indicators/core.py`)
- ✅ Price/volume analytics snapshot, relative volume, volume acceleration (`market/analytics/price_volume.py`)
- ✅ Market/sector context + relative strength + regime classification (`market/analytics/context.py`)
- ✅ Momentum, breakout, pullback detectors + extensible pattern engine (`patterns/`)
- ✅ Important-event detection — price/volume/technical/market (`patterns/engine/events.py`)
- ✅ Alert engine — severity gate, dedup, cooldown (`alerts/engine/`, `alerts/deduplication/`)
- ✅ Telegram formatter (formatting only, no analysis logic) (`alerts/telegram/formatter.py`)
- ✅ End-to-end deterministic pipeline with no LLM dependency (`app/orchestration/pipeline.py`)
- ⬜ Actual market-data provider adapter (still behind `MarketDataProvider` — needs a real vendor integration)
- ⬜ Wiring the pipeline into the always-on real-time service process

### Phase 3 — Historical intelligence ✅ (scaffolded, deterministic path complete)
- ✅ Historical domain models — setup, outcome, horizon/summary, manifest (`app/domain/history.py`)
- ✅ Dataset store requiring a valid `DatasetManifest`, version-checked (`history/datasets/store.py`)
- ✅ Similarity search over stored setups, explainable normalized-distance ranking (`history/similarity/matcher.py`)
- ✅ Outcome calculation across horizons, with a runtime leakage guard on forward bars (`history/outcomes/calculator.py`)
- ✅ Outcome-distribution statistics — sample size, median/mean, pos/neg frequency, MFE/MAE, regime breakdown, uncertainty notes on thin samples — never a single percentage (`history/statistics/summary.py`)
- ✅ Chronological split, walk-forward splits, purge/embargo (`history/backtest/validation.py`)
- ✅ Automated leakage tests — temporal overlap, duplicate items, forward-only outcomes, undeclared features (`history/backtest/leakage_tests.py`)
- ⬜ Durable dataset storage (Parquet/blob) — still in-memory
- ⬜ Strategy research harness (hypothesis → setup → historical test → limitations doc) — **partially done**, see "Strategy profiles" below; still missing the historical-test step itself
- ⬜ Wiring the historical engine into the opportunity/candidate pipeline

### Phase 4 — LLM intelligence ✅ (scaffolded, deterministic path complete)
- ✅ `GroqProvider` / `CerebrasProvider` behind `LLMProvider`, network abstracted via an injectable transport (`intelligence/llm/providers.py`)
- ✅ Multi-key `CredentialPool` per provider — Retry-After aware, exponential backoff, never a rate-limit bypass (`intelligence/llm/credentials.py`)
- ✅ `LLMRouter` — task-tier classification, per-provider validation retry, ordered failover, full routing/failover log (`intelligence/llm/router.py`)
- ✅ Structured-output validation — required fields, types, and a false-certainty language filter ("will go up", "guaranteed", ...) (`intelligence/llm/validation.py`)
- ✅ Deterministic fallback — builds an `LLMAnalysis` straight from evidence with zero model calls when every provider fails (`intelligence/llm/fallback.py`)
- ✅ Evidence builder — converts Phase 2/3 snapshots, context, patterns and historical summaries into the LLM payload; no free-text generation (`intelligence/llm/evidence_builder.py`)
- ✅ News normalization — drops any item missing provenance (source/timestamp/symbol) before it can reach the LLM as "news" (`intelligence/research/news_synthesis.py`)
- ✅ End-to-end test: pattern detection → evidence → router → validated analysis, with no network dependency
- ⬜ Real `transport` implementation (httpx call to Groq/Cerebras chat-completions endpoints) — only the interface + a fake transport exist so far
- ⬜ Wiring LLM-enriched alerts into the Telegram formatter (today's formatter only renders deterministic `AlertRecord`s from Phase 2)
- ⬜ Model registry (available models per provider, capability metadata)

### Phase 5 — ML ✅ (registry + lifecycle discipline complete; 2 of 6 tasks implemented)
- ✅ Model lifecycle domain models — `ModelManifest`, `ValidationResult`, `RegistryEntry` (`app/domain/ml.py`)
- ✅ `ModelRegistry` — promotion is deliberate and gated: requires a `ValidationResult` that passed leakage tests *and* beat its baseline; promoting a new version auto-retires the old one (`ml/registry/registry.py`)
- ✅ **Anomaly detection** (task 1/6) — per-feature z-score model with a required `BaselineAnomalyModel` (single-feature threshold) to beat, explainable per-feature contributions on every score (`ml/models/anomaly/`)
- ✅ **Candidate ranking** (task 5/6) — explicit, config-driven weights with a mandatory `EqualWeightBaselineRanking`; every score exposes its full contribution breakdown, never a bare number (`ml/models/ranking/`)
- ✅ Training harness — chronological split, an automated leakage check gate, baseline-vs-model precision@k comparison, full manifest + validation output (`ml/training/train_anomaly.py`)
- ✅ End-to-end lifecycle test: synthetic data → chronological train/validate → model beats baseline → registry promotion → promoted model scores a live example explainably
- ⬜ **Pattern classification** (task 2/6) — not yet implemented
- ⬜ **Historical similarity as a scored ML task** (task 3/6) — today `history/similarity/matcher.py` is a deterministic baseline only, not a trained/versioned model
- ⬜ **Outcome-distribution estimation** (task 4/6) — today `history/statistics/summary.py` is the deterministic baseline only
- ⬜ **Market-regime detection** (task 6/6) — today `market/analytics/context.classify_regime` is the deterministic baseline only
- ⬜ Feature-store wiring (`ml/features/` is still an empty package — Phase 2/3 objects are converted ad hoc per model today)

### Integration/wiring pass (post-Phase 5) ✅
Closed several accumulated "still open" gaps rather than starting Phase 6 early —
docs §41 explicitly says Phase 6 waits until earlier phases are stable, and a working
end-to-end path is a better stability signal than more standalone modules.
- ✅ Operational database — SQLAlchemy models for instruments, watchlist entries, alerts, provider health, LLM usage; `init_db()` for local/dev (a real Alembic migration path is still the production TODO) (`data/storage/`)
- ✅ Repository layer — `WatchlistRepository`, `AlertRepository`, translating domain objects to/from ORM rows so business logic never imports SQLAlchemy directly (`data/storage/repositories.py`)
- ✅ `TelegramNotifier` implementing `NotificationProvider`, network abstracted behind an injectable transport like the LLM providers (`alerts/telegram/notifier.py`)
- ✅ `DeliveryQueue` — queues and retries failed Telegram sends with exponential backoff instead of dropping them (docs §48) (`alerts/telegram/delivery_queue.py`)
- ✅ `CommandRouter` — clean registration point for `/status`, `/analyze`, etc., with only routing logic, no formatting (`alerts/telegram/commands.py`)
- ✅ `RealTimeService` — the actual wiring: pipeline evaluation → persistence → delivery attempt → queue-and-retry on failure (`app/orchestration/realtime_service.py`)
- ✅ End-to-end test covering both the delivery-succeeds and delivery-fails-then-retries paths against a real (in-memory) SQLite database
- ⬜ Still open: real market-data provider adapter, real LLM HTTP transport, real Telegram HTTP transport (all three now have a proven interface + fake-transport test pattern to follow), Alembic migrations, Azure deployment wiring

### Strategy profiles ✅
Two concrete, documented strategies (docs §24 shape) rather than one hard-coded set
of pattern thresholds — each with its own bar interval, thresholds, and alert cadence:
- ✅ `StrategyDefinition` — hypothesis, setup, confirmation, invalidation, required data, costs/slippage notes, liquidity assumptions, limitations, all required non-empty (`app/domain/strategy.py`)
- ✅ `StrategyProfile` — the operational bundle a definition maps to: bar interval, lookback window, per-detector thresholds, alert cooldown, minimum severity (`market/strategies/profile.py`)
- ✅ **Scalping** — 5-minute bars, tight thresholds (0.3% move / 1.2x volume), 5-minute alert cooldown (`market/strategies/scalping.py`)
- ✅ **Swing** — daily bars, the original wider thresholds (2.0% move / 1.5x volume), 4-hour alert cooldown (`market/strategies/swing.py`)
- ✅ `build_pipeline_from_profile()` — constructs a `MonitoringPipeline` wired to a given profile's detectors/cooldown (`app/orchestration/pipeline.py`)
- ✅ `/strategy` Telegram command — lists strategies, or shows a strategy's full definition text (`alerts/telegram/handlers.py`)
- ✅ `scripts/run_local_test.py --strategy {scalping,swing}` — runs the free-provider test setup against either profile
- ⬜ Neither profile has been run through `history/backtest/` yet — thresholds are hand-set starting hypotheses, not validated against Indian-market history (each definition's `limitations` field says so explicitly)
- ⬜ No sector-rotation, options, or futures strategy profiles yet — just these two equity styles

### Temporary testing providers ✅
Real (non-fake) provider adapters for free/keyless-or-cheap sources, so the whole
pipeline can be exercised end to end before a broker account is set up:
- ✅ `IndianApiMarketDataProvider` — IndianAPI.in, polling-based (REST, not WebSocket — a documented stand-in until a real broker feed is wired in) (`data/providers/indianapi_provider.py`)
- ✅ `YFinanceHistoricalProvider` — free daily-bar backfill via `yfinance`, no API key (`data/providers/yfinance_provider.py`)
- ✅ `RssNewsProvider` — BSE notices RSS + per-symbol Google News RSS, no API key; output shape matches `intelligence/research/news_synthesis.normalize_news_items` with zero changes needed there (`data/providers/rss_news_provider.py`)
- ✅ `scripts/run_local_test.py` — wires all three into the real `MonitoringPipeline` + `RealTimeService`, backfilling ~120 daily bars per symbol, running real pattern/event detection, and attempting real Telegram delivery
- All three follow the same injectable-transport pattern as the LLM/Telegram providers, so they're fully unit-tested without hitting IndianAPI.in, Yahoo Finance, BSE, or Google News from CI
- ⬜ Not yet real: the true intraday/WebSocket broker feed this is standing in for; BSE's per-scrip announcement feed (only the exchange-wide notices feed is wired, since the per-symbol URL pattern wasn't confirmed)

### Phase 6 — Advanced features
- Deeper research, more strategies, personalization, dashboard, additional data providers

## First implementation task (this pass)

1. ✅ Create architecture documents (this file and the nine siblings listed below)
2. ✅ Create the project skeleton
3. → Configuration schema
4. → Canonical domain/data models
5. → Provider interfaces
6. → Test structure
7. → Implement Phase 1

Sibling docs: DATA_MODEL.md, CONFIGURATION.md, LLM_ARCHITECTURE.md, ALERT_ARCHITECTURE.md,
ML_ARCHITECTURE.md, AZURE_DEPLOYMENT.md, TELEGRAM.md, TESTING.md.

## Git discipline

Small, sequential commits — one concern each: foundation → configuration → data models →
database → market provider abstraction → session engine → real-time ingestion → analytics →
patterns → alerts → Telegram → historical engine → LLM router → ML framework → Azure deployment.
Never one massive commit for the whole system.
