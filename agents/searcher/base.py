import json
import re
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page


_VALID_SAMESITE = ("Strict", "Lax", "None")


def _parse_cookies(raw: list) -> list[dict]:
    """Validate and normalise raw cookie list from JSON file."""
    if not isinstance(raw, list):
        raise ValueError("Cookie file must contain a JSON array")
    cleaned = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise ValueError(f"Cookie entry {i} is not an object")
        name = c.get("name")
        value = c.get("value")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Cookie entry {i} missing 'name'")
        if not isinstance(value, str):
            raise ValueError(f"Cookie entry {i} missing 'value'")
        same_site = c.get("sameSite", "Lax")
        cleaned.append({
            "name":     name,
            "value":    value,
            "domain":   str(c.get("domain", "")),
            "path":     str(c.get("path", "/")),
            "secure":   bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
            "sameSite": same_site if same_site in _VALID_SAMESITE else "Lax",
        })
    return cleaned


async def load_cookies(context: BrowserContext, cookies_file: str):
    path = Path(cookies_file)
    if not path.exists():
        raise FileNotFoundError(
            f"Cookie file not found: {cookies_file}\n"
            "Export cookies from your browser using 'EditThisCookie' or similar extension as JSON."
        )
    with open(path) as f:
        raw = json.load(f)
    cleaned = _parse_cookies(raw)
    await context.add_cookies(cleaned)


def parse_salary_lpa(text: str) -> float | None:
    """Extract numeric LPA value from salary strings like '35-50 LPA', '₹40L', etc."""
    if not text:
        return None
    text = text.lower().replace(",", "")
    # range like "35-50 lpa" or "1.5–3 lpa" — take lower bound
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*\d+(?:\.\d+)?\s*(?:lpa|l\b|lakh)", text)
    if m:
        return float(m.group(1))
    # single value like "35 lpa", "35l", "40 lakhs"
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lpa|l\b|lakh)", text)
    if m:
        return float(m.group(1))
    # bare range with no unit like "35-50" — take lower bound
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*\d+", text)
    if m:
        return float(m.group(1))
    return None


async def make_browser(playwright, headless: bool = True, slow_mo: int = 500,
                       executable_path: str | None = None):
    """Ephemeral browser + context. Use make_persistent_context for sites that log out."""
    launch_kwargs: dict = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"],
    }
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return browser, context


async def make_persistent_context(playwright, profile_dir: str,
                                   headless: bool = True, slow_mo: int = 500,
                                   executable_path: str | None = None):
    """
    Persistent browser context backed by a real profile directory.
    Session cookies, localStorage, and login state survive between runs.
    First run with a new profile_dir: browser opens so user can log in manually.
    Subsequent runs: already authenticated.
    Returns context only (no separate browser object — they're fused in persistent mode).
    """
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    launch_kwargs: dict = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        "viewport": {"width": 1280, "height": 800},
    }
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
    context = await playwright.chromium.launch_persistent_context(profile_dir, **launch_kwargs)
    return context
