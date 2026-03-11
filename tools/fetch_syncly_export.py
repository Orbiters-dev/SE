"""
Syncly Insight Posts Excel Export Tool
======================================
Playwright 기반 브라우저 자동화로 Syncly에서 CSV 다운로드.
100개 제한 우회를 위해 날짜를 30일씩 끊어서 export 후 합침.

사용법:
  # 1) 최초 1회: 수동 로그인 후 세션 저장
  python tools/fetch_syncly_export.py --login

  # 2) 이후: 저장된 세션으로 자동 다운로드 (30일 chunk)
  python tools/fetch_syncly_export.py --region us
  python tools/fetch_syncly_export.py --region jp

  # 특정 URL 지정
  python tools/fetch_syncly_export.py --url "https://social.syncly.app/workspace/..."

  # chunk 크기 조정 (기본 30일)
  python tools/fetch_syncly_export.py --region us --chunk-days 14
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# WAT framework: project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

# Syncly URLs per region
REGION_URLS = {
    "us": (
        "https://social.syncly.app/workspace/696986d0b20b4ccc86695fcd"
        "/insight/posts?q=6976fe6546f8775e88ca86b8"
    ),
    "jp": (
        "https://social.syncly.app/workspace/696986d0b20b4ccc86695fcd"
        "/insight/posts?q=69a941f3208fdb401a8043fb"
    ),
}
DEFAULT_URL = REGION_URLS["us"]

# Session state: stored in user's home directory (not in shared NAS)
STATE_DIR = Path.home() / ".syncly_state"
STATE_FILE = STATE_DIR / "browser_state.json"

# Default output directory
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "syncly"

TOTAL_DAYS = 90  # Syncly default: last 90 days


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

        try:
            page.wait_for_event("close", timeout=600000)
        except Exception:
            pass

        try:
            context.storage_state(path=str(STATE_FILE))
            print(f"[LOGIN] Session saved to {STATE_FILE}")
        except Exception:
            print(f"[LOGIN] Session saved via persistent profile: {STATE_DIR / 'chrome_profile'}")

        try:
            context.close()
        except Exception:
            pass

    print("[LOGIN] Done! You can now run without --login flag.")


def _set_date_filter(page, start_date, end_date, output_path):
    """Syncly 날짜 필터를 start_date ~ end_date로 설정.

    UI 구조 (스크린샷 기반):
    1. "Last 90 days" 버튼 클릭 → 캘린더 팝업
    2. 상단 날짜 입력 필드: MM / DD / YYYY - MM / DD / YYYY
    3. "Update" 버튼 클릭
    """
    # Click "Custom" date filter button (Syncly UI updated 2026-03)
    date_btn = page.locator('button:has-text("Custom")').first
    if not date_btn.is_visible(timeout=3000):
        # Fallback: try old selectors
        date_btn = page.locator('button:has-text("days"), button:has-text("Last")').first
    date_btn.click()
    page.wait_for_timeout(1500)

    # Date inputs: M, D, YYYY x2 (skip first input which is search bar)
    inputs = page.locator('input').all()
    date_inputs = [inp for inp in inputs if inp.is_visible() and inp.get_attribute('placeholder') in ('M', 'D', 'YYYY')]

    if len(date_inputs) >= 6:
        for inp, val in [
            (date_inputs[0], f"{start_date.month}"),
            (date_inputs[1], f"{start_date.day}"),
            (date_inputs[2], f"{start_date.year}"),
            (date_inputs[3], f"{end_date.month}"),
            (date_inputs[4], f"{end_date.day}"),
            (date_inputs[5], f"{end_date.year}"),
        ]:
            inp.click()
            inp.press("Control+a")
            inp.fill(val)
            page.wait_for_timeout(200)
    else:
        debug_path = output_path / "debug_date_filter.png"
        page.screenshot(path=str(debug_path))
        print(f"[WARN] Could not find date inputs ({len(date_inputs)} found)")
        print(f"[DEBUG] Screenshot: {debug_path}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return False

    # Click Update button
    update_btn = page.locator('button:has-text("Update")').first
    update_btn.click()
    page.wait_for_timeout(5000)  # Wait for data to reload
    return True


def _do_single_export(page, output_path):
    """현재 필터 상태에서 export 버튼 클릭 → CSV 다운로드. 경로 반환."""
    # Find the export icon button
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
        export_icon = max(candidates, key=lambda c: c[1]["x"])[0]

    if not export_icon:
        debug_path = output_path / "debug_screenshot.png"
        page.screenshot(path=str(debug_path), full_page=True)
        print(f"[ERROR] Could not find export icon button.")
        print(f"[DEBUG] Screenshot: {debug_path}")
        return None

    # Click export icon to open dialog
    export_icon.click()
    page.wait_for_timeout(2000)

    # Find and click "Export" button in the dialog
    export_btn = page.locator('button:has-text("Export")').last
    if not export_btn.is_visible(timeout=5000):
        debug_path = output_path / "debug_dialog.png"
        page.screenshot(path=str(debug_path))
        print(f"[ERROR] Export dialog did not appear.")
        return None

    # Click Export and wait for download
    with page.expect_download(timeout=60000) as download_info:
        export_btn.click()

    download = download_info.value
    today_str = datetime.now().strftime("%Y-%m-%d")
    original_name = download.suggested_filename or f"syncly_export_{today_str}.csv"

    if not original_name.startswith(today_str):
        save_name = f"{today_str}_{original_name}"
    else:
        save_name = original_name

    save_path = output_path / save_name
    download.save_as(str(save_path))
    return save_path


def _merge_csvs(csv_paths, output_path):
    """여러 CSV를 source.id 기준 중복 제거하며 합침."""
    seen_ids = set()
    all_rows = []
    fieldnames = None

    for cp in csv_paths:
        with open(cp, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            for row in reader:
                pid = row.get("source.id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_rows.append(row)

    if not all_rows or not fieldnames:
        return None

    today_str = datetime.now().strftime("%Y-%m-%d")
    # Use the first CSV name as base
    first_name = csv_paths[0].name
    merged_name = first_name  # Overwrite the first chunk file
    merged_path = output_path / f"{today_str}_merged_{first_name.split('_', 1)[-1] if '_' in first_name else first_name}"

    with open(merged_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    return merged_path, len(all_rows)


def do_export(url: str, output_dir: str, chunk_days: int = 30):
    """날짜를 chunk_days씩 끊어서 export 후 합침."""
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
    print(f"[EXPORT] Strategy: {TOTAL_DAYS} days in {chunk_days}-day chunks")

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
        page.wait_for_timeout(8000)

        # Check if we're still logged in
        page_text = page.locator("body").inner_text(timeout=5000)
        if "Continue with Google" in page_text or "Get started" in page_text[:100]:
            print("[ERROR] Session expired! Please run with --login again.")
            print("  python tools/fetch_syncly_export.py --login")
            context.close()
            sys.exit(1)

        print("[EXPORT] Page loaded successfully.")

        # Build date chunks (newest first)
        today = datetime.now()
        chunks = []
        cursor = today
        while cursor > today - timedelta(days=TOTAL_DAYS):
            chunk_end = cursor
            chunk_start = max(cursor - timedelta(days=chunk_days - 1), today - timedelta(days=TOTAL_DAYS))
            chunks.append((chunk_start, chunk_end))
            cursor = chunk_start - timedelta(days=1)

        csv_paths = []

        for i, (start_dt, end_dt) in enumerate(chunks):
            label = f"[{i+1}/{len(chunks)}]"
            print(f"{label} {start_dt.strftime('%m/%d')} ~ {end_dt.strftime('%m/%d')}...")

            # Set date filter
            ok = _set_date_filter(page, start_dt, end_dt, output_path)
            if not ok and i == 0:
                # First chunk failed to set filter — fall back to default export
                print(f"{label} Date filter failed, using default filter")
            elif not ok:
                print(f"{label} Skipping chunk (filter failed)")
                continue

            page.wait_for_timeout(2000)

            # Export
            saved = _do_single_export(page, output_path)
            if saved:
                # Count rows
                with open(saved, "r", encoding="utf-8") as f:
                    row_count = sum(1 for _ in f) - 1
                print(f"{label} {row_count} posts exported -> {saved.name}")
                csv_paths.append(saved)
            else:
                print(f"{label} Export failed")

        context.close()

    # Merge all CSVs
    if len(csv_paths) == 0:
        print("[ERROR] No CSVs exported")
        sys.exit(1)
    elif len(csv_paths) == 1:
        final_path = csv_paths[0]
        with open(final_path, "r", encoding="utf-8") as f:
            total = sum(1 for _ in f) - 1
        print(f"[EXPORT] Single chunk: {total} posts")
    else:
        result = _merge_csvs(csv_paths, output_path)
        if result:
            final_path, total = result
            print(f"[EXPORT] Merged {len(csv_paths)} chunks -> {total} posts (deduped)")
            # Clean up chunk files
            for cp in csv_paths:
                if cp != final_path:
                    try:
                        cp.unlink()
                    except Exception:
                        pass
        else:
            final_path = csv_paths[0]
            total = 0

    file_size = final_path.stat().st_size
    print(f"[EXPORT] File: {final_path}")
    print(f"[EXPORT] Size: {file_size:,} bytes")
    print("[EXPORT] Done!")
    return str(final_path)


def main():
    parser = argparse.ArgumentParser(description="Syncly Excel Export Tool")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser for manual login and save session",
    )
    parser.add_argument(
        "--region",
        choices=["us", "jp"],
        default=None,
        help="Region (us or jp) - determines Syncly URL automatically",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Syncly insight posts URL (overrides --region)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to save downloaded files",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=30,
        help="Days per export chunk (default 30)",
    )

    args = parser.parse_args()

    if args.login:
        do_login()
    else:
        url = args.url or REGION_URLS.get(args.region or "us", DEFAULT_URL)
        do_export(url, args.output_dir, args.chunk_days)


if __name__ == "__main__":
    main()
