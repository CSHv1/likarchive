# Likarchive — Restart Plan

> Re-entry notes for picking the project back up after a gap. Drop this in the repo root next to `CLAUDE.md`. Read it once, work top-to-bottom.

## What this project is

A Python/Playwright scraper that logs into LinkedIn, navigates to the saved-posts page (`/my-items/saved-posts/`), paginates the full list via infinite scroll, auto-tags posts via Claude Haiku, and stores everything in SQLite. Runs on Cloud Run (Job for the scraper, Service for the GUI), triggered daily by Cloud Scheduler, with Cloud Monitoring alerting on failures. End goal: a shipped, owned, end-to-end thing — cloud-native, scheduled, secrets done properly. **As of 2026-08-06, that goal is achieved** — all 7 planned phases are complete. `post_mvp` (merged to `main` 2026-08-12) then fixed the backfill-plateau/tagging bug below and added absolute dates + a calendar date-range picker to the GUI. **As of 2026-10-07, the GUI also requires sign-in (Clerk) and deploys itself via GitHub Actions on every push to `main`** — see Phase 9.

## Current state

**Live on GCP** (project `csh-data-engineering-on-gcp`, region `europe-west2`):
- Scraper: Cloud Run **Job** `likarchive-scraper` — `gcloud run jobs execute likarchive-scraper --region europe-west2`. Image **pinned to a specific digest** (not `:latest` — see Phase 9), so it's unaffected by GUI deploys; update deliberately with `gcloud run jobs update likarchive-scraper --image=...@sha256:...`.
- GUI: Cloud Run **Service** `likarchive-ui` — `https://likarchive-ui-588295099118.europe-west2.run.app` — **now requires Clerk sign-in** (open sign-up: anyone with the link can create an account). Auto-deploys on every push to `main` via GitHub Actions. Runs its own lightweight image (`likarchive-ui`, built from `Dockerfile.ui` — ~224MB, no Playwright/Chromium), fully decoupled from the scraper's heavy image.
- Storage: `gs://likarchive-db` (SQLite DB), Secret Manager (`linkedin-auth-state`, `anthropic-api-key`, `clerk-secret-key`)
- Scheduler: `likarchive-daily-sync`, fires `0 7 * * *` UTC via the Cloud Run Admin API (not a service URL — the scraper is a Job, see below)
- Monitoring: alert policy on `likarchive-scraper` execution failures → email to `conradsamuelhall@gmail.com`
- CI/CD: `.github/workflows/deploy.yml` — WIF-authenticated (no stored keys), builds + pushes `Dockerfile.ui`'s image, deploys `likarchive-ui` only on push to `main`. Zero manual deploy steps for the GUI now; the scraper Job (still on the heavy `Dockerfile`/`likarchive` image) is fully untouched by CI — build/push/update it by hand, exactly the pre-CI/CD flow.
- **485 real posts archived and fully tagged**, confirmed served correctly by the GUI (now behind sign-in). Daily incremental runs now complete in ~1m15s (was previously hitting the 1h/2h task-timeout every time — see Known open items history below).

**Branch:** `post_mvp` merged into `main` 2026-08-12 (fast-forward); CI/CD + Clerk work merged into `main` 2026-10-07 (`post_mvp_cicd`, fast-forward). `main` is current and deployed. Public repo — `github.com/CSHv1/likarchive`.

## Known open items (not blocking, tracked as tasks)

