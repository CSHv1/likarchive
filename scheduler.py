"""
Daily sync scheduler.
Runs scraper.run_sync() once immediately on start, then every 24h.

Usage:
    python scheduler.py

To run in the background (Mac/Linux):
    nohup python scheduler.py >> sync.log 2>&1 &
"""

import schedule
import time
from datetime import datetime, timezone

from scraper import run_sync

SYNC_TIME = "06:00"  # Local time — adjust to taste


def job():
    print(f"\n[scheduler] Triggering scheduled sync at {datetime.now(timezone.utc).isoformat()}")
    try:
        run_sync()
    except Exception as e:
        print(f"[scheduler] Sync failed: {e}")


if __name__ == "__main__":
    print(f"[scheduler] Starting. Daily sync scheduled at {SYNC_TIME} local time.")
    print("[scheduler] Running initial sync now...")
    job()

    schedule.every().day.at(SYNC_TIME).do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)
