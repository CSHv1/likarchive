# Likarchive — Claude Code Instructions

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the user's saved posts page (`/my-items/saved-posts/`), paginates through the full list via infinite scroll, and stores extracted posts in a local SQLite database. Daily auto-sync via a scheduler. GCP Cloud Run deployment planned for a later phase.

On session start, also read LIKARCHIVE_RESTART.md for current state and next steps.

## File structure

```
scraper.py           — Playwright scroll loop, DOM extraction, main entry point
save_session.py      — One-time manual login; saves browser profile to browser_profile/
db.py                — SQLite schema, upsert logic, sync logging, FTS5, tag helpers
scheduler.py         — Daily cron wrapper around scraper.run_sync()
query.py             — CLI browser/search: recent posts, FTS search, author filter
tagger.py            — Claude API auto-tagger (claude-haiku-4-5-20251001)
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
python save_session.py        # one-time: log in manually, saves browser_profile/
python scraper.py             # one-off sync (skip save_session.py if profile exists)
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
| `BROWSER_PROFILE`   | `browser_profile`   | Playwright persistent profile dir — run `save_session.py` first                      |
| `ANTHROPIC_API_KEY` | —                   | Claude API key (required for `tagger.py`)                                            |

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

- **Auth**: persistent browser profile via `save_session.py` (manual login once, profile saved to `browser_profile/`). `scraper.py` loads the profile at runtime — no credentials are read by any code. Re-run `save_session.py` if the session expires. Credentials are stored in `.env` for personal reference only.
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

### Phase 4 — Containerisation (next immediate step)

- [ ] Write `Dockerfile`
  - Base image: `python:3.11-slim`
  - Install system deps for Playwright: `libnss3`, `libatk1.0-0`, `libgbm1` etc. (use `playwright install-deps chromium`)
  - Copy project files, install `requirements.txt`, run `playwright install chromium`
  - Set `HEADLESS=true` as default env var — no display in Cloud Run
  - Scraper entrypoint: `python scraper.py` (single sync run — Cloud Scheduler handles cadence)
  - GUI entrypoint: separate Cloud Run service or `CMD` flag, serving `app.py` via gunicorn
- [ ] Write `.dockerignore`
  - Exclude: `.env`, `*.db`, `*.html`, `*.png`, `__pycache__`, `.git`
- [ ] Build and test locally
  - `docker build -t likarchive .`
  - `docker run --env-file .env likarchive`
  - Confirm posts land in DB and GUI is reachable at `localhost:8080`

### Phase 5 — GCP infrastructure

- [ ] GCP project setup
  - Enable APIs: Cloud Run, Cloud Scheduler, Secret Manager, Artifact Registry, Cloud Storage
  - Create a dedicated service account `likarchive-sa` with minimum required roles
- [ ] Secret Manager — store credentials, never pass as plain env vars in Cloud Run
  - `LINKEDIN_EMAIL` → `projects/{id}/secrets/linkedin-email`
  - `LINKEDIN_PASSWORD` → `projects/{id}/secrets/linkedin-password`
  - Grant `likarchive-sa` the `secretmanager.secretAccessor` role
  - Update `scraper.py` to pull from Secret Manager when running in GCP (detect via `K_SERVICE` env var being set)
- [ ] Cloud Storage — persistent SQLite volume
  - Create a GCS bucket: `likarchive-db`
  - On container start: download `linkedin_likes.db` from GCS if it exists, fall back to fresh init
  - On container end: upload updated `linkedin_likes.db` back to GCS
  - Add `db_sync.py` helper with `download_db()` and `upload_db()` functions using `google-cloud-storage`
  - Add these calls to `run_sync()` in `scraper.py` — download at start, upload in `finally` block
  - **Note**: simplest persistence approach; alternative is Cloud SQL (Postgres) but adds cost/complexity for a personal tool

### Phase 6 — Cloud Run deployment + staging

- [ ] Push image to Artifact Registry
  - `gcloud artifacts repositories create likarchive --repository-format=docker --location=europe-west2`
  - Tag and push: `docker tag likarchive europe-west2-docker.pkg.dev/{project}/likarchive/likarchive:latest`
- [ ] Deploy scraper service (no public URL — scheduler-triggered only)
  - `gcloud run deploy likarchive-scraper --image ... --region europe-west2 --service-account likarchive-sa --no-allow-unauthenticated --memory 2Gi --timeout 900`
  - Memory: Playwright + Chromium needs at least 1Gi, 2Gi is safer
  - Timeout: 900s (15 min) — give the scroll loop room to complete
  - Mount secrets: `--set-secrets LINKEDIN_EMAIL=linkedin-email:latest,LINKEDIN_PASSWORD=linkedin-password:latest`
- [ ] Deploy GUI service (public URL)
  - `gcloud run deploy likarchive-ui --image ... --region europe-west2 --service-account likarchive-sa --allow-unauthenticated --memory 512Mi`
  - GUI reads DB from GCS on startup — download on each container cold start
  - Consider `--min-instances=1` to avoid cold start latency on the UI
- [ ] Staging test — run full archive sync: set `MAX_POSTS=0`, trigger scraper manually
  - Verify full post count in DB via Cloud Logging output
  - Spot-check GUI filtering and search against full dataset

### Phase 7 — Cloud Scheduler

- [ ] Create daily sync job
  - Frequency: `0 7 * * *` (07:00 UTC daily)
  - Target: HTTP POST to the `likarchive-scraper` Cloud Run service URL
  - Auth: OIDC token with `likarchive-sa`
  - `gcloud scheduler jobs create http likarchive-daily-sync --schedule "0 7 * * *" --uri {cloud-run-url} --http-method POST --oidc-service-account-email likarchive-sa@{project}.iam.gserviceaccount.com --location europe-west2`
- [ ] Test trigger manually: `gcloud scheduler jobs run likarchive-daily-sync --location europe-west2`
- [ ] Verify via Cloud Run logs that sync completed and DB was uploaded back to GCS

### Phase 8 — BigQuery sink (optional, for Looker)

- [ ] Add `bq_sink.py` — reads from SQLite, pushes new/updated rows to BigQuery
  - Table: `likarchive.liked_posts` — mirror of SQLite schema
  - Use `scraped_at` / `last_updated` to identify rows to push since last BQ write
  - Use `google-cloud-bigquery` client with `load_table_from_dataframe` or streaming inserts
- [ ] Call `bq_sink.push()` at the end of `run_sync()` after DB upload
- [ ] Create LookML model on top of `likarchive.liked_posts` for exploration in Looker
