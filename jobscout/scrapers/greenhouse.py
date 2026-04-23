import httpx
from jobscout.scrapers.base import BaseScraper
from jobscout.config import TITLE_KEYWORDS


class GreenhouseScraper(BaseScraper):
    portal = "greenhouse"
    API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

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
                resp = httpx.get(url, timeout=30, params={"content": "true"})
            except httpx.RequestError:
                continue

            if resp.status_code != 200:
                continue

            data = resp.json()
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if not self._title_matches(title):
                    continue

                loc = job.get("location", {})
                location = loc.get("name", "Unknown") if isinstance(loc, dict) else str(loc)

                results.append({
                    "id": f"greenhouse-{slug}-{job['id']}",
                    "portal": self.portal,
                    "url": job.get("absolute_url", ""),
                    "title": title,
                    "company": name,
                    "location": location,
                    "raw_html": job.get("content", ""),
                })

        return results

    def close(self):
        pass
