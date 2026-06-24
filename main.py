#!/usr/bin/env python3
"""
Job Application Agent
Run: python main.py [--search] [--rank] [--review] [--apply] [--all]
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from db.database import init_db, upsert_job, update_job, get_jobs_for_review, get_approved_jobs, add_blacklist, get_stats
from agents.ranker import rank_jobs_batch
from agents.cover_letter import generate_cover_letter
from agents.applier import apply_to_job
from agents.exporter import export_all_approved, export_job_board_html
from ui.review import run_review

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_profile(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


async def run_search(config: dict) -> list[dict]:
    keywords = config["search"]["keywords"]
    max_jobs = config["search"]["max_jobs_per_run"]
    all_jobs = []

    if config["sources"]["linkedin"]["enabled"]:
        console.print("[cyan]→ Searching LinkedIn...[/]")
        from agents.searcher.linkedin import search_linkedin
        try:
            jobs = await search_linkedin(config, keywords, max_jobs)
            console.print(f"  [green]LinkedIn: {len(jobs)} jobs found[/]")
            all_jobs.extend(jobs)
        except Exception as e:
            console.print(f"  [red]LinkedIn failed: {e}[/]")

    if config["sources"]["indeed"]["enabled"]:
        console.print("[cyan]→ Searching Indeed...[/]")
        from agents.searcher.indeed import search_indeed
        try:
            jobs = await search_indeed(config, keywords, max_jobs)
            console.print(f"  [green]Indeed: {len(jobs)} jobs found[/]")
            all_jobs.extend(jobs)
        except Exception as e:
            console.print(f"  [red]Indeed failed: {e}[/]")

    if config["sources"]["naukri"]["enabled"]:
        console.print("[cyan]→ Searching Naukri...[/]")
        from agents.searcher.naukri import search_naukri
        try:
            jobs = await search_naukri(config, keywords, max_jobs)
            console.print(f"  [green]Naukri: {len(jobs)} jobs found[/]")
            all_jobs.extend(jobs)
        except Exception as e:
            console.print(f"  [red]Naukri failed: {e}[/]")

    return all_jobs


_TITLE_BLOCKLIST = {
    "software engineer", "sre", "site reliability", "devops", "frontend",
    "backend engineer", "full stack", "fullstack", "mobile", "ios", "android",
    "power bi developer", "bi developer", "compiler", "ml engineer",
    "machine learning engineer", "ai engineer", "product manager",
    "scrum master", "qa engineer", "test engineer", "security engineer",
}


def _title_relevant(title: str) -> bool:
    """Return False if title clearly matches a non-DE role."""
    if not title:
        return True  # no title yet — let ranker decide
    t = title.lower()
    # must contain at least one DE signal
    de_signals = ["data engineer", "data engineering", "etl", "pipeline",
                  "databricks", "spark", "azure data", "lead data", "staff data"]
    if any(s in t for s in de_signals):
        return True
    # block clear non-DE titles
    if any(s in t for s in _TITLE_BLOCKLIST):
        return False
    return True  # unknown — keep, ranker will score low


def save_jobs(jobs: list[dict], config: dict) -> int:
    db_path = config["db"]["path"]
    salary_floor = config["search"]["salary_floor_lpa"]
    new_count = 0
    skipped_title = 0
    for job in jobs:
        if job.get("salary_lpa") and job["salary_lpa"] < salary_floor:
            continue
        if not _title_relevant(job.get("title", "")):
            skipped_title += 1
            continue
        job.setdefault("description", "")
        job.setdefault("salary_text", "")
        job.setdefault("salary_lpa", None)
        job.setdefault("posted_date", "")
        if upsert_job(db_path, job):
            new_count += 1
    if skipped_title:
        console.print(f"  [dim]Skipped {skipped_title} jobs with irrelevant titles[/]")
    return new_count


def run_ranking(config: dict, profile: dict):
    db_path = config["db"]["path"]

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs WHERE status = 'found'").fetchall()
    conn.close()
    jobs = [dict(r) for r in rows]

    if not jobs:
        console.print("[yellow]No unranked jobs found.[/]")
        return

    console.print(f"[cyan]→ Ranking {len(jobs)} jobs via LLM...[/]")
    ranked = rank_jobs_batch(jobs, profile)

    min_score = config["ranker"]["min_score"]
    for job in ranked:
        status = "ranked" if job["score"] >= min_score else "rejected"
        update_job(db_path, job["source"], job["job_id"],
                   score=job["score"], score_reason=job["score_reason"], status=status)

    passed = sum(1 for j in ranked if j["score"] >= min_score)
    console.print(f"  [green]{passed} jobs passed score threshold {min_score}/10[/]")


def run_cover_letters(approved_jobs: list[dict], profile: dict, config: dict):
    max_words = config["cover_letter"]["max_words"]
    db_path = config["db"]["path"]

    console.print(f"[cyan]→ Generating cover letters for {len(approved_jobs)} jobs...[/]")
    for job in approved_jobs:
        if job.get("cover_letter"):
            continue
        try:
            cl = generate_cover_letter(job, profile, max_words=max_words)
            update_job(db_path, job["source"], job["job_id"], cover_letter=cl)
            job["cover_letter"] = cl
            console.print(f"  [green]✓ {job['title']} @ {job['company']}[/]")
        except Exception as e:
            console.print(f"  [red]Failed CL for {job['title']}: {e}[/]")


async def run_apply(approved_jobs: list[dict], profile: dict, config: dict):
    db_path = config["db"]["path"]
    for job in approved_jobs:
        cl = job.get("cover_letter") or ""
        console.print(f"[cyan]→ Applying: {job['title']} @ {job['company']} ({job['source']})[/]")
        try:
            result = await apply_to_job(job, profile, cl, config)
            if result is True:
                update_job(db_path, job["source"], job["job_id"],
                           status="applied", applied_at=datetime.now().isoformat())
                console.print(f"  [green]✓ Applied[/]")
            elif result == "external":
                update_job(db_path, job["source"], job["job_id"], status="manual")
                console.print(f"  [yellow]⚠ External ATS — apply manually: {job['url']}[/]")
            else:
                console.print(f"  [yellow]⚠ Apply did not complete (manual check needed)[/]")
        except Exception as e:
            console.print(f"  [red]✗ Apply failed: {e}[/]")

    # export cover letters as Word docs + regenerate job board
    paths = export_all_approved(config["db"]["path"])
    if paths:
        console.print(f"\n[bold]Cover letter docs exported:[/]")
        for p in paths:
            console.print(f"  [dim]{p}[/]")


def run_open_manual(config: dict, profile: dict | None = None):
    import webbrowser
    html_path = export_job_board_html(config["db"]["path"], profile=profile)
    abs_path = Path(html_path).resolve()
    console.print(f"[green]Job board generated:[/] {abs_path}")
    webbrowser.open(f"file://{abs_path}")
    console.print("[dim]Sticky sidebar: copy any ATS field instantly. Click 'Open Job →' per listing.[/]")


def print_stats(config: dict):
    stats = get_stats(config["db"]["path"])
    console.print("\n[bold]─── Session Stats ───[/]")
    for k, v in stats.items():
        console.print(f"  {k:10} {v}")
    console.print()


async def main():
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument("--search",  action="store_true", help="Search job boards")
    parser.add_argument("--rank",    action="store_true", help="Rank found jobs via LLM")
    parser.add_argument("--review",  action="store_true", help="Review ranked jobs (interactive)")
    parser.add_argument("--apply",        action="store_true", help="Apply to approved jobs")
    parser.add_argument("--open-manual",  action="store_true", help="Open manual ATS jobs in browser, 5 at a time")
    parser.add_argument("--all",          action="store_true", help="Run full pipeline")
    parser.add_argument("--config",  default="config.yaml", help="Config file path")
    args = parser.parse_args()

    if not any([args.search, args.rank, args.review, args.apply, args.open_manual, args.all]):
        parser.print_help()
        sys.exit(0)

    config = load_config(args.config)
    profile = load_profile(config["profile"]["profile_path"])
    init_db(config["db"]["path"])

    console.print(f"\n[bold cyan]Job Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}[/]\n")

    if args.search or args.all:
        jobs = await run_search(config)
        new = save_jobs(jobs, config)
        console.print(f"[green]Saved {new} new jobs to DB[/]")

    if args.rank or args.all:
        run_ranking(config, profile)

    if args.review or args.all:
        jobs_to_review = get_jobs_for_review(
            config["db"]["path"],
            config["ranker"]["min_score"],
            config["ranker"]["top_n"],
        )
        approved, blacklisted = run_review(jobs_to_review)

        db_path = config["db"]["path"]
        for job in approved:
            update_job(db_path, job["source"], job["job_id"], status="approved")
        for company in blacklisted:
            add_blacklist(db_path, "company", company)
            # reject all jobs from this company
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE jobs SET status='rejected' WHERE lower(company)=lower(?) AND status != 'applied'",
                (company,)
            )
            conn.commit()
            conn.close()

        # generate cover letters for approved jobs
        if approved:
            run_cover_letters(approved, profile, config)

    if args.open_manual:
        run_open_manual(config, profile=profile)

    if args.apply or args.all:
        approved_jobs = get_approved_jobs(config["db"]["path"])
        if not approved_jobs:
            console.print("[yellow]No approved jobs to apply to. Run --review first.[/]")
        else:
            await run_apply(approved_jobs, profile, config)

    print_stats(config)


if __name__ == "__main__":
    asyncio.run(main())
