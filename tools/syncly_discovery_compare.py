#!/usr/bin/env python3
"""
Syncly Discovery Comparison Tool
=================================
Syncly JP에서 Mar23-30 기간 데이터를 크롤링하고,
Discovery 시트의 213건과 비교하여 누락/노이즈 분석.

Usage:
  python tools/syncly_discovery_compare.py
  python tools/syncly_discovery_compare.py --start 2026-03-23 --end 2026-03-30
  python tools/syncly_discovery_compare.py --skip-crawl  # 기존 CSV만 비교
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
DISCOVERY_TAB = "Discovery Mar23-30"
OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "syncly"
STATE_DIR = Path.home() / ".syncly_state"

SYNCLY_JP_URL = (
    "https://social.syncly.app/workspace/696986d0b20b4ccc86695fcd"
    "/insight/posts?q=69a941f3208fdb401a8043fb"
)


def crawl_syncly_jp(start_date: datetime, end_date: datetime) -> Path | None:
    """Playwright로 Syncly JP를 크롤링, 지정 기간 필터 적용."""
    from playwright.sync_api import sync_playwright

    chrome_profile = STATE_DIR / "chrome_profile"
    if not chrome_profile.exists():
        print("ERROR: No Syncly session. Run: python tools/fetch_syncly_export.py --login")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[CRAWL] Syncly JP: {start_date.strftime('%m/%d')} ~ {end_date.strftime('%m/%d')}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(chrome_profile),
            headless=False,
            channel="chromium",
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Navigate
        print("[CRAWL] Loading Syncly JP...")
        page.goto(SYNCLY_JP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        # Check login
        body = page.locator("body").inner_text(timeout=5000)
        if "Continue with Google" in body or "Get started" in body[:100]:
            print("ERROR: Session expired! Run: python tools/fetch_syncly_export.py --login")
            context.close()
            return None

        print("[CRAWL] Page loaded. Setting date filter...")

        # Screenshot before filter
        page.screenshot(path=str(OUTPUT_DIR / "debug_before_filter.png"))

        # --- Count total results BEFORE export ---
        # Syncly shows "N posts" somewhere on the page
        try:
            page.wait_for_timeout(3000)
            body_text = page.locator("body").inner_text(timeout=5000)
            # Look for patterns like "700 posts" or "123 results"
            count_match = re.search(r"(\d{1,5})\s*(?:posts?|results?|개|건)", body_text, re.IGNORECASE)
            if count_match:
                print(f"[CRAWL] Syncly shows: {count_match.group(0)}")
            else:
                # Try to find any number near top of page
                nums = re.findall(r"\b(\d{2,4})\b", body_text[:500])
                if nums:
                    print(f"[CRAWL] Numbers in page header: {nums[:5]}")
        except Exception as e:
            print(f"[CRAWL] Could not read post count: {e}")

        # Set date filter
        ok = _set_date_filter(page, start_date, end_date)
        if not ok:
            print("[CRAWL] Date filter failed, trying with default range")

        page.wait_for_timeout(5000)

        # Read post count after filter
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
            count_match = re.search(r"(\d{1,5})\s*(?:posts?|results?|개|건)", body_text, re.IGNORECASE)
            if count_match:
                print(f"[CRAWL] After filter: {count_match.group(0)}")

            # Screenshot after filter
            page.screenshot(path=str(OUTPUT_DIR / "debug_after_filter.png"))
        except:
            pass

        # Export CSV
        print("[CRAWL] Exporting CSV...")
        csv_path = _do_export(page)

        context.close()
        return csv_path


def _set_date_filter(page, start_date, end_date):
    """Set Syncly date filter."""
    # Click date filter button
    date_btn = page.locator('button:has-text("Custom")').first
    if not date_btn.is_visible(timeout=3000):
        date_btn = page.locator('button:has-text("days"), button:has-text("Last")').first

    try:
        date_btn.click()
        page.wait_for_timeout(1500)
    except:
        print("[WARN] Could not click date filter button")
        page.screenshot(path=str(OUTPUT_DIR / "debug_no_date_btn.png"))
        return False

    # Find date inputs (M, D, YYYY)
    inputs = page.locator('input').all()
    date_inputs = [inp for inp in inputs
                   if inp.is_visible() and inp.get_attribute('placeholder') in ('M', 'D', 'YYYY')]

    if len(date_inputs) >= 6:
        values = [
            (date_inputs[0], str(start_date.month)),
            (date_inputs[1], str(start_date.day)),
            (date_inputs[2], str(start_date.year)),
            (date_inputs[3], str(end_date.month)),
            (date_inputs[4], str(end_date.day)),
            (date_inputs[5], str(end_date.year)),
        ]
        for inp, val in values:
            inp.click()
            inp.press("Control+a")
            inp.fill(val)
            page.wait_for_timeout(200)

        # Click Update
        update_btn = page.locator('button:has-text("Update")').first
        update_btn.click()
        page.wait_for_timeout(5000)
        print(f"[FILTER] Set: {start_date.strftime('%m/%d/%Y')} ~ {end_date.strftime('%m/%d/%Y')}")
        return True
    else:
        page.screenshot(path=str(OUTPUT_DIR / "debug_date_inputs.png"))
        print(f"[WARN] Found {len(date_inputs)} date inputs (need 6)")
        page.keyboard.press("Escape")
        return False


def _do_export(page) -> Path | None:
    """Export current view as CSV."""
    # Find export icon
    buttons = page.locator("button:has(svg)").all()
    candidates = []
    for btn in buttons:
        try:
            if btn.is_visible():
                box = btn.bounding_box()
                if box and 140 < box["y"] < 200 and box["width"] < 50:
                    candidates.append((btn, box))
        except:
            continue

    if not candidates:
        page.screenshot(path=str(OUTPUT_DIR / "debug_no_export.png"))
        print("[ERROR] Could not find export button")
        return None

    export_icon = max(candidates, key=lambda c: c[1]["x"])[0]
    export_icon.click()
    page.wait_for_timeout(2000)

    export_btn = page.locator('button:has-text("Export")').last
    if not export_btn.is_visible(timeout=5000):
        page.screenshot(path=str(OUTPUT_DIR / "debug_no_dialog.png"))
        print("[ERROR] Export dialog did not appear")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with page.expect_download(timeout=60000) as dl_info:
        export_btn.click()

    download = dl_info.value
    save_path = OUTPUT_DIR / f"syncly_jp_discovery_compare_{ts}.csv"
    download.save_as(str(save_path))

    # Count rows
    with open(save_path, "r", encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1
    print(f"[EXPORT] Saved: {save_path.name} ({row_count} rows)")
    return save_path


def compare_with_discovery(csv_path: Path):
    """Compare Syncly CSV with Discovery sheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    # Read Syncly CSV
    syncly_rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        syncly_headers = reader.fieldnames
        for row in reader:
            syncly_rows.append(row)

    print(f"\n{'='*60}")
    print(f"  SYNCLY vs DISCOVERY 비교")
    print(f"{'='*60}")
    print(f"\nSyncly CSV: {len(syncly_rows)} rows")
    print(f"Syncly headers: {syncly_headers[:15]}")

    # Read Discovery sheet
    sa_path = PROJECT_ROOT / "credentials" / "google_service_account.json"
    creds = Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(DISCOVERY_TAB)
    disc_data = ws.get_all_records()

    print(f"Discovery sheet: {len(disc_data)} rows")

    # Build comparable keys
    # Syncly: source.id or source.url
    syncly_urls = set()
    syncly_handles = set()
    syncly_by_handle = {}
    for r in syncly_rows:
        url = r.get("source.url", r.get("url", "")).strip()
        handle = r.get("source.username", r.get("username", "")).strip().lower()
        if url:
            syncly_urls.add(url)
        if handle:
            syncly_handles.add(handle)
            if handle not in syncly_by_handle:
                syncly_by_handle[handle] = []
            syncly_by_handle[handle].append(r)

    disc_urls = set()
    disc_handles = set()
    for r in disc_data:
        url = r.get("URL", "").strip()
        handle = r.get("Handle", "").strip().lower()
        if url:
            disc_urls.add(url)
        if handle:
            disc_handles.add(handle)

    # Overlap analysis
    url_overlap = syncly_urls & disc_urls
    handle_overlap = syncly_handles & disc_handles
    syncly_only_handles = syncly_handles - disc_handles
    disc_only_handles = disc_handles - syncly_handles

    print(f"\n--- Handle 비교 ---")
    print(f"Syncly unique handles: {len(syncly_handles)}")
    print(f"Discovery unique handles: {len(disc_handles)}")
    print(f"겹치는 handles: {len(handle_overlap)}")
    print(f"Syncly에만 있는: {len(syncly_only_handles)}")
    print(f"Discovery에만 있는: {len(disc_only_handles)}")

    print(f"\n--- URL 비교 ---")
    print(f"Syncly URLs: {len(syncly_urls)}")
    print(f"Discovery URLs: {len(disc_urls)}")
    print(f"겹치는 URLs: {len(url_overlap)}")

    # Analyze what's in Syncly but not Discovery
    print(f"\n--- Syncly에만 있는 데이터 분석 ---")
    syncly_only_rows = [r for r in syncly_rows
                        if r.get("source.username", r.get("username", "")).strip().lower()
                        in syncly_only_handles]
    print(f"Syncly-only rows: {len(syncly_only_rows)}")

    # Platform distribution of syncly-only
    from collections import Counter
    platforms = Counter()
    types = Counter()
    for r in syncly_only_rows:
        plat = r.get("source.platform", r.get("platform", "unknown"))
        platforms[plat] += 1
        ptype = r.get("analyzation.type", r.get("type", "unknown"))
        types[ptype] += 1

    print(f"\nSyncly-only platform distribution:")
    for p, c in platforms.most_common():
        print(f"  {p}: {c}")

    print(f"\nSyncly-only type distribution:")
    for t, c in types.most_common():
        print(f"  {t}: {c}")

    # Sample syncly-only entries
    print(f"\nSample Syncly-only entries (first 10):")
    for r in syncly_only_rows[:10]:
        handle = r.get("source.username", r.get("username", ""))
        url = r.get("source.url", r.get("url", ""))[:60]
        followers = r.get("source.followersCount", r.get("followers", "?"))
        content = r.get("content", r.get("text", ""))[:60]
        print(f"  @{handle} | {followers} followers | {content}")

    # Save comparison report
    report = {
        "timestamp": datetime.now().isoformat(),
        "syncly_total": len(syncly_rows),
        "discovery_total": len(disc_data),
        "gap": len(syncly_rows) - len(disc_data),
        "handle_overlap": len(handle_overlap),
        "syncly_only_handles": len(syncly_only_handles),
        "disc_only_handles": len(disc_only_handles),
        "syncly_only_rows": len(syncly_only_rows),
    }
    report_path = OUTPUT_DIR / f"discovery_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved: {report_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-23")
    parser.add_argument("--end", default="2026-03-30")
    parser.add_argument("--skip-crawl", action="store_true", help="Skip Syncly crawl, use latest CSV")
    parser.add_argument("--csv", help="Use specific CSV file for comparison")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    csv_path = None
    if args.csv:
        csv_path = Path(args.csv)
    elif args.skip_crawl:
        # Find latest syncly JP CSV
        csvs = sorted(OUTPUT_DIR.glob("*jp*discovery*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if csvs:
            csv_path = csvs[0]
            print(f"Using existing CSV: {csv_path}")
        else:
            print("No existing CSV found, will crawl")

    if not csv_path:
        csv_path = crawl_syncly_jp(start, end)

    if csv_path and csv_path.exists():
        compare_with_discovery(csv_path)
    else:
        print("No CSV to compare")


if __name__ == "__main__":
    main()
