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

| Variable | Description |
|---|---|
| `LINKEDIN_EMAIL` | Your LinkedIn login email |
| `LINKEDIN_PASSWORD` | Your LinkedIn password |
| `ANTHROPIC_API_KEY` | Claude API key — only needed for `tagger.py` |
| `DB_PATH` | SQLite file path (default: `linkedin_likes.db`) |
| `HEADLESS` | `false` while getting started; `true` once confirmed working |
| `SCROLL_PAUSE_MS` | Pause between scrolls in ms (increase to 3000–4000 if rate-limited) |
| `MAX_POSTS` | Posts to fetch per sync run — `0` for unlimited |

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

## Auto-tagging with Claude

`tagger.py` calls the Claude API to generate 3–5 topic tags per post.

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

| Symptom | Fix |
|---|---|
| `seen=0 new=0` on every run | LinkedIn DOM may have changed — selectors need updating in `scraper.py` |
| Login fails / `login_failed.png` created | Open browser headfully and solve CAPTCHA manually, then re-run `save_session.py` |
| Rate limited (scroll stops early) | Increase `SCROLL_PAUSE_MS` to 3000–5000 in `.env` |
| `ANTHROPIC_API_KEY not set` | Add your key to `.env` before running `tagger.py` |
| FTS returns no results | Run `INSERT INTO posts_fts(posts_fts) VALUES('rebuild');` in sqlite3 to rebuild the index |
