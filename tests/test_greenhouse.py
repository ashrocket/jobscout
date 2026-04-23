import json
from unittest.mock import patch, MagicMock
from jobscout.scrapers.greenhouse import GreenhouseScraper


SAMPLE_API_RESPONSE = {
    "jobs": [
        {
            "id": 12345,
            "title": "VP of Engineering",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "content": "<p>We need a VP Eng to scale our team.</p>",
        },
        {
            "id": 67890,
            "title": "Senior Software Engineer",
            "location": {"name": "New York, NY"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/67890",
            "content": "<p>Build features for our platform.</p>",
        },
    ]
}


@patch("jobscout.scrapers.greenhouse.httpx.get")
def test_greenhouse_returns_matching_jobs(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_API_RESPONSE
    mock_get.return_value = mock_resp

    scraper = GreenhouseScraper([{"slug": "acme", "name": "Acme Corp"}])
    results = scraper.search()

    assert len(results) == 1
    assert results[0]["title"] == "VP of Engineering"
    assert results[0]["id"] == "greenhouse-acme-12345"
    assert results[0]["portal"] == "greenhouse"
    assert results[0]["company"] == "Acme Corp"


@patch("jobscout.scrapers.greenhouse.httpx.get")
def test_greenhouse_filters_non_matching_titles(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {"id": 1, "title": "Junior Developer", "location": {"name": "NYC"},
             "absolute_url": "https://boards.greenhouse.io/x/jobs/1", "content": ""},
        ]
    }
    mock_get.return_value = mock_resp

    scraper = GreenhouseScraper([{"slug": "x", "name": "X"}])
    results = scraper.search()
    assert len(results) == 0


@patch("jobscout.scrapers.greenhouse.httpx.get")
def test_greenhouse_handles_api_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    scraper = GreenhouseScraper([{"slug": "nonexistent", "name": "Gone"}])
    results = scraper.search()
    assert results == []
