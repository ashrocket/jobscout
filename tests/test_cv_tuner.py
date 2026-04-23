import json
from unittest.mock import patch
from jobscout.llm import LLMResponse
from jobscout.pipeline.cv_tuner import tune_cv


SAMPLE_HTML = """<html><body>
<h1>Jane Doe</h1>
<p class="summary">Engineering leader who builds and scales organizations.</p>
<ul>
<li>Grew startup from 5 to 150+ engineers</li>
<li>Deployed agentic AI into production healthcare infrastructure</li>
</ul>
</body></html>"""

SAMPLE_EXTRACTED = {
    "title": "VP Engineering",
    "company": "HealthCo",
    "industry": "healthcare",
    "signals": ["scaling", "healthcare"],
    "description": "Lead engineering for healthcare platform",
}

SAMPLE_CLASSIFICATION = {
    "archetype": "healthcare",
    "confidence": 0.9,
    "resume_variant": "healthcare",
    "reasoning": "Healthcare company",
}


@patch("jobscout.pipeline.cv_tuner.call_llm")
def test_tune_cv_returns_modified_html(mock_llm):
    tuned_html = SAMPLE_HTML.replace(
        "Engineering leader who builds and scales organizations.",
        "Engineering leader specializing in healthcare platform scaling.",
    )
    mock_llm.return_value = LLMResponse(
        text=tuned_html,
        tokens_in=3000, tokens_out=3000,
        model="claude-sonnet-4-6-20250514", provider="anthropic",
    )
    result = tune_cv(SAMPLE_HTML, SAMPLE_EXTRACTED, SAMPLE_CLASSIFICATION, conn=None)
    assert result is not None
    assert "healthcare platform scaling" in result
    assert "<html>" in result


@patch("jobscout.pipeline.cv_tuner.call_llm")
def test_tune_cv_returns_none_on_failure(mock_llm):
    mock_llm.side_effect = Exception("LLM failed")
    result = tune_cv(SAMPLE_HTML, SAMPLE_EXTRACTED, SAMPLE_CLASSIFICATION, conn=None)
    assert result is None
