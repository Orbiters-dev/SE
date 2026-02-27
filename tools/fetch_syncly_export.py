"""
Syncly Insight Posts Excel Export Tool
======================================
Playwright 기반 브라우저 자동화로 Syncly에서 Excel 다운로드.

사용법:
  # 1) 최초 1회: 수동 로그인 후 세션 저장
  python tools/fetch_syncly_export.py --login

  # 2) 이후: 저장된 세션으로 자동 다운로드
  python tools/fetch_syncly_export.py

  # 특정 URL 지정
  python tools/fetch_syncly_export.py --url "https://social.syncly.app/workspace/..."

  # 다운로드 폴더 지정
  python tools/fetch_syncly_export.py --output-dir "Data Storage/syncly"
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# WAT framework: project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

# Syncly default URL
DEFAULT_URL = (
    "https://social.syncly.app/workspace/696986d0b20b4ccc86695fcd"
    "/insight/posts?q=699b45af6f31e59c19aee721"
)

# Session state: stored in user's home directory (not in shared NAS)
STATE_DIR = Path.home() / ".syncly_state"
STATE_FILE = STATE_DIR / "browser_state.json"

# Default output directory
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "syncly"


def ensure_dirs():
    """Create necessary directories."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def do_login():
    """Open browser for manual Google login, then save session state."""
    from playwright.sync_api import sync_playwright

    ensure_dirs()

    print("[LOGIN] Opening browser for manual Google login...")
    print("[LOGIN] Please log in to Syncly, then close the browser window.")
    print()

    with sync_playwright() as p:
        # Use persistent context to save all cookies/localStorage
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR / "chrome_profile"),
            headless=False,
            channel="chromium",
            viewport={"width": 1280, "height": 800},
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(DEFAULT_URL, wait_until="domcontentloaded", timeout=60000)

        print("[LOGIN] Browser opened! Please:")
        print("  1. Log in with Google")
        print("  2. Wait until the data page fully loads")
        print("  3. Close the browser window (X button)")
        print()
        print("[LOGIN] Waiting for browser to close...")

        # Wait until user closes the browser manually
        try:
            page.wait_for_event("close", timeout=600000)  # 10 min max
        except Exception:
            pass

        # Save storage state (cookies + localStorage)
        try:
            context.storage_state(path=str(STATE_FILE))
            print(f"[LOGIN] Session saved to {STATE_FILE}")
        except Exception:
            # Context may already be closed, but persistent profile is saved
            print(f"[LOGIN] Session saved via persistent profile: {STATE_DIR / 'chrome_profile'}")

        try:
            context.close()
        except Exception:
            pass

    print("[LOGIN] Done! You can now run without --login flag.")


def do_export(url: str, output_dir: str):
    """Use saved session to download Excel from Syncly.

    Flow:
    1. Navigate to Syncly insight/posts page
    2. Find the export icon button (rightmost icon near "Posts" header)
    3. Click it to open "Export Posts" dialog
    4. Click "Export" button in the dialog
    5. Wait for file download
    """
    from playwright.sync_api import sync_playwright

    ensure_dirs()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    chrome_profile = STATE_DIR / "chrome_profile"
    if not chrome_profile.exists():
        print("[ERROR] No saved session found. Run with --login first.")
        print("  python tools/fetch_syncly_export.py --login")
        sys.exit(1)

    print(f"[EXPORT] Loading saved session...")
    print(f"[EXPORT] Target: {url}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(chrome_profile),
            headless=True,
            channel="chromium",
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to the page
        print("[EXPORT] Navigating to Syncly...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)  # SPA needs time to render

        # Check if we're still logged in
        page_text = page.locator("body").inner_text(timeout=5000)
        if "Continue with Google" in page_text or "Get started" in page_text[:100]:
            print("[ERROR] Session expired! Please run with --login again.")
            print("  python tools/fetch_syncly_export.py --login")
            context.close()
            sys.exit(1)

        print("[EXPORT] Page loaded successfully.")

        # Step 1: Find the export icon button
        # It's the rightmost icon-only button in the Posts header row (y ~ 140-200)
        export_icon = None
        buttons = page.locator("button:has(svg)").all()
        candidates = []
        for btn in buttons:
            try:
                if btn.is_visible():
                    box = btn.bounding_box()
                    if box and 140 < box["y"] < 200 and box["width"] < 50:
                        candidates.append((btn, box))
            except Exception:
                continue

        if candidates:
            # Rightmost small icon button in the row
            export_icon = max(candidates, key=lambda c: c[1]["x"])[0]

        if not export_icon:
            debug_path = output_path / "debug_screenshot.png"
            page.screenshot(path=str(debug_path), full_page=True)
            print(f"[ERROR] Could not find export icon button.")
            print(f"[DEBUG] Screenshot: {debug_path}")
            context.close()
            sys.exit(1)

        # Step 2: Click export icon to open dialog
        print("[EXPORT] Opening export dialog...")
        export_icon.click()
        page.wait_for_timeout(2000)

        # Step 3: Find and click "Export" button in the dialog
        export_btn = page.locator('button:has-text("Export")').last
        if not export_btn.is_visible(timeout=5000):
            debug_path = output_path / "debug_dialog.png"
            page.screenshot(path=str(debug_path))
            print(f"[ERROR] Export dialog did not appear.")
            print(f"[DEBUG] Screenshot: {debug_path}")
            context.close()
            sys.exit(1)

        # Step 4: Click Export and wait for download
        today = datetime.now().strftime("%Y-%m-%d")
        print("[EXPORT] Clicking Export button, waiting for download...")

        with page.expect_download(timeout=60000) as download_info:
            export_btn.click()

        download = download_info.value
        original_name = download.suggested_filename or f"syncly_export_{today}.xlsx"

        # Add date prefix
        if not original_name.startswith(today):
            save_name = f"{today}_{original_name}"
        else:
            save_name = original_name

        save_path = output_path / save_name
        download.save_as(str(save_path))

        file_size = save_path.stat().st_size
        print(f"[EXPORT] File saved: {save_path}")
        print(f"[EXPORT] Size: {file_size:,} bytes")

        context.close()

    print("[EXPORT] Done!")
    return str(save_path)


def main():
    parser = argparse.ArgumentParser(description="Syncly Excel Export Tool")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser for manual login and save session",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Syncly insight posts URL",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to save downloaded files",
    )

    args = parser.parse_args()

    if args.login:
        do_login()
    else:
        do_export(args.url, args.output_dir)


if __name__ == "__main__":
    main()
