import httpx
from jobscout.scrapers.base import BaseScraper
from jobscout.config import TITLE_KEYWORDS


class AshbyScraper(BaseScraper):
    portal = "ashby"
    API_URL = "https://api.ashby.info/posting-api/job-board/{slug}"

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

            data = resp.json()
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if not self._title_matches(title):
                    continue

                results.append({
                    "id": f"ashby-{slug}-{job['id']}",
                    "portal": self.portal,
                    "url": job.get("jobUrl", ""),
                    "title": title,
                    "company": name,
                    "location": job.get("location", "Unknown"),
                    "raw_html": job.get("descriptionHtml", ""),
                })

        return results

    def close(self):
        pass
