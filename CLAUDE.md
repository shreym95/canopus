# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Job application automation agent for Shrey Marwaha (Senior Data Engineer, 8 years). Scrapes LinkedIn, Indeed, and Naukri; ranks jobs via LLM; presents interactive review; auto-applies via Playwright.

## Running the agent

```bash
cd /home/shrey/job_agent

# Full pipeline (search → rank → review → apply)
python3 main.py --all

# Individual steps (can be chained across sessions — state persists in SQLite)
python3 main.py --search    # scrape job boards, save to DB
python3 main.py --rank      # LLM scores each found job 1-10
python3 main.py --review    # interactive TUI: approve/skip/blacklist
python3 main.py --apply     # Playwright submits approved jobs
```

## Setup (one-time)

```bash
pip3 install -r requirements.txt --break-system-packages
playwright install chromium --with-deps
```

Cookie files required in `cookies/` before `--search` will work. See `cookies/HOW_TO_EXPORT.md`.

## Architecture

**Pipeline flow:** `main.py` orchestrates four sequential phases. Each phase reads/writes `db/jobs.db` (SQLite), so phases can be run independently across sessions.

**Status state machine in DB:**
`found` → `ranked` (score ≥ 6) or `rejected` (score < 6) → `approved` (user review) → `applied`

**LLM client** (`agents/llm_client.py`): auto-detects which API key is set in `.env` and returns an OpenAI-compatible client. Priority: `XAI_API_KEY` → `GROQ_API_KEY` → `GEMINI_API_KEY`. All LLM calls go through `chat()` in this module — don't import provider SDKs directly elsewhere.

**Searchers** (`agents/searcher/`): each is an async function `search_<source>(config, keywords, max_jobs) → list[dict]`. They load cookies via `base.load_cookies()`, return job dicts with keys: `source, job_id, title, company, location, work_mode, url, description, salary_text, salary_lpa, posted_date`. The `job_id` + `source` pair is the deduplication key in DB.

**Applier** (`agents/applier.py`): per-source handlers in `APPLY_HANDLERS` dict. Each handler receives `(page, job, profile, cover_letter)`. LinkedIn uses Easy Apply modal; Naukri and Indeed redirect to their own flows. Applier is best-effort — check logs for failures.

## Key files

| File | Purpose |
|------|---------|
| `config.yaml` | All tuneable settings — keywords, salary floor, LLM model, score threshold |
| `profile.json` | Shrey's structured resume data used by ranker and cover letter prompts |
| `.env` | API keys (GROQ_API_KEY active) |
| `db/database.py` | All DB operations; never raw SQL outside this module |
| `agents/llm_client.py` | Single place for LLM provider switching |

## Configuration notes

- `ranker.min_score` (default 6/10): raise to 7-8 to reduce review queue, lower to 5 for more volume
- `browser.headless`: set `false` to watch Playwright navigate for debugging
- `browser.slow_mo`: increase if sites flag bot behaviour
- `search.max_jobs_per_run`: split evenly across 3 sources (÷3 each)

## Git workflow

- After every major bug fix confirmed by Shrey, commit automatically without asking
- Commit message: max 10-20 words, technical, no fluff — e.g. `fix: LinkedIn title fallback via page title`
- No `Co-Authored-By` line in commits

## LLM provider

Currently using **Groq** (`GROQ_API_KEY` in `.env`) with model `llama-3.3-70b-versatile` (auto-selected by `llm_client.py`). The `model` field in `config.yaml` under `ranker`/`cover_letter` is passed through but overridden by the provider's default model in `llm_client.py` — to force a specific model, edit `_provider` default in `llm_client.get_client()`.
