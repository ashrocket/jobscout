# jobscout/config.py
import os
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths — can be overridden by user config or env vars
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = Path(__file__).parent / "templates"
SOURCES_DIR = PROJECT_ROOT / "sources"
CRED_DIR = Path(os.environ.get(
    "JOBSCOUT_CRED_DIR",
    os.path.expanduser("~/.config/jobscout/credentials"),
))

# Database
DB_PATH = DATA_DIR / "jobscout.db"

# Local CLI mode — set JOBSCOUT_LOCAL=1 to use claude/gemini/codex CLIs instead of APIs
LOCAL_MODE = bool(os.environ.get("JOBSCOUT_LOCAL", ""))

# Ollama model to use when remapping Gemini models in local mode
OLLAMA_MODEL = os.environ.get("JOBSCOUT_OLLAMA_MODEL", "gemma4:e4b")

# ---------------------------------------------------------------------------
# Budget limits (USD) — public framework defaults
# ---------------------------------------------------------------------------
BUDGET_PER_PROVIDER = 10.0
BUDGET_ALERT_THRESHOLD = 0.70  # alert at 70%

# ---------------------------------------------------------------------------
# Model config — primary and fallback for each pipeline stage
# ---------------------------------------------------------------------------
MODELS = {
    "extract": {
        "primary": {"provider": "openai", "model": "gpt-4o-mini"},
        "fallback": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    },
    "score": {
        "primary": {"provider": "openai", "model": "gpt-4o"},
        "fallback": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
    },
    "report": {
        "primary": {"provider": "openai", "model": "gpt-4o"},
        "fallback": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
    },
    "classify": {
        "primary": {"provider": "openai", "model": "gpt-4o-mini"},
        "fallback": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    },
    "cv_tune": {
        "primary": {"provider": "openai", "model": "gpt-4o"},
        "fallback": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
    },
    "apply_q": {
        "primary": {"provider": "openai", "model": "gpt-4o-mini"},
        "fallback": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    },
}

# ---------------------------------------------------------------------------
# Scoring thresholds — public framework defaults
# ---------------------------------------------------------------------------
SCORE_THRESHOLD = 60
STAR_RANGES = [(90, 5), (75, 4), (60, 3)]

# ---------------------------------------------------------------------------
# Archetype definitions — generic, not PII
# ---------------------------------------------------------------------------
ARCHETYPES = {
    "hypergrowth_builder": {
        "label": "Hypergrowth Builder",
        "signals": ["hypergrowth", "scaling", "rapid-growth", "series", "fundraise", "org-building"],
        "resume_variant": "vpeng",
    },
    "travel_aviation": {
        "label": "Travel/Aviation",
        "signals": ["travel", "aviation", "airline", "airport", "flight", "hospitality", "tourism"],
        "resume_variant": "travel",
    },
    "agentic_ai_ops": {
        "label": "Agentic AI / Ops Automation",
        "signals": ["AI", "ML", "agentic", "automation", "LLM", "generative", "machine-learning", "NLP"],
        "resume_variant": "default",
    },
    "healthcare": {
        "label": "Healthcare",
        "signals": ["healthcare", "health-tech", "medical", "therapy", "clinical", "pharma", "biotech"],
        "resume_variant": "healthcare",
    },
    "fintech": {
        "label": "Fintech",
        "signals": ["fintech", "financial", "banking", "payments", "lending", "insurance", "trading"],
        "resume_variant": "default",
    },
    "saas_enterprise": {
        "label": "SaaS Enterprise",
        "signals": ["SaaS", "enterprise", "B2B", "platform", "cloud", "subscription", "multi-tenant"],
        "resume_variant": "vpeng",
    },
    "platform_builder": {
        "label": "Platform Builder",
        "signals": ["platform", "rebuild", "migration", "acquisition", "integration", "rewrite", "modernization"],
        "resume_variant": "vpeng",
    },
}

ARCHETYPE_RESUME_MAP = {k: v["resume_variant"] for k, v in ARCHETYPES.items()}

# Title keywords for career page filtering — generic
TITLE_KEYWORDS = [
    "vp of engineering", "vp engineering", "head of engineering",
    "cto", "svp engineering", "vp ai", "vp machine learning",
    "vp platform", "chief technology",
]

# Backward-compat shim for legacy module-level imports during the YAML-config
# refactor. New code should call get_subreddits() / get_imessage_phone() instead.
REDDIT_SUBREDDITS: list[str] = []
IMESSAGE_PHONE: str = ""

# ---------------------------------------------------------------------------
# Paths for new features
# ---------------------------------------------------------------------------
DISCOVERED_COMPANIES_PATH = DATA_DIR / "discovered_companies.json"
TAILORED_DIR = DATA_DIR / "tailored"

# ---------------------------------------------------------------------------
# Cloudflare KV config for cloud credential fetch
# ---------------------------------------------------------------------------
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")

# ---------------------------------------------------------------------------
# User config — loaded from YAML, all PII lives here
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(os.environ.get(
    "JOBSCOUT_CONFIG",
    os.path.expanduser("~/.config/jobscout/config.yaml"),
))

_user_config: dict | None = None


def _load_user_config() -> dict:
    """Load user config from YAML file. Returns empty dict if file missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_user_config() -> dict:
    """Cached accessor for user config. Call this at runtime, not import time."""
    global _user_config
    if _user_config is None:
        _user_config = _load_user_config()
    return _user_config


# ---------------------------------------------------------------------------
# Convenience accessors for user config values used across many modules.
# Each returns the user's value or a sensible empty default.
# ---------------------------------------------------------------------------

def get_candidate() -> dict:
    return get_user_config().get("candidate", {})


def get_queries(portal: str) -> list[str]:
    return get_user_config().get("queries", {}).get(portal, [])


def get_subreddits() -> list[str]:
    return get_user_config().get("queries", {}).get("subreddits", [])


def get_resume_map() -> dict[str, str]:
    return get_user_config().get("resume_map", {"default": "resume.html"})


def get_company_seeds() -> dict[str, list[dict]]:
    return get_user_config().get("company_seeds", {})


def get_profile_summary() -> str:
    return get_user_config().get("profile_summary", "")


def get_imessage_phone() -> str:
    return get_user_config().get("notifications", {}).get("imessage_phone", "")


def get_pigeon_project() -> str:
    return get_user_config().get("notifications", {}).get("pigeon_project", "jobscout")


def get_contact_email() -> str:
    return get_user_config().get("candidate", {}).get("email", "")


# ---------------------------------------------------------------------------
# Credential reader — local files with Cloudflare KV fallback
# ---------------------------------------------------------------------------
_credential_cache: dict[str, str] = {}


def _fetch_from_cloudflare_kv(name: str) -> str:
    """Fetch a credential from Cloudflare KV. Never log or print the value."""
    import httpx
    if not CF_API_TOKEN:
        raise RuntimeError(
            f"Credential '{name}' not found locally and CF_API_TOKEN not set for KV fallback"
        )
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        f"/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/values/{name}"
    )
    resp = httpx.get(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
    resp.raise_for_status()
    return resp.text.strip()


def read_credential(name: str) -> str:
    """Read a credential file locally, falling back to Cloudflare KV. Never log or print."""
    if name in _credential_cache:
        return _credential_cache[name]
    local_path = CRED_DIR / name
    if local_path.exists():
        value = local_path.read_text().strip()
    else:
        value = _fetch_from_cloudflare_kv(name)
    _credential_cache[name] = value
    return value
