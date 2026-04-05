# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scripts for automating cleanup of social media accounts via Playwright browser automation. Currently supports X (Twitter).

## Key Commands

```bash
# Install dependencies and Playwright browser binaries
uv sync
uv run playwright install firefox   # or chromium

# Run scripts
uv run -m erase_your_social.x.unlike_tweets
uv run -m erase_your_social.x.delete_tweets

# Lint/format (via pre-commit or directly)
uv run ruff check --fix
uv run ruff format
```

## Code Architecture

### Session Management (`src/erase_your_social/x/session.py`)

All scripts share `session.py` for authentication:

1. Users export cookies from their logged-in browser via Cookie-Editor extension
2. Save as `.session/x/cookie.json` or `.session/x/cookies.json` (gitignored)
3. On first run, cookies are converted to Playwright `storage_state.json`
4. `browser_context()` context manager handles launching a visible browser with the saved session

Key constants at module level control pacing: `DELAY_AFTER_PAGE_LOAD`, `DELAY_BETWEEN_ACTIONS`, `DELAY_AFTER_SCROLL`, `DELAY_ON_RETRY_NUDGE`.

### X Scripts

- **`unlike_tweets.py`** — Navigates to `/username/likes`, repeatedly finds and clicks `data-testid="unlike"` buttons.
- **`delete_tweets.py`** — Navigates to `/username` (or `/username/replies`), iterates through articles, detects own posts/reposts, opens the "More" menu, clicks Delete, confirms. Also handles undoing own reposts.

Both scripts use the same pattern: loop over visible DOM elements, batch-process them, scroll, repeat until no new elements found.

### Cookie/Session Files

- `.session/x/cookie.json` or `cookies.json` — User-provided cookie export
- `.session/x/storage_state.json` — Auto-generated Playwright storage state (delete to re-generate from fresh cookie export)

## Important Patterns

- All scripts use Playwright **sync** API (`sync_playwright`)
- Scripts import `session` as a relative import from the same directory (not as a package import)
- `human_delay()` adds jitter to all `time.sleep()` calls to appear more natural
- Scripts run with `headless=False` — the browser window must stay visible/foregrounded
