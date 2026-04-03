"""Export filtered Syncly sheets to Excel for pipeline import.

Downloads Creators_updated + Output_updated from Syncly spreadsheet,
filters out:
  - Creators: no email, blacklisted, 제휴 진행중/완료
  - Output: not full_matched

Saves to Z:\...\제갈량\syncly_creators_clean.xlsx and syncly_output_clean.xlsx

Usage:
    python tools/export_syncly_clean.py
    python tools/export_syncly_clean.py --dry-run
"""

import os, sys, time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o"
PROJECT_ROOT = os.path.dirname(DIR)
OUTPUT_DIR = r"Z:\Orbiters\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\Shared\ONZ Creator Collab\제갈량"


def get_gc():
    creds = Credentials.from_service_account_file(
        os.path.join(PROJECT_ROOT, "credentials", "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


def download_sheet_data(gc, sheet_id, tab_name, max_retries=3):
    """Download sheet tab data with retry logic for 503 errors."""
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)
    for attempt in range(max_retries):
        try:
            print(f"  Reading {tab_name} (attempt {attempt+1})...", flush=True)
            data = ws.get_all_values()
            return data
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                wait = 30 * (attempt + 1)
                print(f"  503 error, waiting {wait}s before retry...", flush=True)
                time.sleep(wait)
            else:
                raise


def main():
    import csv, io, argparse
    try:
        import openpyxl
    except ImportError:
        print("Installing openpyxl...")
        os.system(f'"{sys.executable}" -m pip install openpyxl')
        import openpyxl

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    import json as _json
    CACHE_DIR = os.path.join(PROJECT_ROOT, ".tmp", "syncly_cache")
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Helper: cache sheet data to avoid re-reading on retry
    def _cached_read(sheet_name, cache_key):
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        if os.path.exists(cache_file):
            print(f"  Using cached {cache_key}...", flush=True)
            with open(cache_file, "r", encoding="utf-8") as f:
                return _json.load(f)
        gc = get_gc()
        data = download_sheet_data(gc, SHEET_ID, sheet_name)
        with open(cache_file, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False)
        return data

    # ── 1. Creators_updated (gid=522613099) ──
    print("=== Creators_updated ===", flush=True)
    raw_data = _cached_read("Creators_updated", "creators_raw")
    headers = raw_data[0]
    all_rows = []
    for row in raw_data[1:]:
        d = {}
        for i, h in enumerate(headers):
            d[h] = row[i] if i < len(row) else ""
        all_rows.append(d)
    print(f"  Total rows: {len(all_rows)}", flush=True)

    # Filter
    clean_creators = []
    stats = {"no_email": 0, "blacklist": 0, "collab": 0, "kept": 0}

    for row in all_rows:
        email = (row.get("Email") or "").strip()
        blacklist = (row.get("Blacklist \uc5ec\ubd80") or row.get("Blacklist 여부") or "").strip()
        collab = (row.get("\uc81c\ud734 \uc0c1\ud0dc") or row.get("제휴 상태") or "").strip()

        # Skip no email / placeholder
        if not email or "@" not in email or "@discovered." in email.lower():
            stats["no_email"] += 1
            continue

        # Skip blacklist
        if blacklist.upper() == "TRUE":
            stats["blacklist"] += 1
            continue

        # Skip 제휴 진행중/완료
        if collab:
            stats["collab"] += 1
            continue

        clean_creators.append(row)
        stats["kept"] += 1

    print(f"  Filtered: {stats}", flush=True)
    print(f"  Clean creators: {stats['kept']}", flush=True)

    # ── 2. Output_updated (gid=1123915760) ──
    print("\n=== Output_updated ===", flush=True)
    raw_data2 = _cached_read("Output_updated", "output_raw")
    headers2 = raw_data2[0]
    all_output = []
    for row in raw_data2[1:]:
        d = {}
        for i, h in enumerate(headers2):
            d[h] = row[i] if i < len(row) else ""
        all_output.append(d)
    print(f"  Total rows: {len(all_output)}", flush=True)

    # Filter: only full_matched
    # Level column (I) = "full_matched"
    clean_output = []
    out_stats = {"not_matched": 0, "kept": 0}

    for row in all_output:
        level = (row.get("Level") or "").strip().lower()
        if level != "full_matched":
            out_stats["not_matched"] += 1
            continue
        clean_output.append(row)
        out_stats["kept"] += 1

    print(f"  Filtered: {out_stats}", flush=True)
    print(f"  Clean output: {out_stats['kept']}", flush=True)

    if args.dry_run:
        print("\n[DRY RUN] Would save:")
        print(f"  {OUTPUT_DIR}/syncly_creators_clean.xlsx ({stats['kept']} rows)")
        print(f"  {OUTPUT_DIR}/syncly_output_clean.xlsx ({out_stats['kept']} rows)")
        return

    # ── 3. Save to Excel ──
    import re as _re
    # Remove illegal XML characters that openpyxl can't handle
    _ILLEGAL_CHARS = _re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
    def clean_cell(val):
        if isinstance(val, str):
            return _ILLEGAL_CHARS.sub('', val)
        return val

    print("\nSaving Excel files...", flush=True)

    # Creators
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.title = "Creators"
    ws1.append(headers)
    for row in clean_creators:
        ws1.append([clean_cell(row.get(h, "")) for h in headers])
    path1 = os.path.join(OUTPUT_DIR, "syncly_creators_clean.xlsx")
    wb1.save(path1)
    print(f"  Saved: {path1} ({len(clean_creators)} rows)", flush=True)

    # Output
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.title = "Output"
    ws2.append(headers2)
    for row in clean_output:
        ws2.append([clean_cell(row.get(h, "")) for h in headers2])
    path2 = os.path.join(OUTPUT_DIR, "syncly_output_clean.xlsx")
    wb2.save(path2)
    print(f"  Saved: {path2} ({len(clean_output)} rows)", flush=True)

    print(f"\nDone! Files saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
