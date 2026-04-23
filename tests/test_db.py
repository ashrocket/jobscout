import sqlite3
import tempfile
from pathlib import Path
from jobscout.db import init_db, insert_job, get_job, update_job_status, get_jobs_by_status, insert_run, complete_run


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return Path(f.name)


def test_init_db_creates_tables():
    db_path = _tmp_db()
    conn = init_db(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "jobs" in tables
    assert "budget" in tables
    assert "runs" in tables
    conn.close()


def test_insert_and_get_job():
    db_path = _tmp_db()
    conn = init_db(db_path)
    insert_job(conn, id="abc123", portal="linkedin", url="https://linkedin.com/jobs/123",
               title="VP Engineering", company="Acme", location="Remote")
    job = get_job(conn, "abc123")
    assert job is not None
    assert job["title"] == "VP Engineering"
    assert job["status"] == "new"
    conn.close()


def test_insert_duplicate_is_ignored():
    db_path = _tmp_db()
    conn = init_db(db_path)
    insert_job(conn, id="abc123", portal="linkedin", url="https://example.com",
               title="VP Eng", company="Acme", location="Remote")
    insert_job(conn, id="abc123", portal="linkedin", url="https://example.com",
               title="VP Eng UPDATED", company="Acme", location="Remote")
    job = get_job(conn, "abc123")
    assert job["title"] == "VP Eng"
    conn.close()


def test_update_job_status():
    db_path = _tmp_db()
    conn = init_db(db_path)
    insert_job(conn, id="abc123", portal="indeed", url="https://indeed.com/123",
               title="CTO", company="Startup", location="NYC")
    update_job_status(conn, "abc123", "scored", score=85.0, star_rating=4)
    job = get_job(conn, "abc123")
    assert job["status"] == "scored"
    assert job["score"] == 85.0
    assert job["star_rating"] == 4
    conn.close()


def test_get_jobs_by_status():
    db_path = _tmp_db()
    conn = init_db(db_path)
    insert_job(conn, id="j1", portal="linkedin", url="https://a.com", title="VP Eng", company="A", location="Remote")
    insert_job(conn, id="j2", portal="indeed", url="https://b.com", title="CTO", company="B", location="NYC")
    update_job_status(conn, "j1", "scored", score=80.0, star_rating=4)
    scored = get_jobs_by_status(conn, "scored")
    assert len(scored) == 1
    assert scored[0]["id"] == "j1"
    conn.close()


def test_insert_and_complete_run():
    db_path = _tmp_db()
    conn = init_db(db_path)
    run_id = insert_run(conn, portal="linkedin")
    assert run_id is not None
    complete_run(conn, run_id, jobs_found=10, jobs_new=3)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row is not None
    conn.close()


def test_migrate_adds_new_columns():
    db_path = _tmp_db()
    conn = init_db(db_path)
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "archetype" in columns
    assert "archetype_confidence" in columns
    assert "tailored_resume_path" in columns
    conn.close()
