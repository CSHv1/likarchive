# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, auto-tags posts via Claude Haiku, and stores everything in SQLite. Runs on Cloud Run (Job for the scraper, Service for the GUI), triggered daily by Cloud Scheduler, with Cloud Monitoring alerting on failures. End goal: a shipped, owned, end-to-end thing — cloud-native, scheduled, secrets done properly. **As of 2026-08-06, that goal is achieved** — all 7 planned phases are complete. `post_mvp` (merged to `main` 2026-08-12) then fixed the backfill-plateau/tagging bug below and added absolute dates + a calendar date-range picker to the GUI.

## Current state

**Live on GCP** (project `csh-data-engineering-on-gcp`, region `europe-west2`):
- Scraper: Cloud Run **Job** `likarchive-scraper` — `gcloud run jobs execute likarchive-scraper --region europe-west2`
- GUI: Cloud Run **Service** `likarchive-ui` — `https://likarchive-ui-588295099118.europe-west2.run.app`
- Storage: `gs://likarchive-db` (SQLite DB), Secret Manager (`linkedin-auth-state`, `anthropic-api-key`)
- Scheduler: `likarchive-daily-sync`, fires `0 7 * * *` UTC via the Cloud Run Admin API (not a service URL — the scraper is a Job, see below)
- Monitoring: alert policy on `likarchive-scraper` execution failures → email to `conradsamuelhall@gmail.com`
- **485 real posts archived and fully tagged**, confirmed served correctly by the GUI. Daily incremental runs now complete in ~1m15s (was previously hitting the 1h/2h task-timeout every time — see Known open items history below).

**Branch:** `post_mvp` merged into `main` 2026-08-12 (fast-forward). `main` is current and deployed. Public repo — `github.com/CSHv1/likarchive`.

## Known open items (not blocking, tracked as tasks)

1. **GUI still shares the scraper's 2GB Chromium-inclusive image**, despite never touching a browser. Deferred optimization — split into a lightweight image once there's a reason to prioritize it (cold-start latency, storage cost).

### Resolved (2026-08-12) — was open, keeping the history for context

**Full-archive backfill plateau + stalled tagging.** Runs had been plateauing at exactly 483 posts, hitting the task-timeout every single day rescrolling through already-known posts, and — undetected until this fix, because tagging had never actually completed a full run in Cloud Run — every checkpoint-tagging attempt was also silently 401ing due to a stray-quotes bug in the `anthropic-api-key` secret. Both fixed on `post_mvp`; full root-cause writeup in `CLAUDE.md`'s Phase 6 section. Confirmed in production: runs now finish in ~1m15s and new posts get tagged immediately.

## Key mechanisms worth knowing before touching this again

- **Auth**: `save_session.py` (interactive, local) → `auth_state.json` (portable Playwright `storage_state()`, NOT the OS-encrypted persistent profile) → Secret Manager `linkedin-auth-state` → `cloud_auth.py` fetches it at runtime. Re-run `save_session.py` + push a new secret version whenever the session expires (no way to automate this — 2FA/CAPTCHA needs a human).
- **Session-expiry detection**: `scraper.py` raises immediately if redirected to `/login`/`/authwall`/`/checkpoint`, instead of silently reporting a fake "success." Surfaces as a red banner in the GUI (`/api/sync_status`) and, in Cloud Run, as a real non-zero exit code that the Monitoring alert above will catch.
- **Checkpointing**: `scrape_saves()` uploads the DB to GCS after every scroll batch, not just at the end — Cloud Run's task-timeout is a hard kill that bypasses Python's `finally`, so without this, a timed-out run used to lose 100% of its progress.
- **Early-stop**: since `post_mvp`, `scrape_saves()` also stops once `MAX_CONSECUTIVE_SKIPPED` (default 40, env-configurable, `0` disables) already-known posts show up in a row — saved posts come back newest-first, so a long run of unchanged duplicates means it's reached previously-synced content. This is what actually fixed the backfill plateau; the old scrollHeight-staleness check alone often missed it (ad/sidebar noise kept the page height changing).
- **Tagging**: `tagger.py`'s `tag_posts()` runs on every `checkpoint()` call (since `post_mvp` — previously only after a fully clean scrape, which is what let tagging silently stop happening once runs started timing out) *and* again as a final catch-all after a clean finish. Only tags posts with no existing `post_tags` row — never touches existing classifications, so re-running it is always safe/idempotent.
- **Scraper = Cloud Run Job, GUI = Cloud Run Service** — not interchangeable. The scraper has no HTTP listener and can never pass a Service's port health-check; Jobs are the correct primitive for run-to-completion, non-HTTP work. Corollary: Jobs set `CLOUD_RUN_JOB`, not `K_SERVICE` — `scraper.py`'s cloud-detection checks both.
- **`/tmp`, not `/data`**, for `DB_PATH`/`STATE_PATH` in Cloud Run — `/data` was a local-Docker-only convention (bind-mounted volume) that doesn't exist in Cloud Run's filesystem.
- **Always `docker build --platform linux/amd64`** — this Mac is Apple Silicon; Cloud Run needs `amd64`, fails with a cryptic `exec format error` otherwise.

