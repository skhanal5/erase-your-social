import time

from playwright.sync_api import sync_playwright


def unlike_all_tweets(username: str) -> None:
    likes_url = f"https://x.com/{username}/likes"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("\nOpening X/Twitter... Please log in if prompted.")
        page.goto("https://x.com/login")
        input("\nPress ENTER once you're fully logged in and can see your feed: ")

        print(f"\nNavigating to likes page: {likes_url}")
        page.goto(likes_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        unliked_count = 0
        no_new_count = 0

        print("\nStarting to unlike tweets... (press Ctrl+C to stop early)\n")

        while True:
            unlike_buttons = page.locator('button[data-testid="unlike"]').all()

            if not unlike_buttons:
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1.5)
                no_new_count += 1
                if no_new_count >= 6:
                    print("No more liked tweets found. All done!")
                    break
                continue

            no_new_count = 0

            for button in unlike_buttons:
                try:
                    button.scroll_into_view_if_needed()
                    button.click()
                    unliked_count += 1
                    print(f"Unliked tweet #{unliked_count}")
                    time.sleep(0.8)
                except Exception as e:
                    print(f"Skipped a button ({e})")

            page.evaluate("window.scrollBy(0, 600)")
            time.sleep(1.5)

        print(f"\nDone! Unliked {unliked_count} tweets total.")
        browser.close()


if __name__ == "__main__":
    username = input("Enter your X/Twitter username (without @): ").strip()
    unlike_all_tweets(username)
