import asyncio
from playwright.async_api import async_playwright, Page
from .searcher.base import load_cookies, make_browser


async def apply_linkedin(page: Page, job: dict, profile: dict, cover_letter: str) -> bool:
    """LinkedIn Easy Apply flow."""
    await page.goto(job["url"], timeout=20000, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # click Easy Apply button
    easy_apply_btn = await page.query_selector("button.jobs-apply-button")
    if not easy_apply_btn:
        print(f"[applier] no Easy Apply button: {job['url']}")
        return False

    await easy_apply_btn.click()
    await asyncio.sleep(2)

    # handle multi-step modal
    max_steps = 10
    for step in range(max_steps):
        # fill phone if empty
        phone_field = await page.query_selector("input[name*='phone'], input[id*='phone']")
        if phone_field:
            val = await phone_field.input_value()
            if not val:
                await phone_field.fill(profile["phone"])

        # fill cover letter text area if present
        cl_field = await page.query_selector(
            "textarea[id*='cover'], textarea[name*='cover'], "
            "div[data-test-form-element-id*='cover'] textarea"
        )
        if cl_field and cover_letter:
            await cl_field.fill(cover_letter)

        # check for "Next" button
        next_btn = await page.query_selector("button[aria-label='Continue to next step']")
        review_btn = await page.query_selector("button[aria-label='Review your application']")
        submit_btn = await page.query_selector("button[aria-label='Submit application']")

        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(2)
            return True
        elif review_btn:
            await review_btn.click()
            await asyncio.sleep(2)
        elif next_btn:
            await next_btn.click()
            await asyncio.sleep(2)
        else:
            # unknown state
            break

    return False


async def apply_naukri(page: Page, job: dict, profile: dict, cover_letter: str) -> bool:
    """Naukri apply flow."""
    await page.goto(job["url"], timeout=20000, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    apply_btn = await page.query_selector("button#apply-button, a#apply-button, button.apply-button")
    if not apply_btn:
        print(f"[applier] no apply button on naukri: {job['url']}")
        return False

    await apply_btn.click()
    await asyncio.sleep(3)

    # fill cover letter if modal appears
    cl_field = await page.query_selector("textarea#coverLetter, textarea[name='coverLetter']")
    if cl_field and cover_letter:
        await cl_field.fill(cover_letter[:1000])

    # submit
    submit_btn = await page.query_selector("button[type='submit'], button.submit")
    if submit_btn:
        await submit_btn.click()
        await asyncio.sleep(2)
        return True

    return False


async def apply_indeed(page: Page, job: dict, profile: dict, cover_letter: str) -> bool:
    """Indeed apply — redirects to company ATS, best-effort."""
    await page.goto(job["url"], timeout=20000, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    apply_btn = await page.query_selector(
        "button[data-testid='indeedApplyButton'], a[data-testid='indeedApplyButton'], "
        "button#indeedApplyButtonContainer"
    )
    if not apply_btn:
        print(f"[applier] no apply button on indeed: {job['url']}")
        return False

    await apply_btn.click()
    await asyncio.sleep(3)

    # Indeed Instant Apply
    cl_field = await page.query_selector("textarea[name='coverletter'], textarea[id='coverletter']")
    if cl_field and cover_letter:
        await cl_field.fill(cover_letter)

    submit_btn = await page.query_selector(
        "button[data-testid='IA-continueButton'], button[type='submit']"
    )
    if submit_btn:
        await submit_btn.click()
        await asyncio.sleep(2)
        return True

    return False


APPLY_HANDLERS = {
    "linkedin": apply_linkedin,
    "naukri": apply_naukri,
    "indeed": apply_indeed,
}


async def apply_to_job(job: dict, profile: dict, cover_letter: str, config: dict) -> bool:
    source = job["source"]
    handler = APPLY_HANDLERS.get(source)
    if not handler:
        print(f"[applier] no handler for source: {source}")
        return False

    browser_cfg = config["browser"]
    cookies_file = config["sources"][source]["cookies_file"]

    async with async_playwright() as p:
        browser, context = await make_browser(
            p, headless=browser_cfg["headless"], slow_mo=browser_cfg["slow_mo"]
        )
        await load_cookies(context, cookies_file)
        page = await context.new_page()

        success = await handler(page, job, profile, cover_letter)
        await browser.close()

    return success
