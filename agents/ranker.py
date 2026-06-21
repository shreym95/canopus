import json
from .llm_client import chat

RANK_PROMPT = """You are a job-fit evaluator. Given a candidate profile and a job description, score how well they match.

Candidate Profile:
{profile_summary}

Job Description:
{jd_text}

Respond with JSON only, no explanation outside the JSON:
{{
  "score": <integer 1-10>,
  "reason": "<1-2 sentence explanation>",
  "role_match": <true|false>
}}

Scoring guide:
- 9-10: near-perfect match, must apply
- 7-8: strong match, should apply
- 5-6: partial match, apply if slim pickings
- 1-4: poor match, skip

Consider: tech stack overlap, seniority level, domain relevance, Azure/Databricks/PySpark emphasis."""


def build_profile_summary(profile: dict) -> str:
    skills = profile.get("skills", {})
    all_skills = (
        skills.get("core", []) +
        skills.get("platforms", []) +
        skills.get("practices", [])
    )
    return (
        f"Role: {profile['current_title']}, {profile['years_experience']} years exp\n"
        f"Key skills: {', '.join(all_skills[:20])}\n"
        f"Target roles: {', '.join(profile['target_roles'])}\n"
        f"Certifications: {', '.join(profile['certifications'])}\n"
        f"Salary floor: {profile['work_preferences']['salary_floor_lpa']} LPA\n"
        f"Work modes: {', '.join(profile['work_preferences']['modes'])}"
    )


def rank_job(job: dict, profile: dict) -> tuple[float, str]:
    """Returns (score, reason)."""
    jd_text = (job.get("description") or "")[:3000]
    if not jd_text:
        jd_text = f"{job['title']} at {job['company']} — {job.get('location', '')}"

    prompt = RANK_PROMPT.format(
        profile_summary=build_profile_summary(profile),
        jd_text=jd_text,
    )

    raw = chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    try:
        result = json.loads(raw)
        score = float(result.get("score", 0))
        reason = result.get("reason", "")
        return score, reason
    except Exception:
        return 0.0, "parse error"


def rank_jobs_batch(jobs: list[dict], profile: dict, model: str = "") -> list[dict]:
    """Rank list of jobs in place, return sorted by score desc. model param unused (auto-detected)."""
    for job in jobs:
        score, reason = rank_job(job, profile)
        job["score"] = score
        job["score_reason"] = reason
    return sorted(jobs, key=lambda j: j["score"], reverse=True)
