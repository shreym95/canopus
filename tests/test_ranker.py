import json
import pytest
from unittest.mock import patch
from agents.ranker import build_profile_summary, rank_job, rank_jobs_batch


def make_chat_mock(response_json: dict):
    """Return a patch target that makes llm_client.chat return response_json as string."""
    return patch("agents.ranker.chat", return_value=json.dumps(response_json))


class TestBuildProfileSummary:
    def test_contains_title_and_years(self, sample_profile):
        summary = build_profile_summary(sample_profile)
        assert "Senior Data Engineer" in summary
        assert "8" in summary

    def test_contains_skills(self, sample_profile):
        summary = build_profile_summary(sample_profile)
        assert "PySpark" in summary
        assert "Databricks" in summary

    def test_contains_salary_floor(self, sample_profile):
        summary = build_profile_summary(sample_profile)
        assert "35" in summary

    def test_handles_empty_skills_gracefully(self):
        profile = {
            "current_title": "DE", "years_experience": 3,
            "target_roles": [], "certifications": [],
            "skills": {},
            "work_preferences": {"salary_floor_lpa": 20, "modes": []},
        }
        summary = build_profile_summary(profile)
        assert "DE" in summary

    def test_caps_skills_at_20(self, sample_profile):
        sample_profile["skills"]["core"] = [f"skill{i}" for i in range(30)]
        summary = build_profile_summary(sample_profile)
        # 20 skills max — skill20 through skill29 should not appear
        assert "skill19" not in summary or "skill20" not in summary


class TestRankJob:
    def test_valid_response_parsed(self, sample_job, sample_profile):
        with make_chat_mock({"score": 8, "reason": "Strong Azure/PySpark match", "role_match": True}):
            score, reason = rank_job(sample_job, sample_profile)
        assert score == 8.0
        assert "Azure" in reason

    def test_score_below_threshold(self, sample_job, sample_profile):
        with make_chat_mock({"score": 3, "reason": "Wrong domain", "role_match": False}):
            score, reason = rank_job(sample_job, sample_profile)
        assert score == 3.0

    def test_malformed_json_returns_zero(self, sample_job, sample_profile):
        with patch("agents.ranker.chat", return_value="not json at all"):
            score, reason = rank_job(sample_job, sample_profile)
        assert score == 0.0
        assert reason == "parse error"

    def test_missing_score_field_returns_zero(self, sample_job, sample_profile):
        with make_chat_mock({"reason": "ok"}):
            score, _ = rank_job(sample_job, sample_profile)
        assert score == 0.0

    def test_no_description_uses_title_fallback(self, sample_profile):
        job = {
            "source": "naukri", "job_id": "x", "title": "Lead DE",
            "company": "BigCo", "location": "Mumbai", "description": "",
        }
        captured = {}
        def capture_chat(messages, **kwargs):
            captured["content"] = messages[0]["content"]
            return json.dumps({"score": 5, "reason": "ok"})

        with patch("agents.ranker.chat", side_effect=capture_chat):
            rank_job(job, sample_profile)
        assert "Lead DE" in captured["content"]
        assert "BigCo" in captured["content"]

    def test_description_truncated_to_3000_chars(self, sample_job, sample_profile):
        sample_job["description"] = "x" * 5000
        captured = {}
        def capture_chat(messages, **kwargs):
            captured["content"] = messages[0]["content"]
            return json.dumps({"score": 7, "reason": "ok"})

        with patch("agents.ranker.chat", side_effect=capture_chat):
            rank_job(sample_job, sample_profile)
        import re
        runs = re.findall(r"x+", captured["content"])
        longest_run = max(len(r) for r in runs) if runs else 0
        assert longest_run <= 3000


class TestRankJobsBatch:
    def test_scores_all_jobs(self, sample_profile):
        jobs = [
            {"source": "linkedin", "job_id": f"j{i}", "title": "DE", "company": "Co",
             "location": "", "description": "PySpark Azure"}
            for i in range(3)
        ]
        responses = [{"score": s, "reason": "ok"} for s in [9, 6, 8]]
        idx = [0]
        def mock_chat(messages, **kwargs):
            r = responses[idx[0] % len(responses)]
            idx[0] += 1
            return json.dumps(r)

        with patch("agents.ranker.chat", side_effect=mock_chat):
            ranked = rank_jobs_batch(jobs, sample_profile)

        assert len(ranked) == 3
        scores = [j["score"] for j in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_jobs_mutated_with_score_fields(self, sample_profile):
        jobs = [{"source": "indeed", "job_id": "z1", "title": "DE", "company": "X",
                 "location": "", "description": ""}]
        with make_chat_mock({"score": 7, "reason": "ok"}):
            rank_jobs_batch(jobs, sample_profile)
        assert "score" in jobs[0]
        assert "score_reason" in jobs[0]

    def test_empty_jobs_list(self, sample_profile):
        result = rank_jobs_batch([], sample_profile)
        assert result == []
