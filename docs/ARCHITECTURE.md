# DataBroker — Architecture

## 1. Purpose

DataBroker is a personal market-intelligence system for the Indian stock market (NSE, main-board
equities, initially priced roughly ₹50–₹300 but never hard-coded to that range). It watches the
market, detects meaningful changes, checks them against history, and explains what it found over
Telegram. It never places trades and never asserts a guaranteed outcome — it produces evidence,
scenarios, risks and invalidation conditions, and leaves the decision to the user.

## 2. Guiding principles

- **Deterministic core, optional intelligence.** Indicators, patterns and alerts must work with
  every LLM provider offline. The LLM explains evidence; it never invents it.
- **Provider isolation.** Every external dependency (market data, news, LLMs, Telegram, Azure)
  sits behind an interface in `app/domain` or a `*/providers` package. Nothing outside that
  boundary imports a vendor SDK directly.
- **Explainability over scoring.** No unexplained numeric score reaches the user. Every ranked
  candidate carries the reasons and the risks that produced it.
- **Auditability.** Every historical dataset and every alert must be reproducible from stored
  configuration, source data and code version.
- **Cost discipline.** The pipeline is tick → deterministic analysis → event → (optional) LLM →
  Telegram, never tick → LLM.
- **Small modules.** No module owns more than one responsibility; no orchestrator becomes a
  god-object (see "no giant agent.py" in PROJECT_PLAN.md).

## 3. Layered pipeline

```
DATA SOURCES → INGESTION → NORMALIZATION → STORAGE → MARKET ANALYTICS
  → EVENT/PATTERN DETECTION → HISTORICAL ANALYSIS → OPPORTUNITY DISCOVERY
  → OPTIONAL ML → LLM INTELLIGENCE → ALERT ENGINE → TELEGRAM
```

Each arrow is a module boundary with a typed contract (see DATA_MODEL.md). A layer may only call
the layer(s) directly below it through those contracts — never reach across layers or back up the
chain.

## 4. Package map

| Package | Responsibility |
|---|---|
| `app/` | Composition root: config loading, domain contracts, service wiring, orchestration entry points |
| `data/` | Ingestion, normalization, provider adapters, storage, schemas |
| `market/` | Universe selection, session calendar, indicators, analytics, sector/regime context |
| `patterns/` | Momentum, breakout, pullback (v1) and the extensible pattern engine |
| `history/` | Historical datasets, similarity search, outcome statistics, backtesting |
| `opportunity/` | Candidate discovery, ranking, evidence assembly |
| `ml/` | Optional models — anomaly detection, similarity, ranking, regime — each independently scoped |
| `intelligence/` | LLM providers, router, prompts, research/news synthesis |
| `alerts/` | Rules, severity, deduplication, Telegram formatting/sending |
| `infrastructure/` | Azure runtime wiring, deployment config |
| `cli/` | Local operator commands (status, backfill, replay) |
| `tests/`, `scripts/`, `docs/` | Support |

## 5. Runtime services (Azure)

Four independently deployable processes, so heavy work never blocks real-time monitoring:

1. **Real-time service** — WebSocket ingestion, normalization, live analytics, event detection,
   alert triggering. Kept lightweight; no training, no heavy backtests.
2. **Batch/historical service** — dataset builds, backtests, statistics, ML training.
3. **LLM/research service** — routes explanation and research requests, isolated so provider
   outages or latency never stall market monitoring.
4. **Notification service** — Telegram delivery, command handling, retry/queueing.

All four share the operational database and, for large historical data, partitioned Parquet/blob
storage (see DATA_MODEL.md §Storage).

## 6. Provider interfaces (defined in `app/domain`)

`MarketDataProvider`, `NewsProvider`, `CompanyDataProvider`, `HistoricalDataProvider`,
`LLMProvider`, `NotificationProvider`. Concrete adapters live under `data/providers/`,
`intelligence/llm/`, and `alerts/telegram/`. Business logic depends only on these interfaces.

## 7. Failure behavior (summary — see individual docs for detail)

- Market feed down → reconnect, then mark unhealthy; never fabricate data.
- Telegram down → queue and retry.
- One LLM provider down → failover to another authorized provider/model.
- All LLM providers down → deterministic analysis and alerts continue unaffected.
- No historical data → never claim historical evidence exists.
- Database down → fail safely, preserve critical runtime state where possible.

## 8. What this document does not cover

Field-level schemas → DATA_MODEL.md. Config keys → CONFIGURATION.md. LLM routing/failover →
LLM_ARCHITECTURE.md. Alert severity/dedup → ALERT_ARCHITECTURE.md. Model lifecycle →
ML_ARCHITECTURE.md. Deployment topology → AZURE_DEPLOYMENT.md. Bot commands → TELEGRAM.md. Test
strategy → TESTING.md. Phasing → PROJECT_PLAN.md.
