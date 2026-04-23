"""Sentry careers scraper.

Sentry lists all open roles directly at https://sentry.io/careers/ — not on
any third-party ATS (Greenhouse/Lever/Ashby). Each row has a stable
structure: an `<a>` that contains a title span and a location span, with
hashed Vite-style class names (`_jobTitle_fkglr_XXX`, `_jobLocation_fkglr_XXX`).
We match on the `[class*="jobTitle"]` partial to survive the hash rotation.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobscout.scrapers.base import BaseScraper
from jobscout.scrapers._browser import BrowserSession

_UUID_RE = re.compile(r"/careers/([a-f0-9-]{30,})")


class SentryScraper(BaseScraper):
    portal = "sentry"
    BASE_URL = "https://sentry.io/careers/"

    def __init__(self):
        self._browser: BrowserSession | None = None

    def _session(self) -> BrowserSession:
        if self._browser is None:
            self._browser = BrowserSession()
        return self._browser

    def search(self, query: str = "") -> list[dict]:
        """Fetch the careers page and return every listed role.

        `query` is accepted for interface parity with other scrapers but is
        not used — Sentry publishes every role on one page and we return them
        all, letting the classifier/scorer filter.
        """
        try:
            html = self._session().fetch(self.BASE_URL, timeout_ms=20000)
        except Exception:
            return []
        return self._parse(html)

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        seen: set[str] = set()

        for a in soup.select('a[href^="/careers/"]'):
            m = _UUID_RE.search(a.get("href", ""))
            if not m:
                continue
            uuid = m.group(1)
            job_id = f"sentry-{uuid}"
            if job_id in seen:
                continue
            seen.add(job_id)

            title_el = a.select_one('[class*="jobTitle"]')
            loc_el = a.select_one('[class*="jobLocation"]')
            title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
            location = loc_el.get_text(strip=True) if loc_el else ""

            url = urljoin("https://sentry.io", a.get("href", ""))
            results.append({
                "id": job_id,
                "portal": self.portal,
                "url": url,
                "title": title,
                "company": "Sentry",
                "location": location or "Remote",
                "raw_html": str(a.parent or a),
            })

        return results

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
