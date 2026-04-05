"""
One-time utility: open a headed persistent browser context, let you log in
manually (handles 2FA, CAPTCHA, etc.), then close — the full browser profile
(cookies, localStorage, etc.) is written automatically to BROWSER_PROFILE/.

Usage:
    python save_session.py

After running, the browser_profile/ directory will contain your session.
scraper.py will load it automatically on subsequent runs.
"""

import os

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

PROFILE_DIR = os.getenv("BROWSER_PROFILE", "browser_profile")


def main() -> None:
    print("[save_session] Opening headed browser with persistent profile...")
    print("[save_session] Log in to LinkedIn, complete any 2FA / CAPTCHA,")
    print("               and wait until you see your LinkedIn feed.")
    print()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        input("[save_session] Press Enter here once you are logged in and on the feed... ")

        context.close()  # profile written to disk automatically

    print(f"[save_session] Browser profile saved to '{PROFILE_DIR}/'")
    print("[save_session] You can now run: python scraper.py")


if __name__ == "__main__":
    main()
