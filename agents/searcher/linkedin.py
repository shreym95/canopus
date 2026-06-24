import asyncio
import re
from urllib.parse import urlencode
from playwright.async_api import async_playwright, Page, BrowserContext
from .base import make_persistent_context, parse_salary_lpa

BASE_URL = "https://www.linkedin.com"
TIMEOUT = 30000  # ms


def _clean(text: str) -> str:
    """Strip LinkedIn UI noise from scraped text."""
    import re as _re
    text = text.strip()
    # remove " with verification" suffix
    text = _re.sub(r"\s*with verification\s*$", "", text, flags=_re.IGNORECASE)
    # remove doubled text: "FooFoo" or "Foo\n\nFoo" → "Foo"
    text = _re.sub(r"^\s*(.+?)\s*\n[\s\S]*$", r"\1", text)  # keep first line
    half = len(text) // 2
    if half > 3 and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    return text.strip()


def build_search_url(keyword: str, location: str, work_mode: str, geo_id: str = "") -> str:
    mode_map = {"remote": "2", "hybrid": "3", "onsite": "1"}
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": "r2592000",  # last 30 days
        # no f_E filter — seniority tags poorly populated; keywords imply level
        "f_JT": "F",          # full-time only
        "sortBy": "DD",
    }
    if geo_id:
        params["geoId"] = geo_id
    if work_mode in mode_map:
        params["f_WT"] = mode_map[work_mode]
    return f"{BASE_URL}/jobs/search/?{urlencode(params)}"


async def scrape_job_detail(context: BrowserContext, url: str) -> dict:
    page = await context.new_page()
    try:
        await page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        description = ""
        for sel in [".jobs-description__content", ".jobs-description", "#job-details"]:
            el = await page.query_selector(sel)
            if el:
                description = (await el.text_content() or "").strip()
                break

        salary_text = ""
        for sel in [".jobs-unified-top-card__job-insight", ".compensation__salary"]:
            el = await page.query_selector(sel)
            if el:
                salary_text = (await el.text_content() or "").strip()
                break

        # title + company: try DOM selectors first, then parse page <title>
        title = ""
        for sel in [".job-details-jobs-unified-top-card__job-title h1",
                    ".jobs-unified-top-card__job-title h1",
                    "h1.t-24", "h1"]:
            el = await page.query_selector(sel)
            if el:
                title = _clean(await el.inner_text() or "")
                if title:
                    break

        company = ""
        for sel in [".job-details-jobs-unified-top-card__company-name a",
                    ".jobs-unified-top-card__company-name a",
                    ".job-details-jobs-unified-top-card__company-name",
                    ".jobs-unified-top-card__company-name"]:
            el = await page.query_selector(sel)
            if el:
                company = _clean(await el.inner_text() or "")
                if company:
                    break

        # reliable fallback: page title is always "<job> | <company> | LinkedIn"
        if not title or not company:
            page_title = await page.title()  # e.g. "Data Engineer | IBM | LinkedIn"
            parts = [p.strip() for p in page_title.split("|")]
            if len(parts) >= 3 and parts[-1].lower() == "linkedin":
                if not title:
                    title = _clean(parts[0])
                if not company:
                    company = _clean(parts[1])

        return {
            "description": description,
            "salary_text": salary_text,
            "salary_lpa": parse_salary_lpa(salary_text),
            "_title_fallback": title,
            "_company_fallback": company,
        }
    except Exception:
        return {"description": "", "salary_text": "", "salary_lpa": None,
                "_title_fallback": "", "_company_fallback": ""}
    finally:
        await page.close()


