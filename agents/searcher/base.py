import json
import re
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page


async def load_cookies(context: BrowserContext, cookies_file: str):
    path = Path(cookies_file)
    if not path.exists():
        raise FileNotFoundError(
            f"Cookie file not found: {cookies_file}\n"
            "Export cookies from your browser using 'EditThisCookie' or similar extension as JSON."
        )
    with open(path) as f:
        cookies = json.load(f)
    # Playwright expects list of dicts with specific keys
    cleaned = []
    for c in cookies:
        cleaned.append({
            "name":     c["name"],
            "value":    c["value"],
            "domain":   c.get("domain", ""),
            "path":     c.get("path", "/"),
            "secure":   c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Strict","Lax","None") else "Lax",
        })
    await context.add_cookies(cleaned)


def parse_salary_lpa(text: str) -> float | None:
    """Extract numeric LPA value from salary strings like '35-50 LPA', '₹40L', etc."""
    if not text:
        return None
    text = text.lower().replace(",", "")
    # match patterns like "35 lpa", "35-50 lpa", "35l", "35 lakhs"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lpa|l\b|lakh)", text)
    if m:
        return float(m.group(1))
    # match "35-50" range — take lower bound
    m = re.search(r"(\d+)\s*[-–]\s*\d+", text)
    if m:
        return float(m.group(1))
    return None


async def make_browser(playwright, headless: bool = True, slow_mo: int = 500):
    browser = await playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return browser, context
