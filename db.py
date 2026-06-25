import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Optional


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Create tables if they don't exist."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS liked_posts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                post_url        TEXT UNIQUE NOT NULL,
                author_name     TEXT,
                author_profile  TEXT,
                post_text       TEXT,
                post_timestamp  TEXT,
                text_hash       TEXT,
                scraped_at      TEXT NOT NULL,
                last_updated    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                posts_seen  INTEGER DEFAULT 0,
                posts_new   INTEGER DEFAULT 0,
                posts_updated INTEGER DEFAULT 0,
                posts_skipped INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'running',
                error       TEXT
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts
            USING fts5(post_url UNINDEXED, author_name, post_text,
                       content='liked_posts', content_rowid='id')
        """)
        conn.execute("INSERT INTO posts_fts(posts_fts) VALUES('rebuild')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_tags (
                post_url TEXT NOT NULL REFERENCES liked_posts(post_url),
                tag_id   INTEGER NOT NULL REFERENCES tags(id),
                PRIMARY KEY (post_url, tag_id)
            )
        """)
        conn.commit()


def hash_text(text: str) -> str:
    return hashlib.md5((text or "").strip().encode("utf-8")).hexdigest()


def upsert_post(conn: sqlite3.Connection, post: dict) -> str:
    """
    Insert or update a post based on post_url.
    Returns: 'new' | 'updated' | 'skipped'
    """
    now = datetime.now(timezone.utc).isoformat()
    new_hash = hash_text(post.get("post_text", ""))

    existing = conn.execute(
        "SELECT id, text_hash FROM liked_posts WHERE post_url = ?",
        (post["post_url"],)
    ).fetchone()

    if existing is None:
        cursor = conn.execute("""
            INSERT INTO liked_posts
                (post_url, author_name, author_profile, post_text, post_timestamp,
                 text_hash, scraped_at, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post["post_url"],
            post.get("author_name"),
            post.get("author_profile"),
            post.get("post_text"),
            post.get("post_timestamp"),
            new_hash,
            now,
            now,
        ))
        conn.execute(
            "INSERT INTO posts_fts(rowid, post_url, author_name, post_text) VALUES (?, ?, ?, ?)",
            (cursor.lastrowid, post["post_url"], post.get("author_name"), post.get("post_text"))
        )
        return "new"

    if existing["text_hash"] != new_hash:
        row_id = existing["id"]
        conn.execute(
            "INSERT INTO posts_fts(posts_fts, rowid, post_url, author_name, post_text) VALUES('delete', ?, ?, ?, ?)",
            (row_id, post["post_url"], post.get("author_name"), post.get("post_text"))
        )
        conn.execute("""
            UPDATE liked_posts
            SET author_name    = ?,
                author_profile = ?,
                post_text      = ?,
                post_timestamp = ?,
                text_hash      = ?,
                last_updated   = ?
            WHERE post_url = ?
        """, (
            post.get("author_name"),
            post.get("author_profile"),
            post.get("post_text"),
            post.get("post_timestamp"),
            new_hash,
            now,
            post["post_url"],
        ))
        conn.execute(
            "INSERT INTO posts_fts(rowid, post_url, author_name, post_text) VALUES (?, ?, ?, ?)",
            (row_id, post["post_url"], post.get("author_name"), post.get("post_text"))
        )
        return "updated"

    return "skipped"


def start_sync_log(conn: sqlite3.Connection) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO sync_log (started_at, status) VALUES (?, 'running')", (now,)
    )
    conn.commit()
    return cursor.lastrowid


def create_tag(conn: sqlite3.Connection, name: str) -> int:
    """Insert tag if it doesn't exist; return its id."""
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    return row["id"]


def set_post_tags(conn: sqlite3.Connection, post_url: str, tag_names: list) -> None:
    """Replace all tags for a post with the given list."""
    conn.execute("DELETE FROM post_tags WHERE post_url = ?", (post_url,))
    for name in tag_names:
        tag_id = create_tag(conn, name.strip().lower())
        conn.execute(
            "INSERT OR IGNORE INTO post_tags (post_url, tag_id) VALUES (?, ?)",
            (post_url, tag_id)
        )


def finish_sync_log(conn: sqlite3.Connection, log_id: int, counts: dict, error: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        UPDATE sync_log
        SET finished_at    = ?,
            posts_seen     = ?,
            posts_new      = ?,
            posts_updated  = ?,
            posts_skipped  = ?,
            status         = ?,
            error          = ?
        WHERE id = ?
    """, (
        now,
        counts.get("seen", 0),
        counts.get("new", 0),
        counts.get("updated", 0),
        counts.get("skipped", 0),
        "error" if error else "success",
        error,
        log_id,
    ))
    conn.commit()
