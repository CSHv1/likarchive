"""
GCS persistence for the SQLite DB. No-op locally — only exercised when
K_SERVICE is set (i.e. running on Cloud Run), so local runs are unaffected.

    download_db(local_path) — pull the DB from GCS before a sync run, falling
                               back to a fresh local init if it doesn't exist yet.
    upload_db(local_path)   — push the (possibly updated) DB back to GCS after
                               a sync run, in run_sync()'s finally block.
"""

import os

GCS_BUCKET = os.getenv("GCS_BUCKET", "likarchive-db")
GCS_DB_BLOB = os.getenv("GCS_DB_BLOB", "linkedin_likes.db")
GCP_PROJECT = os.getenv("GCP_PROJECT")


def _bucket():
    from google.cloud import storage
    client = storage.Client(project=GCP_PROJECT)
    return client.bucket(GCS_BUCKET)


def download_db(local_path: str) -> None:
    blob = _bucket().blob(GCS_DB_BLOB)
    if blob.exists():
        print(f"[db_sync] Downloading gs://{GCS_BUCKET}/{GCS_DB_BLOB} -> {local_path}")
        blob.download_to_filename(local_path)
    else:
        print(f"[db_sync] No existing DB at gs://{GCS_BUCKET}/{GCS_DB_BLOB} — starting fresh")


def upload_db(local_path: str) -> None:
    if not os.path.isfile(local_path):
        print(f"[db_sync] Local DB '{local_path}' not found — skipping upload")
        return
    print(f"[db_sync] Uploading {local_path} -> gs://{GCS_BUCKET}/{GCS_DB_BLOB}")
    _bucket().blob(GCS_DB_BLOB).upload_from_filename(local_path)
