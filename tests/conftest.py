import os
import sys
import pytest

# ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# strip real API keys so no test accidentally hits a live endpoint
for key in ("XAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
    os.environ.pop(key, None)


@pytest.fixture
def sample_profile():
    return {
        "name": "Test User",
        "current_title": "Senior Data Engineer",
        "years_experience": 8,
        "target_roles": ["Senior Data Engineer", "Azure Data Engineer"],
        "certifications": ["DP-203", "DP-700"],
        "skills": {
            "core": ["PySpark", "SQL", "Python", "Databricks", "Azure Data Factory"],
            "platforms": ["Azure", "Airflow", "Hadoop"],
            "practices": ["ETL/ELT", "Pipeline Architecture"],
        },
        "work_preferences": {
            "salary_floor_lpa": 35,
            "modes": ["remote", "hybrid"],
        },
    }


@pytest.fixture
def sample_job():
    return {
        "source": "linkedin",
        "job_id": "123456",
        "title": "Senior Data Engineer",
        "company": "Acme Corp",
        "location": "Bangalore, India",
        "work_mode": "remote",
        "url": "https://linkedin.com/jobs/view/123456",
        "description": "Looking for Senior DE with PySpark, Azure, Databricks. 5+ years exp.",
        "salary_text": "40-55 LPA",
        "salary_lpa": 40.0,
        "posted_date": "2026-06-20",
    }
