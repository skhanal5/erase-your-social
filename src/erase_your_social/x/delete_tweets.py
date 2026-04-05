"""Delete posts (and replies) from your X profile timeline.

Uses the same cookie/session setup as ``unlike_tweets``. Destructive: prefer the
``replies`` feed if you only want reply threads removed.

The DOM flow (tweet article, More menu, Delete, confirmation sheet; repost undo)
was informed by a browser-console script shared by Don McCurdy:

  https://gist.github.com/donmccurdy/c7dbf813e64e2af9c745f9f446c1ee90

This file is a separate Playwright implementation, not a copy of that gist.

Run with:

    uv run -m erase_your_social.x.delete_tweets
"""

import re
import time
from typing import Literal
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page, sync_playwright

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

FeedMode = Literal["posts", "replies"]

# Maximum total runtime before warning and exiting (avoids infinite loops on
# CAPTCHA pages or when the session has silently expired).
MAX_SESSION_SECONDS = 30 * 60

# How many consecutive "stuck" articles to tolerate before giving up on the
# current batch. Raised from 5 because replies feeds are full of other people's
# tweets interspersed with the user's own content.
MAX_STUCK = 15


def _normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def _handle_from_profile_href(href: str) -> str | None:
    """First path segment of a profile or status URL: /you, /you/status/id."""
    if not href:
        return None
    raw = href.split("?", 1)[0].strip()
    if "://" in raw:
        path = urlparse(raw).path or ""
    else:
        path = raw
    if not path.startswith("/"):
        return None
    seg = path.strip("/").split("/")[0].lstrip("@")
    if not seg or len(seg) > 15:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_]+", seg):
        return None
    return seg.lower()


def _article_primary_handle(article: Locator) -> str | None:
    """Handle shown on the top author row of this tweet card (not nested quote internals)."""
    row = article.locator('[data-testid="User-Name"]').first
    if row.count() == 0:
        return None
    link = row.locator("a[href^='/']").first
    if link.count() == 0:
        return None
    href = link.get_attribute("href")
    return _handle_from_profile_href(href or "")


def _is_own_repost_or_retweet_context(label: str) -> bool:
    t = label.strip().lower()
    if not t:
        return False
    # English UI; other locales may need extra phrases.
    return "you reposted" in t or "you retweeted" in t


def _open_profile_feed(page: Page, username: str, mode: FeedMode) -> None:
    page.goto(f"https://x.com/{username}")
    page.wait_for_load_state("domcontentloaded")
    human_delay(DELAY_AFTER_PAGE_LOAD, jitter_ratio=0.3)

    if mode != "replies":
        return

    tab = page.get_by_role("tab", name=re.compile(r"replies", re.I))
    if tab.count() == 0:
        print(
            "No Replies tab found; staying on default profile posts. "
            "(UI may differ by locale or layout.)"
        )
        return
    tab.first.click()
    human_delay(2.0, jitter_ratio=0.25)


def _unrepost_from_article(page: Page, article: Locator) -> bool:
    """Undo a repost/retweet (shows original author on the card)."""
    un = article.locator('[data-testid="unretweet"]')
    if un.count() == 0:
        un = article.get_by_role(
            "button",
            name=re.compile(r"undo (repost|retweet)", re.I),
        )
    if un.count() == 0:
        # Active repost: retweet control is filled; click opens undo.
        rt = article.locator('[data-testid="retweet"]')
        if rt.count() > 0:
            rt.first.click(timeout=15_000)
            human_delay(0.35, jitter_ratio=0.2)
            undo = page.get_by_role(
                "menuitem",
                name=re.compile(r"undo (repost|retweet)", re.I),
            )
            if undo.count() > 0:
                undo.first.click(timeout=10_000)
                human_delay(0.35, jitter_ratio=0.2)
                _dismiss_dialogs(page)
                return True
            page.keyboard.press("Escape")
            _dismiss_dialogs(page)
            return False
        return False

    un.first.click(timeout=15_000)
    human_delay(0.35, jitter_ratio=0.2)
    for testid in ("unretweetConfirm", "confirmationSheetConfirm"):
        confirm = page.locator(f'[data-testid="{testid}"]')
        if confirm.count() > 0:
            confirm.first.wait_for(state="visible", timeout=10_000)
            confirm.first.click(timeout=10_000)
            _dismiss_dialogs(page)
            return True

    # Nothing matched — make sure no stale menu stays open.
    _dismiss_dialogs(page)
    return False


def _delete_from_article(page: Page, article: Locator) -> bool:
    more = article.get_by_role("button", name=re.compile(r"more", re.I))
    if more.count() == 0:
        more = article.locator('[data-testid="caret"]')
    if more.count() == 0:
        return False

    more.first.click(timeout=15_000)
    human_delay(0.5, jitter_ratio=0.2)

    delete_item = page.get_by_role("menuitem", name=re.compile(r"^delete$", re.I))
    if delete_item.count() == 0:
        page.keyboard.press("Escape")
        _dismiss_dialogs(page)
        return False

    delete_item.first.click(timeout=10_000)
    human_delay(0.5, jitter_ratio=0.2)

    confirm = page.locator('[data-testid="confirmationSheetConfirm"]')
    try:
        confirm.wait_for(state="visible", timeout=10_000)
        confirm.click(timeout=10_000)
    except Exception:
        page.keyboard.press("Escape")
        _dismiss_dialogs(page)
        return False
    return True


