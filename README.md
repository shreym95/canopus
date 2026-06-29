# Canopus — Job Application Agent

Automates job hunting for Senior Data Engineers. Scrapes LinkedIn → LLM-ranks matches → interactive review → generates cover letters → opens a personal job board for manual applying.

## How it works

```
--pipeline --fresh
      │
      ├── Search LinkedIn (4 keywords × 2 location profiles)
      ├── Pre-filter irrelevant titles (AWS/GCP-only DE roles dropped)
      ├── LLM ranks each job 1-10 against your profile (Groq, free tier)
      ├── Interactive TUI: approve / skip / blacklist company
      ├── Generate cover letters (Word .docx per job)
      └── Open job board HTML with Quick Copy sidebar (name, links, role bullets)
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/shreym95/canopus
cd canopus
pip3 install -r requirements.txt --break-system-packages
playwright install chromium --with-deps
```

### 2. Config files

```bash
cp config.example.yaml config.yaml
cp profile.example.json profile.json
cp .env.example .env
```

Edit `config.yaml` — set your paths and location preferences.  
Edit `profile.json` — fill in your experience, skills, and target roles.  
Edit `.env` — add your Groq API key (free at [console.groq.com](https://console.groq.com)).

### 3. LinkedIn login (one-time)

```bash
python3 main.py --pipeline --fresh
```

On first run, a browser window opens. Log in to LinkedIn manually, then press Enter in the terminal. The session is saved to `browser_profiles/linkedin/` for future runs.

## Usage

```bash
# Full pipeline — clean slate
python3 main.py --pipeline --fresh

# Incremental — adds to existing DB (skips duplicates)
python3 main.py --pipeline

# Individual steps
python3 main.py --search    # scrape LinkedIn
python3 main.py --rank      # LLM score each found job
python3 main.py --review    # interactive TUI
python3 main.py --open-manual  # regenerate + open job board
```

## Job board

After review, a local HTML file opens with:
- All approved jobs sorted by score
- Score badges (green ≥ 8, amber 7, red < 7)
- **Quick Copy sidebar** — one click to copy name, email, phone, LinkedIn, GitHub, role descriptions, education, certifications
- "Open Job →" button per listing

## Stack

- **Scraping**: Playwright (persistent Chromium profile for LinkedIn)
- **LLM ranking + cover letters**: Groq API (`llama-3.3-70b-versatile`, free tier)
- **State**: SQLite (`db/jobs.db`)
- **TUI**: Rich
- **Cover letters**: python-docx (`.docx` export)

## Config notes

| Setting | Default | Effect |
|---------|---------|--------|
| `ranker.min_score` | 7 | Raise to reduce review queue, lower for more volume |
| `search.max_jobs_per_run` | 100 | Per keyword per search profile |
| `browser.headless` | false | Set true for fully headless runs |
| `sources.indeed.enabled` | false | Enable when cookies are available |

## What gets excluded (gitignored)

`profile.json`, `config.yaml`, `.env`, `db/jobs.db`, `browser_profiles/`, `cookies/`, `job_board.html`, `cover_letters/` — all personal data stays local only.
