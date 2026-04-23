import sqlite3
from jobscout.config import BUDGET_PER_PROVIDER, BUDGET_ALERT_THRESHOLD
from jobscout.db import insert_budget_entry, get_budget_total

# Approximate cost per 1M tokens (USD)
COST_TABLE = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6-20250514": {"input": 3.00, "output": 15.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-pro": {"input": 1.25, "output": 5.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rates = COST_TABLE.get(model, {"input": 1.0, "output": 5.0})
    cost = (tokens_in / 1_000_000) * rates["input"] + (tokens_out / 1_000_000) * rates["output"]
    return round(cost, 6)


def record_usage(conn: sqlite3.Connection, *, provider: str, tokens_in: int,
                 tokens_out: int, task: str, model: str) -> float:
    cost = estimate_cost(model, tokens_in, tokens_out)
    insert_budget_entry(conn, provider=provider, tokens_in=tokens_in,
                        tokens_out=tokens_out, estimated_cost=cost, task=task)
    return cost


def check_budget(conn: sqlite3.Connection, provider: str) -> tuple[bool, float]:
    spent = get_budget_total(conn, provider)
    remaining = BUDGET_PER_PROVIDER - spent
    return remaining > 0, round(remaining, 4)


def is_alert_threshold(conn: sqlite3.Connection, provider: str) -> bool:
    spent = get_budget_total(conn, provider)
    return spent >= BUDGET_PER_PROVIDER * BUDGET_ALERT_THRESHOLD


def budget_summary(conn: sqlite3.Connection) -> dict:
    result = {}
    for provider in ["anthropic", "gemini", "openai"]:
        spent = get_budget_total(conn, provider)
        result[provider] = {
            "spent": round(spent, 4),
            "remaining": round(BUDGET_PER_PROVIDER - spent, 4),
            "limit": BUDGET_PER_PROVIDER,
            "pct": round((spent / BUDGET_PER_PROVIDER) * 100, 1),
        }
    return result
