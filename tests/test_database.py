import pytest
import sqlite3
import tempfile
import os
from db.database import (
    init_db, upsert_job, update_job, get_jobs_for_review,
    get_approved_jobs, is_blacklisted, add_blacklist, get_stats,
    _UPDATABLE_COLUMNS,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_jobs.db")
    init_db(path)
    return path


@pytest.fixture
def job():
    return {
        "source": "linkedin",
        "job_id": "abc123",
        "title": "Senior Data Engineer",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "remote",
        "url": "https://example.com/job/1",
        "description": "PySpark, Azure, Databricks",
        "salary_text": "40 LPA",
        "salary_lpa": 40.0,
        "posted_date": "2026-06-20",
    }


class TestInitDb:
    def test_creates_tables(self, db):
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "jobs" in tables
        assert "blacklist" in tables

    def test_idempotent(self, db):
        init_db(db)  # second call should not raise
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        conn.close()
        assert count == 0


class TestUpsertJob:
    def test_inserts_new_job(self, db, job):
        assert upsert_job(db, job) is True

    def test_duplicate_returns_false(self, db, job):
        upsert_job(db, job)
        assert upsert_job(db, job) is False

    def test_different_source_same_id_is_new(self, db, job):
        upsert_job(db, job)
        job2 = {**job, "source": "indeed"}
        assert upsert_job(db, job2) is True

    def test_job_stored_correctly(self, db, job):
        upsert_job(db, job)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE job_id = 'abc123'").fetchone()
        conn.close()
        assert row["title"] == "Senior Data Engineer"
        assert row["status"] == "found"
        assert row["salary_lpa"] == 40.0


class TestUpdateJob:
    def test_updates_score(self, db, job):
        upsert_job(db, job)
        update_job(db, job["source"], job["job_id"], score=8.5, score_reason="Great match", status="ranked")
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT score, score_reason, status FROM jobs WHERE job_id = ?", (job["job_id"],)).fetchone()
        conn.close()
        assert row["score"] == 8.5
        assert row["score_reason"] == "Great match"
        assert row["status"] == "ranked"

    def test_noop_with_no_fields(self, db, job):
        upsert_job(db, job)
        update_job(db, job["source"], job["job_id"])  # should not raise

    def test_rejects_unknown_column(self, db, job):
        upsert_job(db, job)
        with pytest.raises(ValueError, match="disallowed column"):
            update_job(db, job["source"], job["job_id"], DROP_TABLE="jobs; --")

    def test_rejects_sql_injection_in_column_name(self, db, job):
        upsert_job(db, job)
        with pytest.raises(ValueError, match="disallowed column"):
            update_job(db, job["source"], job["job_id"], **{"status = 'applied'; --": "x"})

    def test_all_allowed_columns_accepted(self, db, job):
        upsert_job(db, job)
        # should not raise for any whitelisted column
        update_job(db, job["source"], job["job_id"],
                   score=7.0, score_reason="ok", status="ranked",
                   cover_letter="Dear Hiring Manager...", applied_at="2026-06-22T10:00:00")


class TestGetJobsForReview:
    def test_returns_ranked_above_threshold(self, db, job):
        upsert_job(db, job)
        update_job(db, job["source"], job["job_id"], score=8.0, status="ranked")
        jobs = get_jobs_for_review(db, min_score=6.0, top_n=10)
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "abc123"

    def test_excludes_below_threshold(self, db, job):
        upsert_job(db, job)
        update_job(db, job["source"], job["job_id"], score=4.0, status="ranked")
        jobs = get_jobs_for_review(db, min_score=6.0, top_n=10)
        assert len(jobs) == 0

    def test_excludes_non_ranked_status(self, db, job):
        upsert_job(db, job)
        update_job(db, job["source"], job["job_id"], score=9.0, status="found")
        jobs = get_jobs_for_review(db, min_score=6.0, top_n=10)
        assert len(jobs) == 0

    def test_top_n_limits_results(self, db):
        for i in range(5):
            j = {
                "source": "linkedin", "job_id": f"job{i}", "title": f"DE {i}",
                "company": "Co", "location": "Remote", "work_mode": "remote",
                "url": f"https://x.com/{i}", "description": "", "salary_text": "",
                "salary_lpa": None, "posted_date": "",
            }
            upsert_job(db, j)
            update_job(db, "linkedin", f"job{i}", score=float(7 + i % 3), status="ranked")
        jobs = get_jobs_for_review(db, min_score=6.0, top_n=2)
        assert len(jobs) == 2

    def test_sorted_by_score_desc(self, db):
        for i, score in enumerate([7.0, 9.0, 8.0]):
            j = {
                "source": "indeed", "job_id": f"s{i}", "title": f"Job {i}",
                "company": "Co", "location": "IN", "work_mode": "hybrid",
                "url": f"https://x.com/{i}", "description": "", "salary_text": "",
                "salary_lpa": None, "posted_date": "",
            }
            upsert_job(db, j)
            update_job(db, "indeed", f"s{i}", score=score, status="ranked")
        jobs = get_jobs_for_review(db, min_score=6.0, top_n=10)
        scores = [j["score"] for j in jobs]
        assert scores == sorted(scores, reverse=True)


class TestBlacklist:
    def test_add_and_check(self, db):
        add_blacklist(db, "company", "Spamco")
        assert is_blacklisted(db, "Spamco") is True

    def test_case_insensitive(self, db):
        add_blacklist(db, "company", "SpamCo")
        assert is_blacklisted(db, "spamco") is True
        assert is_blacklisted(db, "SPAMCO") is True

    def test_not_blacklisted(self, db):
        assert is_blacklisted(db, "GoodCorp") is False

    def test_duplicate_add_is_idempotent(self, db):
        add_blacklist(db, "company", "Spamco")
        add_blacklist(db, "company", "Spamco")  # should not raise


class TestGetStats:
    def test_empty_db(self, db):
        stats = get_stats(db)
        assert stats["total"] == 0

    def test_counts_by_status(self, db):
        statuses = ["found", "found", "ranked", "rejected", "approved", "applied"]
        for i, status in enumerate(statuses):
            j = {
                "source": "linkedin", "job_id": f"st{i}", "title": "DE",
                "company": "Co", "location": "", "work_mode": "remote",
                "url": f"https://x.com/{i}", "description": "", "salary_text": "",
                "salary_lpa": None, "posted_date": "",
            }
            upsert_job(db, j)
            if status != "found":
                update_job(db, "linkedin", f"st{i}", status=status)

        stats = get_stats(db)
        assert stats["total"] == 6
        assert stats["found"] == 2
        assert stats["ranked"] == 1
        assert stats["rejected"] == 1
        assert stats["approved"] == 1
        assert stats["applied"] == 1
