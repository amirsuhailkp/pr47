from datetime import datetime, timedelta, timezone

from ml.registry.registry import ModelRegistry
from ml.training.train_anomaly import TrainingExample, train_and_validate_anomaly_model

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = ("price_change_pct", "relative_volume")


def _train_examples(n: int, start_idx: int) -> list[TrainingExample]:
    """Typical, unremarkable days — used only to fit the model's baseline distribution."""
    out = []
    pcs = [0.8, 1.0, 1.2]
    rvs = [0.9, 1.0, 1.1]
    for i in range(n):
        out.append(
            TrainingExample(
                timestamp=BASE + timedelta(days=start_idx + i),
                features={"price_change_pct": pcs[i % 3], "relative_volume": rvs[i % 3]},
                forward_return_pct=0.2,
            )
        )
    return out


def _test_examples(start_idx: int) -> list[TrainingExample]:
    """4 genuine anomalies (extreme price move, unremarkable volume) mixed with 8
    'volume-noisy' negatives that a volume-only baseline would rank above them."""
    out = []
    for i in range(4):
        out.append(
            TrainingExample(
                timestamp=BASE + timedelta(days=start_idx + i),
                features={"price_change_pct": 10.0, "relative_volume": 1.0},
                forward_return_pct=8.0,
            )
        )
    for i in range(8):
        out.append(
            TrainingExample(
                timestamp=BASE + timedelta(days=start_idx + 4 + i),
                features={"price_change_pct": 1.0, "relative_volume": 2.5},
                forward_return_pct=0.5,
            )
        )
    return out


def test_anomaly_model_beats_baseline_and_gets_promoted():
    train = _train_examples(28, start_idx=0)
    test = _test_examples(start_idx=28)
    examples = train + test  # already chronological

    model, manifest, validation = train_and_validate_anomaly_model(
        examples,
        feature_schema=SCHEMA,
        model_version="anomaly-v1",
        anomaly_return_threshold_pct=5.0,
        top_k=4,
        train_fraction=0.7,
    )

    # The combined-feature model should catch the price-driven anomalies that a
    # volume-only baseline misses (the negatives have deliberately elevated volume).
    assert validation.model_metric > validation.baseline_metric
    assert validation.leakage_tests_passed is True
    assert validation.eligible_for_promotion is True

    registry = ModelRegistry()
    registry.register(manifest, validation)
    registry.promote("anomaly_detection", "anomaly-v1")

    production = registry.production_model("anomaly_detection")
    assert production is not None
    assert production.manifest.model_version == "anomaly-v1"

    # And the promoted model is itself usable and explainable on a live example.
    score = model.score({"price_change_pct": 10.0, "relative_volume": 1.0})
    assert score.combined_z > 0
    assert score.top_contributors(1)[0][0] == "price_change_pct"
