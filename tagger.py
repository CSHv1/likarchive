"""
tagger.py — Auto-tag saved posts using the Claude API.

Usage:
    python tagger.py              # tag all untagged posts
    python tagger.py --rerun      # retag every post regardless of existing tags
    python tagger.py --limit 20   # process at most 20 posts
"""

import argparse
import json
import os
import time

import anthropic
from dotenv import load_dotenv

from db import get_connection, init_db, set_post_tags

load_dotenv()

DB_PATH          = os.getenv("DB_PATH", "linkedin_likes.db")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = "claude-haiku-4-5-20251001"
SLEEP_BETWEEN_CALLS = 0.5  # seconds

TAG_SYSTEM = (
    "You are a concise topic tagger for LinkedIn posts. "
    "Given a post, return a JSON array of 3-5 short, lowercase topic tags. "
    "Tags should be single words or short phrases (e.g. \"ai\", \"leadership\", "
    "\"startup advice\"). Return only the JSON array, no other text."
)


def fetch_untagged(conn, limit: int, rerun: bool) -> list:
    if rerun:
        query = "SELECT post_url, author_name, post_text FROM liked_posts"
        params = ()
    else:
        query = """
            SELECT lp.post_url, lp.author_name, lp.post_text
            FROM liked_posts lp
            WHERE NOT EXISTS (
                SELECT 1 FROM post_tags pt WHERE pt.post_url = lp.post_url
            )
        """
        params = ()

    rows = conn.execute(query, params).fetchall()
    if limit:
        rows = rows[:limit]
    return rows


def tag_post(client: anthropic.Anthropic, author_name: str, post_text: str) -> list:
    """Call Claude to get tags for a single post. Returns a list of tag strings."""
    user_content = (
        f"Author: {author_name or '(unknown)'}\n\n"
        f"Post:\n{post_text or '(no text)'}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=TAG_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "[]")

    try:
        tags = json.loads(text)
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
    except json.JSONDecodeError:
        print(f"  [warn] Could not parse tags JSON: {text!r}")

    return []


def run(args: argparse.Namespace) -> None:
    if not ANTHROPIC_API_KEY:
        raise SystemExit(
            "ANTHROPIC_API_KEY not set. Add it to your .env file."
        )

    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    posts = fetch_untagged(conn, limit=args.limit, rerun=args.rerun)
    print(f"[tagger] {len(posts)} post(s) to tag (model={MODEL})\n")

    tagged = 0
    for i, row in enumerate(posts, 1):
        post_url    = row["post_url"]
        author_name = row["author_name"] or ""
        post_text   = row["post_text"] or ""

        print(f"[{i}/{len(posts)}] {author_name or post_url[:60]}")

        try:
            tags = tag_post(client, author_name, post_text)
            if tags:
                set_post_tags(conn, post_url, tags)
                conn.commit()
                print(f"  tags: {tags}")
                tagged += 1
            else:
                print("  (no tags returned)")
        except Exception as e:
            print(f"  [error] {e}")

        if i < len(posts):
            time.sleep(SLEEP_BETWEEN_CALLS)

    conn.close()
    print(f"\n[tagger] Done — tagged {tagged}/{len(posts)} posts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-tag Likarchive posts with Claude")
    parser.add_argument("--rerun",  action="store_true", help="Retag all posts, not just untagged")
    parser.add_argument("--limit",  metavar="N", type=int, default=0, help="Max posts to process (0 = all)")
    run(parser.parse_args())
