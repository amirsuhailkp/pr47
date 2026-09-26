import pytest

from ml.models.anomaly.model import AnomalyModel, BaselineAnomalyModel

SCHEMA = ("price_change_pct", "relative_volume")


def test_fit_requires_examples():
    with pytest.raises(ValueError):
        AnomalyModel.fit([], SCHEMA)


def test_fit_computes_mean_and_std():
    data = [{"price_change_pct": 1.0, "relative_volume": 1.0} for _ in range(9)] + [
        {"price_change_pct": 5.0, "relative_volume": 1.0}
    ]
    model = AnomalyModel.fit(data, SCHEMA)
    assert model.sample_size == 10
    assert round(model.means["price_change_pct"], 2) == round((1.0 * 9 + 5.0) / 10, 2)


def test_score_flags_outlier_with_high_z():
    normal = [{"price_change_pct": 1.0, "relative_volume": 1.0} for _ in range(20)]
    model = AnomalyModel.fit(normal, SCHEMA)
    # all training examples identical -> std is 0, so this model can't discriminate;
    # add slight variance instead
    varied = [
        {"price_change_pct": 1.0 + (i % 3) * 0.1, "relative_volume": 1.0 + (i % 2) * 0.05}
        for i in range(20)
    ]
    model = AnomalyModel.fit(varied, SCHEMA)
    normal_score = model.score({"price_change_pct": 1.1, "relative_volume": 1.0})
    outlier_score = model.score({"price_change_pct": 8.0, "relative_volume": 4.0})
    assert outlier_score.combined_z > normal_score.combined_z


def test_score_returns_explainable_contributions():
    varied = [{"price_change_pct": 1.0 + i * 0.1, "relative_volume": 1.0} for i in range(10)]
    model = AnomalyModel.fit(varied, SCHEMA)
    score = model.score({"price_change_pct": 5.0, "relative_volume": 1.0})
    assert "price_change_pct" in score.per_feature_z
    top = score.top_contributors(1)
    assert top[0][0] == "price_change_pct"


def test_score_skips_zero_variance_features():
    data = [{"price_change_pct": 1.0, "relative_volume": 1.0} for _ in range(10)]
    model = AnomalyModel.fit(data, SCHEMA)  # both features have zero std
    score = model.score({"price_change_pct": 5.0, "relative_volume": 5.0})
    assert score.per_feature_z == {}
    assert score.combined_z == 0.0


def test_baseline_model_uses_single_feature_threshold():
    baseline = BaselineAnomalyModel(feature_key="relative_volume", threshold=2.0)
    score = baseline.score({"relative_volume": 4.0})
    assert score.combined_z == 2.0
    assert score.per_feature_z == {"relative_volume": 2.0}
