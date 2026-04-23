import httpx
from jobscout.scrapers.base import BaseScraper
from jobscout.config import TITLE_KEYWORDS


class LeverScraper(BaseScraper):
    portal = "lever"
    API_URL = "https://api.lever.co/v0/postings/{slug}"

    def __init__(self, companies: list[dict]):
        self._companies = companies

    def _title_matches(self, title: str) -> bool:
        lower = title.lower()
        return any(kw in lower for kw in TITLE_KEYWORDS)

    def search(self, query: str = "") -> list[dict]:
        results = []
        for company in self._companies:
            slug = company["slug"]
            name = company["name"]
            url = self.API_URL.format(slug=slug)

            try:
                resp = httpx.get(url, timeout=30)
            except httpx.RequestError:
                continue

            if resp.status_code != 200:
                continue

            jobs = resp.json()
            if not isinstance(jobs, list):
                continue

            for job in jobs:
                title = job.get("text", "")
                if not self._title_matches(title):
                    continue

                categories = job.get("categories", {})
                location = categories.get("location", "Unknown") if isinstance(categories, dict) else "Unknown"

                results.append({
                    "id": f"lever-{slug}-{job['id']}",
                    "portal": self.portal,
                    "url": job.get("hostedUrl", ""),
                    "title": title,
                    "company": name,
                    "location": location,
                    "raw_html": job.get("descriptionPlain", ""),
                })

        return results

    def close(self):
        pass
