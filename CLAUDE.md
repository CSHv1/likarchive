# Likarchive — Claude Code Instructions

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the user's saved posts page (`/my-items/saved-posts/`), paginates through the full list via infinite scroll, and stores extracted posts in a local SQLite database. Daily auto-sync via a scheduler. GCP Cloud Run deployment planned for a later phase.

On session start, also read LIKARCHIVE_RESTART.md for current state and next steps.

## File structure

```
scraper.py           — Playwright scroll loop, DOM extraction, main entry point
save_session.py      — One-time manual login; saves browser_profile/ (debugging) + auth_state.json (runtime auth)
db.py                — SQLite schema, upsert logic, sync logging, FTS5, tag helpers
db_sync.py           — GCS download_db()/upload_db() — no-op locally, active only when K_SERVICE is set (Phase 5)
cloud_auth.py        — Secret Manager fetch_auth_state() — no-op locally, active only when K_SERVICE is set (Phase 5)
scheduler.py         — Daily cron wrapper around scraper.run_sync()
query.py             — CLI browser/search: recent posts, FTS search, author filter
tagger.py            — Claude API auto-tagger (claude-haiku-4-5-20251001); tag_posts() called automatically from scraper.py after a clean scrape
app.py               — Flask web UI — search, filter, browse saved posts (Phase 3)
templates/index.html — Single-page vanilla JS frontend served by app.py
requirements.txt
.env.example         — Copy to .env and fill in credentials
CLAUDE.md            — This file
NOTES.md             — Current state, known issues, next steps
```

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env          # fill in ANTHROPIC_API_KEY (and DB_PATH if needed)
python save_session.py        # one-time: log in manually, saves browser_profile/ + auth_state.json
python scraper.py             # one-off sync (skip save_session.py if auth_state.json exists)
python scheduler.py           # daily auto-sync (runs immediately, then 08:00 daily)
```

## Environment variables (.env)

| Variable            | Default             | Description                                                                          |
| ------------------- | ------------------- | ------------------------------------------------------------------------------------ |
| `LINKEDIN_EMAIL`    | —                   | LinkedIn login email — stored for reference; not read by code (login is manual)      |
| `LINKEDIN_PASSWORD` | —                   | LinkedIn password — stored for reference; not read by code (login is manual)         |
| `DB_PATH`           | `linkedin_likes.db` | SQLite file path                                                                     |
| `HEADLESS`          | `false`             | Set `true` for headless Chromium (default headful for debugging)                     |
| `SCROLL_PAUSE_MS`   | `2000`              | Pause between scrolls in ms                                                          |
| `MAX_POSTS`         | `0`                 | Cap per sync run — 0 = unlimited                                                     |
| `BROWSER_PROFILE`   | `browser_profile`   | Playwright persistent profile dir — headed local debugging only, not read at runtime |
| `STATE_PATH`        | `auth_state.json`   | Portable Playwright `storage_state()` export — what `scraper.py` actually loads      |
| `ANTHROPIC_API_KEY` | —                   | Claude API key — required for `tagger.py`'s `tag_posts()`, now called automatically from `scraper.py`'s `run_sync()` after a clean scrape (not on error/timeout). Locally from `.env`; in Cloud Run, mounted from the `anthropic-api-key` Secret Manager secret via `--set-secrets` (native Cloud Run mechanism — no custom fetch code needed, unlike `auth_state.json`) |
| `K_SERVICE`         | —                   | Set automatically by Cloud Run — presence toggles the `db_sync.py`/`cloud_auth.py` calls in `run_sync()`. Never set locally. |
| `GCP_PROJECT`       | —                   | GCP project ID — required by `cloud_auth.py` when `K_SERVICE` is set (Phase 5)       |
| `GCS_BUCKET`        | `likarchive-db`     | GCS bucket for SQLite persistence (Phase 5)                                          |
| `AUTH_STATE_SECRET` | `linkedin-auth-state` | Secret Manager secret name holding `auth_state.json` (Phase 5)                     |

## Database schema

**liked_posts**

- `post_url` TEXT UNIQUE — primary key, direct LinkedIn post URL (activity URN)
- `author_name` TEXT
- `author_profile` TEXT — URL to author's LinkedIn profile
- `post_text` TEXT — full post body
- `post_timestamp` TEXT — relative timestamp as scraped (e.g. "3w", "2d")
- `post_date` TEXT — approximate ISO date reconstructed from `post_timestamp` + `scraped_at`; used for date-range filtering in the GUI
- `text_hash` TEXT — MD5 of post_text, used for change detection on upsert
- `scraped_at` TEXT — ISO timestamp of first insert
- `last_updated` TEXT — ISO timestamp of last overwrite (hash changed)

**sync_log**

- One row per sync run: start/end time, posts seen/new/updated/skipped, status, error

**posts_fts** (FTS5 virtual table, content-backed on `liked_posts`)

- Columns: `post_url` (UNINDEXED), `author_name`, `post_text`
- Rebuilt automatically via `INSERT INTO posts_fts(posts_fts) VALUES('rebuild')` in `init_db()`
- Kept in sync on every upsert — delete+reinsert on update, insert on new row

**tags**

- `id` INTEGER PRIMARY KEY, `name` TEXT UNIQUE — normalised tag vocabulary

**post_tags**

- `post_url` → `liked_posts.post_url`, `tag_id` → `tags.id` — many-to-many join table

## Key design decisions

- **Auth**: manual login once via `save_session.py`, which writes two things — a persistent browser profile (`browser_profile/`, for headed local debugging) and a portable Playwright `storage_state()` JSON export (`auth_state.json`). `scraper.py` loads `auth_state.json` at runtime via `STATE_PATH` — no credentials are read by any code. The persistent profile is NOT used at runtime: Chromium encrypts its cookies with an OS-level key (macOS Keychain / Linux libsecret), so a profile created on macOS does not decrypt inside a Linux container (confirmed via Docker testing — LinkedIn silently redirected to the login page). `storage_state()` sidesteps this because Playwright manages the encoding itself rather than delegating to the OS, which is why it's the artifact that travels into Docker/Cloud Run. Re-run `save_session.py` if the session expires. Credentials are stored in `.env` for personal reference only.
- **Session-expiry visibility**: when `auth_state.json` expires, LinkedIn redirects `/my-items/saved-posts/` to `/login`, `/authwall`, or `/checkpoint`. `scrape_saves()` in `scraper.py` checks `page.url` against `AUTH_FAILURE_MARKERS` right after navigation and raises immediately if matched — without this check, a dead session silently produces `posts_seen=0` and a `status='success'` sync_log row, indistinguishable from "no new saved posts today." The raised error propagates to `finish_sync_log()` as `status='error'` with a message telling you to re-run `save_session.py` (and, in Cloud Run, push a new Secret Manager version). `app.py` exposes `/api/sync_status` (latest `sync_log` row), and `templates/index.html` shows a red banner with that message on page load if the last sync errored. **What's still manual**: re-authenticating itself (2FA/CAPTCHA means it can't be scripted); this only gets you *notified* quickly. For Cloud Run, the daily Cloud Scheduler job failing is also visible in Cloud Logging/Cloud Scheduler's own run history — a Cloud Monitoring alert policy on repeated Cloud Run failures would close the last gap (push notification instead of having to check the GUI or logs); not yet built, candidate for Phase 7.
- **Deduplication**: `post_url` is the primary key. On each sync, post text is MD5-hashed and compared — insert if new, overwrite if hash differs, skip if identical.
- **Scroll**: height-based stale detection — stops after 4 consecutive scrolls with no DOM height change.
- **Python version**: use `Optional[str]` / `Optional[dict]` (typing module) not `str | None` — target is Python 3.9 compatibility on Mac.

## Confirmed working selectors (as of 2026-06-25)

Selectors were updated after LinkedIn changed their DOM structure. Author name no longer uses `aria-hidden`; timestamp span is now a plain direct child of the paragraph. Company page posts use `/company/` in the profile URL instead of `/in/`.

| Target         | Selector                                                                                                    |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| Card container | `[data-chameleon-result-urn*="urn:li:activity"]`                                                            |
| Post URL       | `a[href*="/feed/update/"][data-test-app-aware-link]`                                                        |
| Author name    | `span[dir="ltr"]` inside `.entity-result__content-actor a[href*="/in/"], a[href*="/company/"]`              |
| Author profile | `.entity-result__content-actor a[href*="/in/"], .entity-result__content-actor a[href*="/company/"]`         |
| Post text      | `p.entity-result__content-summary--3-lines`                                                                 |
| Timestamp      | `p.t-black--light.t-12 > span` (direct child; falls back to `p.t-black--light > span`)                     |

## Querying the database

```bash
# Recent posts
sqlite3 linkedin_likes.db "SELECT author_name, post_timestamp, substr(post_text,1,80) FROM liked_posts ORDER BY scraped_at DESC LIMIT 10;"

