import json
from unittest.mock import patch, MagicMock
from jobscout.scrapers.lever import LeverScraper


SAMPLE_API_RESPONSE = [
    {
        "id": "aaa-111",
        "text": "CTO",
        "categories": {"location": "Remote", "team": "Engineering"},
        "hostedUrl": "https://jobs.lever.co/acme/aaa-111",
        "descriptionPlain": "We need a CTO to lead our engineering vision.",
    },
    {
        "id": "bbb-222",
        "text": "Account Executive",
        "categories": {"location": "Chicago", "team": "Sales"},
        "hostedUrl": "https://jobs.lever.co/acme/bbb-222",
        "descriptionPlain": "Sell our product.",
    },
]


@patch("jobscout.scrapers.lever.httpx.get")
def test_lever_returns_matching_jobs(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_API_RESPONSE
    mock_get.return_value = mock_resp

    scraper = LeverScraper([{"slug": "acme", "name": "Acme Corp"}])
    results = scraper.search()

    assert len(results) == 1
    assert results[0]["title"] == "CTO"
    assert results[0]["id"] == "lever-acme-aaa-111"
    assert results[0]["portal"] == "lever"


@patch("jobscout.scrapers.lever.httpx.get")
def test_lever_handles_api_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    scraper = LeverScraper([{"slug": "gone", "name": "Gone"}])
    results = scraper.search()
    assert results == []
