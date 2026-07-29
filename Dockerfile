# Official Playwright image ships Python 3.11 + Playwright + Chromium on Ubuntu Jammy.
# Using this avoids manual system-dep installation (playwright install-deps fails on Debian Trixie).
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install remaining Python deps (playwright already in base image; pip pins the version)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only — credentials, DB, and browser profile stay outside
COPY scraper.py db.py tagger.py app.py scheduler.py query.py save_session.py db_sync.py cloud_auth.py ./
COPY templates/ ./templates/

# Container defaults — all can be overridden at docker run / Cloud Run env vars.
# DB and auth state live under /data so a single volume mount covers both.
# STATE_PATH is a portable Playwright storage_state() JSON export (see
# save_session.py) — the OS-encrypted persistent profile does not survive
# the move from macOS to this Linux image, so that is not used at runtime.
ENV HEADLESS=true
ENV DB_PATH=/data/linkedin_likes.db
ENV STATE_PATH=/data/auth_state.json

EXPOSE 8080

# Default: single sync run (Cloud Scheduler triggers this on a schedule).
# GUI service: override CMD with gunicorn in docker run or Cloud Run config.
CMD ["python", "scraper.py"]
