"""Export Data Keeper cache to Shared folder for team access.

This script copies the local .tmp/datakeeper/ cache files to
Shared/datakeeper/latest/ and generates manifest.json.

Run this locally (where Synology Drive is mounted) after Data Keeper
completes, or schedule it via Windows Task Scheduler.

Usage:
    python tools/export_to_shared.py          # Export from local cache
    python tools/export_to_shared.py --from-pg # Pull fresh data from PG first
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from env_loader import load_env
load_env()

CACHE_DIR = DIR.parent / ".tmp" / "datakeeper"
SHARED_DIR = DIR.parent.parent / "Shared" / "datakeeper" / "latest"

ORBITOOLS_BASE = os.getenv("ORBITOOLS_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

TABLES = [
    "amazon_ads_daily",
    "amazon_sales_daily",
    "meta_ads_daily",
    "google_ads_daily",
    "ga4_daily",
    "klaviyo_daily",
    "shopify_orders_daily",
]


def pull_from_pg(table: str) -> list[dict]:
    """Pull all rows for a table from PG via orbitools API."""
    try:
        r = requests.get(
            f"{ORBITOOLS_BASE}/query/",
            params={"table": table},
            auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("rows", [])
    except Exception as e:
        print(f"  [PG] Failed to pull {table}: {e}")
        return []


def export(from_pg: bool = False):
    """Export data to Shared folder."""
    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {"last_updated": datetime.now(timezone.utc).isoformat(), "channels": {}}
    total_exported = 0

    for table in TABLES:
        # Get data
        if from_pg:
            rows = pull_from_pg(table)
        else:
            cache_path = CACHE_DIR / f"{table}.json"
            if not cache_path.exists():
                print(f"  [Skip] {table}: no cache file")
                continue
            with open(cache_path, "r", encoding="utf-8") as f:
                rows = json.load(f)

        if not rows:
            print(f"  [Skip] {table}: no data")
            continue

        # Write to Shared
        shared_path = SHARED_DIR / f"{table}.json"
        with open(shared_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, default=str, ensure_ascii=False)

        # Manifest entry
        dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
        brands = sorted(set(r.get("brand", "") for r in rows if r.get("brand")))
        manifest["channels"][table] = {
            "status": "collecting",
            "last_collected": datetime.now(timezone.utc).isoformat(),
            "row_count": len(rows),
            "date_range": [dates[0], dates[-1]] if dates else [],
            "brands": brands,
        }

        print(f"  [OK] {table}: {len(rows)} rows")
        total_exported += len(rows)

    # Write manifest
    manifest_path = SHARED_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str, ensure_ascii=False)

    print(f"\n  Total: {total_exported} rows across {len(manifest['channels'])} channels")
    print(f"  Manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description="Export Data Keeper cache to Shared folder")
    parser.add_argument("--from-pg", action="store_true", help="Pull fresh data from PG instead of local cache")
    args = parser.parse_args()

    print(f"=== Export to Shared ===")
    print(f"  Source: {'PostgreSQL' if args.from_pg else 'Local cache'}")
    print(f"  Target: {SHARED_DIR}\n")

    export(from_pg=args.from_pg)
    print("\n=== Export Complete ===")


if __name__ == "__main__":
    main()
