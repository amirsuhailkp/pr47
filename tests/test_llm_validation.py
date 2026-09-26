import pytest

from intelligence.llm.validation import LLMValidationError, validate_llm_response

VALID = {
    "summary": "XYZ up 4.7% on strong relative volume.",
    "observations": ["relative_volume=3.4x"],
    "patterns": ["MOMENTUM"],
    "historical_context": {"5d": {"sample_size": 127}},
    "possible_scenarios": ["Continuation if volume persists.", "Reversal if broader market weakens."],
    "risk_factors": ["extended from VWAP"],
    "invalidation_conditions": ["close back below breakout level"],
    "uncertainty": ["small sample for this exact setup"],
    "missing_information": [],
}


def test_valid_response_parses():
    analysis = validate_llm_response(VALID)
    assert analysis.summary == VALID["summary"]
    assert analysis.observations == tuple(VALID["observations"])


def test_missing_required_field_raises():
    bad = dict(VALID)
    del bad["risk_factors"]
    with pytest.raises(LLMValidationError):
        validate_llm_response(bad)


def test_wrong_type_for_list_field_raises():
    bad = dict(VALID)
    bad["observations"] = "not a list"
    with pytest.raises(LLMValidationError):
        validate_llm_response(bad)


def test_non_string_items_in_list_field_raises():
    bad = dict(VALID)
    bad["risk_factors"] = [123]
    with pytest.raises(LLMValidationError):
        validate_llm_response(bad)


def test_false_certainty_language_rejected():
    bad = dict(VALID)
    bad["summary"] = "XYZ will go up sharply tomorrow."
    with pytest.raises(LLMValidationError):
        validate_llm_response(bad)


def test_false_certainty_in_scenario_rejected():
    bad = dict(VALID)
    bad["possible_scenarios"] = ["This is guaranteed to continue."]
    with pytest.raises(LLMValidationError):
        validate_llm_response(bad)
