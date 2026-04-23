import json
import sqlite3
from jobscout.llm import call_llm
from jobscout.config import ARCHETYPES, ARCHETYPE_RESUME_MAP

_archetype_descriptions = "\n".join(
    f"- {key}: {info['label']} — signals: {', '.join(info['signals'])}"
    for key, info in ARCHETYPES.items()
)

CLASSIFY_SYSTEM = f"""You classify job listings into archetypes for a VP Engineering / CTO candidate.

ARCHETYPES:
{_archetype_descriptions}

Given a job listing's extracted data, return the single best-fit archetype.
If a job spans two archetypes, pick the one most aligned with scaling engineering orgs.

Return ONLY valid JSON:
{{
    "archetype": "<archetype_key>",
    "confidence": <0.0-1.0>,
    "reasoning": "<1-2 sentences>"
}}

No markdown wrapping, just the JSON object."""


def classify_job(extracted: dict, conn: sqlite3.Connection | None) -> dict | None:
    prompt = f"Classify this job listing:\n\n{json.dumps(extracted, indent=2)}"

    response = call_llm(task="classify", system=CLASSIFY_SYSTEM, prompt=prompt, conn=conn)

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        archetype = result["archetype"]
        result["resume_variant"] = ARCHETYPE_RESUME_MAP.get(archetype, "default")
        return result
    except (json.JSONDecodeError, KeyError, IndexError):
        return None
