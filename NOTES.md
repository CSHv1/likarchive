# Likarchive — Dev Notes

## Current state (as of first session)

### What works
- LinkedIn login via email/password (.env) ✅
- Navigation to `/my-items/saved-posts/` ✅
- Infinite scroll loop with stale-height detection ✅
- SQLite schema + MD5-hash upsert logic ✅
- Sync logging (start/end/counts/errors) ✅
- Daily scheduler via `schedule` library ✅

### What doesn't work yet
- DOM extraction — selectors return 0 posts because they were written for the activity/likes feed, not the saved posts page
- Seen=0 new=0 on every run until selectors are fixed

---

## Immediate next task — fix DOM selectors

The saved posts page (`/my-items/saved-posts/`) has a different HTML structure to the likes activity feed the selectors were originally written for.

**Steps:**
1. Run `python scraper.py` with `HEADLESS=false`
2. Check the `page_dump.html` dumped to the project root
3. Find a saved post card in the HTML — search for text you know is in one of your saved posts
4. Identify the correct selectors for:
   - The post card container (currently `.feed-shared-update-v2` etc.)
   - Post URL anchor
   - Author name
   - Author profile URL
   - Post body text
   - Timestamp
5. Update the four extraction functions in `scraper.py`

---

## Known gotchas

- **Python 3.9 on Mac** — use `Optional[str]` from `typing`, not `str | None` syntax (requires 3.10+). Currently scraper.py still has `str | None` in two function signatures — needs fixing.
- **LinkedIn bot detection** — keep `HEADLESS=false` initially. First login on a new automated session may trigger a security checkpoint. Solve it manually once in the browser window.
- **Session persistence** — currently no cookie persistence between runs, so LinkedIn re-authenticates on every sync. This increases detection risk over time. Consider saving browser storage state to a file after first login for future runs.
- **`SAVES_URL` variable missing** — scraper.py still references `SAVES_URL` in the function body but the constant is named `LIKES_URL` at the top of the file. Rename to `SAVES_URL` to fix the `NameError`.

---

## Architecture notes

- Target page: `https://www.linkedin.com/my-items/saved-posts/`
- Primary key: `post_url` (contains LinkedIn activity URN — stable identifier)
- Change detection: MD5 hash of `post_text` — upsert if hash differs, skip if identical
- No ORM — raw sqlite3 for simplicity, easy to swap to SQLAlchemy or BigQuery later

---

## Session log

**Session 1**
- Built scraper.py, db.py, scheduler.py from scratch
- Confirmed login works
- Confirmed scroll navigation works
- Discovered selectors don't match saved posts DOM — seen=0
- Added page_dump.html debug write to diagnose
- Identified Python 3.9 type hint incompatibility (`str | None`)
- Handed off to Claude Code for selector fixing