# Sync history
sqlite3 -column -header linkedin_likes.db "SELECT id, started_at, status, posts_seen, posts_new FROM sync_log ORDER BY id DESC LIMIT 5;"

# FTS search
sqlite3 linkedin_likes.db "SELECT lp.author_name, substr(lp.post_text,1,100) FROM posts_fts JOIN liked_posts lp ON posts_fts.rowid=lp.id WHERE posts_fts MATCH 'leadership' ORDER BY rank LIMIT 10;"

# Tags and post counts
sqlite3 -column -header linkedin_likes.db "SELECT t.name, COUNT(*) n FROM tags t JOIN post_tags pt ON t.id=pt.tag_id GROUP BY t.name ORDER BY n DESC;"

# Posts with all their tags
sqlite3 -column -header linkedin_likes.db "SELECT lp.author_name, substr(lp.post_text,1,60), GROUP_CONCAT(t.name,', ') tags FROM liked_posts lp JOIN post_tags pt ON lp.post_url=pt.post_url JOIN tags t ON pt.tag_id=t.id GROUP BY lp.post_url LIMIT 10;"
```

Use `query.py` for interactive browsing — it wraps the FTS and author filter queries with formatted output.

## Roadmap

### Phase 1 — Local core (complete)

- [x] Fix DOM selectors for `/my-items/saved-posts/`
- [x] Remove debug `page_dump.html` write — selectors confirmed
- [x] Rename `scrape_likes` → `scrape_saves` for clarity
- [x] Simple read UI — `query.py` CLI (browse, FTS search, author filter)
- [x] Full-text search — SQLite FTS5 virtual table (`posts_fts`)
- [x] Claude API integration — `tagger.py` auto-tags posts via `claude-haiku-4-5-20251001`

### Phase 2 — Local test sync (complete)

- [x] Set `MAX_POSTS=100` in `.env` and run `python scraper.py`
- [x] Full archive (`MAX_POSTS=0`) deferred to Phase 6 staging on Cloud Run
- [x] Verify row count via `query.py` and spot-check a few posts after completion

### Phase 3 — GUI (complete)

- [x] Build `app.py` — Flask web UI serving the local SQLite DB
  - Single-page interface, no auth needed (local only at this stage)
  - Stack: Flask backend + vanilla JS frontend (no build step, keep it simple)
- [x] Post list view
  - Paginated card layout — author name, timestamp, post text truncated to ~3 lines, tags
  - Each card links out to the original LinkedIn post (direct URL)
  - Click to expand full post text inline; default sort by most-recent LinkedIn post date
- [x] Filters (sidebar or top bar)
  - Filter by tag — multi-select, populated from `tags` table via `tagger.py`
  - Filter by author name — dropdown populated from distinct `author_name` values
  - Filter by date range — "Month Year" dropdowns (e.g. "Feb 2026") against `post_date`; newest months first
  - Filters combine with AND logic; reset button to clear all
- [x] Full-text search
  - Search box hits the existing FTS5 `posts_fts` virtual table (300ms debounce)
  - Results ranked by relevance (SQLite FTS5 `rank` column)
  - Compatible with active filters — search within current filtered set
- [x] Run and test locally: `python app.py` → http://localhost:5000

### Phase 4 — Containerisation (complete)

- [x] Write `Dockerfile`
  - Base image: `mcr.microsoft.com/playwright/python:v1.44.0-jammy` (deviation from originally planned `python:3.11-slim` — ships Python 3.11 + Playwright + Chromium prebuilt on Ubuntu Jammy, `playwright install-deps` fails on Debian Trixie)
  - `HEADLESS=true` default env var — no display in Cloud Run
  - Scraper entrypoint (default `CMD`): `python scraper.py`
  - GUI: override `CMD` with `gunicorn --bind 0.0.0.0:8080 app:app` at `docker run` / Cloud Run
- [x] Write `.dockerignore` — excludes `.env`, `*.db`, `browser_profile/`, `auth_state.json`, `__pycache__`, `.git`, docs
- [x] Build and test locally
  - `docker build -t likarchive .` — succeeds
  - GUI container (`gunicorn` + mounted `/data` volume) verified end-to-end: real posts/tags/pagination served correctly at `localhost:8080`
  - Scraper container: initial attempt with the persistent `browser_profile/` (copied in from macOS) failed — LinkedIn redirected to login, because Chromium's OS-level cookie encryption (macOS Keychain) doesn't decrypt on Linux. Fixed by switching runtime auth to Playwright `storage_state()` (`auth_state.json`), which Playwright encodes itself rather than delegating to the OS. See `save_session.py` / `scraper.py` / `STATE_PATH`.
  - Re-verified with `auth_state.json`: scraper container reached the real saved-posts page, extracted real cards, wrote to the mounted DB (`seen=3, new=0, skipped=3` on a `MAX_POSTS=3` capped run against already-archived posts). Confirmed working end-to-end.

### Phase 5 — GCP infrastructure (complete)

**Note — plan updated from the original roadmap:** `LINKEDIN_EMAIL`/`LINKEDIN_PASSWORD` are not read by any code (login is manual only via `save_session.py`), so they don't need a Secret Manager entry — storing them there would protect nothing that's actually load-bearing. The artifact that actually needs protecting is `auth_state.json` — a live LinkedIn session (Playwright `storage_state()` export). Treat it as a bearer token, not a password.

**Project**: reusing existing GCP project `csh-data-engineering-on-gcp` (not a fresh dedicated project — a deliberate choice to avoid extra setup). Region: `europe-west2` throughout, per the original roadmap.

- [x] `db_sync.py` — `download_db()`/`upload_db()` via `google-cloud-storage`, wired into `run_sync()` in `scraper.py` (gated on `K_SERVICE` being set — no-op locally)
- [x] `cloud_auth.py` — `fetch_auth_state()` via `google-cloud-secret-manager`, wired into `run_sync()` the same way
- [x] GCP project setup
  - APIs enabled: `run.googleapis.com`, `cloudscheduler.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `storage.googleapis.com`
  - Service account created: `likarchive-sa@csh-data-engineering-on-gcp.iam.gserviceaccount.com`
  - **Billing gotcha hit during setup**: the project's linked billing account was closed (`OPEN: False`) — had to be reactivated in the console (payment method re-verification) before any API could be enabled. After reactivation, `gcloud billing projects link` then failed with `FAILED_PRECONDITION: Cloud billing quota exceeded` — this was a red herring: reactivating the account had already auto-restored its pre-existing link to this project (`gcloud billing projects describe` confirmed `billingEnabled: true`), so the "link" call was attempting a redundant new link. If this ever recurs (e.g. spinning up a genuinely new project), check `gcloud billing projects describe csh-data-engineering-on-gcp` before assuming the quota error means real work is needed.
