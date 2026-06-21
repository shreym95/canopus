import pytest
from unittest.mock import patch
from agents.cover_letter import generate_cover_letter


MOCK_CL = "With 8 years building PySpark pipelines on Azure, I am a strong fit for the Senior DE role at Acme."


class TestGenerateCoverLetter:
    def test_returns_string(self, sample_job, sample_profile):
        with patch("agents.cover_letter.chat", return_value=MOCK_CL):
            result = generate_cover_letter(sample_job, sample_profile)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_strips_whitespace(self, sample_job, sample_profile):
        with patch("agents.cover_letter.chat", return_value="  \n" + MOCK_CL + "\n  "):
            result = generate_cover_letter(sample_job, sample_profile)
        assert result == MOCK_CL

    def test_prompt_contains_job_title_and_company(self, sample_job, sample_profile):
        captured = {}
        def capture(messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return MOCK_CL

        with patch("agents.cover_letter.chat", side_effect=capture):
            generate_cover_letter(sample_job, sample_profile)

        assert "Senior Data Engineer" in captured["prompt"]
        assert "Acme Corp" in captured["prompt"]

    def test_prompt_contains_candidate_name(self, sample_job, sample_profile):
        captured = {}
        def capture(messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return MOCK_CL

        with patch("agents.cover_letter.chat", side_effect=capture):
            generate_cover_letter(sample_job, sample_profile)

        assert "Test User" in captured["prompt"]

    def test_jd_excerpt_truncated_to_2000(self, sample_job, sample_profile):
        sample_job["description"] = "y" * 4000
        captured = {}
        def capture(messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return MOCK_CL

        with patch("agents.cover_letter.chat", side_effect=capture):
            generate_cover_letter(sample_job, sample_profile)

        # prompt includes template text too; count only the run of y's from description
        import re
        runs = re.findall(r"y+", captured["prompt"])
        longest_run = max(len(r) for r in runs) if runs else 0
        assert longest_run <= 2000

    def test_max_words_passed_to_prompt(self, sample_job, sample_profile):
        captured = {}
        def capture(messages, **kwargs):
            captured["prompt"] = messages[0]["content"]
            return MOCK_CL

        with patch("agents.cover_letter.chat", side_effect=capture):
            generate_cover_letter(sample_job, sample_profile, max_words=150)

        assert "150" in captured["prompt"]

    def test_empty_description_still_works(self, sample_job, sample_profile):
        sample_job["description"] = ""
        with patch("agents.cover_letter.chat", return_value=MOCK_CL):
            result = generate_cover_letter(sample_job, sample_profile)
        assert result == MOCK_CL
