"""Apple Jobs scraper.

Apple publishes every open role on `jobs.apple.com` via a React app. SSR
responses include a `window.__staticRouterHydrationData` blob with the full
first page of results as JSON; CSR responses (hit via CDN cache paths) ship
the same data in the DOM without the blob. We try hydration first, fall
back to parsing the rendered `/details/{id}/{slug}?team={team}` anchors.

Apple has 4,900+ open roles globally; we restrict to an Engineering-leaning
keyword + US location (`united-states-USA`) + team filter (`SFTWR` = Software
& Services). Without a `team` filter the `search` param is silently ignored.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from jobscout.scrapers.base import BaseScraper
from jobscout.scrapers._browser import BrowserSession

_HYDRATION_RE = re.compile(
    r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);',
    re.DOTALL,
)
_DETAIL_URL_RE = re.compile(r"/details/([A-Za-z0-9_-]+)/([^?]+)(?:\?team=([A-Z0-9-]+))?")


def _unescape_js(s: str) -> str:
    """window.__staticRouterHydrationData = JSON.parse("...") — the inner
    string is double-escaped. Parsing it as a JSON string gives us the real
    JSON text, which we then parse again.
    """
    return json.loads(f'"{s}"')


class AppleScraper(BaseScraper):
    portal = "apple"
    BASE_URL = "https://jobs.apple.com/en-us/search"
    MAX_PAGES = 3  # 20 results/page — 60 roles per query is plenty

    def __init__(self, *, queries: list[str] | None = None, team: str = "SFTWR"):
        self._browser: BrowserSession | None = None
        # `team=SFTWR` is Apple's top-level Software & Services team code.
        # Without a team filter, the `search` param is ignored by the React
        # app — discovered 2026-04-21. Keep this default unless we find a
        # broader code that still narrows the 4,900-role firehose.
        self._team = team
        self._queries = queries or [
            "engineering manager",
            "director engineering",
            "principal engineer",
            "ai engineering",
            "machine learning engineer",
            "platform engineering",
        ]

    def _session(self) -> BrowserSession:
        if self._browser is None:
            self._browser = BrowserSession()
        return self._browser

    def search(self, query: str = "") -> list[dict]:
        """Run the configured query list and return deduped roles. `query`
        from the caller is ignored to match the cross-scraper interface.
        """
        results: list[dict] = []
        seen: set[str] = set()
        for q in self._queries:
            for page in range(1, self.MAX_PAGES + 1):
                params = {
                    "search": q,
                    "team": self._team,
                    "location": "united-states-USA",
                    "page": page,
                    "sort": "relevance",
                }
                url = f"{self.BASE_URL}?{urlencode(params)}"
                try:
                    html = self._session().fetch(
                        url,
                        wait_for='a[href*="/details/"]',
                        timeout_ms=25000,
                    )
                except Exception:
                    break
                page_results = self._parse(html)
                if not page_results:
                    break
                added = 0
                for r in page_results:
                    if r["id"] in seen:
                        continue
                    seen.add(r["id"])
                    results.append(r)
                    added += 1
                # If the whole page was duplicates, stop paging this query
                if added == 0:
                    break
        return results

    @staticmethod
    def _parse(html: str) -> list[dict]:
        out = AppleScraper._parse_hydration(html)
        if out:
            return out
        return AppleScraper._parse_dom(html)

    @staticmethod
    def _parse_hydration(html: str) -> list[dict]:
        m = _HYDRATION_RE.search(html)
        if not m:
            return []
        try:
            raw = _unescape_js(m.group(1))
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

        search_state = data.get("loaderData", {}).get("search") or {}
        records = search_state.get("searchResults") or []
        out: list[dict] = []
        for r in records:
            pos_id = r.get("positionId") or r.get("id")
            if not pos_id:
                continue
            title = r.get("postingTitle") or r.get("transformedPostingTitle") or "?"
            slug = r.get("transformedPostingTitle") or "role"
            team = r.get("team") or ""
            team_slug = team.get("teamCode") if isinstance(team, dict) else team
            url = (
                f"https://jobs.apple.com/en-us/details/{pos_id}/"
                f"{_slugify(slug)}"
                + (f"?team={team_slug}" if team_slug else "")
            )
            locs = r.get("locations") or []
            if isinstance(locs, list) and locs:
                first = locs[0]
                location = first.get("name") if isinstance(first, dict) else str(first)
            else:
                location = ""
            if r.get("homeOffice"):
                location = (location + " (remote)").strip()
            summary = r.get("jobSummary") or ""
            out.append({
                "id": f"apple-{pos_id}",
                "portal": "apple",
                "url": url,
                "title": title,
                "company": "Apple",
                "location": location or "United States",
                "raw_html": json.dumps({
                    "positionId": pos_id,
                    "title": title,
                    "team": team_slug,
                    "locations": locs,
                    "jobSummary": summary,
                    "type": r.get("type"),
                    "postingDate": r.get("postingDate"),
                }),
            })
        return out

    @staticmethod
    def _parse_dom(html: str) -> list[dict]:
        """Fallback: extract from rendered anchors when hydration is absent."""
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        seen: set[str] = set()
        for a in soup.select('a[href*="/details/"]'):
            href = a.get("href", "")
            m = _DETAIL_URL_RE.search(href)
            if not m:
                continue
            pos_id, slug, team = m.group(1), m.group(2), m.group(3) or ""
            if pos_id in seen:
                continue
            # The title anchor has visible text; the "See full role description"
            # anchor is empty — only keep anchors with real text.
            text = a.get_text(strip=True)
            if not text or text.lower().startswith("see full"):
                continue
            seen.add(pos_id)

            # Location: walk up a few levels to find a sibling location block.
            location = ""
            cur = a
            for _ in range(5):
                cur = cur.parent
                if cur is None:
                    break
                loc_el = cur.select_one('[class*="location"], [data-qa*="location"]')
                if loc_el:
                    txt = loc_el.get_text(" ", strip=True)
                    # Strip the leading "Location" label if present
                    location = re.sub(r"^Location:?\s*", "", txt, flags=re.I)
                    break

            base = href if href.startswith("http") else f"https://jobs.apple.com{href}"
            out.append({
                "id": f"apple-{pos_id}",
                "portal": "apple",
                "url": base,
                "title": text,
                "company": "Apple",
                "location": location or "United States",
                "raw_html": json.dumps({
                    "positionId": pos_id,
                    "title": text,
                    "team": team,
                    "slug": slug,
                }),
            })
        return out

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None


def _slugify(s: str) -> str:
    s = (s or "role").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "role"