- [x] Secret Manager
  - Secret `linkedin-auth-state` created, version 1 = the working `auth_state.json` as of 2026-07-23
  - `likarchive-sa` granted `roles/secretmanager.secretAccessor` scoped to this secret only
  - **Re-auth procedure (manual, no way around this):** when the LinkedIn session in `auth_state.json` expires, run `save_session.py` locally again, then push the new file as a fresh secret version: `gcloud secrets versions add linkedin-auth-state --data-file=auth_state.json`. Cloud Run has no display, so this step can't happen in the cloud — it always requires a local interactive login.
- [x] Cloud Storage — persistent SQLite volume
  - Bucket `gs://likarchive-db` created in `europe-west2`, uniform bucket-level access
  - `likarchive-sa` granted `roles/storage.objectAdmin` scoped to this bucket only
  - `db_sync.py` already implements download-at-start / upload-at-end
  - **Note**: simplest persistence approach; alternative is Cloud SQL (Postgres) but adds cost/complexity for a personal tool

### Phase 6 — Cloud Run deployment + staging (complete)

Live resources (region `europe-west2`, project `csh-data-engineering-on-gcp`):
- Image: `europe-west2-docker.pkg.dev/csh-data-engineering-on-gcp/likarchive/likarchive:latest`
- Scraper: Cloud Run **Job** `likarchive-scraper` — trigger with `gcloud run jobs execute likarchive-scraper --region europe-west2`
- GUI: Cloud Run **Service** `likarchive-ui` — `https://likarchive-ui-588295099118.europe-west2.run.app`

