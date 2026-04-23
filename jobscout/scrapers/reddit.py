import re
import time
import httpx
from jobscout.scrapers.base import BaseScraper
from jobscout.config import TITLE_KEYWORDS, get_subreddits, get_contact_email


class RedditScraper(BaseScraper):
    portal = "reddit"
    BASE_URL = "https://www.reddit.com"
    HEADERS = {
        "User-Agent": f"JobScout/1.0 (career search bot; contact: {get_contact_email() or 'jobscout@example.com'})",
        "Accept": "application/json",
    }
    MAX_RETRIES = 3
    MEGATHREAD_PATTERNS = re.compile(
        r"who.?s\s+hiring|hiring\s+thread|monthly\s+job|job\s+posting\s+thread",
        re.IGNORECASE,
    )

    def search(self, query: str) -> list[dict]:
        results = []
        for subreddit in get_subreddits():
            results.extend(self._search_subreddit(subreddit, query))
        return results

    def _search_subreddit(self, subreddit: str, query: str) -> list[dict]:
        url = f"{self.BASE_URL}/r/{subreddit}/search.json"
        params = {
            "q": query,
            "restrict_sr": "1",
            "sort": "new",
            "t": "week",
            "limit": "50",
        }
        data = self._fetch_json(url, params)
        if data is None:
            return []

        results = []
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})
            if not post:
                continue

            title = post.get("title", "")

            # Megathread: fetch comments, each top-level comment is a job listing
            if self.MEGATHREAD_PATTERNS.search(title):
                results.extend(self._parse_megathread(subreddit, post))
                continue

            # Regular post: check title against keywords
            if not self._matches_keywords(title):
                continue

            post_id = post.get("id", "")
            results.append({
                "id": f"reddit-{subreddit}-{post_id}",
                "portal": self.portal,
                "url": f"https://www.reddit.com{post.get('permalink', '')}",
                "title": title,
                "company": self._extract_company(title, post.get("selftext", "")),
                "location": self._extract_location(post.get("selftext", "")),
                "raw_html": post.get("selftext_html") or post.get("selftext", ""),
            })

        return results

    def _parse_megathread(self, subreddit: str, post: dict) -> list[dict]:
        permalink = post.get("permalink", "")
        if not permalink:
            return []

        url = f"{self.BASE_URL}{permalink}.json"
        data = self._fetch_json(url, params={"limit": "200", "sort": "new"})
        if not data or not isinstance(data, list) or len(data) < 2:
            return []

        results = []
        comments = data[1].get("data", {}).get("children", [])

        for comment in comments:
            cdata = comment.get("data", {})
            if comment.get("kind") != "t1":
                continue

            body = cdata.get("body", "")
            if not body or len(body) < 20:
                continue

            # Check first few lines for title keyword match
            first_lines = "\n".join(body.split("\n")[:3])
            if not self._matches_keywords(first_lines):
                continue

            comment_id = cdata.get("id", "")
            first_line = body.split("\n")[0].strip()

            results.append({
                "id": f"reddit-{subreddit}-{comment_id}",
                "portal": self.portal,
                "url": f"https://www.reddit.com{cdata.get('permalink', '')}",
                "title": first_line[:200],
                "company": self._extract_company(first_line, body),
                "location": self._extract_location(body),
                "raw_html": cdata.get("body_html") or body,
            })

        return results

    def _fetch_json(self, url: str, params: dict) -> dict | list | None:
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = httpx.get(
                    url, params=params, headers=self.HEADERS,
                    timeout=30, follow_redirects=True,
                )
                if resp.status_code == 429:
                    wait = min(2 ** (attempt + 1), 10)
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    return None
                return resp.json()
            except (httpx.HTTPError, ValueError):
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1)
                    continue
                return None
        return None

    def _matches_keywords(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in TITLE_KEYWORDS)

    def _extract_company(self, title: str, body: str) -> str:
        """Best-effort company extraction from post text."""
        # Common patterns: "Company Name | Title" or "Company Name - Title"
        for sep in ["|", " - ", " — ", " @ "]:
            if sep in title:
                return title.split(sep)[0].strip()[:100]
        # Look for "at Company" or "@ Company" in body first line
        first_line = body.split("\n")[0] if body else ""
        match = re.search(r"(?:at|@)\s+([A-Z][\w\s&.]+)", first_line)
        if match:
            return match.group(1).strip()[:100]
        return "Unknown"

    def _extract_location(self, body: str) -> str:
        """Best-effort location extraction from body text."""
        first_lines = "\n".join(body.split("\n")[:5]).lower()
        if "remote" in first_lines:
            return "Remote"
        match = re.search(
            r"(?:location|based in|office in)[:\s]+([^\n,]{3,50})",
            first_lines, re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return "Unknown"
