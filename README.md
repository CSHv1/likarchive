# Likarchive

Scrapes your LinkedIn saved posts and archives them in a local SQLite database.
Extracts: post text, author name, author profile URL, direct post URL, and timestamp.
Includes full-text search, CLI browsing, and Claude-powered auto-tagging.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable            | Description                                                         |
| ------------------- | ------------------------------------------------------------------- |
| `LINKEDIN_EMAIL`    | Your LinkedIn login email                                           |
| `LINKEDIN_PASSWORD` | Your LinkedIn password                                              |
| `ANTHROPIC_API_KEY` | Claude API key — only needed for `tagger.py`                        |
| `DB_PATH`           | SQLite file path (default: `linkedin_likes.db`)                     |
| `HEADLESS`          | `false` while getting started; `true` once confirmed working        |
| `SCROLL_PAUSE_MS`   | Pause between scrolls in ms (increase to 3000–4000 if rate-limited) |
| `MAX_POSTS`         | Posts to fetch per sync run — `0` for unlimited                     |

### 3. Save your browser session

Run this once to log in interactively and save the browser session:

```bash
python save_session.py
```

A browser window opens. Log in to LinkedIn manually (handle any CAPTCHA).
Close the window when done — the session is saved to `browser_profile/`.

### 4. Run your first sync

```bash
python scraper.py
```

Output looks like:

```
[scraper] Navigating to saved posts...
  [NEW    ] Jane Smith — https://www.linkedin.com/feed/update/urn:li:activity:...
  [NEW    ] John Doe   — https://www.linkedin.com/feed/update/urn:li:activity:...
...
[sync] Done — seen=100 new=100 updated=0 skipped=0
```

---

## Daily auto-sync

Run the scheduler to sync once immediately, then again every day at 08:00:

```bash
python scheduler.py
```

To run it in the background and keep a log:

```bash
nohup python scheduler.py >> sync.log 2>&1 &
```

---

## Browse and search posts

`query.py` is a terminal UI for reading your archive.

```bash
# 20 most recently scraped posts
python query.py

# Full-text search across post text and author name
python query.py --search "machine learning"

# Filter by author (partial match, case-insensitive)
python query.py --author "Jane"

# Change result limit (default 20)
python query.py --search "startup" --limit 50
```

Each result shows:

```
------------------------------------------------------------------------
Author : Jane Smith
URL    : https://www.linkedin.com/feed/update/urn:li:activity:...
When   : 3w
Text   : Here's what I've learned after 5 years building ML infra at scale…
```

---

## Web UI

`app.py` is a Flask web interface for browsing your archive.

```bash
python app.py
```

Opens at `http://localhost:5000`. Currently serves a health-check endpoint (`GET /`) that returns the total post count. Full post list, filters, FTS search, and tag editing are being built out in Phase 3.

---

## Auto-tagging with Claude

`tagger.py` calls the Claude API to generate 3–5 topic tags per post. Haiku is used as it's a relatively simple task we need the LLM to perform, so, minimises costs when extrapolated over multiple tasks of auto-tagging, and, has low latency.

```bash
# Tag all posts that don't have tags yet
python tagger.py

# Retag every post (overwrite existing tags)
python tagger.py --rerun

# Process at most 20 posts
python tagger.py --limit 20
```

Tags are stored in the `tags` and `post_tags` tables and can be queried directly (see below).

Requires `ANTHROPIC_API_KEY` in `.env`.

---

## Investigating the database

Open the database with the SQLite CLI:

```bash
sqlite3 linkedin_likes.db
```

Or run one-off queries inline:

```bash
sqlite3 -column -header linkedin_likes.db "SELECT ..."
```

### liked_posts — your saved posts