**Four real bugs surfaced during this deploy, all fixed — worth reading before touching this again:**

1. **Image architecture**: built on Apple Silicon, images default to `arm64`; Cloud Run requires `linux/amd64`. Fails as `exec format error` at container start, not at build or push time. Always build with `docker build --platform linux/amd64 ...` for anything headed to Cloud Run.
2. **Dockerfile `COPY` drift**: the explicit file list (`COPY scraper.py db.py ... ./`) wasn't updated when `db_sync.py`/`cloud_auth.py` were added in Phase 5 — `ModuleNotFoundError` at runtime, invisible at build time since nothing checks the copied set against what the code imports. Fixed; watch for this again if new top-level modules are added.
3. **Cloud Run Service vs. Job**: `scraper.py` is a one-shot script with no HTTP listener. `gcloud run deploy` (Services) requires the container to bind `$PORT` and pass a startup TCP probe — the scraper can never satisfy that, no matter the timeout. It has to be a Cloud Run **Job** (`gcloud run jobs create`/`execute`), which runs to completion and exits normally. The GUI (gunicorn, binds a port) is correctly a Service. Corollary: `K_SERVICE` is a Services-only env var; Jobs set `CLOUD_RUN_JOB` instead — `scraper.py`'s cloud-detection now checks both.
4. **`/data` doesn't exist in Cloud Run**: `DB_PATH`/`STATE_PATH` defaulted to `/data/...` per the Dockerfile, which assumes a bind-mounted volume (`docker run -v host:/data`) — fine locally, but Cloud Run has no such mount, so `/data` is simply a missing directory and `sqlite3.connect()`/file writes fail with `unable to open database file`. Both the Job and the Service now explicitly override `DB_PATH=/tmp/linkedin_likes.db` (Job also overrides `STATE_PATH=/tmp/auth_state.json`) via `--set-env-vars`/`--update-env-vars` — `/tmp` always exists and is writable in Cloud Run. The Dockerfile's own `/data` defaults are left as-is; they're still correct for local `docker run` testing with an explicit volume.

