# DataBroker — Alert Architecture

## Severity

`INFO`, `WATCH`, `IMPORTANT`, `CRITICAL` — thresholds and mapping from event type → severity are
config-driven (`ALERT_SEVERITY_THRESHOLDS`), not hard-coded per pattern.

## Pipeline

```
MarketEvent / DetectedPattern / Candidate
  → severity classification
  → deduplication (dedup_key)
  → cooldown check
  → aggregation (batch related sub-events)
  → priority ordering
  → (optional) LLM interpretation
  → AlertRecord
  → TelegramNotifier
```

Not every event reaches Telegram — only those clearing the configured severity/dedup/cooldown
gates. The Telegram layer (`alerts/telegram/`) contains no market-analysis logic; it receives a
fully-formed structured `AlertRecord` and formats/sends it.

## No blind scoring

If a candidate or alert is ranked, the ranking is never an opaque number. Every ranked item
carries its reasons (positive factors) and risks (negative factors) — see `CandidateEvidence` in
DATA_MODEL.md. Example shape:

```
XYZ
Reasons:
  + high relative volume
  + positive relative strength
  + breakout proximity
Risks:
  - high volatility
  - small historical sample
```

## No false certainty

Alert language describes evidence and scenarios, never guarantees:
"historical cases with similar characteristics showed…", "current evidence suggests…",
"sample size is small…", "insufficient evidence" (a valid, expected output — not a failure).

## Example alert shape

```
⚠️ IMPORTANT ACTIVITY
XYZ — NSE
Price: ₹184.60   Change: +4.72%
Relative Volume: 3.4×   Trend: Positive
Sector: +1.8%   Market: +0.9%
Pattern: Momentum + Breakout Attempt
Historical Cases: 127
Historical Context: 1D: ...  3D: ...  5D: ...
Why it matters: <plain-language explanation>
Risks: • failed breakout • declining volume • broader market reversal
This is market analysis, not a guaranteed outcome.
```

## Deduplication & cooldown

Each alert has a `dedup_key` derived from (instrument, event category, pattern) and a
`cooldown_until`. Repeated firing of the same underlying condition within the cooldown window is
suppressed, not re-sent. Aggregation groups closely-related sub-events into one message instead of
spamming several.

## Failure behavior

Telegram delivery failure → queue and retry (never drop silently). See ARCHITECTURE.md §7 for the
system-wide failure table.
