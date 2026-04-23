from unittest.mock import patch, MagicMock
import json
import tempfile
from pathlib import Path
from jobscout.main import run_scan
from jobscout.db import init_db, get_job
from jobscout.llm import LLMResponse


def _tmp_db():
    return Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)


@patch("jobscout.main.try_discover_career_page")
@patch("jobscout.main.classify_job")
@patch("jobscout.main.IndeedScraper")
@patch("jobscout.main.extract_job_data")
@patch("jobscout.main.score_job")
@patch("jobscout.main.send_document")
@patch("jobscout.main.send_imessage")
def test_run_scan_end_to_end(mock_imsg, mock_pigeon, mock_score, mock_extract,
                             mock_indeed, mock_classify, mock_discover):
    mock_indeed_instance = MagicMock()
    mock_indeed_instance.search.return_value = [
        {"id": "indeed-abc", "portal": "indeed", "url": "https://indeed.com/123",
         "title": "VP Eng", "company": "Acme", "location": "Remote", "raw_html": "<div>test</div>"}
    ]
    mock_indeed.return_value = mock_indeed_instance

    mock_extract.return_value = {
        "title": "VP Eng", "company": "Acme", "industry": "healthcare",
        "signals": ["healthcare"], "remote": True,
    }
    mock_classify.return_value = {
        "archetype": "healthcare", "confidence": 0.85,
        "reasoning": "Healthcare signals", "resume_variant": "healthcare",
    }
    mock_score.return_value = {
        "score": 85, "star_rating": 4, "reasoning": "Good match", "resume": "healthcare",
    }
    mock_pigeon.return_value = "msg-123"
    mock_discover.return_value = None

    db_path = _tmp_db()
    result = run_scan(portals=["indeed"], db_path=db_path)

    assert result["jobs_found"] >= 1
    mock_pigeon.assert_called_once()
    mock_imsg.assert_called_once()


@patch("jobscout.main.try_discover_career_page")
@patch("jobscout.main.send_document")
@patch("jobscout.main.send_imessage")
@patch("jobscout.main.send_message")
@patch("jobscout.pipeline.cv_tuner.call_llm")
@patch("jobscout.pipeline.scorer.call_llm")
@patch("jobscout.pipeline.classifier.call_llm")
@patch("jobscout.pipeline.extractor.call_llm")
@patch("jobscout.main.IndeedScraper")
def test_scan_with_classifier_and_tuner(
    mock_scraper_cls, mock_extract_llm, mock_classify_llm, mock_score_llm,
    mock_tune_llm, mock_send_msg, mock_imessage, mock_send_doc,
    mock_discover,
):
    mock_scraper = MagicMock()
    mock_scraper.search.return_value = [{
        "id": "indeed-full-pipeline",
        "portal": "indeed",
        "url": "https://indeed.com/viewjob?jk=full",
        "title": "VP Engineering",
        "company": "HealthCo",
        "location": "Remote",
        "raw_html": "<div>VP Eng at HealthCo</div>",
    }]
    mock_scraper_cls.return_value = mock_scraper
    mock_discover.return_value = None

    mock_extract_llm.return_value = LLMResponse(
        text=json.dumps({
            "title": "VP Engineering", "company": "HealthCo",
            "location": "Remote", "industry": "healthcare",
            "company_stage": "Series C", "team_size": "100",
            "description": "Lead eng", "signals": ["healthcare", "scaling"],
            "posted_date": "1 day ago", "salary_range": None, "remote": True,
        }),
        tokens_in=1000, tokens_out=200,
        model="gemini-2.0-flash", provider="gemini",
    )

    mock_classify_llm.return_value = LLMResponse(
        text=json.dumps({
            "archetype": "healthcare",
            "confidence": 0.9,
            "reasoning": "Healthcare company scaling eng",
        }),
        tokens_in=500, tokens_out=100,
        model="gemini-2.0-flash", provider="gemini",
    )

    mock_score_llm.return_value = LLMResponse(
        text=json.dumps({
            "score": 85,
            "reasoning": "Strong healthcare fit",
        }),
        tokens_in=800, tokens_out=150,
        model="gemini-2.0-pro", provider="gemini",
    )

    mock_tune_llm.return_value = LLMResponse(
        text="<html><body>Tuned resume</body></html>",
        tokens_in=3000, tokens_out=3000,
        model="claude-sonnet-4-6-20250514", provider="anthropic",
    )

    db_path = _tmp_db()
    stats = run_scan(["indeed"], db_path=db_path)

    assert stats["jobs_scored"] == 1
    conn = init_db(db_path)
    job = get_job(conn, "indeed-full-pipeline")
    assert job["archetype"] == "healthcare"
    assert job["score"] == 85
    conn.close()


@patch("jobscout.main.send_document")
@patch("jobscout.main.send_imessage")
@patch("jobscout.main.send_message")
@patch("jobscout.main.try_discover_career_page", return_value=None)
@patch("jobscout.pipeline.scorer.call_llm")
@patch("jobscout.pipeline.classifier.call_llm")
@patch("jobscout.pipeline.extractor.call_llm")
@patch("jobscout.main.IndeedScraper")
def test_scan_continues_when_classifier_fails(
    mock_scraper_cls, mock_extract_llm, mock_classify_llm, mock_score_llm,
    mock_discover, mock_send_msg, mock_imessage, mock_send_doc,
):
    mock_scraper = MagicMock()
    mock_scraper.search.return_value = [{
        "id": "indeed-classify-fail",
        "portal": "indeed",
        "url": "https://indeed.com/viewjob?jk=cf",
        "title": "CTO",
        "company": "Mystery Corp",
        "location": "Remote",
        "raw_html": "<div>CTO at Mystery</div>",
    }]
    mock_scraper_cls.return_value = mock_scraper

    mock_extract_llm.return_value = LLMResponse(
        text=json.dumps({
            "title": "CTO", "company": "Mystery Corp",
            "location": "Remote", "industry": "other",
            "company_stage": "unknown", "team_size": None,
            "description": "Lead tech", "signals": [],
            "posted_date": None, "salary_range": None, "remote": True,
        }),
        tokens_in=500, tokens_out=100,
        model="gemini-2.0-flash", provider="gemini",
    )

    # Classifier returns bad JSON — should not block pipeline
    mock_classify_llm.return_value = LLMResponse(
        text="not json",
        tokens_in=100, tokens_out=50,
        model="gemini-2.0-flash", provider="gemini",
    )

    mock_score_llm.return_value = LLMResponse(
        text=json.dumps({"score": 45, "reasoning": "Weak fit"}),
        tokens_in=800, tokens_out=150,
        model="gemini-2.0-pro", provider="gemini",
    )

    db_path = _tmp_db()
    stats = run_scan(["indeed"], db_path=db_path)

    assert stats["jobs_scored"] == 1
    conn = init_db(db_path)
    job = get_job(conn, "indeed-classify-fail")
    assert job["archetype"] is None  # classifier failed, no archetype
    assert job["score"] == 45
    from jobscout.config import get_resume_map
    assert job["resume_used"] == get_resume_map()["default"]  # default fallback
    conn.close()
