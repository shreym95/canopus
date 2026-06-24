import asyncio
import re
from urllib.parse import urlencode, quote
from playwright.async_api import async_playwright, Page
from .base import load_cookies, make_browser, parse_salary_lpa

BASE_URL = "https://www.naukri.com"


def build_search_url(keyword: str, location: str = "", work_mode: str = "") -> str:
    slug = keyword.lower().replace(" ", "-")
    loc_slug = location.lower().replace(" ", "-") if location and location != "Remote" else ""
    if loc_slug:
        url = f"{BASE_URL}/{slug}-jobs-in-{loc_slug}"
    else:
        url = f"{BASE_URL}/{slug}-jobs"
    params = {"jobAge": "7"}
    if work_mode == "remote":
        params["wfhType"] = "remote"
    elif work_mode == "hybrid":
        params["wfhType"] = "hybrid"
    return f"{url}?{urlencode(params)}"


async def search_naukri(config: dict, keywords: list[str], max_jobs: int) -> list[dict]:
    jobs = []
    cfg = config["sources"]["naukri"]
    browser_cfg = config["browser"]

    async with async_playwright() as p:
        browser, context = await make_browser(
            p, headless=browser_cfg["headless"], slow_mo=browser_cfg["slow_mo"],
            executable_path=browser_cfg.get("executable_path"),
        )
        await load_cookies(context, cfg["cookies_file"])
        page = await context.new_page()

        profiles = config["search"]["profiles"]
        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            for profile in profiles:
                if len(jobs) >= max_jobs:
                    break
                location = profile["location"]
                naukri_loc = "bangalore" if "Bengaluru" in location else "india"
                for mode in profile["work_modes"]:
                    if len(jobs) >= max_jobs:
                        break
                    url = build_search_url(keyword, naukri_loc, mode)
                    try:
                        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        await asyncio.sleep(2)

                        for _ in range(3):
                            await page.keyboard.press("End")
                            await asyncio.sleep(1.5)

                        cards = await page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple")

                        for card in cards:
                            try:
                                title_el = await card.query_selector("a.title")
                                company_el = await card.query_selector("a.comp-name, .comp-name")
                                location_el = await card.query_selector(".locWdth, .loc-wrap")
                                salary_el = await card.query_selector(".salary")
                                date_el = await card.query_selector(".job-post-day")

                                title = (await title_el.text_content() or "").strip() if title_el else ""
                                company = (await company_el.text_content() or "").strip() if company_el else ""
                                loc = (await location_el.text_content() or "").strip() if location_el else ""
                                salary_text = (await salary_el.text_content() or "").strip() if salary_el else ""
                                posted = (await date_el.text_content() or "").strip() if date_el else ""
                                href = await title_el.get_attribute("href") if title_el else ""

                                m = re.search(r"-(\d+)(?:\?|$)", href or "")
                                job_id = m.group(1) if m else re.sub(r"[^\w]", "", title + company)[:32]

                                description = ""
                                if href:
                                    try:
                                        detail_page = await context.new_page()
                                        await detail_page.goto(href, timeout=15000, wait_until="domcontentloaded")
                                        desc_el = await detail_page.query_selector(".job-desc, #job-desc, .jd-desc")
                                        if desc_el:
                                            description = (await desc_el.text_content() or "").strip()
                                        await detail_page.close()
                                    except Exception:
                                        pass
                                    await asyncio.sleep(1)

                                jobs.append({
                                    "source": "naukri",
                                    "job_id": job_id,
                                    "title": title,
                                    "company": company,
                                    "location": loc,
                                    "work_mode": mode or "onsite",
                                    "url": href or url,
                                    "posted_date": posted,
                                    "salary_text": salary_text,
                                    "salary_lpa": parse_salary_lpa(salary_text),
                                    "description": description,
                                })

                                if len(jobs) >= max_jobs:
                                    break
                            except Exception:
                                continue

                    except Exception as e:
                        print(f"[naukri] search failed: {keyword} / {naukri_loc} / {mode}: {e}")

        await browser.close()

    return jobs
