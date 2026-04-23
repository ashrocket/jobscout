import hashlib
import re
import httpx
from bs4 import BeautifulSoup
from jobscout.scrapers.base import BaseScraper
from jobscout.config import read_credential

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


class LinkedInScraper(BaseScraper):
    portal = "linkedin"
    SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def __init__(self):
        self._cookie: str | None = None

    def _get_cookie(self) -> str:
        if self._cookie is None:
            self._cookie = read_credential("linkedin-cookie")
        return self._cookie

    def search(self, query: str) -> list[dict]:
        params = {
            "keywords": query,
            "f_TPR": "r86400",
            "f_WT": "2",
            "sortBy": "DD",
            "start": "0",
        }

        resp = httpx.get(
            self.SEARCH_URL, params=params, headers=_HEADERS,
            timeout=30, follow_redirects=True,
        )
        if resp.status_code != 200:
            return []

        return self._parse(resp.text)

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for card in soup.select(".job-search-card, .base-card"):
            title_el = card.select_one(".base-search-card__title, h3")
            company_el = card.select_one(".base-search-card__subtitle a, h4 a")
            location_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")

            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue

            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location = location_el.get_text(strip=True) if location_el else "Unknown"

            href = link_el.get("href", "") if link_el else ""
            job_url = href.split("?")[0] if href else ""

            match = re.search(r"/jobs/view/(\d+)", href)
            job_id = f"linkedin-{match.group(1)}" if match else f"linkedin-{hashlib.md5(f'{title}{company}'.encode()).hexdigest()[:12]}"

            results.append({
                "id": job_id,
                "portal": self.portal,
                "url": job_url,
                "title": title,
                "company": company,
                "location": location,
                "raw_html": str(card),
            })

        return results

    def get_job_detail(self, url: str) -> str:
        cookies = {"li_at": self._get_cookie()}
        resp = httpx.get(url, headers=_HEADERS, cookies=cookies, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        desc = soup.select_one(".description__text, .show-more-less-html__markup")
        return str(desc) if desc else resp.text

    def close(self):
        pass
