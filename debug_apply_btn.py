"""Run: python3 debug_apply_btn.py"""
import asyncio
import yaml
from playwright.async_api import async_playwright
from agents.searcher.base import make_persistent_context

TEST_URL = "https://www.linkedin.com/jobs/view/4431481555/"


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
        await asyncio.sleep(3)

        print(f"Final URL: {page.url}")
        print(f"Page title: {await page.title()}\n")

        # dump all buttons
        buttons = await page.query_selector_all("button")
        print(f"--- ALL BUTTONS ({len(buttons)}) ---")
        for btn in buttons:
            text = (await btn.inner_text() or "").strip()[:60]
            cls = (await btn.get_attribute("class") or "")[:80]
            aria = await btn.get_attribute("aria-label") or ""
            if text or aria:
                print(f"  text={text!r:40s} aria={aria!r:30s} class={cls!r}")

        await context.close()

asyncio.run(main())
