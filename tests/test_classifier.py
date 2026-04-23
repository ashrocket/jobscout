import json
from unittest.mock import patch
from jobscout.llm import LLMResponse
from jobscout.pipeline.classifier import classify_job


SAMPLE_EXTRACTED = {
    "title": "VP of Engineering",
    "company": "Nomi Health",
    "location": "Remote, US",
    "industry": "healthcare",
    "company_stage": "Series C",
    "team_size": "200",
    "description": "Lead 200-person engineering team through next growth phase",
    "signals": ["healthcare", "scaling", "Series C"],
    "posted_date": "2 days ago",
    "salary_range": None,
    "remote": True,
}


@patch("jobscout.pipeline.classifier.call_llm")
def test_classify_returns_archetype(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "archetype": "healthcare",
            "confidence": 0.9,
            "reasoning": "Healthcare company, Series C, scaling eng team",
        }),
        tokens_in=500, tokens_out=100,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = classify_job(SAMPLE_EXTRACTED, conn=None)
    assert result is not None
    assert result["archetype"] == "healthcare"
    assert result["confidence"] == 0.9
    assert result["resume_variant"] == "healthcare"


@patch("jobscout.pipeline.classifier.call_llm")
def test_classify_maps_resume_variant(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "archetype": "travel_aviation",
            "confidence": 0.85,
            "reasoning": "Airline technology company",
        }),
        tokens_in=500, tokens_out=100,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = classify_job({"title": "CTO", "company": "SITA", "signals": ["aviation"]}, conn=None)
    assert result["resume_variant"] == "travel"


@patch("jobscout.pipeline.classifier.call_llm")
def test_classify_handles_bad_json(mock_llm):
    mock_llm.return_value = LLMResponse(
        text="not valid json",
        tokens_in=500, tokens_out=50,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = classify_job(SAMPLE_EXTRACTED, conn=None)
    assert result is None


@patch("jobscout.pipeline.classifier.call_llm")
def test_classify_handles_unknown_archetype(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "archetype": "unknown_type",
            "confidence": 0.5,
            "reasoning": "Unclear fit",
        }),
        tokens_in=500, tokens_out=100,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = classify_job(SAMPLE_EXTRACTED, conn=None)
    assert result is not None
    assert result["resume_variant"] == "default"