None open right now — the last two (Dockerfile COPY-list drift, GUI sharing the scraper's heavy image) were both resolved 2026-10-10. See resolved history below.

### Resolved (2026-10-10) — was open, keeping the history for context

**GUI shared the scraper's 2GB Chromium-inclusive image**, despite never touching a browser. Split onto its own lightweight image: `Dockerfile.ui` (`python:3.11-slim`) + `requirements-ui.txt` (just the GUI's actual deps — `db.py` itself is pure stdlib), explicit `COPY` allowlist rather than `COPY . .` (opposite risk direction from the main Dockerfile's fix — here over-inclusion is the risk, not under-inclusion). Result: 224MB vs. 2.13GB, ~90% smaller. `deploy.yml` now builds/pushes/deploys only this image for `likarchive-ui`; CI no longer touches the scraper's heavy image at all. Verified locally (image contents, both entrypoints) and in production (new revision confirmed on the new image, zero errors, scraper Job confirmed still untouched) before and after pushing. Full writeup in `CLAUDE.md`'s Phase 9 section (follow-up note).

### Resolved (2026-10-07, later same day) — was open, keeping the history for context

**Dockerfile's explicit `COPY` file list was drift-prone.** Bit us twice (Phase 6: `db_sync.py`/`cloud_auth.py`; Phase 9: `clerk_auth.py`) before actually being fixed — every new top-level module needed a manual Dockerfile edit or the container crash-looped with `ModuleNotFoundError`, invisible until something actually imported it at runtime. Replaced with `COPY . .` plus a hardened `.dockerignore` (now also excludes `.claude/`, `.github/`, `.DS_Store`, `.env.example`, and the Dockerfile/`.dockerignore` themselves). Verified locally: built the image, inspected `/app` directly to confirm every expected file present and every excluded path genuinely absent, then booted both entrypoints (`gunicorn app:app` and `python -c "import scraper"`) to confirm clean startup before this ever touched a real deploy.

### Resolved (2026-10-07) — was open, keeping the history for context

**GUI was fully public, deploys were 100% manual.** Added Clerk auth (app-layer auth boundary, Cloud Run ingress stays public) and GitHub Actions CI/CD (Workload Identity Federation, GUI-only auto-deploy). Full writeup, including three bugs caught along the way (Dockerfile COPY drift recurrence, an over-broad IAM grant caught before use, and a mutable-tag gap that would have silently exposed the scraper Job to new images), in `CLAUDE.md`'s Phase 9 section.

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
- **Clerk auth**: `clerk_auth.py`'s `require_auth` decorator gates every `/api/*` route in `app.py` — active in *every* environment (not gated on `K_SERVICE`/`CLOUD_RUN_JOB` like `db_sync.py`/`cloud_auth.py`), since a logged-out browser should see the sign-in screen locally too. Cloud Run ingress itself stays public; Clerk is the actual auth boundary, at the app layer.
- **CI/CD auto-deploys the GUI only.** The scraper Job's image is pinned to a specific digest and is never touched by `.github/workflows/deploy.yml` — update it deliberately with `gcloud run jobs update likarchive-scraper --image=...@sha256:...` when ready. Don't let the Job's image drift back onto a mutable `:latest` tag — that's what silently re-exposes it to every future GUI deploy (see Phase 9's bug #3 in `CLAUDE.md`).

## Environment notes

- `gcloud` needs `CLOUDSDK_PYTHON` pointed at a supported Python (system default is 3.7) and its bin dir on `PATH` — neither is picked up automatically mid-session by Claude Code's Bash tool, so set both explicitly in-command:
  ```bash
  export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"
  export CLOUDSDK_PYTHON="/Users/conradhallpro/.pyenv/versions/3.10.11/bin/python3"
  ```
- Local testing of `db_sync.py`/`cloud_auth.py` needs `gcloud auth application-default login` (separate from the CLI's `gcloud auth login`).
- `git push` to the public repo: `git -c credential.helper=store push ...` avoids a hang on the system `osxkeychain` credential helper trying to show a GUI prompt with no display attached.
- **Public-repo caution**: scan for billing account IDs or credential material before committing anything documenting GCP setup — project IDs/service account emails/bucket/secret *names* are fine (IAM controls access, not obscurity), but billing account IDs and any actual key/token material are not.
- **`gh` CLI isn't installed, and Homebrew can't build it** — the Xcode Command Line Tools on this machine are too outdated for `brew install gh` to build its `go` dependency from source. Workaround that worked: download the precompiled binary directly from `https://github.com/cli/cli/releases` (the macOS arm64 `.zip` asset), unzip, and run it standalone — no build step needed. It doesn't persist anywhere permanent yet (was run from `/tmp` last time), so this may need re-downloading next session. `gh auth login --web` is interactive (device code + browser approval) — needs you, not scriptable.

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
- **Phase 9** — CI/CD (GitHub Actions + WIF) + Clerk auth for the GUI ✅ (merged to `main` 2026-10-07)

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
- [x] Phase 9 built on `post_mvp_cicd`: Clerk auth (`clerk_auth.py`, gates all `/api/*` routes, sign-in screen in `index.html`) + GitHub Actions CI/CD (`.github/workflows/deploy.yml`, WIF-authenticated, GUI-only auto-deploy) — GCP-side WIF pool/provider/`likarchive-ci` SA and `clerk-secret-key` secret all provisioned; verified locally (401 signed-out, real Clerk sign-in works) before touching `main` (2026-09-04, session paused here — GitHub repo variables not yet set)
- [x] Resumed after a month-long gap: confirmed via GitHub's Actions API that zero workflow runs had ever fired (nothing had reached `main` yet) and all GCP resources were still intact; installed `gh` CLI via a precompiled binary (Homebrew's build failed on outdated Xcode tools) to set the two missing GitHub repo variables (2026-10-07)
- [x] Merged `post_mvp_cicd` → `main` and pushed — triggered the first-ever Actions run. It succeeded, but the deployed revision crash-looped (`ModuleNotFoundError: No module named 'clerk_auth'` — Dockerfile `COPY` list drift, same bug class as Phase 6). Fixed and pushed again; second run succeeded and the new revision came up clean (2026-10-07)
- [x] Caught and fixed two more issues surfaced by having a real CI/CD pipeline for the first time: an `iam.serviceAccountUser` grant that had been scoped to the whole project instead of just `likarchive-sa` (corrected before anything used it), and the scraper Job referencing the mutable `:latest` tag instead of a pinned digest, which would have silently exposed it to future GUI-only deploys — pinned to its last known-good pre-Clerk digest (2026-10-07)
- [x] End-to-end verified in production: unauthenticated `likarchive-ui` requests get the Clerk sign-in screen and a 401 on `/api/*`; real Clerk SSO sign-in confirmed working against the live 485-post archive (2026-10-07)
- [x] Fixed the Dockerfile COPY-drift pattern for good: switched to `COPY . .` + hardened `.dockerignore` (added `.claude/`, `.github/`, `.DS_Store`, `.env.example`, Dockerfile/`.dockerignore` themselves); verified locally by inspecting the built image's `/app` contents and booting both entrypoints before pushing (2026-10-07)
- [x] Split the GUI onto its own lightweight image: new `Dockerfile.ui` + `requirements-ui.txt`, `deploy.yml` updated to build/push/deploy only this image for `likarchive-ui` and no longer touch the scraper's heavy image at all. 224MB vs. 2.13GB. Verified locally (image contents, both entrypoints) and in production (new revision confirmed, zero errors, scraper Job confirmed untouched) (2026-10-10)
- [ ] Next concrete task: your call — start Phase 8 (optional), or move on to the planned RAG layer (Vertex AI embeddings + BigQuery vector search, hand-built per the original project plan)
