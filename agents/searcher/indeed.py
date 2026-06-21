import asyncio
import re
from urllib.parse import urlencode
from playwright.async_api import Page
from .base import load_cookies, make_browser, parse_salary_lpa

BASE_URL = "https://in.indeed.com"


def build_search_url(keyword: str, location: str, work_mode: str) -> str:
    params = {
        "q": keyword,
        "l": location,
        "fromage": "7",
        "sort": "date",
    }
    if work_mode == "remote":
        params["remotejob"] = "1"
    return f"{BASE_URL}/jobs?{urlencode(params)}"


async def search_indeed(config: dict, keywords: list[str], max_jobs: int) -> list[dict]:
    jobs = []
    cfg = config["sources"]["indeed"]
    browser_cfg = config["browser"]

    async with async_playwright() as p:
        browser, context = await make_browser(
            p, headless=browser_cfg["headless"], slow_mo=browser_cfg["slow_mo"],
            executable_path=browser_cfg.get("executable_path"),
        )
        await load_cookies(context, cfg["cookies_file"])
        page = await context.new_page()

        for keyword in keywords:
            for location in ["India", "Remote"]:
                for mode in ["remote", "hybrid", "onsite"]:
                    url = build_search_url(keyword, location, mode)
                    try:
                        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        await asyncio.sleep(2)

                        # handle CAPTCHA or login wall
                        if "indeed.com/account" in page.url or "challenge" in page.url:
                            print("[indeed] login wall hit — check cookies")
                            break

                        cards = await page.query_selector_all("[data-jk]")

                        for card in cards:
                            try:
                                job_id = await card.get_attribute("data-jk") or ""
                                if not job_id:
                                    continue

                                title_el = await card.query_selector("h2.jobTitle span")
                                company_el = await card.query_selector("[data-testid='company-name'], .companyName")
                                location_el = await card.query_selector("[data-testid='text-location'], .companyLocation")
                                salary_el = await card.query_selector(".salary-snippet-container, [data-testid='attribute_snippet_testid']")
                                date_el = await card.query_selector("[data-testid='myJobsStateDate'], .date")

                                title = (await title_el.text_content() or "").strip() if title_el else ""
                                company = (await company_el.text_content() or "").strip() if company_el else ""
                                loc = (await location_el.text_content() or "").strip() if location_el else location
                                salary_text = (await salary_el.text_content() or "").strip() if salary_el else ""
                                posted = (await date_el.text_content() or "").strip() if date_el else ""

                                job_url = f"{BASE_URL}/viewjob?jk={job_id}"

                                # fetch description
                                description = ""
                                try:
                                    detail_page = await context.new_page()
                                    await detail_page.goto(job_url, timeout=15000, wait_until="domcontentloaded")
                                    desc_el = await detail_page.query_selector("#jobDescriptionText")
                                    if desc_el:
                                        description = (await desc_el.text_content() or "").strip()
                                    await detail_page.close()
                                except Exception:
                                    pass
                                await asyncio.sleep(1)

                                jobs.append({
                                    "source": "indeed",
                                    "job_id": job_id,
                                    "title": title,
                                    "company": company,
                                    "location": loc,
                                    "work_mode": mode,
                                    "url": job_url,
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
                        print(f"[indeed] search failed: {keyword} / {location} / {mode}: {e}")

                    if len(jobs) >= max_jobs:
                        break

        await browser.close()

    return jobs
