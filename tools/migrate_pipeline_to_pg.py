#!/usr/bin/env python3
"""Migrate JP Pipeline staticData → PostgreSQL.

Reads current creator data from n8n webhook (GET /jp-pipeline-list)
and upserts into gk_pipeline_creators via DataKeeper Pipeline API.

Usage:
  python tools/migrate_pipeline_to_pg.py              # dry-run (default)
  python tools/migrate_pipeline_to_pg.py --execute     # actually migrate
  python tools/migrate_pipeline_to_pg.py --verify      # check PG data after migration
"""

import argparse
import json
import os
import sys
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
N8N_PIPELINE_LIST = "https://n8n.orbiters.co.kr/webhook/jp-pipeline-list"


def fetch_n8n_data():
    """Fetch current staticData from n8n JP Pipeline."""
    import requests
    resp = requests.get(N8N_PIPELINE_LIST, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()


def upsert_creators(creators, dry_run=True):
    """Upsert creators to PG via Pipeline API."""
    import requests
    url = f"{ORBITOOLS_BASE}/api/datakeeper/pipeline/creators/"
    auth = (ORBITOOLS_USER, ORBITOOLS_PASS)

    if dry_run:
        print(f"\n[DRY-RUN] Would upsert {len(creators)} creators to PG")
        for c in creators[:5]:
            print(f"  @{c.get('username', '?'):20s} status={c.get('status', '?'):15s} "
                  f"followers={c.get('followers', 0)}")
        if len(creators) > 5:
            print(f"  ... and {len(creators) - 5} more")
        return

    # Send in batches of 20
    batch_size = 20
    total_created, total_updated = 0, 0
    for i in range(0, len(creators), batch_size):
        batch = creators[i:i + batch_size]
        resp = requests.post(url, json={"creators": batch}, auth=auth, verify=False, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        total_created += result.get("created", 0)
        total_updated += result.get("updated", 0)
        print(f"  Batch {i // batch_size + 1}: created={result.get('created', 0)}, "
              f"updated={result.get('updated', 0)}")

    print(f"\nTotal: created={total_created}, updated={total_updated}")


def verify_pg_data():
    """Verify data in PG matches n8n."""
    import requests
    auth = (ORBITOOLS_USER, ORBITOOLS_PASS)

    # Get PG data
    url = f"{ORBITOOLS_BASE}/api/datakeeper/pipeline/creators/"
    resp = requests.get(url, auth=auth, verify=False, timeout=30)
    resp.raise_for_status()
    pg_data = resp.json()
    pg_creators = {c["username"]: c for c in pg_data.get("creators", [])}

    # Get n8n data
    n8n_data = fetch_n8n_data()
    n8n_creators = {c["username"]: c for c in n8n_data.get("creators", [])}

    print(f"\n=== Verification ===")
    print(f"n8n: {len(n8n_creators)} creators")
    print(f"PG:  {len(pg_creators)} creators")

    missing = set(n8n_creators) - set(pg_creators)
    extra = set(pg_creators) - set(n8n_creators)

    if missing:
        print(f"\nMissing in PG ({len(missing)}):")
        for u in missing:
            print(f"  @{u}")

    if extra:
        print(f"\nExtra in PG ({len(extra)}):")
        for u in extra:
            print(f"  @{u}")

    if not missing and not extra:
        print("All creators match!")

    # Check status consistency
    mismatched = []
    for u in set(n8n_creators) & set(pg_creators):
        if n8n_creators[u].get("status") != pg_creators[u].get("status"):
            mismatched.append((u, n8n_creators[u].get("status"), pg_creators[u].get("status")))

    if mismatched:
        print(f"\nStatus mismatches ({len(mismatched)}):")
        for u, n8n_s, pg_s in mismatched:
            print(f"  @{u}: n8n={n8n_s} vs PG={pg_s}")


def main():
    parser = argparse.ArgumentParser(description="Migrate JP Pipeline staticData to PostgreSQL")
    parser.add_argument("--execute", action="store_true", help="Actually perform migration (default: dry-run)")
    parser.add_argument("--verify", action="store_true", help="Verify PG data vs n8n")
    args = parser.parse_args()

    if args.verify:
        verify_pg_data()
        return

    print("=== JP Pipeline → PostgreSQL Migration ===")
    print(f"Source: {N8N_PIPELINE_LIST}")
    print(f"Target: {ORBITOOLS_BASE}/api/datakeeper/pipeline/creators/")

    # Step 1: Fetch n8n data
    print("\n[1] Fetching current n8n staticData...")
    data = fetch_n8n_data()
    creators = data.get("creators", [])
    print(f"    Found {len(creators)} creators")

    # Show status distribution
    from collections import Counter
    statuses = Counter(c.get("status", "?") for c in creators)
    for s, n in statuses.most_common():
        print(f"      {s}: {n}")

    # Step 2: Save backup
    backup_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               ".tmp", "pipeline_backup_before_pg.json")
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[2] Backup saved: {backup_path}")

    # Step 3: Upsert to PG
    dry_run = not args.execute
    print(f"\n[3] {'DRY-RUN' if dry_run else 'EXECUTING'} upsert to PostgreSQL...")
    upsert_creators(creators, dry_run=dry_run)

    if dry_run:
        print("\n>>> Run with --execute to perform actual migration")
    else:
        print("\n[4] Verifying...")
        verify_pg_data()
        print("\nMigration complete!")


if __name__ == "__main__":
    main()
