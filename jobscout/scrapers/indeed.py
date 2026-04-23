import hashlib
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobscout.scrapers.base import BaseScraper
from jobscout.scrapers._browser import BrowserSession


class IndeedScraper(BaseScraper):
    """Playwright-backed Indeed scraper.

    Raw httpx hits Indeed's CAPTCHA wall and returns no .job_seen_beacon cards.
    Headless chromium with a stealth init script gets the JS-rendered DOM.
    """
    portal = "indeed"
    BASE_URL = "https://www.indeed.com/jobs"

    def __init__(self):
        self._browser: BrowserSession | None = None

    def _session(self) -> BrowserSession:
        if self._browser is None:
            self._browser = BrowserSession()
        return self._browser

    def search(self, query: str) -> list[dict]:
        params = {
            "q": query,
            "l": "Remote",
            "fromage": 1,
            "sort": "date",
        }
        url = f"{self.BASE_URL}?{urlencode(params)}"
        try:
            html = self._session().fetch(
                url,
                wait_for=".job_seen_beacon, [data-jk]",
                timeout_ms=25000,
            )
        except Exception:
            return []
        return self._parse(html)

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for card in soup.select(".job_seen_beacon"):
            title_el = card.select_one(".jobTitle span") or card.select_one("h2.jobTitle a span")
            company_el = card.select_one("[data-testid='company-name']")
            location_el = card.select_one("[data-testid='text-location']")
            link_el = card.select_one(".jobTitle a") or card.select_one("h2.jobTitle a")

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else "Unknown"

            jk = link_el.get("data-jk", "")
            job_id = (f"indeed-{jk}" if jk
                      else f"indeed-{hashlib.md5(title.encode()).hexdigest()[:12]}")
            url = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""

            results.append({
                "id": job_id,
                "portal": self.portal,
                "url": url,
                "title": title,
                "company": company,
                "location": location,
                "raw_html": str(card),
            })

        return results

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
