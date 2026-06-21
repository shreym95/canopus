import sqlite3
import json
from datetime import datetime
from pathlib import Path


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            job_id      TEXT NOT NULL,
            title       TEXT NOT NULL,
            company     TEXT NOT NULL,
            location    TEXT,
            work_mode   TEXT,
            salary_text TEXT,
            salary_lpa  REAL,
            url         TEXT NOT NULL,
            description TEXT,
            posted_date TEXT,
            score       REAL,
            score_reason TEXT,
            status      TEXT DEFAULT 'found',
            cover_letter TEXT,
            applied_at  TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(source, job_id)
        );

        CREATE TABLE IF NOT EXISTS blacklist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL,
            value       TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(type, value)
        );

        CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_score  ON jobs(score DESC);
    """)
    conn.commit()
    conn.close()


def upsert_job(db_path: str, job: dict) -> bool:
    """Returns True if new, False if already exists."""
    conn = get_conn(db_path)
    try:
        conn.execute("""
            INSERT INTO jobs (source, job_id, title, company, location, work_mode,
                              salary_text, salary_lpa, url, description, posted_date)
            VALUES (:source, :job_id, :title, :company, :location, :work_mode,
                    :salary_text, :salary_lpa, :url, :description, :posted_date)
        """, job)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_job(db_path: str, source: str, job_id: str, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [source, job_id]
    conn = get_conn(db_path)
    conn.execute(
        f"UPDATE jobs SET {set_clause} WHERE source = ? AND job_id = ?", vals
    )
    conn.commit()
    conn.close()


def get_jobs_for_review(db_path: str, min_score: float, top_n: int) -> list[dict]:
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT * FROM jobs
        WHERE status = 'ranked' AND score >= ?
        ORDER BY score DESC
        LIMIT ?
    """, (min_score, top_n)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approved_jobs(db_path: str) -> list[dict]:
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT * FROM jobs WHERE status = 'approved'
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_blacklisted(db_path: str, company: str) -> bool:
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT 1 FROM blacklist WHERE type = 'company' AND lower(value) = lower(?)",
        (company,)
    ).fetchone()
    conn.close()
    return row is not None


def add_blacklist(db_path: str, type_: str, value: str):
    conn = get_conn(db_path)
    try:
        conn.execute("INSERT INTO blacklist (type, value) VALUES (?, ?)", (type_, value))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def get_stats(db_path: str) -> dict:
    conn = get_conn(db_path)
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'found'    THEN 1 ELSE 0 END) as found,
            SUM(CASE WHEN status = 'ranked'   THEN 1 ELSE 0 END) as ranked,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'applied'  THEN 1 ELSE 0 END) as applied,
            SUM(CASE WHEN status = 'skipped'  THEN 1 ELSE 0 END) as skipped
        FROM jobs
    """).fetchone()
    conn.close()
    return dict(row)
