import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from jobscout.scrapers.discovery import try_discover_career_page, load_discovered, save_discovered


@patch("jobscout.scrapers.discovery.httpx.get")
def test_discover_finds_greenhouse(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobs": [{"id": 1, "title": "Engineer"}]}
    mock_get.return_value = mock_resp

    result = try_discover_career_page("Acme Corp")
    assert result is not None
    assert result["platform"] == "greenhouse"
    assert result["slug"] == "acme-corp"


@patch("jobscout.scrapers.discovery.httpx.get")
def test_discover_returns_none_for_unknown(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    result = try_discover_career_page("Totally Unknown Inc")
    assert result is None


def test_load_save_discovered():
    tmp = Path(tempfile.mktemp(suffix=".json"))
    data = {"greenhouse": [{"slug": "acme", "name": "Acme"}]}
    save_discovered(tmp, data)
    loaded = load_discovered(tmp)
    assert loaded["greenhouse"][0]["slug"] == "acme"
    tmp.unlink()


def test_load_discovered_missing_file():
    tmp = Path(tempfile.mktemp(suffix=".json"))
    loaded = load_discovered(tmp)
    assert loaded == {"greenhouse": [], "ashby": [], "lever": []}
