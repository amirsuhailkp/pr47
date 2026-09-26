# DataBroker — Testing

Testing is mandatory, written alongside functionality, not retrofitted.

## Coverage areas

- Data normalization and canonical model construction
- Timestamp/timezone handling (no naive datetimes reach storage)
- Market session engine (trading days, holidays, pre-open/close)
- Indicator calculations (known-input/known-output cases)
- Pattern detection (momentum/breakout/pullback fixtures)
- Historical calculations and outcome statistics
- Leakage prevention (chronological split integrity, no future-feature leakage)
- Alert deduplication and cooldown behavior
- Telegram message formatting
- LLM routing and structured-output validation
- Provider failover (market data and LLM)
- Rate-limit / `Retry-After` handling
- Stale-data detection and the "do not alert on stale data" rule
- Database access and migrations
- Configuration validation (missing/invalid keys fail startup)
- API failure handling for every external provider

## Test types

- **Unit tests** — required for all critical components (indicators, session engine, dedup logic,
  validators, config loading).
- **Integration tests** — required for critical workflows: ingestion → normalization → storage,
  event → alert → Telegram, LLM request → validation → fallback.

## Leakage tests specifically

Automated checks that: training windows never see post-window data, labels don't overlap in a way
that leaks information across the train/validation boundary, and walk-forward splits are strictly
chronological. These run in CI on every change touching `history/` or `ml/`.

## Secrets in tests

No real credentials in test fixtures or CI logs. Provider adapters are tested against mocks/stubs;
a separate, manually-run integration check may exercise real sandbox credentials if available.
