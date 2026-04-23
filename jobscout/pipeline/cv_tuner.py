import json
import sqlite3
from jobscout.llm import call_llm

CV_TUNE_SYSTEM = """You are an ATS resume optimizer. Given an HTML resume and a job description, make targeted adjustments to improve match rate:

1. SUMMARY: Adjust the opening summary to emphasize the most relevant experience for this specific role. Do not invent new claims.

2. BULLET REORDERING: Within each job's bullet points, move the most relevant accomplishments to the top. Do not add or remove bullets.

3. KEYWORD ALIGNMENT: Where the candidate's experience matches a JD requirement but uses different terminology, align the language. Example: JD says "CI/CD pipelines", resume says "deployment automation" → adjust to "CI/CD pipeline automation"

4. DO NOT: Add new accomplishments, change numbers/metrics, remove sections, alter job titles or dates, or change the HTML structure.

Return the complete modified HTML. No markdown wrapping — just the HTML."""


def tune_cv(
    resume_html: str,
    extracted: dict,
    classification: dict,
    conn: sqlite3.Connection | None,
) -> str | None:
    prompt = (
        f"JOB DESCRIPTION:\n{json.dumps(extracted, indent=2)}\n\n"
        f"ARCHETYPE: {classification.get('archetype', 'unknown')}\n\n"
        f"RESUME HTML:\n{resume_html}"
    )

    try:
        response = call_llm(task="cv_tune", system=CV_TUNE_SYSTEM, prompt=prompt, conn=conn)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return text
    except Exception:
        return None
