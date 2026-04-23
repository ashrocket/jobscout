import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    portal TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    posted_at TEXT,
    discovered_at TEXT NOT NULL,
    raw_html TEXT,
    extracted_json TEXT,
    score REAL,
    star_rating INTEGER,
    status TEXT DEFAULT 'new',
    pigeon_message_id TEXT,
    resume_used TEXT,
    applied_at TEXT,
    notes TEXT,
    archetype TEXT,
    archetype_confidence REAL,
    tailored_resume_path TEXT
);

CREATE TABLE IF NOT EXISTS budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    estimated_cost REAL,
    task TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    jobs_found INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cursor.fetchall()}
    if "archetype" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN archetype TEXT")
        conn.execute("ALTER TABLE jobs ADD COLUMN archetype_confidence REAL")
    if "tailored_resume_path" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN tailored_resume_path TEXT")
    conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def insert_job(conn: sqlite3.Connection, *, id: str, portal: str, url: str,
               title: str, company: str, location: str,
               posted_at: str | None = None, raw_html: str | None = None) -> bool:
    try:
        conn.execute(
            "INSERT INTO jobs (id, portal, url, title, company, location, posted_at, discovered_at, raw_html) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id, portal, url, title, company, location, posted_at, _now(), raw_html),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_job(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row


def update_job_status(conn: sqlite3.Connection, job_id: str, status: str, **kwargs) -> None:
    sets = ["status = ?"]
    vals = [status]
    for key, val in kwargs.items():
        sets.append(f"{key} = ?")
        vals.append(val)
    vals.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def get_jobs_by_status(conn: sqlite3.Connection, status: str) -> list[dict]:
    return conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY score DESC", (status,)).fetchall()


def insert_run(conn: sqlite3.Connection, portal: str) -> int:
    cursor = conn.execute(
        "INSERT INTO runs (portal, started_at) VALUES (?, ?)",
        (portal, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def complete_run(conn: sqlite3.Connection, run_id: int, jobs_found: int = 0,
                 jobs_new: int = 0, error: str | None = None) -> None:
    status = "failed" if error else "completed"
    conn.execute(
        "UPDATE runs SET completed_at = ?, jobs_found = ?, jobs_new = ?, status = ?, error = ? WHERE id = ?",
        (_now(), jobs_found, jobs_new, status, error, run_id),
    )
    conn.commit()


def insert_budget_entry(conn: sqlite3.Connection, *, provider: str, tokens_in: int,
                        tokens_out: int, estimated_cost: float, task: str) -> None:
    conn.execute(
        "INSERT INTO budget (provider, tokens_in, tokens_out, estimated_cost, task, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (provider, tokens_in, tokens_out, estimated_cost, task, _now()),
    )
    conn.commit()


def get_budget_total(conn: sqlite3.Connection, provider: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(estimated_cost), 0) as total FROM budget WHERE provider = ?",
        (provider,),
    ).fetchone()
    return row["total"]
