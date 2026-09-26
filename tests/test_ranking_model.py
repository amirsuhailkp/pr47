from ml.models.ranking.model import CandidateRankingModel, EqualWeightBaselineRanking


def test_ranking_model_weights_are_explicit_and_explainable():
    model = CandidateRankingModel(weights={"relative_strength": 2.0, "historical_win_rate": 1.0})
    score = model.score({"relative_strength": 3.0, "historical_win_rate": 0.6, "unused": 99})
    assert score.total == 2.0 * 3.0 + 1.0 * 0.6
    assert score.contributions == {"relative_strength": 6.0, "historical_win_rate": 0.6}
    assert score.explain()[0].startswith("relative_strength")


def test_ranking_model_ignores_factors_without_a_configured_weight():
    model = CandidateRankingModel(weights={"a": 1.0})
    score = model.score({"a": 1.0, "b": 100.0})
    assert "b" not in score.contributions


def test_baseline_ranking_uses_equal_weights_over_available_factors():
    baseline = EqualWeightBaselineRanking()
    score = baseline.score({"a": 1.0, "b": 2.0})
    assert score.total == 3.0


def test_baseline_ranking_restricted_to_configured_keys():
    baseline = EqualWeightBaselineRanking(factor_keys=("a",))
    score = baseline.score({"a": 1.0, "b": 2.0})
    assert score.total == 1.0
