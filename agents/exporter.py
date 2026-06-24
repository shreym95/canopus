import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "_", text.strip())[:40]


def export_cover_letter_docx(job: dict, output_dir: str = "cover_letters") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{_slug(job['company'])}_{_slug(job['title'])}.docx"
    path = Path(output_dir) / filename

    doc = Document()

    # margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    # header: name + contact
    header = doc.add_paragraph()
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header.add_run("Shrey Marwaha")
    run.bold = True
    run.font.size = Pt(14)
    doc.add_paragraph(
        "shrym.95@gmail.com  |  LinkedIn: linkedin.com/in/shreymarwaha"
    ).alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()  # spacer

    # job target line
    target = doc.add_paragraph()
    target.add_run(f"Applying for: ").bold = True
    target.add_run(f"{job['title']} @ {job['company']}")
    target.add_run(f"\n{job['url']}")

    doc.add_paragraph()  # spacer

    # cover letter body
    cover_letter = (job.get("cover_letter") or "").strip()
    if cover_letter:
        for para in cover_letter.split("\n\n"):
            p = doc.add_paragraph(para.strip())
            p.paragraph_format.space_after = Pt(8)
    else:
        doc.add_paragraph("[No cover letter generated — add manually]")

    doc.save(str(path))
    return str(path)


def export_all_approved(db_path: str, output_dir: str = "cover_letters") -> list[str]:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status IN ('approved', 'manual')"
    ).fetchall()
    conn.close()

    paths = []
    for row in rows:
        job = dict(row)
        path = export_cover_letter_docx(job, output_dir)
        paths.append(path)
    return paths