- [x] Push image to Artifact Registry — repo `likarchive` created, image pushed
- [x] Deploy scraper as a Cloud Run **Job** (not a Service — see above): `likarchive-sa`, 2Gi memory, 900s task-timeout, `GCP_PROJECT`/`GCS_BUCKET`/`AUTH_STATE_SECRET`/`DB_PATH`/`STATE_PATH` env vars
- [x] Deploy GUI as a Cloud Run Service: `likarchive-sa`, 512Mi memory, public (`--allow-unauthenticated`), `GCP_PROJECT`/`GCS_BUCKET`/`DB_PATH` env vars, `--command gunicorn --args="--bind","0.0.0.0:8080","app:app"`
  - `--min-instances=1` not yet set — GUI will cold-start on the first request after idling; revisit if that latency matters
- [x] Capped staging test (not the full `MAX_POSTS=0` archive — deliberately small first, per established practice for anything touching the live LinkedIn account): `gcloud run jobs execute likarchive-scraper --update-env-vars=MAX_POSTS=5 --wait` — 5 real posts scraped, uploaded to `gs://likarchive-db`, confirmed served correctly by the GUI after a forced revision refresh
- [~] Full-archive sync (`MAX_POSTS=0`) — **deferred at 483 posts** (2026-08-05). Grew steadily across runs (5 → 285 → 483) via checkpointing, but the next three consecutive full-hour runs all landed on **exactly 0 new posts** each time — confirmed via logs (`[NEW` count = 0, `[SKIPPED` count in the hundreds each run). This is not a resource problem: bumped memory 2Gi→4Gi (fixed an earlier Chromium crash, didn't move this number) and CPU 1→2 vCPU (also no effect) with zero change to the plateau. Most likely a LinkedIn-side soft limit on infinite-scroll depth within one continuous session — `document.body.scrollHeight` apparently still fluctuates enough (ads/sidebar/other page elements) to keep resetting the stale-scroll counter without the post *list* actually advancing, so the loop burns the full hour instead of correctly detecting "nothing new is coming." Needs diagnostic logging (actual DOM card count per scroll, not just `scrollHeight`) to characterize precisely — deferred, tracked as a todo, not blocking Phase 7 (daily incremental syncs never scroll anywhere near this deep, so they won't hit it). 483 tagged, real posts is a solid working archive for now.

**Full-archive backfill surfaced four more real bugs, all fixed — this is the reliability hardening pass, separate from the four deploy bugs above:**

