from .llm_client import chat

CL_PROMPT = """Write a concise, tailored cover letter for this job application.

Candidate: {name}, {title}, {years} years experience
Key strengths: {skills}
Notable achievements: {achievements}

Job: {job_title} at {company}
Job Description (excerpt):
{jd_excerpt}

Instructions:
- Max {max_words} words
- No fluff, no clichés ("I am writing to express my interest...")
- Open with the strongest alignment point between candidate and role
- Mention 2-3 specific skills/achievements most relevant to this JD
- End with a clear call to action
- Professional but direct tone
- Do NOT include subject line, date, or address blocks — body only"""


def generate_cover_letter(job: dict, profile: dict, model: str = "", max_words: int = 250) -> str:
    skills_str = ", ".join(
        profile.get("skills", {}).get("core", [])[:8]
    )
    achievements = "; ".join([
        "66% pipeline runtime reduction via Spark migration",
        "Led 6-member team managing 5-10TB payments data pipelines",
        "Built PySpark data quality framework adopted across EU markets",
        "Early AI adoption driving 20% productivity gain",
    ])

    jd_excerpt = (job.get("description") or "")[:2000]

    prompt = CL_PROMPT.format(
        name=profile["name"],
        title=profile["current_title"],
        years=profile["years_experience"],
        skills=skills_str,
        achievements=achievements,
        job_title=job["title"],
        company=job["company"],
        jd_excerpt=jd_excerpt,
        max_words=max_words,
    )

    return chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    ).strip()
