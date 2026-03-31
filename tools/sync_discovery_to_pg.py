#!/usr/bin/env python3
"""
Sync Discovery Sheet → PostgreSQL (orbitools)
==============================================
Google Sheets의 Discovery 탭 데이터를 PG onz_discovery_posts 테이블에 동기화.
URL 기준 upsert → 중복 안 생김.

Usage:
  # Sync specific tab
  python tools/sync_discovery_to_pg.py --tab "Discovery Mar24-Mar31"

  # Sync with region
  python tools/sync_discovery_to_pg.py --tab "Discovery Mar24-Mar31" --region jp

  # Dry run
  python tools/sync_discovery_to_pg.py --tab "Discovery Mar24-Mar31" --dry-run

  # Sync from raw JSON (skip sheet, use local file)
  python tools/sync_discovery_to_pg.py --json "Data Storage/discovery/2026-03-31_jp_ig_discovery.json" --region jp
"""

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

# ── Config ────────────────────────────────────────────────────────────────── #
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
BATCH_SIZE = 100  # posts per API call


def _auth_header():
    """Build Basic Auth header."""
    import base64
    cred = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return f"Basic {cred}"


def _api_post(endpoint: str, data: dict) -> dict:
    """POST to orbitools API."""
    url = f"{ORBITOOLS_URL}/api/onzenna/{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", _auth_header())

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _api_get(endpoint: str, params: dict = None) -> dict:
    """GET from orbitools API."""
    url = f"{ORBITOOLS_URL}/api/onzenna/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header())

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Sheet Reader ──────────────────────────────────────────────────────────── #
def read_discovery_sheet(tab_name: str) -> list[dict]:
    """Read Discovery tab from Google Sheets."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = PROJECT_ROOT / "credentials" / "google_service_account.json"
    creds = Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(tab_name)

    records = ws.get_all_records()
    print(f"[SHEET] Read {len(records)} rows from '{tab_name}'")
    return records


def read_discovery_json(json_path: str) -> list[dict]:
    """Read Discovery data from local JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[JSON] Read {len(data)} posts from {json_path}")
    return data


# ── Normalizer ─────────────────────────────────────────────────────────────── #
def normalize_for_pg(row: dict, region: str, batch: str) -> dict:
    """Normalize a sheet/JSON row to PG API format."""
    # Handle both sheet format (Title Case) and JSON format (Title Case from fetch_jp_discovery)
    return {
        "handle": row.get("Handle", row.get("handle", "")),
        "full_name": row.get("Full Name", row.get("full_name", "")),
        "platform": row.get("Platform", row.get("platform", "")),
        "url": row.get("URL", row.get("url", "")),
        "post_date": row.get("Date", row.get("post_date", "")) or None,
        "content_type": row.get("Type", row.get("content_type", "")),
        "caption": row.get("Caption", row.get("caption", "")),
        "hashtags": row.get("Hashtags", row.get("hashtags", "")),
        "mentions": row.get("Mentions", row.get("mentions", "")),
        "followers": _int_or_none(row.get("Followers", row.get("followers"))),
        "views": _int_or_none(row.get("Views", row.get("views"))),
        "likes": _int_or_none(row.get("Likes", row.get("likes"))),
        "comments_count": _int_or_none(row.get("Comments Count", row.get("comments_count"))),
        "source": row.get("Source", row.get("source", "")),
        "region": region,
        "discovery_batch": batch,
    }


def _int_or_none(val):
    """Convert to int or None."""
    if val is None or val == "":
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


# ── Sync Logic ────────────────────────────────────────────────────────────── #
def sync_to_pg(posts: list[dict], region: str, batch: str, dry_run: bool = False):
    """Sync normalized posts to PG via orbitools API."""
    normalized = [normalize_for_pg(p, region, batch) for p in posts]
    # Filter out posts without URL
    normalized = [p for p in normalized if p["url"]]

    print(f"\n[SYNC] {len(normalized)} posts to sync (region={region}, batch={batch})")

    if dry_run:
        print(f"[DRY RUN] Would sync {len(normalized)} posts")
        for p in normalized[:5]:
            print(f"  @{p['handle']} | {p['platform']} | {p['url'][:50]}")
        return {"created": 0, "updated": 0, "total": len(normalized)}

    total_created = 0
    total_updated = 0
    total_skipped = 0

    # Send in batches
    for i in range(0, len(normalized), BATCH_SIZE):
        chunk = normalized[i:i + BATCH_SIZE]
        try:
            result = _api_post("discovery/posts/", {"posts": chunk})
            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            total_skipped += result.get("skipped", 0)
            print(f"  Batch {i//BATCH_SIZE + 1}: +{result.get('created', 0)} new, ~{result.get('updated', 0)} updated")
        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            print(f"  Batch {i//BATCH_SIZE + 1}: ERROR {e.code} — {body[:200]}")
        except Exception as e:
            print(f"  Batch {i//BATCH_SIZE + 1}: ERROR — {e}")

    print(f"\n[SYNC] Done: +{total_created} created, ~{total_updated} updated, ×{total_skipped} skipped")

    # Show stats
    try:
        stats = _api_get("discovery/posts/stats/", {"region": region})
        print(f"\n[STATS] Region={region}: {stats.get('total', 0)} total, "
              f"{stats.get('unique_handles', 0)} handles, "
              f"avg followers: {stats.get('avg_followers', 0)}")
        print(f"  By platform: {stats.get('by_platform', {})}")
        print(f"  By status: {stats.get('by_status', {})}")
    except Exception as e:
        print(f"[STATS] Could not fetch stats: {e}")

    return {"created": total_created, "updated": total_updated, "skipped": total_skipped}


# ── Main ──────────────────────────────────────────────────────────────────── #
def main():
    parser = argparse.ArgumentParser(description="Sync Discovery data to PostgreSQL")
    parser.add_argument("--tab", help="Google Sheets tab name")
    parser.add_argument("--json", help="Local JSON file path (skip sheet)")
    parser.add_argument("--region", default="jp", help="Region: jp or us")
    parser.add_argument("--batch", help="Batch name (default: auto from tab name)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not ORBITOOLS_PASS:
        print("ERROR: ORBITOOLS_PASS not set in ~/.wat_secrets")
        sys.exit(1)

    if not args.tab and not args.json:
        print("ERROR: --tab or --json required")
        sys.exit(1)

    batch_name = args.batch or (args.tab or Path(args.json).stem if args.json else "unknown")

    if args.json:
        posts = read_discovery_json(args.json)
    else:
        posts = read_discovery_sheet(args.tab)

    sync_to_pg(posts, region=args.region, batch=batch_name, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
