"""
query.py — CLI browser/search for the Likarchive SQLite database.

Usage:
    python query.py                      # 20 most-recent posts
    python query.py --search "keyword"   # FTS search across text + author
    python query.py --author "name"      # filter by author (LIKE match)
    python query.py --limit 50           # change result count (default 20)
"""

import argparse
import os
import textwrap

from dotenv import load_dotenv

from db import get_connection, init_db

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "linkedin_likes.db")


def fmt_post(row) -> str:
    author    = row["author_name"] or "(unknown)"
    url       = row["post_url"] or ""
    ts        = row["post_timestamp"] or ""
    text      = (row["post_text"] or "").strip()
    preview   = textwrap.shorten(text, width=200, placeholder="…")

    lines = [
        f"Author : {author}",
        f"URL    : {url}",
    ]
    if ts:
        lines.append(f"When   : {ts}")
    if preview:
        lines.append(f"Text   : {preview}")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    limit = args.limit

    if args.search:
        rows = conn.execute(
            """
            SELECT lp.post_url, lp.author_name, lp.post_text, lp.post_timestamp
            FROM posts_fts
            JOIN liked_posts lp ON posts_fts.rowid = lp.id
            WHERE posts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (args.search, limit)
        ).fetchall()
        print(f"[search] '{args.search}' — {len(rows)} result(s)\n")

    elif args.author:
        rows = conn.execute(
            """
            SELECT post_url, author_name, post_text, post_timestamp
            FROM liked_posts
            WHERE author_name LIKE ?
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (f"%{args.author}%", limit)
        ).fetchall()
        print(f"[author] '{args.author}' — {len(rows)} result(s)\n")

    else:
        rows = conn.execute(
            """
            SELECT post_url, author_name, post_text, post_timestamp
            FROM liked_posts
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        print(f"[recent] {len(rows)} post(s)\n")

    conn.close()

    sep = "-" * 72
    for row in rows:
        print(sep)
        print(fmt_post(row))
    if rows:
        print(sep)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Browse / search Likarchive posts")
    parser.add_argument("--search", metavar="QUERY", help="Full-text search")
    parser.add_argument("--author", metavar="NAME",  help="Filter by author name (LIKE)")
    parser.add_argument("--limit",  metavar="N", type=int, default=20, help="Max results (default 20)")
    run(parser.parse_args())
