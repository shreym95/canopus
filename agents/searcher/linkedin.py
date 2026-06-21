import asyncio
import re
from urllib.parse import urlencode
from playwright.async_api import Page
from .base import load_cookies, make_browser, parse_salary_lpa

BASE_URL = "https://www.linkedin.com"


def build_search_url(keyword: str, location: str, work_mode: str) -> str:
    mode_map = {"remote": "2", "hybrid": "3", "onsite": "1"}
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": "r604800",  # last 7 days
        "sortBy": "DD",
    }
    if work_mode in mode_map:
        params["f_WT"] = mode_map[work_mode]
    return f"{BASE_URL}/jobs/search/?{urlencode(params)}"


async def scrape_job_detail(page: Page, url: str) -> dict:
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_selector(".job-view-layout", timeout=8000)
        description = await page.text_content(".jobs-description__content") or ""
        salary_text = ""
        try:
            salary_text = await page.text_content(".jobs-unified-top-card__job-insight") or ""
        except Exception:
            pass
        return {
            "description": description.strip(),
            "salary_text": salary_text.strip(),
            "salary_lpa": parse_salary_lpa(salary_text),
        }
    except Exception:
        return {"description": "", "salary_text": "", "salary_lpa": None}


async def search_linkedin(config: dict, keywords: list[str], max_jobs: int) -> list[dict]:
    jobs = []
    cfg = config["sources"]["linkedin"]
    browser_cfg = config["browser"]

    async with async_playwright() as p:
        browser, context = await make_browser(
            p, headless=browser_cfg["headless"], slow_mo=browser_cfg["slow_mo"]
        )
        await load_cookies(context, cfg["cookies_file"])
        page = await context.new_page()

        for keyword in keywords:
            for location in config["search"]["locations"]:
                for mode in config["search"]["work_modes"]:
                    url = build_search_url(keyword, location, mode)
                    try:
                        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        await asyncio.sleep(2)

                        # scroll to load more results
                        for _ in range(3):
                            await page.keyboard.press("End")
                            await asyncio.sleep(1.5)

                        cards = await page.query_selector_all(".jobs-search__results-list li")
                        if not cards:
                            cards = await page.query_selector_all('[data-occludable-job-id]')

                        for card in cards[:max_jobs]:
                            try:
                                job_id = await card.get_attribute("data-occludable-job-id") or ""
                                if not job_id:
                                    a = await card.query_selector("a[href*='/jobs/view/']")
                                    href = await a.get_attribute("href") if a else ""
                                    m = re.search(r"/jobs/view/(\d+)", href or "")
                                    job_id = m.group(1) if m else ""

                                if not job_id:
                                    continue

                                title_el = await card.query_selector(".base-search-card__title, .job-card-list__title")
                                company_el = await card.query_selector(".base-search-card__subtitle, .job-card-container__company-name")
                                location_el = await card.query_selector(".job-search-card__location, .job-card-container__metadata-item")
                                date_el = await card.query_selector("time")

                                title = (await title_el.text_content() or "").strip() if title_el else ""
                                company = (await company_el.text_content() or "").strip() if company_el else ""
                                loc = (await location_el.text_content() or "").strip() if location_el else location
                                posted = await date_el.get_attribute("datetime") if date_el else ""

                                job_url = f"{BASE_URL}/jobs/view/{job_id}/"

                                jobs.append({
                                    "source": "linkedin",
                                    "job_id": job_id,
                                    "title": title,
                                    "company": company,
                                    "location": loc,
                                    "work_mode": mode,
                                    "url": job_url,
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
                        print(f"[linkedin] search failed: {keyword} / {location} / {mode}: {e}")

                    if len(jobs) >= max_jobs:
                        break

        # fetch descriptions for collected jobs
        for job in jobs:
            detail = await scrape_job_detail(page, job["url"])
            job.update(detail)
            await asyncio.sleep(1)

        await browser.close()

    return jobs
