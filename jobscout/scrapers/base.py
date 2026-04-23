from abc import ABC, abstractmethod


class BaseScraper(ABC):
    portal: str = "unknown"

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """Search for jobs. Returns list of dicts with keys:
        id, portal, url, title, company, location, raw_html (optional)
        """
        ...
