from unittest.mock import patch
from jobscout.scrapers.indeed import IndeedScraper

MOCK_INDEED_HTML = """
<html><body>
<div class="job_seen_beacon">
    <h2 class="jobTitle"><a href="/viewjob?jk=abc123" data-jk="abc123">
    <span>VP of Engineering</span></a></h2>
    <span data-testid="company-name">HealthCo</span>
    <div data-testid="text-location">Remote</div>
</div>
<div class="job_seen_beacon">
    <h2 class="jobTitle"><a href="/viewjob?jk=def456" data-jk="def456">
    <span>CTO - Series B Startup</span></a></h2>
    <span data-testid="company-name">Finova</span>
    <div data-testid="text-location">New York, NY</div>
</div>
</body></html>
"""


@patch("jobscout.scrapers.indeed.BrowserSession.fetch")
def test_indeed_scraper_extracts_listings(mock_fetch):
    mock_fetch.return_value = MOCK_INDEED_HTML

    scraper = IndeedScraper()
    results = scraper.search("VP of Engineering")
    assert len(results) == 2
    assert results[0]["title"] == "VP of Engineering"
    assert results[0]["company"] == "HealthCo"
    assert results[0]["portal"] == "indeed"
    assert "abc123" in results[0]["id"]


def test_indeed_scraper_has_correct_portal():
    scraper = IndeedScraper()
    assert scraper.portal == "indeed"
