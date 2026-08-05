# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, auto-tags posts via Claude Haiku, and stores everything in SQLite. Runs on Cloud Run (Job for the scraper, Service for the GUI), triggered daily by Cloud Scheduler, with Cloud Monitoring alerting on failures. End goal: a shipped, owned, end-to-end thing — cloud-native, scheduled, secrets done properly. **As of 2026-08-06, that goal is achieved** — all 7 planned phases are complete.

## Current state

**Live on GCP** (project `csh-data-engineering-on-gcp`, region `europe-west2`):
- Scraper: Cloud Run **Job** `likarchive-scraper` — `gcloud run jobs execute likarchive-scraper --region europe-west2`
- GUI: Cloud Run **Service** `likarchive-ui` — `https://likarchive-ui-588295099118.europe-west2.run.app`
- Storage: `gs://likarchive-db` (SQLite DB), Secret Manager (`linkedin-auth-state`, `anthropic-api-key`)
- Scheduler: `likarchive-daily-sync`, fires `0 7 * * *` UTC via the Cloud Run Admin API (not a service URL — the scraper is a Job, see below)
- Monitoring: alert policy on `likarchive-scraper` execution failures → email to `conradsamuelhall@gmail.com`
- **483 real posts archived and fully tagged**, confirmed served correctly by the GUI

**Branch:** all work is on `gcp_deploy`, pushed to `origin/gcp_deploy` (public repo — `github.com/CSHv1/likarchive`). `main` is untouched. Merge via PR whenever that feels right; nothing forces it.

## Known open items (not blocking, tracked as tasks)

1. **Full-archive backfill deferred at 483 posts.** Three consecutive full-hour runs plateaued at exactly 483 with zero new posts each — not a resource issue (CPU 1→2 vCPU, memory 2Gi→4Gi bumps had no effect). Most likely a LinkedIn-side soft limit on infinite-scroll depth within one session. Doesn't block daily operation — incremental daily syncs never scroll anywhere near this deep. Needs diagnostic logging (actual DOM card count per scroll, not just `scrollHeight`) to characterize properly before attempting a real fix. Full detail in `CLAUDE.md` Phase 6 section.
2. **GUI still shares the scraper's 2GB Chromium-inclusive image**, despite never touching a browser. Deferred optimization — split into a lightweight image once there's a reason to prioritize it (cold-start latency, storage cost).

## Key mechanisms worth knowing before touching this again

- **Auth**: `save_session.py` (interactive, local) → `auth_state.json` (portable Playwright `storage_state()`, NOT the OS-encrypted persistent profile) → Secret Manager `linkedin-auth-state` → `cloud_auth.py` fetches it at runtime. Re-run `save_session.py` + push a new secret version whenever the session expires (no way to automate this — 2FA/CAPTCHA needs a human).
- **Session-expiry detection**: `scraper.py` raises immediately if redirected to `/login`/`/authwall`/`/checkpoint`, instead of silently reporting a fake "success." Surfaces as a red banner in the GUI (`/api/sync_status`) and, in Cloud Run, as a real non-zero exit code that the Monitoring alert above will catch.
- **Checkpointing**: `scrape_saves()` uploads the DB to GCS after every scroll batch, not just at the end — Cloud Run's task-timeout is a hard kill that bypasses Python's `finally`, so without this, a timed-out run used to lose 100% of its progress.
- **Tagging**: `tagger.py`'s `tag_posts()` runs automatically after a *clean* scrape completion (deliberately not wired into the checkpoint loop, so it never competes with an in-progress backfill's time budget). Only tags posts with no existing `post_tags` row — never touches existing classifications.
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
- **Phase 6** — Cloud Run deploy ✅ (full-archive backfill deferred at 483 posts — see open items)
- **Phase 7** — Cloud Scheduler + Monitoring alert ✅
- **Phase 8** — BigQuery sink (`bq_sink.py` → `likarchive.liked_posts`) + LookML model ⬜ (optional, not started)

## Session log

- [x] Phases 1–5 complete (2026-07-23)
- [x] Phase 6 complete — Cloud Run Job + Service deployed, capped test passed (2026-07-29)
- [x] Phase 6 hardening — checkpointing, exit-code, and counts-tracking fixes; full-archive backfill attempted, deferred at 483 posts (2026-08-01 – 2026-08-05)
- [x] Tagger wired into scrape pipeline; 483 posts tagged via standalone catch-up pass (2026-08-05)
- [x] Phase 7 complete — Cloud Scheduler + Cloud Monitoring alert policy, both confirmed working (2026-08-06)
- [ ] Next concrete task: your call — diagnose the backfill plateau (Task #10), split the GUI image (Task #5), or start Phase 8 (optional)
