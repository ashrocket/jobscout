import json
from unittest.mock import patch
from jobscout.llm import LLMResponse
from jobscout.pipeline.extractor import extract_job_data

SAMPLE_HTML = """
<div class="job-card">
    <h2>VP of Engineering</h2>
    <h3>Nomi Health</h3>
    <span class="location">Remote, US</span>
    <p>We're looking for a VP of Engineering to lead our 200-person engineering team
    through our next phase of growth. Series C healthcare technology company.</p>
    <span>Posted 2 days ago</span>
</div>
"""


@patch("jobscout.pipeline.extractor.call_llm")
def test_extract_returns_structured_data(mock_llm):
    mock_llm.return_value = LLMResponse(
        text=json.dumps({
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
        }),
        tokens_in=2000, tokens_out=300,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = extract_job_data(SAMPLE_HTML, conn=None)
    assert result["title"] == "VP of Engineering"
    assert result["company"] == "Nomi Health"
    assert result["remote"] is True
    assert "healthcare" in result["signals"]


@patch("jobscout.pipeline.extractor.call_llm")
def test_extract_handles_bad_json(mock_llm):
    mock_llm.return_value = LLMResponse(
        text="not valid json at all",
        tokens_in=100, tokens_out=50,
        model="gemini-2.0-flash", provider="gemini",
    )
    result = extract_job_data("<div>bad</div>", conn=None)
    assert result is None
