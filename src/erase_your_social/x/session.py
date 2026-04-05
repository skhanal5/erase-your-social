"""Shared Playwright session helpers for X (cookies -> storage state, browser context)."""

import fcntl
import json
import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from playwright.sync_api import BrowserContext, Page, Playwright

SESSION_DIR = Path(".session/x")
COOKIE_FILES = (SESSION_DIR / "cookie.json", SESSION_DIR / "cookies.json")
STORAGE_STATE_FILE = SESSION_DIR / "storage_state.json"

# Conservative pacing; tune per script if needed.
DELAY_AFTER_PAGE_LOAD = 4.0
DELAY_BETWEEN_ACTIONS = 2.5
DELAY_AFTER_SCROLL = 3.0
DELAY_ON_RETRY_NUDGE = 1.2

BrowserType = Literal["firefox", "chromium"]


def resolve_cookies_file() -> Path:
    for path in COOKIE_FILES:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No cookies file found. Put an export at one of: "
        f"{', '.join(str(p) for p in COOKIE_FILES)}. "
        "Export from Cookie-Editor, then delete storage_state.json if you re-export."
    )


def normalize_same_site(raw: object) -> str:
    if raw is None:
        return "None"
    if isinstance(raw, bool):
        return "Lax"
    text = str(raw).strip()
    if not text:
        return "None"
    key = text.lower().replace("-", "_")
    if key in ("lax", "unspecified"):
        return "Lax"
    if key == "strict":
        return "Strict"
    if key in ("none", "no_restriction"):
        return "None"
    return "Lax"


def load_cookies_into_storage_state(
    cookies_file: Path, storage_state_file: Path
) -> str:
    raw = json.loads(cookies_file.read_text())
    storage_state = {
        "cookies": [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".x.com"),
                "path": c.get("path", "/"),
                "expires": c.get("expirationDate", -1),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": normalize_same_site(c.get("sameSite")),
            }
            for c in raw
        ],
        "origins": [],
    }
    storage_state_file.write_text(json.dumps(storage_state, indent=2))
    return f"Session saved to {storage_state_file}"


def storage_state_for_playwright(path: Path) -> dict:
    data = json.loads(path.read_text())
    for cookie in data.get("cookies", []):
        cookie["sameSite"] = normalize_same_site(cookie.get("sameSite"))
    return data


def ensure_storage_state() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if STORAGE_STATE_FILE.exists():
        return
    cookies_file = resolve_cookies_file()
    print("Converting cookies to session state...")
    lock_path = STORAGE_STATE_FILE.with_suffix(".lock")
    with open(lock_path, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            while not STORAGE_STATE_FILE.exists():
                time.sleep(0.2)
            return
        try:
            if STORAGE_STATE_FILE.exists():
                return
            load_cookies_into_storage_state(cookies_file, STORAGE_STATE_FILE)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def browser_context(
    playwright: Playwright, browser: BrowserType = "firefox"
) -> Iterator[BrowserContext]:
    ensure_storage_state()
    browser_type = getattr(playwright, browser)
    browser_instance = browser_type.launch(headless=False)
    ctx = browser_instance.new_context(
        storage_state=storage_state_for_playwright(STORAGE_STATE_FILE)
    )
    try:
        yield ctx
    finally:
        ctx.close()
        browser_instance.close()


def human_delay(seconds: float, jitter_ratio: float = 0.35) -> None:
    low = max(0.05, seconds * (1 - jitter_ratio))
    high = seconds * (1 + jitter_ratio)
    time.sleep(random.uniform(low, high))


def ensure_logged_in(page: Page) -> None:
    page.goto("https://x.com")
    page.wait_for_load_state("domcontentloaded")
    if "login" in page.url or page.locator('a[href="/login"]').count() > 0:
        raise RuntimeError(
            "Not logged in. Your cookies may have expired. "
            "Re-export from Cookie-Editor and delete storage_state.json to try again."
        )
