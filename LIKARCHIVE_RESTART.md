# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, and stores extracted posts in SQLite. Daily auto-sync via scheduler. GCP Cloud Run deployment planned for a later phase. End goal for *me*: a shipped, owned, end-to-end thing I'd actually claim — cloud-native, scheduled, secrets done properly.

## Current state (where I left it)

**Built and working locally:**

- `scraper.py` — Playwright saved-posts navigation, infinite-scroll pagination, extracts post text / author / URL / timestamp (auth via portable `storage_state()` JSON, `STATE_PATH`/`auth_state.json`)
- `save_session.py` — one-time manual login; saves browser profile to `browser_profile/` (headed debugging) AND exports `auth_state.json` (what scraper.py actually reads)
- `db.py` — SQLite with MD5 hash dedup; FTS5 + tags schema; `post_date` column (reconstructed from relative timestamps)
- `query.py` — CLI browser with FTS5 search
- `tagger.py` — auto-tagging via Claude Haiku (`claude-haiku-4-5-20251001`)
- `scheduler.py` — daily sync
- `app.py` + `templates/index.html` — Flask web UI: card list, tag/author/date filters, FTS search, load more pagination, plus a red banner if the last sync failed (`/api/sync_status`)
- `db_sync.py` / `cloud_auth.py` — GCS DB persistence / Secret Manager auth fetch, both gated on `K_SERVICE` (no-op locally)
- `CLAUDE.md` — merged instructions + 8-phase roadmap
- ~148 posts in local DB, all tagged

**Stopped at:** Phase 5 complete. Phase 4 (containerisation) verified end-to-end including the `storage_state()` auth fix for running headless in Linux. Also added session-expiry detection: `scrape_saves()` now raises immediately if redirected to `/login`/`/authwall`/`/checkpoint` instead of silently logging a "successful" 0-post sync, and the GUI shows a banner when the last sync errored. Phase 5 (GCP infra) is fully provisioned on the existing project `csh-data-engineering-on-gcp` (region `europe-west2`): APIs enabled, `likarchive-sa` service account created, `gs://likarchive-db` bucket created, `linkedin-auth-state` secret created (version 1 = current `auth_state.json`), IAM grants scoped to just that bucket/secret. Hit and resolved a billing hiccup along the way — see CLAUDE.md Phase 5 notes for details (closed billing account, plus a red-herring quota error on re-linking).

Also fixed a gap found while scoping Phase 6: `app.py` (the GUI service) never called `download_db()` and had `init_db()` trapped inside `if __name__ == "__main__"`, which gunicorn never executes — the GUI would have started with no DB file and no schema on Cloud Run, 500ing on every API route. Both are now module-level, gated the same way as the scraper (`K_SERVICE` check). Verified locally by simulating the Cloud Run env against the real `gs://likarchive-db` bucket — confirmed it reaches the bucket, handles "no DB yet" gracefully (bucket is genuinely empty, no scraper Cloud Run run has happened yet), and creates the schema correctly. Along the way, also fixed `db_sync.py`'s `storage.Client()` call to pass `project=GCP_PROJECT` explicitly — without it, the client couldn't infer a project from these particular ADC credentials (multiple GCP projects on this account, no unambiguous default).

**Next up:** Phase 6 — Cloud Run deployment (push image to Artifact Registry, deploy scraper + GUI services, full-archive staging test — this will be the first time `gs://likarchive-db` actually gets populated).

**Branch:** all of this session's work (Phase 4 auth fix, session-expiry detection, Phase 5 GCP infra, Phase 6 app.py fix) is on `gcp_deploy`, pushed to `origin/gcp_deploy` on GitHub (this repo is public — `github.com/CSHv1/likarchive`). `main` is unaffected. Continue Phase 6 work on `gcp_deploy`; merge to `main` via PR once Cloud Run deployment is verified end-to-end.

**Public-repo caution:** this repo is public. One near-miss this session: the GCP billing account ID got written into `CLAUDE.md` and almost got pushed before being caught and redacted. Before committing anything that documents GCP setup, double-check for billing account IDs, service account keys, or other account-identifying details that shouldn't be public — project IDs/service account emails/bucket names are fine (access is via IAM, not obscurity), but billing account IDs and any credential material are not.

