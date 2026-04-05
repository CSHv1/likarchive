# Likarchive — Claude Code Instructions

## What this project is

A local Python/Playwright scraper that logs into LinkedIn, navigates to the user's saved posts page (`/my-items/saved-posts/`), paginates through the full list via infinite scroll, and stores extracted posts in a local SQLite database. Daily auto-sync via a scheduler. GCP Cloud Run deployment planned for a later phase.

## File structure

```
scraper.py      — Playwright login, scroll loop, DOM extraction, main entry point
db.py           — SQLite schema, upsert logic, sync logging, FTS5, tag helpers
scheduler.py    — Daily cron wrapper around scraper.run_sync()
query.py        — CLI browser/search: recent posts, FTS search, author filter
tagger.py       — Claude API auto-tagger (claude-haiku-4-5-20251001)
requirements.txt
.env.example    — Copy to .env and fill in credentials
CLAUDE.md       — This file
NOTES.md        — Current state, known issues, next steps
```

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in credentials
python scraper.py      # one-off sync
python scheduler.py    # daily auto-sync (runs immediately, then 08:00 daily)
```

## Environment variables (.env)

| Variable | Default | Description |
|---|---|---|
| `LINKEDIN_EMAIL` | — | LinkedIn login email |
| `LINKEDIN_PASSWORD` | — | LinkedIn password |
| `DB_PATH` | `linkedin_likes.db` | SQLite file path |
| `HEADLESS` | `false` | Set true once login confirmed working headful |
| `SCROLL_PAUSE_MS` | `2000` | Pause between scrolls in ms |
| `MAX_POSTS` | `0` | Cap per sync run — 0 = unlimited |
| `ANTHROPIC_API_KEY` | — | Claude API key (required for `tagger.py`) |

## Database schema

**liked_posts**
- `post_url` TEXT UNIQUE — primary key, direct LinkedIn post URL (activity URN)
- `author_name` TEXT
- `author_profile` TEXT — URL to author's LinkedIn profile
- `post_text` TEXT — full post body
- `post_timestamp` TEXT — when post was published
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

- **Auth**: username + password via .env, loaded by python-dotenv. Credentials never hardcoded.
- **Deduplication**: `post_url` is the primary key. On each sync, post text is MD5-hashed and compared — insert if new, overwrite if hash differs, skip if identical.
- **Scroll**: height-based stale detection — stops after 4 consecutive scrolls with no DOM height change.
- **Python version**: use `Optional[str]` / `Optional[dict]` (typing module) not `str | None` — target is Python 3.9 compatibility on Mac.

## Confirmed working selectors (as of 2026-04-05)

DOM selectors were rewritten after inspecting `page_dump.html` from the live saved posts page. All five are confirmed working (`seen=10 new=10` on first run).

| Target | Selector |
|---|---|
| Card container | `[data-chameleon-result-urn*="urn:li:activity"]` |
| Post URL | `a[href*="/feed/update/"][data-test-app-aware-link]` |
| Author name | `.entity-result__content-actor span[aria-hidden="true"]` |
| Author profile | `.entity-result__content-actor a[href*="/in/"]` |
| Post text | `p.entity-result__content-summary--3-lines` |
| Timestamp | `p.t-black--light.t-12 span[aria-hidden="true"]` (relative, e.g. "3w") |

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

- [x] Fix DOM selectors for `/my-items/saved-posts/`
- [x] Remove debug `page_dump.html` write from `scrape_saves()` — selectors confirmed
- [ ] Run full sync with `MAX_POSTS=0` to archive all saved posts
- [x] Rename `scrape_likes` → `scrape_saves` for clarity
- [x] Simple read UI — `query.py` CLI (browse, FTS search, author filter)
- [x] Full-text search — SQLite FTS5 virtual table (`posts_fts`)
- [x] Claude API integration — `tagger.py` auto-tags posts via `claude-haiku-4-5-20251001`
- [ ] GCP Cloud Run deployment + Cloud Scheduler for hosted daily sync
- [ ] BigQuery sink for Looker reporting layer
