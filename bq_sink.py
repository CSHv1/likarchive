"""
BigQuery mirror of the SQLite liked_posts table. No-op locally — only
exercised when K_SERVICE/CLOUD_RUN_JOB is set (same gating as db_sync.py/
cloud_auth.py), called from scraper.py's run_sync() after db_sync.upload_db().

Originally scoped as the optional Phase 8 "BigQuery sink" (for Looker), its
ingestion shape is reused here as the feeder for the RAG vector-search layer.

    push(db_path) — find rows new/updated since the last push (via
                    last_updated), load them into a staging table, then
                    MERGE into likarchive.liked_posts by post_url. MERGE
                    (not append) keeps the BigQuery table upsert-safe —
                    an appended duplicate row per update would silently
                    corrupt the vector index built on top of this table.
"""

import os

from google.cloud import bigquery

from db import get_connection

GCP_PROJECT = os.getenv("GCP_PROJECT")
BQ_DATASET = os.getenv("BQ_DATASET", "likarchive")
TABLE_ID = f"{GCP_PROJECT}.{BQ_DATASET}.liked_posts"
STAGING_TABLE_ID = f"{GCP_PROJECT}.{BQ_DATASET}.liked_posts_staging"

_COLUMNS = [
    "post_url", "author_name", "author_profile", "post_text",
    "post_timestamp", "post_date", "text_hash", "scraped_at", "last_updated",
]


def _client() -> bigquery.Client:
    return bigquery.Client(project=GCP_PROJECT)


def _ensure_table(client: bigquery.Client) -> None:
    schema = [bigquery.SchemaField(c, "STRING") for c in _COLUMNS]
    client.create_table(bigquery.Table(TABLE_ID, schema=schema), exists_ok=True)


def _watermark(client: bigquery.Client) -> str:
    """Most recent last_updated already pushed, or '' if the table is empty/new."""
    rows = list(client.query(f"SELECT MAX(last_updated) AS w FROM `{TABLE_ID}`").result())
    return rows[0]["w"] or ""


def push(db_path: str) -> None:
    client = _client()
    _ensure_table(client)
    watermark = _watermark(client)

    conn = get_connection(db_path)
    cols = ",".join(_COLUMNS)
    if watermark:
        rows = conn.execute(
            f"SELECT {cols} FROM liked_posts WHERE last_updated > ?", (watermark,)
        ).fetchall()
    else:
        rows = conn.execute(f"SELECT {cols} FROM liked_posts").fetchall()
    conn.close()

    if not rows:
        print("[bq_sink] No new/updated rows to push")
        return

    rows_json = [dict(r) for r in rows]
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[bigquery.SchemaField(c, "STRING") for c in _COLUMNS],
    )
    client.load_table_from_json(rows_json, STAGING_TABLE_ID, job_config=job_config).result()

    set_clause = ", ".join(f"{c} = S.{c}" for c in _COLUMNS if c != "post_url")
    values_clause = ", ".join(f"S.{c}" for c in _COLUMNS)
    client.query(f"""
        MERGE `{TABLE_ID}` T
        USING `{STAGING_TABLE_ID}` S
        ON T.post_url = S.post_url
        WHEN MATCHED THEN UPDATE SET {set_clause}
        WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({values_clause})
    """).result()

    print(f"[bq_sink] Pushed {len(rows)} new/updated rows to {TABLE_ID}")
