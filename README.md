# erase-your-social

Scripts for automating tasks to clean up your social media accounts.

## About

Most social platforms make it tedious to undo years of activity (likes, posts, follows) one click at a time. This project is a collection of browser automation scripts that do the grunt work for you.

## Disclaimer

Bulk automation may conflict with platform **terms of use** or trigger **rate limits**, challenges, or account restrictions. These scripts are a convenience only and do not guarantee uninterrupted access. Sites can change their **HTML and APIs** at any time; scripts here may need updates when that happens.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

Install dependencies, browser binaries for Playwright, and pre-commit hooks:

```bash
uv sync
uv run playwright install firefox   # and/or: playwright install chromium
uv run pre-commit install
```

## X

Automation for [X](https://x.com) lives in `src/erase_your_social/x/`. Multiple scripts share the same cookie/session helpers in `session.py` (for example `delete_tweets.py`).

### Session and cookies

Logging in directly inside Playwright often fails (X treats automated browsers strictly). This project instead reuses a session from a browser where you are already logged in:

1. In your normal browser, log into X.
2. Export cookies with an extension such as [Cookie-Editor](https://cookie-editor.com/) (JSON export).
3. Save the file as **either** `.session/x/cookie.json` **or** `.session/x/cookies.json` (the directory is gitignored).
4. On first run, `session.py` converts that JSON into Playwright’s `storage_state` format at `.session/x/storage_state.json`.

If you **re-export** cookies after they expire, delete `storage_state.json` so it is regenerated from the new export.

### Unlike tweets

The `unlike_tweets.py` script opens X in a **visible** Playwright browser, loads your **likes** timeline (`/yourname/likes`), and clicks each **Unlike** control until the page stops offering new ones.

### Delete tweets

The `delete_tweets.py` script opens your profile feed and deletes your own content (posts, replies, and optionally reposts). You'll be prompted for:

- **Feed mode** — `replies` (default) to target reply threads only, or `posts` for the full profile feed.
- **Remove reposts** — whether to also undo your own reposts/retweets (defaults to yes). Prefer the `replies` feed if you only want replies removed.

The DOM flow was informed by a [browser-console script](https://gist.github.com/donmccurdy/c7dbf813e64e2af9c745f9f446c1ee90) from Don McCurdy.

### How to run

From the repository root:

```bash
uv run -m erase_your_social.x.unlike_tweets
uv run -m erase_your_social.x.delete_tweets
```

You will be prompted for your X handle (without `@`) and for `firefox` or `chromium`. Keep the automated browser window **in the foreground** enough that it can scroll and click; avoid using that same window manually while the script runs. You can stop with **Ctrl+C** at any time.
