"""Title-based hard-zero prefilter for the scorer.

The LLM scorer has a tendency to latch onto isolated keywords ("AI",
"platform", "engineering") inside listings that are really sales, HR,
payroll, marketing, legal, or recruiting roles. This module provides a
cheap pre-filter that returns score=0 with a reason when a title clearly
belongs to a vetoed category AND lacks an engineering-leadership signal.

Used by both jobscout.pipeline.scorer and contractscout.scorer before the
LLM call — saves tokens and prevents false positives from entering the
'tuned' backlog.
"""
from __future__ import annotations

import re

# Role vetoes — case-insensitive substring match on the title.
_VETO_PATTERNS = [
    r"\bsales\b",
    r"\baccount executive\b",
    r"\baccount manager\b",
    r"\bcustomer success\b",
    r"\bbusiness development\b",
    r"\bpayroll\b",
    r"\bhris\b",
    r"\bhuman resources\b",
    r"\brecruit(er|ing|ment)\b",
    r"\btalent acquisition\b",
    r"\blegal\b",
    r"\bcounsel\b",
    r"\battorney\b",
    r"\bparalegal\b",
    r"\bmarketing\b",
    r"\bbrand\b",
    r"\bcontent\b",
    r"\beditor(ial)?\b",
    r"\bcopywrit(er|ing)\b",
    r"\bpublic relations\b",
    r"\bcommunications?\b",
    r"\bfinance\b",
    r"\baccountant\b",
    r"\baccounting\b",
    r"\bcontroller\b",
    r"\btreasur(er|y)\b",
    r"\btax\b",
    r"\baudit\b",
    r"\bprocurement\b",
    r"\bbuyer\b",
    r"\bsupply chain\b",
    r"\blogistics\b",
    r"\boperations? (manager|analyst|specialist|coordinator)\b",
    r"\bproject manager\b",
    r"\bprogram manager\b",
    r"\bscrum master\b",
    r"\banalyst\b",  # stand-alone "Analyst", but not "Data Analyst" if also eng
    r"\bsupport (specialist|engineer|analyst|agent|rep)\b",
    r"\bhelp ?desk\b",
    r"\btrainer\b",
    r"\bteacher\b",
    r"\bnurse\b",
    r"\bphysician\b",
    r"\btherapist\b",
    r"\bconsultant\b",  # body-shop consultancy listings
    r"\bsdr\b",
    r"\bbdr\b",
    r"\bcsm\b",
]

# Engineering leadership / IC engineering signals that OVERRIDE the veto.
# If a title matches ANY of these, the hard-zero does not apply.
_ENG_SIGNALS = [
    r"\b(vp|vice president)\b.*\b(engineering|technology|platform|infra|ai|ml|data|product engineering)\b",
    r"\b(svp|senior vp|senior vice president)\b.*\b(engineering|technology|platform)\b",
    r"\b(cto|cio|ciso|cpo|cdo|chief technology|chief information|chief data|chief ai|chief product|chief engineering)\b",
    r"\bhead of (engineering|technology|platform|infra|ai|ml|data|product engineering|developer)\b",
    r"\bdirector\b.*\b(engineering|platform|infra|ai|ml|data|technology|developer|devops|site reliability)\b",
    r"\b(staff|principal|distinguished|senior staff)\b.*\b(engineer|architect)\b",
    r"\b(engineering manager|em|tech lead|technical lead|lead engineer|lead architect)\b",
    r"\b(software engineer|software developer|backend engineer|backend developer|"
    r"full[- ]?stack engineer|platform engineer|infrastructure engineer|site reliability engineer|"
    r"devops engineer|data engineer|ml engineer|ai engineer|security engineer|"
    r"cloud engineer|systems engineer|mobile engineer|ios engineer|android engineer|frontend engineer)\b",
    r"\b(architect|solutions architect|enterprise architect|data architect|platform architect|ai architect|ml architect|cloud architect)\b",
    r"\bfounding (engineer|cto|head of)\b",
]

_VETO_RE = re.compile("|".join(_VETO_PATTERNS), re.IGNORECASE)
_ENG_RE = re.compile("|".join(_ENG_SIGNALS), re.IGNORECASE)


def hard_zero_reason(title: str | None) -> str | None:
    """Return a reason string if the title should be hard-zeroed, else None.

    A title is hard-zeroed when it matches a veto pattern AND does NOT also
    match an engineering leadership / IC engineering signal. This is
    intentionally strict: when both signals appear (e.g. "Director of
    Engineering, Sales Operations"), the engineering signal wins.
    """
    if not title:
        return None
    t = title.strip()
    if not t:
        return None
    veto_match = _VETO_RE.search(t)
    if not veto_match:
        return None
    if _ENG_RE.search(t):
        return None
    return f"title matches veto pattern '{veto_match.group(0)}' without engineering-leadership signal"


def hard_zero_result(title: str | None) -> dict | None:
    """Return a ready-to-insert score dict if the title is hard-zeroed."""
    reason = hard_zero_reason(title)
    if reason is None:
        return None
    return {
        "score": 0,
        "star_rating": 0,
        "reasoning": f"HARD ZERO: {reason}",
        "hard_zero": True,
    }
