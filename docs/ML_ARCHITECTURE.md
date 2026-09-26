# DataBroker — ML Architecture

ML is an optional analytical tool, not the center of DataBroker. There is no single "will this
stock go up" model. A model is only built when there's a clearly scoped, independently
answerable problem.

## Candidate model tasks

1. Anomaly detection
2. Pattern classification
3. Historical similarity
4. Outcome-distribution estimation
5. Candidate ranking
6. Market-regime detection

Each is trained, evaluated and versioned independently under `ml/models/<task>/`.

## Required for every model

- Feature schema (versioned, linked to `DatasetManifest`)
- Target definition
- Training data definition (date range, universe, source)
- Chronological / walk-forward validation — never random splits on time-series data
- A baseline to beat (e.g. a simple deterministic rule)
- Leakage tests (automated, part of CI — see TESTING.md)
- Calibration where the output is a probability/confidence
- Uncertainty reporting alongside any prediction
- Version, training metadata, and full reproducibility from the manifest

A model is not promoted to production because it scored well on a random-split test; it must
clear chronological/walk-forward validation and leakage checks first.

## Registry

`ml/registry/` tracks model versions, their manifests, validation results, and current
production/candidate status. Promotion is a deliberate, logged action — not automatic on
training completion.

## Relationship to the rest of the pipeline

ML sits after historical/pattern analysis and before LLM interpretation:
```
... → HISTORICAL ANALYSIS → OPPORTUNITY DISCOVERY → OPTIONAL ML → LLM INTELLIGENCE → ...
```
ML outputs (e.g. an anomaly score or a similarity match) become additional structured evidence for
the LLM to explain — they are never sent to the user as a bare, unexplained number.
