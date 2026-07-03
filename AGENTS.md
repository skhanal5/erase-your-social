# AGENTS.md

Single-package Python project automating X account cleanup via Playwright (sync API).

## Commands

```bash
uv sync                                 # install deps
uv run playwright install firefox       # browser binary
uv run pre-commit install               # ruff --fix + ruff-format
uv run ruff check --fix                 # lint (or via pre-commit)
uv run ruff format                      # format
uv run -m erase_your_social.x.unfollow_users
uv run -m erase_your_social.x.unlike_tweets
uv run -m erase_your_social.x.delete_tweets
```

No `__main__.py` at the package level — scripts are always invoked via `-m`.

## Structure

```
src/erase_your_social/x/
  session.py         # shared auth: cookies → storage_state, browser_context()
  unfollow_users.py  # /username/following, clicks "Following" → confirm unfollow
  unlike_tweets.py   # /username/likes, clicks data-testid="unlike"
  delete_tweets.py   # profile feed, deletes own posts/replies, undoes reposts
```

## Critical conventions

- **Relative imports**: scripts import session as `.session` (not the package path).
- **Not headless**: `headless=False` — browser window must stay visible/foregrounded.
- **Session setup**: user exports cookies via Cookie-Editor → `.session/x/cookie.json` or `cookies.json` (gitignored). On first run `session.py` converts to Playwright `storage_state.json`. Delete `storage_state.json` to regenerate from a fresh cookie export.
- **Pacing constants** in `session.py:17-21`: `DELAY_AFTER_PAGE_LOAD=4.0`, `DELAY_BETWEEN_ACTIONS=2.5`, `DELAY_AFTER_SCROLL=3.0`, `DELAY_ON_RETRY_NUDGE=1.2`. `human_delay()` adds random jitter (default ±35%) to all sleeps.
- **30‑min timeout**: both scripts abort after `MAX_SESSION_SECONDS = 30 * 60` to avoid unbounded runs.
- **Interactive prompts**: scripts prompt for username, browser (firefox/chromium), and mode at `__main__`.

## Testing

No tests exist. No test framework configured. Lint (ruff) is the only CI gate via pre-commit.

## Key constraints from existing instructions

- Never push/commit to `main` directly; never merge a PR without explicit instruction.