```sql
-- Count total posts
SELECT COUNT(*) FROM liked_posts;

-- 10 most recently scraped
SELECT author_name, post_timestamp, substr(post_text, 1, 100)
FROM liked_posts
ORDER BY scraped_at DESC
LIMIT 10;

-- Posts by a specific author
SELECT post_url, post_timestamp, substr(post_text, 1, 120)
FROM liked_posts
WHERE author_name LIKE '%Jane%';

-- Full text of a single post
SELECT post_text FROM liked_posts WHERE post_url LIKE '%urn:li:activity:12345%';

-- Posts that have been updated since first scrape (post text changed)
SELECT author_name, scraped_at, last_updated, substr(post_text, 1, 80)
FROM liked_posts
WHERE last_updated != scraped_at;

-- Posts with no text extracted
SELECT post_url, author_name FROM liked_posts WHERE post_text = '' OR post_text IS NULL;
```

### posts_fts — full-text search index

```sql
-- Search for posts mentioning a topic (ranks by relevance)
SELECT lp.author_name, lp.post_timestamp, snippet(posts_fts, 2, '[', ']', '...', 20)
FROM posts_fts
JOIN liked_posts lp ON posts_fts.rowid = lp.id
WHERE posts_fts MATCH 'artificial intelligence'
ORDER BY rank
LIMIT 20;

-- Phrase search
SELECT lp.author_name, substr(lp.post_text, 1, 120)
FROM posts_fts
JOIN liked_posts lp ON posts_fts.rowid = lp.id
WHERE posts_fts MATCH '"product market fit"';

-- Boolean search (AND is implicit; use OR / NOT explicitly)
SELECT lp.author_name, substr(lp.post_text, 1, 120)
FROM posts_fts
JOIN liked_posts lp ON posts_fts.rowid = lp.id
WHERE posts_fts MATCH 'startup NOT funding';
```

### tags / post_tags — auto-generated topic tags

```sql
-- All tags and how many posts each has
SELECT t.name, COUNT(pt.post_url) AS post_count
FROM tags t
JOIN post_tags pt ON t.id = pt.tag_id
GROUP BY t.name
ORDER BY post_count DESC;

-- Tags applied to a specific post
SELECT t.name
FROM post_tags pt
JOIN tags t ON pt.tag_id = t.id
WHERE pt.post_url = 'https://www.linkedin.com/feed/update/urn:li:activity:...';

-- All posts with a given tag, with author and preview
SELECT lp.author_name, lp.post_timestamp, substr(lp.post_text, 1, 100)
FROM post_tags pt
JOIN tags t ON pt.tag_id = t.id
JOIN liked_posts lp ON pt.post_url = lp.post_url
WHERE t.name = 'leadership'
ORDER BY lp.scraped_at DESC;

-- Posts and all their tags in one row (comma-separated)
SELECT lp.author_name,
       substr(lp.post_text, 1, 80) AS preview,
       GROUP_CONCAT(t.name, ', ') AS tags
FROM liked_posts lp
JOIN post_tags pt ON lp.post_url = pt.post_url
JOIN tags t ON pt.tag_id = t.id
GROUP BY lp.post_url
ORDER BY lp.scraped_at DESC
LIMIT 20;

-- Posts that haven't been tagged yet
SELECT post_url, author_name
FROM liked_posts
WHERE post_url NOT IN (SELECT DISTINCT post_url FROM post_tags);
```

### sync_log — sync history

```sql
-- Last 10 sync runs
SELECT id, started_at, status, posts_seen, posts_new, posts_updated, posts_skipped
FROM sync_log
ORDER BY id DESC
LIMIT 10;

-- Any syncs that errored
SELECT started_at, error FROM sync_log WHERE status = 'error';

-- Total posts collected across all syncs
SELECT SUM(posts_new) AS total_new FROM sync_log WHERE status = 'success';
```

### Handy one-liners (shell)

```bash
# Total posts in the archive
sqlite3 linkedin_likes.db "SELECT COUNT(*) FROM liked_posts;"

# Top 10 most-saved authors
sqlite3 -column -header linkedin_likes.db \
  "SELECT author_name, COUNT(*) n FROM liked_posts GROUP BY author_name ORDER BY n DESC LIMIT 10;"

# All unique tags, alphabetically
sqlite3 linkedin_likes.db "SELECT name FROM tags ORDER BY name;"

# Last sync summary
sqlite3 -column -header linkedin_likes.db \
  "SELECT started_at, status, posts_seen, posts_new FROM sync_log ORDER BY id DESC LIMIT 1;"
```