def _dismiss_dialogs(page: Page) -> None:
    """Press Escape and wait briefly to clear any lingering menus/sheets."""
    page.keyboard.press("Escape")
    human_delay(0.2, jitter_ratio=0.1)


# Process result sentinels.
_RESULT_DONE = "done"
_RESULT_REPOST = "repost"
_RESULT_POST = "post"
_RESULT_STUCK = "stuck"


def _process_next_own_content(
    page: Page, username: str, *, remove_reposts: bool
) -> str:
    """Find the next deletable *yours* card or own repost; skip OP tweets in threads.

    Returns one of the ``_RESULT_*`` sentinels.
    """
    articles = page.locator('article[data-testid="tweet"]')
    n = articles.count()
    if n == 0:
        return _RESULT_DONE

    want = _normalize_username(username)

    for i in range(n):
        article = articles.nth(i)
        try:
            article.scroll_into_view_if_needed(timeout=20_000)
        except Exception:
            continue

        ctx = article.locator('[data-testid="socialContext"]')
        if ctx.count() > 0:
            try:
                label = ctx.first.inner_text(timeout=5_000)
            except Exception:
                continue
            if _is_own_repost_or_retweet_context(label):
                if remove_reposts and _unrepost_from_article(page, article):
                    return _RESULT_REPOST
                # User chose to keep reposts — intentionally skip.
                continue

        handle = _article_primary_handle(article)
        if handle != want:
            continue

        if _delete_from_article(page, article):
            return _RESULT_POST

    return _RESULT_STUCK


def delete_visible_posts(
    page: Page,
    username: str,
    running_total: int,
    *,
    remove_reposts: bool,
) -> tuple[int, int]:
    batch = 0
    consecutive_stuck = 0

    while True:
        result = _process_next_own_content(
            page, username, remove_reposts=remove_reposts
        )
        if result == _RESULT_DONE:
            break
        if result in (_RESULT_REPOST, _RESULT_POST):
            consecutive_stuck = 0
            batch += 1
            running_total += 1
            label = "repost" if result == _RESULT_REPOST else "post/reply"
            print(f"Removed {label} #{running_total}")
            human_delay(DELAY_BETWEEN_ACTIONS)
            continue
        consecutive_stuck += 1
        print(
            "  no matching cards in view (others' tweets, blocked menu); nudging scroll…"
        )
        page.keyboard.press("Escape")
        page.evaluate("window.scrollBy(0, 400)")
        human_delay(DELAY_ON_RETRY_NUDGE)
        if consecutive_stuck >= MAX_STUCK:
            print("  too many stuck cards in a row; scroll the timeline and retry.")
            break

    return batch, running_total


def delete_posts_from_profile(
    username: str,
    browser: BrowserType = "firefox",
    *,
    mode: FeedMode = "replies",
    remove_reposts: bool = True,
) -> None:
    start_time = time.monotonic()

    with sync_playwright() as p:
        with browser_context(p, browser) as context:
            page = context.new_page()
            ensure_logged_in(page)

            print(f"\nOpening profile @{username} (feed: {mode})…")
            _open_profile_feed(page, username, mode)

            total_removed = 0
            no_new_count = 0

            print(
                "\nDeleting visible posts… (Ctrl+C to stop). "
                "Confirm dialogs are automated.\n"
            )

            while True:
                elapsed = time.monotonic() - start_time
                if elapsed > MAX_SESSION_SECONDS:
                    print(
                        f"\nSession reached {MAX_SESSION_SECONDS // 60} min. "
                        f"Stopped after removing {total_removed} items. "
                        f"Run again if more posts remain."
                    )
                    break

                batch, total_removed = delete_visible_posts(
                    page, username, total_removed, remove_reposts=remove_reposts
                )

                if batch == 0:
                    page.evaluate("window.scrollBy(0, 800)")
                    human_delay(DELAY_AFTER_SCROLL)
                    no_new_count += 1
                    if no_new_count >= 8:
                        print("No more deletable posts in view. Done.")
                        break
                else:
                    no_new_count = 0
                    page.evaluate("window.scrollBy(0, 600)")
                    human_delay(DELAY_AFTER_SCROLL)

            print(f"\nFinished. Removed {total_removed} posts/reposts this session.")


if __name__ == "__main__":
    username = input("Your X username (without @): ").strip()
    browser = (
        input("Browser to use (firefox/chromium) [firefox]: ").strip() or "firefox"
    )
    mode_in = (
        input("Feed: replies only or all profile posts? [replies/posts]: ")
        .strip()
        .lower()
        or "replies"
    )
    mode: FeedMode = "posts" if mode_in.startswith("p") else "replies"
    repost_in = input("Also remove your own reposts/retweets? [Y/n]: ").strip().lower()
    remove_reposts = repost_in not in ("n", "no")
    delete_posts_from_profile(
        username, browser, mode=mode, remove_reposts=remove_reposts
    )
