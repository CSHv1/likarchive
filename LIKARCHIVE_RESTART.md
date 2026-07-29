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

**Phase 6 is now done too (2026-07-29).** Live: Cloud Run Job `likarchive-scraper` and Cloud Run Service `likarchive-ui` (`https://likarchive-ui-588295099118.europe-west2.run.app`), both on `csh-data-engineering-on-gcp`/`europe-west2`. A capped test (`MAX_POSTS=5`) scraped 5 real posts, uploaded them to `gs://likarchive-db`, and the GUI served them correctly after a revision refresh — full pipeline confirmed working.

This deploy surfaced four real, non-obvious bugs (all fixed, all detailed in `CLAUDE.md`'s Phase 6 section — read that before touching deployment again): (1) images built on this Apple Silicon Mac default to `arm64`, Cloud Run needs `linux/amd64` — always `docker build --platform linux/amd64`; (2) the Dockerfile's `COPY` line wasn't updated when `db_sync.py`/`cloud_auth.py` were added in Phase 5, causing `ModuleNotFoundError`; (3) the scraper *cannot* be a Cloud Run Service (`gcloud run deploy`) — it's a one-shot script with no HTTP listener, and Services require a port health-check the scraper can never pass. It has to be a Cloud Run **Job**. This also means it sets `CLOUD_RUN_JOB`, not `K_SERVICE`, so `scraper.py`'s cloud-detection now checks both; (4) `DB_PATH`/`STATE_PATH` defaulted to `/data/...`, which doesn't exist in Cloud Run (that path assumed a locally-bind-mounted volume) — both now explicitly override to `/tmp/...` via `--set-env-vars`.

**Not yet done:** the full-archive sync (`MAX_POSTS=0`) — the capped test proved the pipeline works, but the complete backlog hasn't been pulled into Cloud Run's copy of the DB.

**⚠️ `likarchive-ui` is currently locked down (2026-07-29 end of session)** — public access (`allUsers` invoker) was deliberately removed overnight since there was no need to leave a personal project's GUI publicly reachable while unattended. Note: neither Cloud Run resource actually "runs" or costs anything while idle regardless (the scraper is a Job that only executes when triggered — nothing is scheduled yet in Phase 7 — and the GUI Service scales to zero with no traffic), so this was a precaution, not a required safety step. To restore public access next session:

```bash
export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"
export CLOUDSDK_PYTHON="/Users/conradhallpro/.pyenv/versions/3.10.11/bin/python3"
gcloud run services add-iam-policy-binding likarchive-ui \
  --project=csh-data-engineering-on-gcp --region=europe-west2 \
  --member="allUsers" --role="roles/run.invoker"
```

**Next up:** Phase 7 — Cloud Scheduler. Its plan also needed correcting: since the scraper is a Job (not a Service), Cloud Scheduler can't just POST to a service URL — it has to call the Cloud Run Admin API's job-execution endpoint instead. Full corrected command is in `CLAUDE.md`.

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

### Step 2 — Next build: Phase 7 (Cloud Scheduler)

Phases 3–6 are all done, including a fully verified Cloud Run deployment (scraper Job + GUI Service, capped test passed). Next:
- Full-archive sync: `gcloud run jobs execute likarchive-scraper --region europe-west2 --update-env-vars=MAX_POSTS=0 --wait` — flag this before running, same as any live LinkedIn action; this pulls the *entire* saved-posts backlog in one go
- Cloud Scheduler daily job — targets the Cloud Run Admin API job-run endpoint, not a service URL (corrected plan, see `CLAUDE.md` Phase 7)
- Cloud Monitoring alert policy on scraper execution failures (also Phase 7)

*Why this order:* "running headless on Cloud Run, daily schedule, secrets managed properly" is the sentence that anchors a Staff/Principal conversation.

## Roadmap (from CLAUDE.md, condensed)

- **Phase 1** — Local core ✅
- **Phase 2** — Test sync (50-post cap) ✅
- **Phase 3** — Flask GUI (cards, filters, FTS) ✅
- **Phase 4** — Containerise (Dockerfile ✅, `.dockerignore` ✅, GUI verified ✅, scraper `storage_state()` auth fix verified ✅) ✅
- **Phase 5** — GCP infra (SA ✅, Secret Manager ✅, GCS bucket ✅, IAM ✅ — all on `csh-data-engineering-on-gcp`) ✅
- **Phase 6** — Cloud Run deploy (scraper Job ✅, UI Service ✅, capped staging test ✅ — full-archive sync still pending) ✅
- **Phase 7** — Cloud Scheduler (`0 7 * * *`, Cloud Run Admin API job-run target, `likarchive-sa`) ← **next**
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
- [x] Phase 6 complete — Cloud Run Job + Service deployed, capped test scraped 5 real posts end-to-end (2026-07-29)
- [ ] Next concrete task: full-archive sync, then start Phase 7 (Cloud Scheduler)
