import json
import sqlite3
from jobscout.llm import call_llm
from jobscout.config import STAR_RANGES, ARCHETYPES, get_profile_summary
from jobscout.pipeline.title_filter import hard_zero_result

_score_system: str | None = None


def _build_score_system() -> str:
    global _score_system
    if _score_system is not None:
        return _score_system
    profile = get_profile_summary()
    _score_system = f"""You are a job fit scorer. Given a candidate profile and a job listing, score the fit from 0-100.

CANDIDATE PROFILE:
{profile}

Return ONLY valid JSON:
{{
    "score": <0-100>,
    "reasoning": "<2-3 sentences explaining the score>"
}}

Scoring weights:
- Title match (30%): VP Eng, CTO, SVP Eng, Head of Eng, VP AI/ML
- Industry alignment (20%): healthcare, fintech, travel, retail, defense, AI, automotive
- Scaling signal (20%): hypergrowth, rebuilding, post-acquisition, platform migration
- Company stage (15%): Series B+ through mid-market
- Location (15%): Remote > hybrid > onsite

No markdown wrapping, just the JSON object."""
    return _score_system


def _to_star_rating(score: int) -> int:
    for min_score, stars in STAR_RANGES:
        if score >= min_score:
            return stars
    return 0


def score_job(extracted: dict, conn: sqlite3.Connection | None,
              classification: dict | None = None) -> dict | None:
    hz = hard_zero_result(extracted.get("title") if isinstance(extracted, dict) else None)
    if hz is not None:
        return hz

    context = ""
    if classification:
        archetype_key = classification.get("archetype", "")
        archetype_info = ARCHETYPES.get(archetype_key, {})
        label = archetype_info.get("label", archetype_key)
        context = f"\n\nARCHETYPE CLASSIFICATION: {label} (confidence: {classification.get('confidence', 'N/A')})\nReasoning: {classification.get('reasoning', '')}\n"

    prompt = f"Score this job listing for fit:{context}\n\n{json.dumps(extracted, indent=2)}"

    response = call_llm(task="score", system=_build_score_system(), prompt=prompt, conn=conn)

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        result["star_rating"] = _to_star_rating(result["score"])
        return result
    except (json.JSONDecodeError, KeyError, IndexError):
        return None
