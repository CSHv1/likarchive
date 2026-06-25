# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, and stores extracted posts in SQLite. Daily auto-sync via scheduler. GCP Cloud Run deployment planned for a later phase. End goal for *me*: a shipped, owned, end-to-end thing I'd actually claim — cloud-native, scheduled, secrets done properly.

## Current state (where I left it)

**Built and working locally:**

- `scraper.py` — Playwright saved-posts navigation, infinite-scroll pagination, extracts post text / author / URL / timestamp (auth via persistent browser profile)
- `save_session.py` — one-time manual login; saves browser profile to `browser_profile/`
- `db.py` — SQLite with MD5 hash dedup; FTS5 + tags schema; `post_date` column (reconstructed from relative timestamps)
- `query.py` — CLI browser with FTS5 search
- `tagger.py` — auto-tagging via Claude Haiku (`claude-haiku-4-5-20251001`)
- `scheduler.py` — daily sync
- `app.py` + `templates/index.html` — Flask web UI: card list, tag/author/date filters, FTS search, load more pagination
- `CLAUDE.md` — merged instructions + 8-phase roadmap
- ~148 posts in local DB, all tagged

**Stopped at:** end of Phase 3 (Flask GUI). Next build is Phase 4 (Docker containerisation), then GCP infra (Phases 5–7).

## ⚠️ Known watch-point — check this FIRST

LinkedIn class names are unstable. Selectors were rewritten in June 2026 after the DOM changed (author name moved out of `aria-hidden` spans; timestamp span lost its `aria-hidden` attribute). They may drift again.

**First action on restart:** sanity run, confirm extraction lands in the DB with real author names and timestamps.

```bash
HEADLESS=false MAX_POSTS=5 python scraper.py
```

- `browser_profile/` holds the saved session — no login needed unless the session has expired.
- If the session has expired, run `python save_session.py` first (opens a headed browser, log in manually, close when on the feed).
- If `author_name` comes back empty or shows "• 3rd+" / "• 2nd" → selector drift. Grab the outerHTML of `.entity-result__content-actor` from DevTools and update `extract_author` in `scraper.py`.
- If `post_timestamp` is empty → timestamp selector drifted. Check `p.t-black--light > span` structure in DevTools and update `extract_timestamp`.

## Re-entry sequence

### Step 1 — Verify it still runs (always do this first)
- Headful, 5 posts, confirm text/author/URL/timestamp populate in SQLite.
- Fix selectors if drifted. (Bonus: this reloads the whole codebase into my head.)

### Step 2 — Next build: Phase 4 (Containerisation)

GUI is done (Phase 3 ✅). The next step is Docker + GCP (Phases 4–7):
- Dockerfile: `python:3.11-slim`, `playwright install-deps chromium`, `HEADLESS=true` default
- `.dockerignore`: exclude `.env`, `*.db`, `browser_profile/`, `__pycache__`, `.git`
- Build and test locally: `docker build -t likarchive . && docker run --env-file .env likarchive`
- GCP infra: dedicated SA, Secret Manager for creds, GCS for SQLite persistence (`db_sync.py`)
- Cloud Run deploy + Cloud Scheduler daily trigger

*Why this order:* "running headless on Cloud Run, daily schedule, secrets managed properly" is the sentence that anchors a Staff/Principal conversation.

## Roadmap (from CLAUDE.md, condensed)

- **Phase 1** — Local core ✅
- **Phase 2** — Test sync (50-post cap) ✅
- **Phase 3** — Flask GUI (cards, filters, FTS) ✅
- **Phase 4** — Containerise (Dockerfile, `.dockerignore`, build + local test) ← **next**
- **Phase 5** — GCP infra (SA, Secret Manager, GCS persistence, `db_sync.py`) ⬜
- **Phase 6** — Cloud Run deploy (scraper + UI services) + full-archive staging test ⬜
- **Phase 7** — Cloud Scheduler (`0 7 * * *`, OIDC, `likarchive-sa`) ⬜
- **Phase 8** — BigQuery sink (`bq_sink.py` → `likarchive.liked_posts`) + LookML model ⬜ (optional)

## Local quickstart (reminder)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in LINKEDIN_EMAIL / LINKEDIN_PASSWORD
HEADLESS=false MAX_POSTS=5 python scraper.py
```

## Session log (fill in as I go)

- [ ] Step 1 verify run — selectors OK? (date: ___)
- [ ] Chosen order: A / B
- [ ] Next concrete task: ___