async def scrape_search_page(context: BrowserContext, url: str, mode: str, location: str, max_jobs: int) -> list[dict]:
    """Open fresh page per search URL, return job stubs."""
    jobs = []
    page = await context.new_page()
    try:
        await page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # detect login wall
        if "/login" in page.url or "/authwall" in page.url or "/checkpoint" in page.url:
            print(f"[linkedin] login wall at {page.url} — re-export cookies")
            return []

        # scroll to load cards
        for _ in range(3):
            await page.keyboard.press("End")
            await asyncio.sleep(1)

        # try logged-in selectors first, fall back to public
        cards = await page.query_selector_all('[data-occludable-job-id]')
        if not cards:
            cards = await page.query_selector_all(".jobs-search__results-list li")
        if not cards:
            cards = await page.query_selector_all(".job-card-container")

        for card in cards:
            try:
                job_id = await card.get_attribute("data-occludable-job-id") or \
                         await card.get_attribute("data-job-id") or ""
                if not job_id:
                    a = await card.query_selector("a[href*='/jobs/view/']")
                    href = await a.get_attribute("href") if a else ""
                    m = re.search(r"/jobs/view/(\d+)", href or "")
                    job_id = m.group(1) if m else ""
                if not job_id:
                    continue

                # title — prefer inner <strong> to avoid duplicated anchor text
                title = ""
                for sel in [
                    ".job-card-list__title--link strong",
                    ".job-card-list__title strong",
                    ".job-card-list__title--link",
                    ".job-card-list__title",
                    ".base-search-card__title",
                    "a.job-card-container__link strong",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        title = _clean(await el.inner_text() or "")
                        if title:
                            break

                # company
                company = ""
                for sel in [
                    ".job-card-container__primary-description",
                    ".job-card-container__company-name",
                    ".artdeco-entity-lockup__subtitle span",
                    ".base-search-card__subtitle",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        company = _clean(await el.inner_text() or "")
                        if company:
                            break

                # location
                loc = location
                for sel in [
                    ".job-card-container__metadata-item--workplace-type",
                    ".job-card-container__metadata-item",
                    ".job-search-card__location",
                    ".artdeco-entity-lockup__caption span",
                ]:
                    el = await card.query_selector(sel)
                    if el:
                        t = _clean(await el.inner_text() or "")
                        if t:
                            loc = t
                            break

                date_el = await card.query_selector("time")
                posted = await date_el.get_attribute("datetime") if date_el else ""

                jobs.append({
                    "source": "linkedin",
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": loc,
                    "work_mode": mode,
                    "url": f"{BASE_URL}/jobs/view/{job_id}/",
                    "posted_date": posted,
                    "salary_text": "",
                    "salary_lpa": None,
                    "description": "",
                })
                if len(jobs) >= max_jobs:
                    break
            except Exception:
                continue

    except Exception as e:
        print(f"[linkedin] page failed {url}: {e}")
    finally:
        await page.close()

    return jobs


async def search_linkedin(config: dict, keywords: list[str], max_jobs: int) -> list[dict]:
    jobs = []
    seen_ids: set[str] = set()
    cfg = config["sources"]["linkedin"]
    browser_cfg = config["browser"]

    async with async_playwright() as p:
        context = await make_persistent_context(
            p,
            profile_dir=cfg["profile_dir"],
            headless=browser_cfg["headless"],
            slow_mo=browser_cfg["slow_mo"],
            executable_path=browser_cfg.get("executable_path"),
        )
        # check login state — if not logged in, open linkedin.com so user can log in
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/feed/", timeout=30000, wait_until="domcontentloaded")
        if "/login" in page.url or "/authwall" in page.url:
            print("[linkedin] Not logged in. Please log in to LinkedIn in the browser window, then press Enter here...")
            input()
        await page.close()

        profiles = config["search"]["profiles"]
        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            for profile in profiles:
                if len(jobs) >= max_jobs:
                    break
                location = profile["location"]
                geo_id = profile.get("geo_id", "")
                for mode in profile["work_modes"]:
                    if len(jobs) >= max_jobs:
                        break
                    url = build_search_url(keyword, location, mode, geo_id)
                    stubs = await scrape_search_page(
                        context, url, mode, location, max_jobs - len(jobs)
                    )
                    for s in stubs:
                        if s["job_id"] not in seen_ids:
                            seen_ids.add(s["job_id"])
                            jobs.append(s)
                    await asyncio.sleep(2)

        # fetch descriptions + fill in missing title/company from detail page
        print(f"[linkedin] fetching descriptions for {len(jobs)} jobs...")
        for job in jobs:
            detail = await scrape_job_detail(context, job["url"])
            if not job.get("title"):
                job["title"] = detail.pop("_title_fallback", "")
            else:
                detail.pop("_title_fallback", None)
            if not job.get("company"):
                job["company"] = detail.pop("_company_fallback", "")
            else:
                detail.pop("_company_fallback", None)
            detail.pop("_title_fallback", None)
            detail.pop("_company_fallback", None)
            job.update(detail)
            if not job.get("title"):
                print(f"[linkedin] WARN blank title after detail scrape: {job['url']}")
            await asyncio.sleep(1)

        await context.close()

    return jobs
