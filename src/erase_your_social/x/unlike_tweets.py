"""Unlike all liked tweets for a given X/Twitter account."""

from playwright.sync_api import Page, sync_playwright

from session import (
    DELAY_AFTER_PAGE_LOAD,
    DELAY_AFTER_SCROLL,
    DELAY_BETWEEN_ACTIONS,
    DELAY_ON_RETRY_NUDGE,
    BrowserType,
    browser_context,
    ensure_logged_in,
    human_delay,
)


def unlike_visible_tweets(page: Page, running_total: int) -> tuple[int, int]:
    """Unlike tweets currently in the DOM (re-resolve first unlike each time)."""
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
            human_delay(DELAY_ON_RETRY_NUDGE)
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
        human_delay(DELAY_BETWEEN_ACTIONS)

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
            human_delay(DELAY_AFTER_PAGE_LOAD, jitter_ratio=0.3)

            total_unliked = 0
            no_new_count = 0

            print("\nStarting to unlike tweets... (press Ctrl+C to stop early)\n")

            while True:
                batch, total_unliked = unlike_visible_tweets(page, total_unliked)

                if batch == 0:
                    page.evaluate("window.scrollBy(0, 800)")
                    human_delay(DELAY_AFTER_SCROLL)
                    no_new_count += 1
                    if no_new_count >= 6:
                        print("No more liked tweets found. All done!")
                        break
                else:
                    no_new_count = 0
                    page.evaluate("window.scrollBy(0, 600)")
                    human_delay(DELAY_AFTER_SCROLL)

            print(f"\nDone! Unliked {total_unliked} tweets total.")


if __name__ == "__main__":
    username = input("Enter your X username (without @): ").strip()
    browser = (
        input("Browser to use (firefox/chromium) [firefox]: ").strip() or "firefox"
    )
    unlike_all_tweets(username, browser)
