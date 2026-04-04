"""Export filtered Syncly sheets to Excel for pipeline import.

Downloads Creators_updated + Output_updated from Syncly spreadsheet,
filters out:
  - Creators: no email, blacklisted, 제휴 진행중/완료
  - Output: not full_matched

JOINs best post from Output to each Creator (highest views).
Saves to Z:\...\제갈량\syncly_creators_clean.xlsx

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

# Output_updated column indices (0-based) — from load_syncly_output_to_pg.py
OUT_COL = {
    "username": 6,       # G
    "level": 8,          # I
    "post_url": 15,      # P
    "text": 18,          # S
    "transcript": 19,    # T
    "caption": 20,       # U
    "post_date": 21,     # V
    "followers": 32,     # AG
    "avg_view": 33,      # AH
    "views_30d": 39,     # AN
    "likes_30d": 40,     # AO
}


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


def safe_int(val):
    """Parse integer from string, return None on failure."""
    if not val:
        return None
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def build_best_post_map(output_rows):
    """Build username → best post dict from Output_updated rows.

    For each username, picks the post with highest views_30d (or avg_view fallback).
    Returns: {username_lower: {post_url, transcript, caption, views, post_date, views_30d, likes_30d, followers}}
    """
    best = {}

    for row in output_rows:
        def col(key):
            idx = OUT_COL.get(key, -1)
            if 0 <= idx < len(row):
                return (row[idx] or "").strip()
            return ""

        level = col("level").lower()
        if level != "full_matched":
            continue

        username = col("username").lstrip("@").lower()
        if not username:
            continue

        views = safe_int(col("views_30d")) or safe_int(col("avg_view")) or 0
        post_url = col("post_url")
        transcript = col("transcript")
        caption = col("caption")
        text = col("text")
        post_date = col("post_date")
        followers = safe_int(col("followers"))
        views_30d = safe_int(col("views_30d"))
        likes_30d = safe_int(col("likes_30d"))
        avg_view = safe_int(col("avg_view"))

        # Use transcript, fallback to text, fallback to caption
        best_transcript = transcript or text or caption or ""

        current = best.get(username)
        if not current or views > (current.get("_sort_views") or 0):
            best[username] = {
                "top_post_url": post_url,
                "top_post_transcript": best_transcript,
                "top_post_caption": caption,
                "top_post_views": safe_int(col("views_30d")) or safe_int(col("avg_view")),
                "top_post_date": post_date,
                "views_30d": views_30d,
                "likes_30d": likes_30d,
                "avg_view": avg_view,
                "followers": followers,
                "_sort_views": views,
            }

    return best


def main():
    import argparse
    try:
        import openpyxl
    except ImportError:
        print("Installing openpyxl...")
        os.system(f'"{sys.executable}" -m pip install openpyxl')
        import openpyxl

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear-cache", action="store_true", help="Delete cached sheet data")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    import json as _json
    CACHE_DIR = os.path.join(PROJECT_ROOT, ".tmp", "syncly_cache")
    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.clear_cache:
        import glob
        for f in glob.glob(os.path.join(CACHE_DIR, "*.json")):
            os.remove(f)
            print(f"  Deleted cache: {f}", flush=True)

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

    # ── 1. Output_updated (read first to build best post map) ──
    print("=== Output_updated ===", flush=True)
    raw_data2 = _cached_read("Output_updated", "output_raw")
    output_rows = raw_data2[1:]  # skip header
    print(f"  Total rows: {len(output_rows)}", flush=True)

    best_post_map = build_best_post_map(output_rows)
    print(f"  Unique creators with best post: {len(best_post_map)}", flush=True)

    # ── 2. Creators_updated ──
    print("\n=== Creators_updated ===", flush=True)
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
    stats = {"no_email": 0, "blacklist": 0, "collab": 0, "kept": 0, "with_content": 0}

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

        # JOIN best post from Output
        username = (row.get("Username") or "").lstrip("@").lower()
        bp = best_post_map.get(username, {})

        row["__top_post_url"] = bp.get("top_post_url", "")
        row["__top_post_transcript"] = bp.get("top_post_transcript", "")
        row["__top_post_caption"] = bp.get("top_post_caption", "")
        row["__top_post_views"] = bp.get("top_post_views")
        row["__top_post_date"] = bp.get("top_post_date", "")
        row["__views_30d"] = bp.get("views_30d")
        row["__likes_30d"] = bp.get("likes_30d")
        row["__avg_view"] = bp.get("avg_view")
        row["__followers"] = bp.get("followers")

        if bp:
            stats["with_content"] += 1

        clean_creators.append(row)
        stats["kept"] += 1

    print(f"  Filtered: {stats}", flush=True)
    print(f"  Clean creators: {stats['kept']} ({stats['with_content']} with content data)", flush=True)

    # Extra columns appended to each creator row
    EXTRA_COLS = [
        "__top_post_url", "__top_post_transcript", "__top_post_caption",
        "__top_post_views", "__top_post_date", "__views_30d", "__likes_30d",
        "__avg_view", "__followers",
    ]
    EXTRA_HEADERS = [
        "top_post_url", "top_post_transcript", "top_post_caption",
        "top_post_views", "top_post_date", "views_30d", "likes_30d",
        "avg_view", "followers_output",
    ]

    if args.dry_run:
        print(f"\n[DRY RUN] Would save:")
        print(f"  {OUTPUT_DIR}/syncly_creators_clean.xlsx ({stats['kept']} rows, +{len(EXTRA_HEADERS)} content columns)")
        # Show sample
        sample = [c for c in clean_creators if c.get("__top_post_url")][:3]
        for s in sample:
            uname = (s.get("Username") or "").lstrip("@")
            print(f"  @{uname} | views_30d={s.get('__views_30d')} | transcript={len(s.get('__top_post_transcript',''))} chars | {s.get('__top_post_url','')[:60]}")
        return

    # ── 3. Save to Excel ──
    import re as _re
    _ILLEGAL_CHARS = _re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
    def clean_cell(val):
        if isinstance(val, str):
            return _ILLEGAL_CHARS.sub('', val)
        if val is None:
            return ""
        return val

    print("\nSaving Excel...", flush=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Creators"
    ws.append(headers + EXTRA_HEADERS)
    for row in clean_creators:
        base = [clean_cell(row.get(h, "")) for h in headers]
        extra = [clean_cell(row.get(k, "")) for k in EXTRA_COLS]
        ws.append(base + extra)

    path = os.path.join(OUTPUT_DIR, "syncly_creators_clean.xlsx")
    wb.save(path)
    print(f"  Saved: {path} ({len(clean_creators)} rows, {len(headers)+len(EXTRA_HEADERS)} cols)", flush=True)

    print(f"\nDone! Files saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