5. **A single run can't necessarily finish the whole backlog.** First attempt hit the 900s task-timeout partway through; bumped to 3600s (1h, Cloud Run Jobs support up to 24h). Even at 1h, a full backfill on a large backlog may take multiple runs — see the checkpointing fix below for why that's fine.
6. **Cloud Run's task-timeout is a hard kill, not a catchable exception** — `finally` blocks never run, so the original design (upload the DB once, at the very end of `run_sync()`) meant a run that timed out lost **100% of its progress**, every time, confirmed when a run that visibly scraped 200+ posts left the bucket completely unchanged. Fixed: `scrape_saves()` now takes an optional `checkpoint` callback (wired to `upload_db()` when in Cloud Run) and calls it after every scroll-batch commit, not just at the end. This also means a full backfill no longer needs one giant successful run — each run, even one that fails partway, permanently banks its progress, so just re-running enough times converges on the full backlog.
7. **Counts silently zeroed out on any mid-scrape exception.** `run_sync()` assigned `counts = scrape_saves(...)`; if the function raised before returning, the outer `counts` was never updated, so `sync_log` recorded `error, posts_seen=0` even when hundreds of posts had genuinely been saved. Fixed: `scrape_saves()` now takes `counts` as a parameter and mutates it in place, so partial progress is visible regardless of how the call ends.
8. **Failures never made the process exit non-zero.** `run_sync()` caught every exception, logged it, and returned normally — Cloud Run saw exit code 0 (success) even on a real failure, which would have silently defeated the Phase 7 Monitoring alert (built on execution failures) before it's even built. Fixed: the exception handler now re-raises after cleanup, so an uncaught exception produces Python's normal non-zero exit in Cloud Run, while `scheduler.py`'s `job()` (which already catches `Exception` around `run_sync()` for its own daily-retry loop) is unaffected.
- Also made per-card extraction resilient: a single stale DOM handle (LinkedIn virtualizes the list on long scrolls) no longer aborts the whole run — one bad card is now skipped and logged, not fatal.
- Observed failure modes while converging on the full backlog, for reference: task-timeout (fixed by raising the limit), a Playwright `ElementHandle` timeout on a stale card (fixed by per-card try/except), a Chromium `Target crashed` (fixed by bumping Job memory 2Gi → 4Gi — classic renderer OOM signature on a very long-lived page), and one Cloud Run platform-level `Internal error` with exit code 0 (transient infra hiccup, not our code — resolved by simply retrying).

### Phase 7 — Cloud Scheduler (mostly complete)

**Plan corrected from the original roadmap**: this assumed the scraper was a Cloud Run Service reachable by a plain HTTP POST to its URL. Since Phase 6 established it has to be a Cloud Run **Job** instead (see Phase 6 notes), there is no service URL to POST to — Cloud Scheduler has to call the Cloud Run Admin API's job-execution endpoint instead.

- [x] Grant `likarchive-sa` `roles/run.invoker` on the `likarchive-scraper` Job specifically (separate from its bucket/secret grants — needed for the Admin API `:run` call)
- [x] Create daily sync job — `likarchive-daily-sync`, `0 7 * * *` UTC, targets `POST https://europe-west2-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/csh-data-engineering-on-gcp/jobs/likarchive-scraper:run` via OAuth token (not OIDC — this is a direct Admin API call, not a Cloud Run Service invocation) as `likarchive-sa`
- [x] Test trigger manually: `gcloud scheduler jobs run likarchive-daily-sync --location europe-west2` — confirmed working end-to-end; the resulting execution's `RUN BY` field showed `likarchive-sa@...`, not a personal account, proving the service-account auth chain works
- [ ] Verify via Cloud Run logs that a *real scheduled* (not manually forced) run completes and uploads — will naturally confirm at the next 07:00 UTC firing
- [ ] Cloud Monitoring alert policy on `likarchive-scraper` execution failures — pushes a notification (email at minimum) instead of relying on noticing the GUI banner or checking logs manually. Closes the last gap in session-expiry visibility (see Key design decisions); the scraper already fails loudly and distinctly on auth expiry, this just makes that failure page someone instead of sitting in Cloud Logging

### Phase 8 — BigQuery sink (optional, for Looker)

- [ ] Add `bq_sink.py` — reads from SQLite, pushes new/updated rows to BigQuery
  - Table: `likarchive.liked_posts` — mirror of SQLite schema
  - Use `scraped_at` / `last_updated` to identify rows to push since last BQ write
  - Use `google-cloud-bigquery` client with `load_table_from_dataframe` or streaming inserts
- [ ] Call `bq_sink.push()` at the end of `run_sync()` after DB upload
- [ ] Create LookML model on top of `likarchive.liked_posts` for exploration in Looker
