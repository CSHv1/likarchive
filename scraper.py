import os
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from db import get_connection, init_db, upsert_post, start_sync_log, finish_sync_log

load_dotenv()

DB_PATH           = os.getenv("DB_PATH", "linkedin_likes.db")
HEADLESS          = os.getenv("HEADLESS", "false").lower() == "true"
SCROLL_PAUSE_MS   = int(os.getenv("SCROLL_PAUSE_MS", "2000"))
MAX_POSTS         = int(os.getenv("MAX_POSTS", "0"))
BROWSER_PROFILE   = os.getenv("BROWSER_PROFILE", "browser_profile")

SAVES_URL = "https://www.linkedin.com/my-items/saved-posts/?savedPostType=ALL"


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_post_url(card) -> Optional[str]:
    anchor = card.query_selector('a[href*="/feed/update/"][data-test-app-aware-link]')
    if anchor:
        return (anchor.get_attribute("href") or "").split("?")[0]
    return None


def extract_author(card) -> Tuple[str, str]:
    """Returns (author_name, author_profile_url)."""
    name = ""
    profile_url = ""
    profile_el = card.query_selector(
        '.entity-result__content-actor a[href*="/in/"],'
        '.entity-result__content-actor a[href*="/company/"]'
    )
    if profile_el:
        profile_url = (profile_el.get_attribute("href") or "").split("?")[0]
        # Name is in <span dir="ltr"> inside the anchor (no aria-hidden attribute).
        name_span = profile_el.query_selector('span[dir="ltr"]')
        if name_span:
            name = name_span.inner_text().strip()
    return name, profile_url


def extract_post_text(card) -> str:
    el = card.query_selector("p.entity-result__content-summary--3-lines")
    return el.inner_text().strip() if el else ""


def extract_timestamp(card) -> str:
    # Timestamp span is a plain direct child of p.t-black--light.t-12 (no aria attribute).
    for sel in ('p.t-black--light.t-12 > span', 'p.t-black--light > span'):
        el = card.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text.split("•")[0].strip()
    return ""


def parse_card(card) -> Optional[dict]:
    post_url = extract_post_url(card)
    if not post_url:
        return None  # Can't identify post — skip

    author_name, author_profile = extract_author(card)
    post_text    = extract_post_text(card)
    post_ts      = extract_timestamp(card)

    return {
        "post_url":       post_url,
        "author_name":    author_name,
        "author_profile": author_profile,
        "post_text":      post_text,
        "post_timestamp": post_ts,
    }


# ---------------------------------------------------------------------------
# Scroll + scrape
# ---------------------------------------------------------------------------

def scrape_saves(page, conn, log_id: int) -> dict:
    counts = {"seen": 0, "new": 0, "updated": 0, "skipped": 0}
    seen_urls: set[str] = set()

    print(f"[scraper] Navigating to saved posts: {SAVES_URL}")
    page.goto(SAVES_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    last_height = 0
    stale_scrolls = 0
    MAX_STALE = 4  # Stop after N scrolls with no new content

    while True:
        # Collect all post cards currently in the DOM
        cards = page.query_selector_all('[data-chameleon-result-urn*="urn:li:activity"]')

        for card in cards:
            post = parse_card(card)
            if not post or post["post_url"] in seen_urls:
                continue

            seen_urls.add(post["post_url"])
            counts["seen"] += 1

            result = upsert_post(conn, post)
            counts[result] += 1

            print(
                f"  [{result.upper():7s}] {post['author_name'] or '(unknown)'} — "
                f"{post['post_url']}"
            )

            if MAX_POSTS and counts["seen"] >= MAX_POSTS:
                print(f"[scraper] MAX_POSTS={MAX_POSTS} reached. Stopping.")
                conn.commit()
                return counts

        conn.commit()  # Commit after each scroll batch

        # Scroll down
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            stale_scrolls += 1
            if stale_scrolls >= MAX_STALE:
                print("[scraper] No new content after scrolling. Reached end of feed.")
                break
        else:
            stale_scrolls = 0

        last_height = new_height
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SCROLL_PAUSE_MS)

    return counts


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_sync() -> None:
    print(f"\n{'='*60}")
    print(f"[sync] Starting at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    log_id = start_sync_log(conn)

    error_msg = None
    counts = {"seen": 0, "new": 0, "updated": 0, "skipped": 0}

    try:
        with sync_playwright() as p:
            if not os.path.isdir(BROWSER_PROFILE):
                raise RuntimeError(
                    f"No browser profile found at '{BROWSER_PROFILE}'. "
                    "Run `python save_session.py` first to log in and save your session."
                )

            print(f"[auth] Loading browser profile from '{BROWSER_PROFILE}/'")
            context = p.chromium.launch_persistent_context(
                user_data_dir=BROWSER_PROFILE,
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            counts = scrape_saves(page, conn, log_id)

            context.close()

    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"[sync] ERROR: {e}")

    finally:
        finish_sync_log(conn, log_id, counts, error=error_msg)
        conn.close()

    print(f"\n[sync] Done — seen={counts['seen']} new={counts['new']} "
          f"updated={counts['updated']} skipped={counts['skipped']}")


if __name__ == "__main__":
    run_sync()
