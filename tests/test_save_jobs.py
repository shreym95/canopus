"""Tests for main.save_jobs — salary filtering and deduplication logic."""
import pytest
from db.database import init_db
from main import save_jobs


@pytest.fixture
def config(tmp_path):
    db = str(tmp_path / "jobs.db")
    init_db(db)
    return {
        "db": {"path": db},
        "search": {"salary_floor_lpa": 35},
    }


def make_job(job_id, salary_lpa=None, salary_text=""):
    return {
        "source": "linkedin",
        "job_id": job_id,
        "title": "Senior DE",
        "company": "Co",
        "location": "Remote",
        "work_mode": "remote",
        "url": f"https://x.com/{job_id}",
        "description": "PySpark Azure",
        "salary_text": salary_text,
        "salary_lpa": salary_lpa,
        "posted_date": "2026-06-20",
    }


class TestSaveJobs:
    def test_saves_job_with_unknown_salary(self, config):
        """Jobs with no salary info should pass through — we can't rule them out."""
        jobs = [make_job("j1", salary_lpa=None)]
        count = save_jobs(jobs, config)
        assert count == 1

    def test_saves_job_above_floor(self, config):
        jobs = [make_job("j2", salary_lpa=40.0)]
        count = save_jobs(jobs, config)
        assert count == 1

    def test_skips_job_below_floor(self, config):
        jobs = [make_job("j3", salary_lpa=20.0)]
        count = save_jobs(jobs, config)
        assert count == 0

    def test_skips_job_at_exactly_floor(self, config):
        """35 LPA is NOT below 35 — should save."""
        jobs = [make_job("j4", salary_lpa=35.0)]
        count = save_jobs(jobs, config)
        assert count == 1

    def test_deduplication_across_calls(self, config):
        jobs = [make_job("dup1", salary_lpa=45.0)]
        assert save_jobs(jobs, config) == 1
        assert save_jobs(jobs, config) == 0  # second call — already exists

    def test_mixed_batch(self, config):
        jobs = [
            make_job("ok1", salary_lpa=50.0),
            make_job("skip1", salary_lpa=15.0),
            make_job("ok2", salary_lpa=None),   # unknown → keep
        ]
        count = save_jobs(jobs, config)
        assert count == 2

    def test_sets_default_fields(self, config):
        """Jobs missing optional fields should not crash."""
        job = {
            "source": "naukri", "job_id": "min1",
            "title": "DE", "company": "X",
            "location": "IN", "work_mode": "onsite",
            "url": "https://x.com/1",
        }
        count = save_jobs([job], config)
        assert count == 1
