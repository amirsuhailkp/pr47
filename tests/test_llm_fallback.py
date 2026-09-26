from intelligence.llm.fallback import build_fallback_analysis


def test_fallback_builds_readable_summary_without_llm():
    evidence = {
        "instrument_symbol": "XYZ",
        "price": 184.6,
        "price_change_pct": 4.72,
        "relative_volume": 3.4,
        "rsi_14": 68.0,
        "detected_patterns": [{"family": "MOMENTUM"}, {"family": "BREAKOUT"}],
        "risk_flags": ["extended from VWAP"],
    }
    analysis = build_fallback_analysis(evidence)
    assert "XYZ" in analysis.summary
    assert "+4.72%" in analysis.summary
    assert "MOMENTUM" in analysis.patterns
    assert "extended from VWAP" in analysis.risk_factors
    assert any("without LLM" in u for u in analysis.uncertainty)


def test_fallback_handles_missing_fields_gracefully():
    analysis = build_fallback_analysis({"instrument_symbol": "XYZ"})
    assert analysis.summary  # never empty/crashes
    assert analysis.observations == ()
