"""Run: python3 debug_selectors.py"""
import asyncio
import yaml
from playwright.async_api import async_playwright
from agents.searcher.base import make_persistent_context

TEST_URL = "https://www.linkedin.com/jobs/view/4429857002/"

TITLE_SELECTORS = [
    ".job-details-jobs-unified-top-card__job-title h1",
    ".jobs-unified-top-card__job-title h1",
    "h1.t-24",
    "h1",
]
COMPANY_SELECTORS = [
    ".job-details-jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name a",
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name",
    "[data-test-id='job-details-company-name']",
]


async def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    browser_cfg = config["browser"]
    profile_dir = config["sources"]["linkedin"]["profile_dir"]

    async with async_playwright() as p:
        context = await make_persistent_context(
            p, profile_dir=profile_dir,
            headless=False, slow_mo=200,
            executable_path=browser_cfg.get("executable_path"),
        )
        page = await context.new_page()
        await page.goto(TEST_URL, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print(f"\n=== URL: {TEST_URL} ===")
        print(f"Final URL: {page.url}\n")

        print("--- TITLE SELECTORS ---")
        for sel in TITLE_SELECTORS:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text() or "").strip()[:80]
                print(f"  FOUND  {sel!r:60s} → {text!r}")
            else:
                print(f"  miss   {sel!r}")

        print("\n--- COMPANY SELECTORS ---")
        for sel in COMPANY_SELECTORS:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text() or "").strip()[:80]
                print(f"  FOUND  {sel!r:60s} → {text!r}")
            else:
                print(f"  miss   {sel!r}")

        # dump all h1s on page
        print("\n--- ALL H1s ---")
        h1s = await page.query_selector_all("h1")
        for h1 in h1s:
            print(f"  {(await h1.inner_text() or '').strip()[:100]!r}")

        # dump page title
        print(f"\n--- PAGE TITLE ---")
        print(f"  {await page.title()}")

        await context.close()

asyncio.run(main())
