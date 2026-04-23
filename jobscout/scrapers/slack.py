"""Slack community channel scraper.

Polls configured Slack channels for recent messages that look like job posts.
Uses the Slack Web API's `conversations.history` endpoint.

Setup required before this returns results:
    1. Create a Slack app at https://api.slack.com/apps (one app per workspace,
       or reuse if using user token).
    2. Install to each workspace with scopes: channels:history, channels:read,
       groups:history, groups:read (for private channels).
    3. Save user token at ~/.env/ashcode/slack/user-token (xoxp-...).
    4. Save channel list at ~/.env/ashcode/slack/channels.json, format:
       [
         {"workspace": "rands-leadership", "channel_id": "C02ABC", "channel_name": "jobs-hiring"},
         {"workspace": "progression-fyi", "channel_id": "C05XYZ", "channel_name": "job-board"}
       ]

Without creds/config, search() returns [] and the run passes cleanly.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

from jobscout.scrapers.base import BaseScraper
from jobscout.config import TITLE_KEYWORDS


SLACK_API = "https://slack.com/api"
_CREDS_DIR = Path(os.path.expanduser("~/.env/ashcode/slack"))
_TOKEN_PATH = _CREDS_DIR / "user-token"
_CHANNELS_PATH = _CREDS_DIR / "channels.json"

_LOOKBACK_SECONDS = 60 * 60 * 24 * 2  # last 48 hours

# Signals a message is a job post (not just chit-chat)
_HIRING_SIGNALS = re.compile(
    r"\b(hiring|we'?re\s+looking|we\s+need|seeking|apply|role|position|opening|VP|CTO|Head of|Director)\b",
    re.IGNORECASE,
)


def _load_config() -> tuple[str | None, list[dict]]:
    if not _TOKEN_PATH.exists() or not _CHANNELS_PATH.exists():
        return None, []
    try:
        token = _TOKEN_PATH.read_text().strip()
        channels = json.loads(_CHANNELS_PATH.read_text())
        if not isinstance(channels, list):
            return None, []
        return token, channels
    except Exception:
        return None, []


def _message_looks_like_job(text: str) -> bool:
    if not text or len(text) < 40:
        return False
    if not _HIRING_SIGNALS.search(text):
        return False
    # Must mention a seniority/role keyword to be worth surfacing
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in TITLE_KEYWORDS)


class SlackScraper(BaseScraper):
    portal = "slack"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=15.0)

    def search(self, query: str) -> list[dict]:
        """Poll configured channels for hiring-related messages in the last 48h.

        `query` is unused — Slack scraper iterates all configured channels.
        """
        token, channels = _load_config()
        if not token or not channels:
            return []

        oldest = int(time.time()) - _LOOKBACK_SECONDS
        results: list[dict] = []

        for ch in channels:
            channel_id = ch.get("channel_id")
            channel_name = ch.get("channel_name", channel_id)
            workspace = ch.get("workspace", "slack")
            if not channel_id:
                continue
            try:
                messages = self._fetch_channel_history(token, channel_id, oldest)
            except Exception:
                continue

            for msg in messages:
                text = msg.get("text", "") or ""
                if not _message_looks_like_job(text):
                    continue
                ts = msg.get("ts", "")
                author = msg.get("user", "") or msg.get("username", "unknown")
                # Derive a stable id
                slug = hashlib.md5(f"{workspace}|{channel_id}|{ts}".encode()).hexdigest()[:14]
                job_id = f"slack-{slug}"

                # Title = first 120 chars of message (cleaned)
                first_line = text.split("\n", 1)[0].strip()
                title = (first_line[:120] + "…") if len(first_line) > 120 else first_line

                # Slack deep-link
                team = msg.get("team", "")
                url = f"https://slack.com/archives/{channel_id}/p{ts.replace('.', '')}" if ts else ""

                results.append({
                    "id": job_id,
                    "portal": self.portal,
                    "url": url,
                    "title": title or f"Slack post in #{channel_name}",
                    "company": f"(via #{channel_name})",
                    "location": "Remote / Unknown",
                    "raw_html": f"<article><p>{text}</p><small>#{channel_name} · {workspace} · {author}</small></article>",
                })

        return results

    def _fetch_channel_history(self, token: str, channel_id: str, oldest: int) -> list[dict]:
        r = self._client.get(
            f"{SLACK_API}/conversations.history",
            headers={"Authorization": f"Bearer {token}"},
            params={"channel": channel_id, "oldest": str(oldest), "limit": "100"},
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return []
        return data.get("messages", [])

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass
