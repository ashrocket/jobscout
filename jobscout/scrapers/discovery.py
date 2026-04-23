import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

_PLATFORM_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "ashby": "https://api.ashby.info/posting-api/job-board/{slug}",
    "lever": "https://api.lever.co/v0/postings/{slug}",
}

_EMPTY = {"greenhouse": [], "ashby": [], "lever": []}


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def try_discover_career_page(company_name: str) -> dict | None:
    slug = _slugify(company_name)

    for platform, url_template in _PLATFORM_URLS.items():
        url = url_template.format(slug=slug)
        try:
            resp = httpx.get(url, timeout=10)
        except httpx.RequestError:
            continue

        if resp.status_code != 200:
            continue

        data = resp.json()
        has_jobs = False
        if isinstance(data, list) and len(data) > 0:
            has_jobs = True
        elif isinstance(data, dict) and len(data.get("jobs", [])) > 0:
            has_jobs = True

        if has_jobs:
            return {
                "platform": platform,
                "slug": slug,
                "name": company_name,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }

    return None


def load_discovered(path: Path) -> dict:
    if not path.exists():
        return dict(_EMPTY)
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(_EMPTY)


def save_discovered(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
