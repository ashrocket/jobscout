import json
from unittest.mock import patch
from jobscout.llm import LLMResponse
from jobscout.pipeline.scorer import score_job

SAMPLE_EXTRACTED = {
    "title": "VP of Engineering",
    "company": "Nomi Health",
    "location": "Remote, US",
    "industry": "healthcare",
    "company_stage": "Series C",
    "team_size": "200",
    "description": "Lead 200-person eng team through next growth phase at healthcare tech company",
    "signals": ["healthcare", "scaling", "Series C"],
    "remote": True,
}


@patch("jobscout.pipeline.scorer.call_llm")
def test_score_high_match(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "score": 92,
            "reasoning": "Strong healthcare + scaling match. Remote. Series C.",
            "resume": "healthcare",
        }),
        tokens_in=3000, tokens_out=200,
        model="gemini-2.0-pro", provider="gemini",
    )
    result = score_job(SAMPLE_EXTRACTED, conn=None)
    assert result["score"] == 92
    assert result["star_rating"] == 5
    assert result["resume"] == "healthcare"


@patch("jobscout.pipeline.scorer.call_llm")
def test_score_low_match(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "score": 45,
            "reasoning": "Junior role, no match.",
            "resume": "default",
        }),
        tokens_in=2000, tokens_out=100,
        model="gemini-2.0-pro", provider="gemini",
    )
    result = score_job({"title": "Junior Dev", "company": "X", "industry": "other",
                        "signals": [], "remote": False}, conn=None)
    assert result["score"] == 45
    assert result["star_rating"] == 0


@patch("jobscout.pipeline.scorer.call_llm")
def test_score_handles_bad_json(mock_llm):
    mock_llm.return_value = LLMResponse(
        text="I think this is a 75",
        tokens_in=100, tokens_out=50,
        model="gemini-2.0-pro", provider="gemini",
    )
    result = score_job(SAMPLE_EXTRACTED, conn=None)
    assert result is None


@patch("jobscout.pipeline.scorer.call_llm")
def test_score_job_with_classification(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
            "score": 88,
            "reasoning": "Strong healthcare fit with scaling signals",
        }),
        tokens_in=800, tokens_out=150,
        model="gemini-2.0-pro", provider="gemini",
    )
    extracted = {
        "title": "VP Engineering",
        "company": "Nomi Health",
        "industry": "healthcare",
        "signals": ["scaling"],
    }
    classification = {
        "archetype": "healthcare",
        "confidence": 0.9,
        "resume_variant": "healthcare",
        "reasoning": "Healthcare company",
    }
    result = score_job(extracted, classification=classification, conn=None)
    assert result is not None
    assert result["score"] == 88
    assert result["star_rating"] == 4
