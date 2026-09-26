# DataBroker — Azure Deployment

Azure is the primary runtime environment, kept strictly behind `infrastructure/azure/` — no
Azure-specific code appears in `market/`, `patterns/`, `history/`, `opportunity/`, `ml/`, or
`intelligence/`.

## Services (deployed separately, low-cost by design)

1. **Real-time service** — long-running, lightweight: WebSocket ingestion, live analytics, event
   detection, alert triggering. Sized to stay responsive; never runs training or heavy backtests.
2. **Batch/historical service** — scheduled or on-demand: dataset builds, backtests, statistics,
   ML training. Can scale up/down independently since it's not latency-critical.
3. **LLM/research service** — handles routing, provider calls, and research synthesis. Isolated so
   LLM latency or an outage never stalls real-time monitoring.
4. **Notification service** — Telegram delivery and command handling, with its own retry/queue.

## Storage

- Operational database (managed Postgres or equivalent) shared by all services.
- Analytical storage (Blob Storage, Parquet, partitioned by date/symbol) for large historical
  datasets and backtest artifacts — kept out of the operational DB.

## Environments

`DEPLOY_ENV=local|staging|production` selects environment-specific settings; secrets are provided
via Azure Key Vault (or environment injection locally via `.env`), never committed.

## Cost posture

Given limited budget: prefer consumption/serverless tiers for the batch and LLM services where
practical, keep the real-time service minimally sized but always-on, and avoid provisioning GPU
or heavy compute until a specific ML task justifies it (Phase 5).

## Verification checklist (end of Phase 1)

- [ ] Configuration loads and validates in each environment
- [ ] Database reachable and migrated
- [ ] Market-session logic returns correct trading/non-trading days
- [ ] Provider interfaces instantiate against stub/mock implementations
- [ ] Telegram connectivity confirmed (bot responds to a ping)
- [ ] Each of the four services starts independently
- [ ] `/status` reports health for feed, DB, Telegram, and configured LLM providers