def export_job_board_html(db_path: str, profile: dict | None = None, output_path: str = "job_board.html") -> str:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute(
        "SELECT * FROM jobs WHERE status = 'manual' ORDER BY score DESC"
    ).fetchall()
    conn.close()

    # ── profile data ──────────────────────────────────────────────────────────
    sidebar_sections = ""
    if profile:
        exp = profile.get("experience", [])
        current_exp = exp[0] if exp else {}
        highlights = current_exp.get("highlights", [])
        role_desc = "\n".join(f"• {h}" for h in highlights)
        all_skills = (
            profile.get("skills", {}).get("core", []) +
            profile.get("skills", {}).get("platforms", []) +
            profile.get("skills", {}).get("practices", [])
        )
        skills_csv = ", ".join(all_skills)
        edu = profile.get("education", {})
        edu_str = f"{edu.get('degree', '')} · {edu.get('institution', '')} · {edu.get('year', '')}"
        certs = "\n".join(profile.get("certifications", []))
        notice_days = profile.get("work_preferences", {}).get("notice_period_days", "")
        salary_floor = profile.get("work_preferences", {}).get("salary_floor_lpa", "")
        github = profile.get("github", "")
        linkedin = profile.get("linkedin", "")
        if linkedin and not linkedin.startswith("http"):
            linkedin = "https://" + linkedin

        idx = [0]
        def field(label, value, multiline=False):
            if not value:
                return ""
            idx[0] += 1
            fid = f"f{idx[0]}"
            safe = value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
            cls = "field-multi" if multiline else "field-single"
            return f"""<div class="field {cls}">
              <div class="field-top">
                <span class="field-label">{label}</span>
                <button class="copy-btn" id="btn-{fid}" onclick="copyField('{fid}')">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  Copy
                </button>
              </div>
              <div class="field-value" id="{fid}">{safe}</div>
            </div>"""

        def section(title, icon, *fields_html):
            inner = "".join(f for f in fields_html if f)
            if not inner:
                return ""
            return f"""<div class="sidebar-section">
              <div class="section-heading"><span class="section-icon">{icon}</span>{title}</div>
              {inner}
            </div>"""

        sidebar_sections = (
            section("Contact", "👤",
                field("Full Name", profile.get("name", "")),
                field("Email", profile.get("email", "")),
                field("Phone", profile.get("phone", "")),
                field("Location", profile.get("location", "")),
            ) +
            section("Links", "🔗",
                field("LinkedIn", linkedin),
                field("GitHub", github),
            ) +
            section("Professional", "💼",
                field("Current Title", current_exp.get("title", profile.get("current_title", ""))),
                field("Current Company", current_exp.get("company", profile.get("current_company", ""))),
                field("Years of Experience", str(profile.get("years_experience", ""))),
                field("Notice Period", f"{notice_days} days" if notice_days else ""),
                field("Expected Salary", f"{salary_floor}+ LPA" if salary_floor else ""),
            ) +
            section("Application Text", "📝",
                field("Professional Summary", profile.get("summary", ""), multiline=True),
                field("Current Role — Bullets", role_desc, multiline=True),
                field("Skills (comma-sep)", skills_csv, multiline=True),
            ) +
            section("Education & Certs", "🎓",
                field("Education", edu_str),
                field("Certifications", certs, multiline=True),
            )
        )

    # ── job cards ─────────────────────────────────────────────────────────────
    cards = ""
    for i, job in enumerate(jobs, 1):
        score = job["score"] or 0
        if score >= 8:
            score_cls, score_bg = "score-green", "#052e16"
        elif score >= 6:
            score_cls, score_bg = "score-amber", "#1c1400"
        else:
            score_cls, score_bg = "score-red", "#1f0707"
        mode = (job["work_mode"] or "").title()
        mode_chip = f'<span class="chip chip-mode">{mode}</span>' if mode else ""
        cards += f"""
        <div class="card" id="card-{i}">
          <div class="card-top">
            <div class="card-left">
              <div class="card-rank">#{i}</div>
              <div>
                <div class="card-title">{job['title']}</div>
                <div class="card-meta">
                  <span class="card-company">{job['company']}</span>
                  <span class="card-dot">·</span>
                  <span class="card-location">{job['location'] or ''}</span>
                  {mode_chip}
                </div>
              </div>
            </div>
            <div class="score-badge {score_cls}" style="background:{score_bg}">
              <span class="score-num">{score:.1f}</span>
              <span class="score-den">/10</span>
            </div>
          </div>
          <div class="card-actions">
            <a class="btn-primary" href="{job['url']}" target="_blank">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15,3 21,3 21,9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              Open Job
            </a>
          </div>
          <details class="cl-details">
            <summary>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
              Cover Letter
            </summary>
            <div class="cl-body">
              <button class="cl-copy-btn" onclick="copyCL({i})">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy
              </button>
              <pre id="cl-{i}">{job['cover_letter'] or '(none generated)'}</pre>
            </div>
          </details>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Board · {len(jobs)} to apply</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:        #080c14;
    --surface:   #0f1623;
    --surface2:  #161d2e;
    --border:    #1e2a40;
    --text:      #e4eaf4;
    --muted:     #5a6a84;
    --accent:    #3b82f6;
    --accent-hi: #60a5fa;
    --green:     #22c55e;
    --amber:     #f59e0b;
    --red:       #ef4444;
    --radius:    14px;
    --radius-sm: 8px;
  }}

  body {{
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 0;
  }}

  /* ── top bar ── */
  .topbar {{
    background: linear-gradient(135deg, #0d1526 0%, #101828 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(12px);
  }}
  .topbar-logo {{
    font-size: 1.1rem;
    font-weight: 700;
    background: linear-gradient(135deg, var(--accent-hi), #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
  }}
  .topbar-sep {{ color: var(--border); }}
  .topbar-count {{
    font-size: 0.82rem;
    color: var(--muted);
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 3px 10px;
    border-radius: 20px;
  }}

  /* ── layout ── */
  .layout {{
    display: flex;
    align-items: flex-start;
    max-width: 1400px;
    margin: 0 auto;
    padding: 28px 24px;
    gap: 24px;
  }}

  /* ── sidebar ── */
  .sidebar {{
    width: 340px;
    flex-shrink: 0;
    position: sticky;
    top: 73px;
    max-height: calc(100vh - 97px);
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }}
  .sidebar::-webkit-scrollbar {{ width: 4px; }}
  .sidebar::-webkit-scrollbar-track {{ background: transparent; }}
  .sidebar::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

  .sidebar-section {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
  }}
  .section-heading {{
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: var(--muted);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .section-icon {{ font-size: 0.85rem; }}

  .field {{ margin-bottom: 10px; }}
  .field:last-child {{ margin-bottom: 0; }}
  .field-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 3px;
  }}
  .field-label {{
    font-size: 0.7rem;
    color: var(--muted);
    font-weight: 500;
  }}
  .field-value {{
    font-size: 0.82rem;
    color: var(--text);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 7px 10px;
  }}
  .field-single .field-value {{
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .copy-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--muted);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px 8px;
    cursor: pointer;
    transition: all .15s;
    font-family: inherit;
  }}
  .copy-btn:hover {{ color: var(--accent-hi); border-color: var(--accent); }}
  .copy-btn.copied {{ color: var(--green); border-color: var(--green); }}

  /* ── main ── */
  .main {{ flex: 1; min-width: 0; }}

  .page-heading {{
    margin-bottom: 20px;
  }}
  .page-title {{
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text);
    margin-bottom: 4px;
  }}
  .page-sub {{
    font-size: 0.85rem;
    color: var(--muted);
  }}

  /* ── cards ── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 22px;
    margin-bottom: 14px;
    transition: border-color .2s, transform .15s;
  }}
  .card:hover {{
    border-color: #2a3a5c;
    transform: translateY(-1px);
  }}

  .card-top {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
  }}
  .card-left {{ display: flex; align-items: flex-start; gap: 12px; flex: 1; min-width: 0; }}
  .card-rank {{
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--muted);
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 7px;
    flex-shrink: 0;
    margin-top: 3px;
    letter-spacing: .03em;
  }}
  .card-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 5px;
    line-height: 1.3;
  }}
  .card-meta {{
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 0.8rem;
  }}
  .card-company {{ color: var(--accent-hi); font-weight: 500; }}
  .card-dot {{ color: var(--border); }}
  .card-location {{ color: var(--muted); }}

  .chip {{
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 20px;
    letter-spacing: .02em;
  }}
  .chip-mode {{
    background: rgba(59,130,246,.12);
    color: var(--accent-hi);
    border: 1px solid rgba(59,130,246,.25);
  }}

  .score-badge {{
    display: flex;
    align-items: baseline;
    gap: 1px;
    padding: 6px 12px;
    border-radius: 10px;
    flex-shrink: 0;
    border: 1px solid transparent;
  }}
  .score-num {{ font-size: 1.15rem; font-weight: 700; }}
  .score-den {{ font-size: 0.72rem; font-weight: 500; opacity: .7; }}
  .score-green {{ color: var(--green); border-color: rgba(34,197,94,.2); }}
  .score-amber {{ color: var(--amber); border-color: rgba(245,158,11,.2); }}
  .score-red   {{ color: var(--red);   border-color: rgba(239,68,68,.2); }}

  .card-actions {{ margin-bottom: 14px; }}
  .btn-primary {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: linear-gradient(135deg, var(--accent), #6366f1);
    color: #fff;
    text-decoration: none;
    padding: 9px 20px;
    border-radius: 9px;
    font-size: 0.85rem;
    font-weight: 600;
    font-family: inherit;
    transition: opacity .15s, transform .1s;
    border: none;
    cursor: pointer;
  }}
  .btn-primary:hover {{ opacity: .88; transform: translateY(-1px); }}

  /* ── cover letter ── */
  .cl-details {{ border-top: 1px solid var(--border); padding-top: 14px; }}
  .cl-details summary {{
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--muted);
    list-style: none;
    user-select: none;
    transition: color .15s;
  }}
  .cl-details summary:hover {{ color: var(--text); }}
  .cl-details[open] summary {{ color: var(--accent-hi); margin-bottom: 12px; }}

  .cl-body {{ position: relative; }}
  .cl-copy-btn {{
    position: absolute;
    top: 10px;
    right: 10px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--muted);
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    font-family: inherit;
    transition: all .15s;
  }}
  .cl-copy-btn:hover {{ color: var(--accent-hi); border-color: var(--accent); }}
  .cl-copy-btn.copied {{ color: var(--green); border-color: var(--green); }}

  pre {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 16px;
    padding-right: 90px;
    font-size: 0.82rem;
    line-height: 1.65;
    white-space: pre-wrap;
    word-break: break-word;
    color: #c8d3e8;
    font-family: 'Inter', system-ui, sans-serif;
  }}
</style>
</head>
<body>

<div class="topbar">
  <span class="topbar-logo">⚡ Job Agent</span>
  <span class="topbar-sep">·</span>
  <span class="topbar-count">{len(jobs)} jobs to apply</span>
</div>

<div class="layout">
  <div class="sidebar">
    {sidebar_sections}
  </div>
  <div class="main">
    <div class="page-heading">
      <div class="page-title">Your Job Board</div>
      <div class="page-sub">Sorted by match score · Click "Open Job" to apply</div>
    </div>
    {cards}
  </div>
</div>

<script>
function copyField(id) {{
  const el = document.getElementById(id);
  const btn = document.getElementById('btn-' + id);
  navigator.clipboard.writeText(el.innerText).then(() => {{
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20,6 9,17 4,12"/></svg> Copied!`;
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
      btn.classList.remove('copied');
    }}, 1500);
  }});
}}
function copyCL(i) {{
  const el = document.getElementById('cl-' + i);
  const btn = el.previousElementSibling;
  navigator.clipboard.writeText(el.innerText).then(() => {{
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20,6 9,17 4,12"/></svg> Copied!`;
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
      btn.classList.remove('copied');
    }}, 1500);
  }});
}}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    return output_path
