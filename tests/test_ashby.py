import json
from unittest.mock import patch, MagicMock
from jobscout.scrapers.ashby import AshbyScraper


SAMPLE_API_RESPONSE = {
    "jobs": [
        {
            "id": "abc-123",
            "title": "Head of Engineering",
            "location": "Remote - US",
            "jobUrl": "https://jobs.ashby.io/acme/abc-123",
            "descriptionHtml": "<p>Lead our engineering org.</p>",
        },
        {
            "id": "def-456",
            "title": "Product Designer",
            "location": "San Francisco",
            "jobUrl": "https://jobs.ashby.io/acme/def-456",
            "descriptionHtml": "<p>Design products.</p>",
        },
    ]
}


@patch("jobscout.scrapers.ashby.httpx.get")
def test_ashby_returns_matching_jobs(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_API_RESPONSE
    mock_get.return_value = mock_resp

    scraper = AshbyScraper([{"slug": "acme", "name": "Acme Corp"}])
    results = scraper.search()

    assert len(results) == 1
    assert results[0]["title"] == "Head of Engineering"
    assert results[0]["id"] == "ashby-acme-abc-123"
    assert results[0]["portal"] == "ashby"


@patch("jobscout.scrapers.ashby.httpx.get")
def test_ashby_handles_api_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_get.return_value = mock_resp

    scraper = AshbyScraper([{"slug": "broken", "name": "Broken"}])
    results = scraper.search()
    assert results == []
