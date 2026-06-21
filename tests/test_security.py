"""
Security-focused tests. Verify that injection and malformed-input
attack surfaces are handled safely.
"""
import sqlite3
import pytest
from db.database import init_db, upsert_job, update_job, add_blacklist, is_blacklisted
from agents.searcher.base import _parse_cookies


# ── SQL injection ─────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "sec.db")
    init_db(path)
    return path


@pytest.fixture
def job(db):
    j = {
        "source": "linkedin", "job_id": "sec001", "title": "DE",
        "company": "Co", "location": "", "work_mode": "remote",
        "url": "https://x.com/1", "description": "", "salary_text": "",
        "salary_lpa": None, "posted_date": "",
    }
    upsert_job(db, j)
    return j


class TestSqlInjectionUpdateJob:
    def test_column_name_injection_blocked(self, db, job):
        with pytest.raises(ValueError):
            update_job(db, "linkedin", "sec001", **{"status=1;DROP TABLE jobs;--": "x"})

    def test_arbitrary_column_blocked(self, db, job):
        with pytest.raises(ValueError):
            update_job(db, "linkedin", "sec001", nonexistent_col="val")

    def test_value_injection_safe(self, db, job):
        """Values are parameterised — SQL in value must not execute."""
        malicious_value = "'; DROP TABLE jobs; --"
        update_job(db, "linkedin", "sec001", score_reason=malicious_value)

        # table must still exist and row must be intact
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT score_reason FROM jobs WHERE job_id='sec001'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == malicious_value  # stored literally, not executed

    def test_source_injection_safe(self, db, job):
        malicious = "linkedin' OR '1'='1"
        update_job(db, malicious, "sec001", score=5.0)
        # should not match any row (source doesn't match) — no error, no corruption
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT score FROM jobs WHERE job_id='sec001'").fetchone()
        conn.close()
        assert row[0] is None  # original row untouched


class TestSqlInjectionBlacklist:
    def test_company_value_injection_safe(self, db):
        malicious = "'; DROP TABLE blacklist; --"
        add_blacklist(db, "company", malicious)

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT * FROM blacklist").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][2] == malicious

    def test_is_blacklisted_injection_safe(self, db):
        add_blacklist(db, "company", "Spamco")
        # injection attempt in lookup value
        result = is_blacklisted(db, "Spamco' OR '1'='1")
        assert result is False  # should NOT match


class TestCookieInjection:
    def test_cookie_value_with_special_chars_accepted(self):
        """Cookie values may legitimately contain special chars — should not be rejected."""
        raw = [{"name": "sess", "value": "<script>alert(1)</script>"}]
        result = _parse_cookies(raw)
        # stored as-is; Playwright handles the actual context
        assert result[0]["value"] == "<script>alert(1)</script>"

    def test_cookie_name_cannot_be_none(self):
        with pytest.raises(ValueError):
            _parse_cookies([{"name": None, "value": "x"}])

    def test_extra_fields_in_cookie_ignored(self):
        raw = [{"name": "x", "value": "y", "evil_field": "DROP TABLE users"}]
        result = _parse_cookies(raw)
        assert "evil_field" not in result[0]

    def test_deeply_nested_value_not_accepted(self):
        with pytest.raises((ValueError, TypeError)):
            _parse_cookies([{"name": "x", "value": {"nested": "dict"}}])


class TestPathTraversal:
    def test_cookie_file_path_traversal_raises_not_found(self, tmp_path):
        import asyncio
        from unittest.mock import AsyncMock
        from agents.searcher.base import load_cookies

        fake_context = AsyncMock()
        malicious_path = str(tmp_path) + "/../../etc/passwd"

        async def run():
            await load_cookies(fake_context, malicious_path)

        with pytest.raises(FileNotFoundError):
            asyncio.run(run())
