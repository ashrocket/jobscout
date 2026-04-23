import hashlib
import re
from urllib.parse import urlencode, quote_plus

from bs4 import BeautifulSoup

from jobscout.scrapers.base import BaseScraper
from jobscout.scrapers._browser import BrowserSession


class MonsterScraper(BaseScraper):
    """Playwright-backed Monster scraper.

    Monster renders job cards through JS; raw httpx hits an empty shell.
    Uses shared BrowserSession for anti-bot-ish stealth.
    """
    portal = "monster"
    BASE_URL = "https://www.monster.com/jobs/search"

    def __init__(self):
        self._browser: BrowserSession | None = None

    def _session(self) -> BrowserSession:
        if self._browser is None:
            self._browser = BrowserSession()
        return self._browser

    def search(self, query: str) -> list[dict]:
        params = {
            "q": query,
            "where": "Remote",
            "page": 1,
            "so": "m.h.s",
        }
        url = f"{self.BASE_URL}?{urlencode(params)}"
        try:
            html = self._session().fetch(
                url,
                wait_for="article[data-testid='svx-job-card'], div[data-testid='JobCard'], a[data-testid='jobTitle']",
                timeout_ms=25000,
            )
        except Exception:
            return []
        return self._parse(html)

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen_ids = set()

        cards = (
            soup.select("article[data-testid='svx-job-card']")
            or soup.select("div[data-testid='JobCard']")
            or soup.select("article.jobCard")
        )

        for card in cards:
            title_el = (
                card.select_one("a[data-testid='jobTitle']")
                or card.select_one("h3 a")
                or card.select_one("a.job-cardstyle__JobTitle")
            )
            company_el = (
                card.select_one("[data-testid='company']")
                or card.select_one("span[data-testid='JobCardCompanyName']")
                or card.select_one("h4")
            )
            location_el = (
                card.select_one("[data-testid='jobDetailLocation']")
                or card.select_one("[data-testid='JobCardLocation']")
                or card.select_one("span.jobCardLocation")
            )

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else "Remote"

            href = title_el.get("href", "") or ""
            if href and not href.startswith("http"):
                href = f"https://www.monster.com{href}"

            # Extract monster job id from URL if present, else hash title+company
            m = re.search(r"/(\d[\w-]{6,})(?:[/?]|$)", href)
            slug = m.group(1) if m else hashlib.md5(f"{title}|{company}".encode()).hexdigest()[:12]
            job_id = f"monster-{slug}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            results.append({
                "id": job_id,
                "portal": self.portal,
                "url": href,
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
