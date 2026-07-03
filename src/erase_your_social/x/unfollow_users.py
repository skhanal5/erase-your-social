"""Unfollow all users you follow on X/Twitter.

The script opens your /following page and clicks each "Following" button,
confirming via the confirmation sheet.

Run with:

    uv run -m erase_your_social.x.unfollow_users
"""

import time

from playwright.sync_api import Page, sync_playwright

from .session import (
    DELAY_AFTER_PAGE_LOAD,
    DELAY_AFTER_SCROLL,
    DELAY_BETWEEN_ACTIONS,
    DELAY_ON_RETRY_NUDGE,
    BrowserType,
    browser_context,
    ensure_logged_in,
    human_delay,
)

MAX_SESSION_SECONDS = 30 * 60


def _dismiss_dialogs(page: Page) -> None:
    page.keyboard.press("Escape")
    human_delay(0.2, jitter_ratio=0.1)


def unfollow_visible_users(page: Page, running_total: int) -> tuple[int, int]:
    batch = 0
    consecutive_failures = 0
    max_failures = 4

    while True:
        following = page.locator('[data-testid$="-unfollow"]')
        if following.count() == 0:
            break

        btn = following.first
        try:
            btn.scroll_into_view_if_needed(timeout=20_000)
            btn.click(timeout=15_000)
        except Exception as e:
            consecutive_failures += 1
            short = str(e).split("\n", 1)[0]
            print(f"  skipped (will retry after nudge): {short}")
            page.evaluate("window.scrollBy(0, 350)")
            human_delay(DELAY_ON_RETRY_NUDGE)
            if consecutive_failures >= max_failures:
                print(
                    "  giving up on this viewport after repeated failures; scrolling on…"
                )
                break
            continue

        consecutive_failures = 0
        human_delay(0.5, jitter_ratio=0.2)

        confirm = page.locator('[data-testid="confirmationSheetConfirm"]')
        if confirm.count() > 0:
            try:
                confirm.first.wait_for(state="visible", timeout=5_000)
                confirm.first.click(timeout=5_000)
                human_delay(0.3, jitter_ratio=0.2)
            except Exception:
                pass

        _dismiss_dialogs(page)

        batch += 1
        running_total += 1
        print(f"Unfollowed user #{running_total}")
        human_delay(DELAY_BETWEEN_ACTIONS)

    return batch, running_total


def unfollow_all_users(username: str, browser: BrowserType = "firefox") -> None:
    start_time = time.monotonic()
    following_url = f"https://x.com/{username}/following"

    with sync_playwright() as p:
        with browser_context(p, browser) as context:
            page = context.new_page()

            ensure_logged_in(page)

            print(f"\nNavigating to following page: {following_url}")
            page.goto(following_url)
            page.wait_for_load_state("domcontentloaded")
            human_delay(DELAY_AFTER_PAGE_LOAD, jitter_ratio=0.3)

            total_unfollowed = 0
            no_new_count = 0

            print("\nStarting to unfollow users... (press Ctrl+C to stop early)\n")

            while True:
                elapsed = time.monotonic() - start_time
                if elapsed > MAX_SESSION_SECONDS:
                    print(
                        f"\nSession reached {MAX_SESSION_SECONDS // 60} min. "
                        f"Stopped after unfollowing {total_unfollowed} users. "
                        f"Run again if more remain."
                    )
                    break

                batch, total_unfollowed = unfollow_visible_users(page, total_unfollowed)

                if batch == 0:
                    page.evaluate("window.scrollBy(0, 800)")
                    human_delay(DELAY_AFTER_SCROLL)
                    no_new_count += 1
                    if no_new_count >= 6:
                        print("No more users to unfollow. All done!")
                        break
                else:
                    no_new_count = 0
                    page.evaluate("window.scrollBy(0, 600)")
                    human_delay(DELAY_AFTER_SCROLL)

            print(f"\nDone! Unfollowed {total_unfollowed} users total.")


if __name__ == "__main__":
    username = input("Your X username (without @): ").strip()
    browser = (
        input("Browser to use (firefox/chromium) [firefox]: ").strip() or "firefox"
    )
    unfollow_all_users(username, browser)