---

## Troubleshooting

| Symptom                                  | Fix                                                                                       |
| ---------------------------------------- | ----------------------------------------------------------------------------------------- |
| `seen=0 new=0` on every run              | LinkedIn DOM may have changed — selectors need updating in `scraper.py`                   |
| Login fails / `login_failed.png` created | Open browser headfully and solve CAPTCHA manually, then re-run `save_session.py`          |
| Rate limited (scroll stops early)        | Increase `SCROLL_PAUSE_MS` to 3000–5000 in `.env`                                         |
| `ANTHROPIC_API_KEY not set`              | Add your key to `.env` before running `tagger.py`                                         |
| FTS returns no results                   | Run `INSERT INTO posts_fts(posts_fts) VALUES('rebuild');` in sqlite3 to rebuild the index |

---

## Architecture & Design Decisions

### Why SQLite?

SQLite was chosen for Phase 1 as a deliberate local-first decision, not a shortcut. As a serverless, file-based database it requires zero infrastructure overhead — no database server to run, no connection pooling to configure, and the entire archive is a single portable file that can be inspected, copied, or backed up trivially.

The relational model is the right fit for this problem: posts, authors, tags and sync history are distinct entities with clear relationships, and SQL gives us filtering, counts, and full-text search without reinventing that logic in application code. Flat files or CSV would have been structurally insufficient for the querying capability we need.

SQLite's limitation is **concurrent writes** — it uses file-level locking, so multiple processes writing simultaneously will block or error. For a single-user local tool this is irrelevant. The migration trigger to Cloud SQL or Postgres is not a user count threshold but the move to a **multi-user hosted deployment** where concurrent writes become a genuine possibility. That's a Phase 3 consideration.

---

### Why MD5 for change detection?

Deduplication and change detection are handled by two separate mechanisms:

- **Identity**: each post is uniquely identified by its `post_url`. The upsert lookup is `WHERE post_url = ?` — one row per URL, always.
- **Change detection**: the MD5 hash of `post_text` is stored as `text_hash`. On each sync, the incoming post's text is hashed and compared against the stored hash. If they differ, the post has been edited and the record is updated.

MD5 was chosen because it is deterministic — the same input string always produces the same 128-bit hash output — which makes it well suited to detecting whether content has changed between scrape runs. Cryptographic strength is not a requirement here; collision resistance at this scale is not a meaningful concern.

A known limitation: if LinkedIn restructures a post's URL (e.g. changing `urn:li:activity:` to a different scheme), the existing record will not be found by the URL lookup and the post will be inserted as a new row, producing a duplicate. In practice LinkedIn's URL format has been stable, and for a personal archive this is an acceptable edge case.

---

### Why the FTS delete-then-reinsert pattern?

The `posts_fts` full-text search index is a SQLite FTS5 virtual table. Unlike the main `liked_posts` table, it has no upsert capability — writes are append-only. If an updated post's new text were inserted without first removing the old entry, both versions would exist in the index under the same `rowid`, and searches could match against content that no longer exists in the source record.

The delete-then-reinsert pattern on update is a manual upsert for the FTS index: remove the stale entry by `rowid`, then insert the fresh text. This keeps the FTS index in sync with `liked_posts`.

---

### Why Playwright instead of the LinkedIn API?

LinkedIn's API does not expose a usable saved posts endpoint for personal or unofficial applications. Access to member data (including saved posts) requires OAuth app approval and specific product permissions — notably `r_memberdata` — which LinkedIn does not grant outside formal partnership agreements. This is not simply a matter of developer verification; the relevant scopes are not available to third-party applications regardless of approval status.

Playwright is used as a workaround: it renders the saved posts page in a real Chromium browser using a persisted session, then extracts post data from the rendered HTML. The data model is designed to align with what an official API would return, making a future migration straightforward if LinkedIn ever opens access.

**Tradeoffs:**

