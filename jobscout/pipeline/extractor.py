import json
import sqlite3
from jobscout.llm import call_llm

EXTRACT_SYSTEM = """You extract structured job listing data from HTML. Return ONLY valid JSON with these fields:
{
    "title": "job title",
    "company": "company name",
    "location": "location string",
    "industry": "primary industry (healthcare, fintech, travel, retail, defense, AI, automotive, other)",
    "company_stage": "startup/Series A/B/C/D/growth/public/unknown",
    "team_size": "engineering team size if mentioned, else null",
    "description": "2-3 sentence summary of the role",
    "signals": ["list of keywords: hypergrowth, rebuilding, post-acquisition, platform-migration, scaling, remote, AI, ML, etc."],
    "posted_date": "when posted if available",
    "salary_range": "salary if mentioned, else null",
    "remote": true/false/null
}
No markdown, no explanation, just the JSON object."""

EXTRACT_PROMPT = "Extract structured job data from this HTML listing:\n\n{html}"


def extract_job_data(raw_html: str, conn: sqlite3.Connection | None) -> dict | None:
    html = raw_html[:8000] if len(raw_html) > 8000 else raw_html

    response = call_llm(
        task="extract",
        system=EXTRACT_SYSTEM,
        prompt=EXTRACT_PROMPT.format(html=html),
        conn=conn,
    )

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return None