**Environment notes for next session:**
- `gcloud` is installed via Homebrew cask but needs `CLOUDSDK_PYTHON` pointed at a supported Python (system default is 3.7, unsupported) — `export CLOUDSDK_PYTHON=/Users/conradhallpro/.pyenv/versions/3.10.11/bin/python3` and add `/usr/local/share/google-cloud-sdk/bin` to `PATH`. This is in `~/.bashrc`/`~/.bash_profile` now, but Claude Code's Bash tool doesn't source either automatically mid-session — set both env vars explicitly in-command if `gcloud` isn't found.
- Testing `db_sync.py`/`cloud_auth.py` locally (outside Docker/Cloud Run) needs Application Default Credentials, separate from the `gcloud auth login` used for the CLI: `gcloud auth application-default login`. Already set up as of 2026-07-23.
- The project venv now has `google-cloud-storage`/`google-cloud-secret-manager` installed (matches `requirements.txt`).

## ⚠️ Known watch-point — check this FIRST

LinkedIn class names are unstable. Selectors were rewritten in June 2026 after the DOM changed (author name moved out of `aria-hidden` spans; timestamp span lost its `aria-hidden` attribute). They may drift again.

**First action on restart:** sanity run, confirm extraction lands in the DB with real author names and timestamps.

```bash
HEADLESS=false MAX_POSTS=5 python scraper.py
```

- `auth_state.json` holds the saved session (portable JSON, read via `STATE_PATH`) — no login needed unless the session has expired.
- If the session has expired or `auth_state.json` doesn't exist yet, run `python save_session.py` first (opens a headed browser, log in manually, close when on the feed — this writes both `browser_profile/` and `auth_state.json`).
- If `author_name` comes back empty or shows "• 3rd+" / "• 2nd" → selector drift. Grab the outerHTML of `.entity-result__content-actor` from DevTools and update `extract_author` in `scraper.py`.
- If `post_timestamp` is empty → timestamp selector drifted. Check `p.t-black--light > span` structure in DevTools and update `extract_timestamp`.

## Re-entry sequence

### Step 1 — Verify it still runs (always do this first)
- Headful, 5 posts, confirm text/author/URL/timestamp populate in SQLite.
- Fix selectors if drifted. (Bonus: this reloads the whole codebase into my head.)

### Step 2 — Next build: Phase 6 (Cloud Run deployment)

Phases 3–5 are all done: GUI, containerisation (including the `storage_state()` auth fix), and GCP infra (SA, bucket, secret, IAM all provisioned on `csh-data-engineering-on-gcp`). Next:
- Push image to Artifact Registry (`europe-west2-docker.pkg.dev/csh-data-engineering-on-gcp/likarchive/likarchive:latest`)
- Deploy scraper service (no public URL, `--service-account likarchive-sa@csh-data-engineering-on-gcp.iam.gserviceaccount.com`, `--set-env-vars GCP_PROJECT=csh-data-engineering-on-gcp`)
- Deploy GUI service (`app.py`'s `download_db()`/`init_db()` wiring already fixed and verified — see above)
- Staging test: full-archive sync (`MAX_POSTS=0`) triggered manually, verify count + spot-check GUI

*Why this order:* "running headless on Cloud Run, daily schedule, secrets managed properly" is the sentence that anchors a Staff/Principal conversation.

## Roadmap (from CLAUDE.md, condensed)

- **Phase 1** — Local core ✅
- **Phase 2** — Test sync (50-post cap) ✅
- **Phase 3** — Flask GUI (cards, filters, FTS) ✅
- **Phase 4** — Containerise (Dockerfile ✅, `.dockerignore` ✅, GUI verified ✅, scraper `storage_state()` auth fix verified ✅) ✅
- **Phase 5** — GCP infra (SA ✅, Secret Manager ✅, GCS bucket ✅, IAM ✅ — all on `csh-data-engineering-on-gcp`) ✅
- **Phase 6** — Cloud Run deploy (scraper + UI services) + full-archive staging test ← **next**
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

- [x] Step 1 verify run — selectors OK, `auth_state.json` generated and working (2026-07-23)
- [x] Phase 4 containerisation verified — GUI + scraper containers both confirmed end-to-end (2026-07-23)
- [x] Session-expiry detection + GUI banner added (2026-07-23)
- [x] Phase 5 GCP infra fully provisioned on `csh-data-engineering-on-gcp` (2026-07-23)
- [x] app.py GCS DB sync fix (+ db_sync.py project fix) — verified against real bucket via ADC (2026-07-23)
- [ ] Next concrete task: start Phase 6 (Artifact Registry push, Cloud Run deploy)