- **Reliability**: dependent on LinkedIn's DOM structure remaining stable. Any change to element selectors requires code updates. Authentication and CAPTCHA handling add further fragility, as does LinkedIn's bot detection — scroll timing, session patterns, and request frequency are all fingerprinted, which is why `SCROLL_PAUSE_MS` is configurable.
- **Maintenance**: unlike a stable first-party API, issues are only discoverable when something breaks upstream. This is manageable for a personal tool but problematic at product scale.
- **Risk**: scraping violates LinkedIn's User Agreement. Personal use sits in a widely tolerated grey area. Any multi-user hosted deployment would almost certainly attract a cease and desist. Likarchive is explicitly scoped as a personal tool for this reason.

---

## Cloud Run Deployment (Planned — Phase 3)

### Overview

The planned Cloud Run deployment will migrate Likarchive from a local tool to a hosted service, enabling access from any device without a local Python environment. The architecture shifts from a single-user file-based system to a containerised, multi-user application running on Google's infrastructure.

### What changes

**Containerisation**
The application is packaged into a Docker image and pushed to **Artifact Registry**. Cloud Run pulls from there to deploy. The `Dockerfile` will install Python dependencies, Playwright, and Chromium, and define the entrypoint for both the Flask web UI and the sync job.

**Database**
SQLite is replaced by **Cloud SQL (Postgres)**. The migration trigger is concurrent writes — multiple users writing simultaneously would cause locking errors under SQLite. Cloud SQL handles connection pooling and concurrent access natively. Schema migrations will be managed via Alembic or a lightweight equivalent.

**Secrets**
All credentials — LinkedIn session tokens, `ANTHROPIC_API_KEY`, database connection strings — move to **Secret Manager**. Nothing sensitive is hardcoded or stored in environment files in the container image. Cloud Run retrieves secrets at runtime via the Secret Manager API.

**Scheduler**
The local `scheduler.py` process (kept alive with `nohup`) is replaced by **Cloud Scheduler** triggering a Cloud Run job on a daily cron schedule. Cloud Run containers are stateless and spin down when idle — a persistent background process is not viable. This is the same pattern used in other GCP pipeline work (Cloud Scheduler → Cloud Run → BigQuery).

**Authentication**
Multi-user support requires user accounts, login flows, and per-user data isolation. Each user's posts, tags, and sync history are scoped to their account. This adds auth middleware (likely Firebase Auth or a simple JWT implementation) and user-keyed database tables.

### Browser session persistence — the hard problem

This is the most architecturally complex part of the Cloud Run migration, and the reason Phase 3 is non-trivial.

Locally, Playwright saves the authenticated LinkedIn browser session to `browser_profile/` on disk. This persists between runs because the filesystem is stable. Cloud Run containers are **stateless and ephemeral** — the local filesystem is wiped between invocations. A session saved during one run does not exist in the next.

**The solution: Cloud Storage as session store**

Each user's browser profile is stored in an isolated path in Cloud Storage:

```
gs://likarchive-sessions/{user_id}/browser_profile/
```

At the start of each Cloud Run invocation, the sync job:

1. Pulls the user's browser profile from Cloud Storage to the container's ephemeral local filesystem
2. Launches Playwright using that local profile
3. Runs the scrape
4. If the session was refreshed during the run, pushes the updated profile back to Cloud Storage before the container shuts down

**Access controls**
Each user's session folder must be readable only by that user's execution context. This is enforced via IAM conditions on the bucket, or by using separate per-user service accounts. A globally readable session bucket would be a significant security vulnerability.

**Session expiry — the unsolved problem**
LinkedIn sessions don't persist indefinitely. Periodic re-authentication is required, particularly if LinkedIn's bot detection flags unusual access patterns. Re-authentication via Playwright requires an interactive headed browser — which is not available in a headless Cloud Run container.

The planned approach is a **local re-auth step**: when a session expires, the user runs `save_session.py` locally (which opens a headed browser for manual login), then the refreshed `browser_profile/` is uploaded to Cloud Storage to replace the stale session. This is a deliberate architectural compromise — it keeps re-authentication out of the hosted environment where it would be technically complex, at the cost of requiring occasional local intervention from the user.

This limitation would need to be reconsidered for a true zero-local-setup multi-user product, potentially requiring a separate hosted re-auth flow with a virtual display (e.g. Xvfb) or a switch away from session-based auth entirely.
