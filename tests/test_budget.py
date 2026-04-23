import tempfile
from pathlib import Path
from jobscout.db import init_db, insert_budget_entry
from jobscout.budget import record_usage, check_budget, budget_summary

def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return init_db(Path(f.name))


def test_record_usage_tracks_cost():
    conn = _tmp_db()
    record_usage(conn, provider="gemini", tokens_in=2000, tokens_out=500,
                 task="extract", model="gemini-2.0-flash")
    row = conn.execute("SELECT * FROM budget WHERE provider = 'gemini'").fetchone()
    assert row is not None
    assert row["tokens_in"] == 2000
    assert row["estimated_cost"] > 0
    conn.close()


def test_check_budget_under_limit():
    conn = _tmp_db()
    ok, remaining = check_budget(conn, "gemini")
    assert ok is True
    assert remaining == 10.0
    conn.close()


def test_check_budget_over_threshold():
    conn = _tmp_db()
    insert_budget_entry(conn, provider="anthropic", tokens_in=0, tokens_out=0,
                        estimated_cost=7.50, task="test")
    ok, remaining = check_budget(conn, "anthropic")
    assert ok is True
    assert remaining == 2.50
    conn.close()


def test_check_budget_exhausted():
    conn = _tmp_db()
    insert_budget_entry(conn, provider="openai", tokens_in=0, tokens_out=0,
                        estimated_cost=10.01, task="test")
    ok, remaining = check_budget(conn, "openai")
    assert ok is False
    assert remaining < 0
    conn.close()


def test_budget_summary():
    conn = _tmp_db()
    insert_budget_entry(conn, provider="gemini", tokens_in=1000, tokens_out=200,
                        estimated_cost=0.50, task="extract")
    insert_budget_entry(conn, provider="anthropic", tokens_in=3000, tokens_out=500,
                        estimated_cost=1.20, task="score")
    summary = budget_summary(conn)
    assert "gemini" in summary
    assert "anthropic" in summary
    assert summary["gemini"]["spent"] == 0.50
    assert summary["anthropic"]["spent"] == 1.20
    conn.close()
