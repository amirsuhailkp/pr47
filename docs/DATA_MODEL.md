# DataBroker — Data Model

All timestamps are timezone-aware. Internal storage uses UTC; presentation to the user uses IST.
Naive `datetime` objects are disallowed by lint rule and code review.

## Core market objects (`app/domain/market.py`)

**Instrument** — symbol, exchange, isin, sector, industry, lot_size, is_active, universe_flags.

**Quote** — instrument, ltp, bid, ask, timestamp, source, ingestion_timestamp, data_quality.

**Trade** — instrument, price, quantity, timestamp, source, ingestion_timestamp.

**OHLCVBar** — instrument, interval, open, high, low, close, volume, timestamp (bar start),
timezone, source, ingestion_timestamp, is_partial, data_quality.

**VolumeStatistics** — instrument, avg_volume(n), relative_volume, volume_acceleration, as_of.

**MarketIndex / SectorIndex** — index code, value, change, change_pct, timestamp, source.

Every record above carries: `symbol`, `exchange`, `timestamp`, `timezone`, `source`,
`ingestion_timestamp`, `data_quality` (OK / STALE / SUSPECT / MISSING). Consumers must check
`data_quality` before treating a record as current.

## Event & pattern objects (`patterns/`, `alerts/`)

**DetectedPattern** — pattern_family (momentum/breakout/pullback/...), instrument, timestamp,
supporting_evidence (list of named signals with values), confirmation_state,
market_context_snapshot, sector_context_snapshot.

**MarketEvent** — category (PRICE/VOLUME/TECHNICAL/NEWS/MARKET), instrument, detected_at,
magnitude, description, severity (INFO/WATCH/IMPORTANT/CRITICAL), source_signals.

**AlertRecord** — event or candidate reference, severity, dedup_key, cooldown_until,
delivered_at, channel, payload (the structured object actually sent).

## Candidate / evidence objects (`opportunity/`)

**CandidateEvidence** — instrument, generated_at, reasons (list of named, signed factors, e.g.
"+ relative volume 3.4×"), risks (list of named factors), historical_reference
(HistoricalSummary or null), news_reference(s). No candidate may exist without at least one
reason and an explicit risk list (possibly empty but present).

## Historical objects (`history/`)

**HistoricalSetup** — symbol, timestamp, price, volume, relative_volume, volatility, trend, RSI,
VWAP, market_state, sector_state, pattern, event/news context, dataset_version.

**OutcomeRecord** — setup reference, horizon (5m/15m/30m/1h/1d/3d/5d/10d/20d), return_pct,
max_favorable_excursion, max_adverse_excursion, realized_volatility, market_regime_at_horizon.

**HistoricalSummary** — setup criteria, sample_size, per-horizon: median_return, mean_return,
positive_frequency, negative_frequency, distribution_summary, mfe, mae, regime_breakdown,
uncertainty_note. Never collapsed to a single percentage.

**DatasetManifest** — dataset_version, source, created_at, date_range, universe_definition,
feature_schema, label_definition, configuration_snapshot, content_hash. Required on every stored
dataset; datasets without a manifest are invalid and must not be used.

## LLM objects (`intelligence/`)

**LLMRequest** — task_type, structured_evidence (never raw prompts to "predict"), model_hint,
token_budget.

**LLMAnalysis** (validated structured output) — summary, observations[], patterns[],
historical_context{}, possible_scenarios[], risk_factors[], invalidation_conditions[],
uncertainty[], missing_information[]. Failing validation triggers retry → alternate
provider/model → deterministic fallback, in that order.

## Storage

- **Operational DB** (Postgres or equivalent): instruments, watchlists, alerts, events, analyses,
  provider health, LLM usage, configuration, historical metadata, model metadata.
- **Analytical storage** (Parquet / partitioned files / blob storage): large historical
  datasets, backtest outputs, bar archives. Large analytical data does not belong in the
  operational DB.

## Leakage prevention (applies to every historical/ML dataset)

No random train/test splits, no future data in features, no future news, survivorship bias
minimized where feasible, no overlapping-label leakage. Chronological and walk-forward
validation with purge/embargo where needed. Automated leakage tests are part of CI
(see TESTING.md).
