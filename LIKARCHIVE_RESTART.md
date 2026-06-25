# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, and stores extracted posts in SQLite. Daily auto-sync via scheduler. GCP Cloud Run deployment planned for a later phase. End goal for *me*: a shipped, owned, end-to-end thing I'd actually claim — cloud-native, scheduled, secrets done properly.

## Current state (where I left it)

**Built and working locally:**

- `scraper.py` — Playwright login, saved-posts navigation, infinite-scroll pagination, extracts post text / author / URL / timestamp
- `db.py` — SQLite with MD5 hash dedup (upsert if hash differs, skip if identical); FTS5 + tags schema
- `query.py` — CLI browser with FTS5 search
- `tagger.py` — auto-tagging via Claude Haiku (`claude-haiku-4-5-20251001`)
- `scheduler.py` — daily sync
- `CLAUDE.md` — merged instructions + 8-phase roadmap
- Test dataset capped at 50 posts locally

**Stopped at:** end of the local core. Next planned build was Phase 3 (Flask GUI), then the cloud path (Phases 4–8).

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

### Step 2 — Pick ONE build to push next

Two valid orders depending on what I'm optimising for:

**Order A — job-search-optimal (recommended): ship to cloud first**
The engineering *story* is a deployed, scheduled, cloud-native pipeline. Do Phases 4–6 next:
- Containerise (Dockerfile, `playwright install chromium`, `HEADLESS=true` default)
- GCP infra: dedicated SA, Secret Manager for creds, GCS as SQLite persistence
- Cloud Run deploy (no public URL, scheduler-triggered, 2Gi mem, 900s timeout)
- Cloud Scheduler daily trigger with OIDC
Then do the GUI as polish.
*Why:* "running headless on Cloud Run, daily schedule, secrets managed properly" is the sentence that anchors a Staff/Principal conversation. UI is nice-to-have.

**Order B — motivation-optimal: GUI first (Phase 3)**
Flask GUI — card layout, tag/author/date filters, FTS search, manual tagging.
*Why:* turns it from "a script" into "a thing I can see," which may be what keeps momentum alive tonight. Momentum beats optimality if the alternative is stalling again.

## Roadmap (from CLAUDE.md, condensed)

- **Phase 1** — Local core ✅
- **Phase 2** — Test sync (50-post cap) ✅
- **Phase 3** — Flask GUI (cards, filters, FTS, manual tagging) ⬜
- **Phase 4** — Containerise + GCP infra (SA, Secret Manager, GCS persistence) ⬜
- **Phase 5** — DB persistence helper (`db_sync.py`: download at start, upload in `finally`) ⬜
- **Phase 6** — Cloud Run deploy (scraper service + UI service) + full-archive staging test ⬜
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
