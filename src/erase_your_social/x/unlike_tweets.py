"""Unlike all liked tweets for a given X/Twitter account."""

import json
import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

SESSION_DIR = Path(".session/x")
# Cookie-Editor export: either name is common
COOKIE_FILES = (SESSION_DIR / "cookie.json", SESSION_DIR / "cookies.json")
STORAGE_STATE_FILE = SESSION_DIR / "storage_state.json"

# Conservative pacing (~2–3× the previous defaults). Tune down if a run is too slow.
_DELAY_AFTER_PAGE_LOAD = 4.0
_DELAY_BETWEEN_UNLIKES = 2.5
_DELAY_AFTER_SCROLL = 3.0
_DELAY_ON_RETRY_NUDGE = 1.2

BrowserType = Literal["firefox", "chromium"]


def _resolve_cookies_file() -> Path:
    for path in COOKIE_FILES:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No cookies file found. Put an export at one of: "
        f"{', '.join(str(p) for p in COOKIE_FILES)}. "
        "Export from Cookie-Editor, then delete storage_state.json if you re-export."
    )


def _normalize_same_site(raw: object) -> str:
    if raw is None:
        return "Lax"
    if isinstance(raw, bool):
        return "Lax"
    text = str(raw).strip()
    if not text:
        return "Lax"
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
) -> None:
    raw = json.loads(cookies_file.read_text())

    # Cookie-Editor exports a list of cookies — convert to Playwright's storage_state format
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
                "sameSite": _normalize_same_site(c.get("sameSite")),
            }
            for c in raw
        ],
        "origins": [],
    }

    storage_state_file.write_text(json.dumps(storage_state, indent=2))
    print(f"Session saved to {storage_state_file}")


def _storage_state_for_playwright(path: Path) -> dict:
    """Load storage state and fix sameSite values Playwright rejects (e.g. Cookie-Editor exports)."""
    data = json.loads(path.read_text())
    for cookie in data.get("cookies", []):
        cookie["sameSite"] = _normalize_same_site(cookie.get("sameSite"))
    return data


def _ensure_storage_state() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if STORAGE_STATE_FILE.exists():
        return
    cookies_file = _resolve_cookies_file()
    print("Converting cookies to session state...")
    load_cookies_into_storage_state(cookies_file, STORAGE_STATE_FILE)


@contextmanager
def browser_context(
    playwright: Playwright, browser: BrowserType = "firefox"
) -> Iterator[BrowserContext]:
    _ensure_storage_state()
    browser_type = getattr(playwright, browser)
    browser_instance = browser_type.launch(headless=False)
    ctx = browser_instance.new_context(
        storage_state=_storage_state_for_playwright(STORAGE_STATE_FILE)
    )
    try:
        yield ctx
    finally:
        ctx.close()
        browser_instance.close()


def _human_delay(seconds: float, jitter_ratio: float = 0.35) -> None:
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


def unlike_visible_tweets(page: Page, running_total: int) -> tuple[int, int]:
    """Unlike tweets currently in the DOM.

    X virtualizes the timeline; ``locator.all()`` returns handles that go stale after
    clicks. We always click the first visible unlike and re-resolve so scroll/click
    targets stay attached.
    """
    batch = 0
    consecutive_failures = 0
    max_failures = 4

    while True:
        unlike = page.locator('button[data-testid="unlike"]')
        if unlike.count() == 0:
            break

        btn = unlike.first
        try:
            btn.scroll_into_view_if_needed(timeout=20_000)
            btn.click(timeout=20_000)
        except Exception as e:
            consecutive_failures += 1
            short = str(e).split("\n", 1)[0]
            print(f"  skipped (will retry after nudge): {short}")
            page.evaluate("window.scrollBy(0, 350)")
            _human_delay(_DELAY_ON_RETRY_NUDGE)
            if consecutive_failures >= max_failures:
                print(
                    "  giving up on this viewport after repeated failures; scrolling on…"
                )
                break
            continue

        consecutive_failures = 0
        batch += 1
        running_total += 1
        print(f"Unliked tweet #{running_total}")
        _human_delay(_DELAY_BETWEEN_UNLIKES)

    return batch, running_total


def unlike_all_tweets(username: str, browser: BrowserType = "firefox") -> None:
    likes_url = f"https://x.com/{username}/likes"

    with sync_playwright() as p:
        with browser_context(p, browser) as context:
            page = context.new_page()

            ensure_logged_in(page)

            print(f"\nNavigating to likes page: {likes_url}")
            page.goto(likes_url)
            page.wait_for_load_state("domcontentloaded")
            _human_delay(_DELAY_AFTER_PAGE_LOAD, jitter_ratio=0.3)

            total_unliked = 0
            no_new_count = 0

            print("\nStarting to unlike tweets... (press Ctrl+C to stop early)\n")

            while True:
                batch, total_unliked = unlike_visible_tweets(page, total_unliked)

                if batch == 0:
                    page.evaluate("window.scrollBy(0, 800)")
                    _human_delay(_DELAY_AFTER_SCROLL)
                    no_new_count += 1
                    if no_new_count >= 6:
                        print("No more liked tweets found. All done!")
                        break
                else:
                    no_new_count = 0
                    page.evaluate("window.scrollBy(0, 600)")
                    _human_delay(_DELAY_AFTER_SCROLL)

            print(f"\nDone! Unliked {total_unliked} tweets total.")


if __name__ == "__main__":
    username = input("Enter your X username (without @): ").strip()
    browser = (
        input("Browser to use (firefox/chromium) [firefox]: ").strip() or "firefox"
    )
    unlike_all_tweets(username, browser)
