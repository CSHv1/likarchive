import os
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
from db import get_connection, init_db

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "linkedin_likes.db")

if os.getenv("K_SERVICE"):
    from db_sync import download_db
    download_db(DB_PATH)

init_db(DB_PATH)


def _build_posts_query(q, tags, author, date_from, date_to, for_count=False):
    select = "SELECT COUNT(*)" if for_count else (
        "SELECT lp.post_url, lp.author_name, lp.author_profile, "
        "lp.post_text, lp.post_timestamp, lp.post_date, lp.scraped_at"
    )
    params = []

    if q:
        fts_q = '"' + q.replace('"', '""') + '"'
        from_clause = "FROM posts_fts JOIN liked_posts lp ON posts_fts.rowid = lp.id"
        where = "WHERE posts_fts MATCH ?"
        params.append(fts_q)
        order = "ORDER BY rank"
    else:
        from_clause = "FROM liked_posts lp"
        where = "WHERE 1=1"
        order = "ORDER BY lp.post_date DESC"

    if author:
        where += " AND lp.author_name = ?"
        params.append(author)

    for tag in tags:
        where += (
            " AND lp.post_url IN ("
            "SELECT pt.post_url FROM post_tags pt "
            "JOIN tags t ON pt.tag_id = t.id WHERE t.name = ?)"
        )
        params.append(tag)

    if date_from:
        where += " AND lp.post_date >= ?"
        params.append(date_from)

    if date_to:
        where += " AND lp.post_date <= ?"
        params.append(date_to)

    sql = f"{select} {from_clause} {where}"
    if not for_count:
        sql += f" {order}"
    return sql, params


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/posts")
def get_posts():
    q         = request.args.get("q", "").strip()
    tags      = request.args.getlist("tags")
    author    = request.args.get("author", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to", "").strip()
    page      = max(1, int(request.args.get("page", 1)))
    per_page  = min(50, max(1, int(request.args.get("per_page", 20))))
    offset    = (page - 1) * per_page

    conn = get_connection(DB_PATH)
    try:
        count_sql, count_params = _build_posts_query(
            q, tags, author, date_from, date_to, for_count=True)
        total = conn.execute(count_sql, count_params).fetchone()[0]

        data_sql, data_params = _build_posts_query(
            q, tags, author, date_from, date_to, for_count=False)
        data_sql += " LIMIT ? OFFSET ?"
        data_params += [per_page, offset]

        try:
            rows = conn.execute(data_sql, data_params).fetchall()
        except Exception:
            return jsonify({"posts": [], "total": 0, "page": page,
                            "per_page": per_page, "pages": 0})

        posts = []
        for row in rows:
            post_tags = conn.execute(
                "SELECT t.name FROM tags t "
                "JOIN post_tags pt ON t.id = pt.tag_id "
                "WHERE pt.post_url = ? ORDER BY t.name",
                (row["post_url"],)
            ).fetchall()
            posts.append({
                "post_url":      row["post_url"],
                "author_name":   row["author_name"] or "",
                "author_profile": row["author_profile"] or "",
                "post_text":     row["post_text"] or "",
                "post_timestamp": row["post_timestamp"] or "",
                "post_date":     row["post_date"] or "",
                "scraped_at":    (row["scraped_at"] or "")[:10],
                "tags":          [t["name"] for t in post_tags],
            })
    finally:
        conn.close()

    return jsonify({
        "posts":    posts,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, -(-total // per_page)),
    })


@app.route("/api/tags")
def get_tags():
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT t.name, COUNT(*) as count FROM tags t "
        "JOIN post_tags pt ON t.id = pt.tag_id "
        "GROUP BY t.name ORDER BY count DESC, t.name"
    ).fetchall()
    conn.close()
    return jsonify([{"name": r["name"], "count": r["count"]} for r in rows])


@app.route("/api/authors")
def get_authors():
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT author_name, COUNT(*) as count FROM liked_posts "
        "WHERE author_name IS NOT NULL AND author_name != '' "
        "GROUP BY author_name ORDER BY count DESC, author_name"
    ).fetchall()
    conn.close()
    return jsonify([{"name": r["author_name"], "count": r["count"]} for r in rows])


@app.route("/api/sync_status")
def get_sync_status():
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT started_at, finished_at, status, error FROM sync_log "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"status": "none"})
    return jsonify({
        "started_at":  row["started_at"],
        "finished_at": row["finished_at"],
        "status":      row["status"],
        "error":       row["error"],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