## Environment notes

- `gcloud` needs `CLOUDSDK_PYTHON` pointed at a supported Python (system default is 3.7) and its bin dir on `PATH` — neither is picked up automatically mid-session by Claude Code's Bash tool, so set both explicitly in-command:
  ```bash
  export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"
  export CLOUDSDK_PYTHON="/Users/conradhallpro/.pyenv/versions/3.10.11/bin/python3"
  ```
- Local testing of `db_sync.py`/`cloud_auth.py` needs `gcloud auth application-default login` (separate from the CLI's `gcloud auth login`).
- `git push` to the public repo: `git -c credential.helper=store push ...` avoids a hang on the system `osxkeychain` credential helper trying to show a GUI prompt with no display attached.
- **Public-repo caution**: scan for billing account IDs or credential material before committing anything documenting GCP setup — project IDs/service account emails/bucket/secret *names* are fine (IAM controls access, not obscurity), but billing account IDs and any actual key/token material are not.

## Local quickstart (reminder)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in ANTHROPIC_API_KEY (LINKEDIN_EMAIL/PASSWORD are reference-only, not read by code)
python save_session.py        # one-time: interactive login, writes auth_state.json
HEADLESS=false MAX_POSTS=5 python scraper.py
```

## Roadmap

- **Phase 1** — Local core ✅
- **Phase 2** — Test sync ✅
- **Phase 3** — Flask GUI ✅
- **Phase 4** — Containerise ✅
- **Phase 5** — GCP infra ✅
- **Phase 6** — Cloud Run deploy ✅ (backfill plateau hit at 483 posts, root-caused and fixed on `post_mvp`)
- **Phase 7** — Cloud Scheduler + Monitoring alert ✅
- **`post_mvp`** — plateau/tagging fix + absolute dates + calendar date-range picker ✅ (merged to `main` 2026-08-12)
- **Phase 8** — BigQuery sink (`bq_sink.py` → `likarchive.liked_posts`) + LookML model ⬜ (optional, not started)

## Session log

- [x] Phases 1–5 complete (2026-07-23)
- [x] Phase 6 complete — Cloud Run Job + Service deployed, capped test passed (2026-07-29)
- [x] Phase 6 hardening — checkpointing, exit-code, and counts-tracking fixes; full-archive backfill attempted, deferred at 483 posts (2026-08-01 – 2026-08-05)
- [x] Tagger wired into scrape pipeline; 483 posts tagged via standalone catch-up pass (2026-08-05)
- [x] Phase 7 complete — Cloud Scheduler + Cloud Monitoring alert policy, both confirmed working (2026-08-06)
- [x] Task timeout bumped 3600s → 7200s after a run timed out (2026-08-07)
- [x] `post_mvp`: root-caused the backfill plateau as the actual cause of stalled tagging (two new posts landed untagged); added early-stop on consecutive already-known posts + moved tagging onto every checkpoint; switched GUI to absolute `YYYY-MM-DD` dates + native calendar date-range picker (`date_to` inclusive) (2026-08-09)
- [x] `post_mvp` deployed: image rebuilt/pushed, both the scraper Job and GUI Service redeployed; live run confirmed early-stop working (1m17s vs. ~1h before); also found and fixed a second bug — `anthropic-api-key` Secret Manager value had stray literal quote characters (a `.env`-parsing artifact never caught before because Cloud Run tagging had never completed a full run), pushed a corrected secret version; re-ran and confirmed the two previously-untagged posts got tagged (2026-08-12)
- [x] `post_mvp` merged into `main` (fast-forward) (2026-08-12)
- [ ] Next concrete task: your call — split the GUI image (open item above), or start Phase 8 (optional)
