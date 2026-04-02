#!/usr/bin/env python3
"""DEPRECATED — Migrate Airtable Creators table -> PostgreSQL onz_pipeline_creators.

One-time migration script. Migration completed 2026-03-31.
All pipeline data now lives in PostgreSQL via Django API (orbitools).
Airtable is no longer used.

Kept for reference only. Do not run.

Usage (historical):
    python tools/migrate_airtable_to_pg.py              # dry-run (preview)
    python tools/migrate_airtable_to_pg.py --execute    # actually migrate
    python tools/migrate_airtable_to_pg.py --dump       # dump AT data to JSON
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import json
import time
import urllib.request
import urllib.error
import ssl
import argparse
from datetime import datetime

# ─── Load env ────────────────────────────────────────────────────────────
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from load_env import load_env
    load_env()
except ImportError:
    pass

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
EC2_API = "https://orbitools.orbiters.co.kr/api/onzenna"
EC2_USER = os.getenv("ORBITOOLS_USER", "admin")
EC2_PASS = os.getenv("ORBITOOLS_PASS", "admin")

# Airtable PROD
AT_BASE = "app3Vnmh7hLAVsevE"
AT_CREATORS = "tblQUz8zQRDdZvES3"

# Brand detection keywords
BRAND_KEYWORDS = {
    "Grosmimi": ["grosmimi", "gros", "straw cup", "ppsu", "tumbler", "baby bottle"],
    "CHA&MOM": ["chaenmom", "cha&mom", "chamom", "cha & mom"],
    "Naeiae": ["naeiae", "snack", "puff", "rice"],
}

# SSL context for Windows
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def at_fetch_all():
    """Fetch all records from Airtable Creators table (handles pagination)."""
    records = []
    offset = None
    while True:
        url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CREATORS}?pageSize=100"
        if offset:
            url += f"&offset={offset}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {AIRTABLE_API_KEY}")
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"[ERROR] Airtable API error: {e.code}")
            body = e.read().decode("utf-8", errors="replace")
            print(f"  {body[:300]}")
            break
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)  # Rate limit courtesy
    return records


def detect_brand(fields):
    """Detect brand from Airtable fields."""
    brand = fields.get("Brand", "").strip()
    if brand:
        return brand
    # Try to infer from other fields
    text = " ".join([
        fields.get("Notes", ""),
        fields.get("Product", ""),
        fields.get("Subject", ""),
    ]).lower()
    for b, keywords in BRAND_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return b
    return "Unknown"


def at_record_to_creator(record):
    """Convert Airtable record to PipelineCreator API payload."""
    f = record.get("fields", {})
    email = (f.get("Email") or "").strip().lower()
    if not email:
        return None

    # Detect outreach type from followers/views
    followers = None
    try:
        followers = int(f.get("Followers") or f.get("followers") or 0)
    except (ValueError, TypeError):
        pass

    avg_views = None
    try:
        avg_views = int(f.get("Avg Views") or f.get("avg_views") or 0)
    except (ValueError, TypeError):
        pass

    outreach_type = f.get("Outreach Type", "") or f.get("Type", "")
    if not outreach_type and followers:
        outreach_type = "HT" if followers >= 100000 else "LT"

    # Status mapping
    status_map = {
        "Not Started": "Not Started",
        "Draft Ready": "Draft Ready",
        "Sent": "Sent",
        "Replied": "Replied",
        "Needs Review": "Needs Review",
        "Accepted": "Accepted",
        "Declined": "Declined",
        "Sample Sent": "Sample Sent",
        "Sample Shipped": "Sample Shipped",
        "Sample Delivered": "Sample Delivered",
        "Posted": "Posted",
    }
    raw_status = f.get("Status", "Not Started")
    pipeline_status = status_map.get(raw_status, raw_status)

    return {
        "email": email,
        "ig_handle": f.get("IG Handle") or f.get("Instagram") or "",
        "tiktok_handle": f.get("TikTok Handle") or f.get("TikTok") or "",
        "full_name": f.get("Name") or f.get("Full Name") or "",
        "platform": f.get("Platform") or "",
        "pipeline_status": pipeline_status,
        "brand": detect_brand(f),
        "outreach_type": outreach_type,
        "source": "outbound",
        "followers": followers,
        "avg_views": avg_views,
        "airtable_record_id": record.get("id", ""),
        "notes": f.get("Notes") or "",
        "changed_by": "migration",
    }


def ec2_upsert(payload):
    """POST creator to EC2 API."""
    url = f"{EC2_API}/pipeline/creators/"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    # Basic auth
    import base64
    cred = base64.b64encode(f"{EC2_USER}:{EC2_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")

    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body


def main():
    parser = argparse.ArgumentParser(description="Migrate Airtable Creators to PG")
    parser.add_argument("--execute", action="store_true", help="Actually migrate (default is dry-run)")
    parser.add_argument("--dump", action="store_true", help="Dump Airtable data to JSON")
    args = parser.parse_args()

    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY not set in environment")
        sys.exit(1)

    print("=" * 60)
    print("Airtable -> PG Migration")
    print(f"  Source: Airtable {AT_BASE}/{AT_CREATORS}")
    print(f"  Target: {EC2_API}/pipeline/creators/")
    print(f"  Mode:   {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print("=" * 60)

    # Fetch all records
    print("\n[1/3] Fetching Airtable Creators...")
    records = at_fetch_all()
    print(f"  Found {len(records)} records")

    if args.dump:
        dump_path = os.path.join(os.path.dirname(__file__), "..", ".tmp", "airtable_creators_dump.json")
        os.makedirs(os.path.dirname(dump_path), exist_ok=True)
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Dumped to {dump_path}")
        return

    # Convert
    print("\n[2/3] Converting records...")
    payloads = []
    skipped = 0
    for rec in records:
        p = at_record_to_creator(rec)
        if p:
            payloads.append(p)
        else:
            skipped += 1

    # Stats
    brands = {}
    statuses = {}
    for p in payloads:
        brands[p["brand"]] = brands.get(p["brand"], 0) + 1
        statuses[p["pipeline_status"]] = statuses.get(p["pipeline_status"], 0) + 1

    print(f"  Valid:   {len(payloads)}")
    print(f"  Skipped: {skipped} (no email)")
    print(f"  Brands:  {dict(sorted(brands.items(), key=lambda x: -x[1]))}")
    print(f"  Status:  {dict(sorted(statuses.items(), key=lambda x: -x[1]))}")

    if not args.execute:
        print("\n[DRY-RUN] No changes made. Use --execute to migrate.")
        print("  Sample payloads:")
        for p in payloads[:3]:
            print(f"    {p['email']} | {p['ig_handle']} | {p['brand']} | {p['pipeline_status']}")
        return

    # Execute migration
    print(f"\n[3/3] Migrating {len(payloads)} creators to PG...")
    created = 0
    updated = 0
    errors = 0
    for i, p in enumerate(payloads):
        status, resp = ec2_upsert(p)
        if status == 201:
            created += 1
        elif status == 200:
            updated += 1
        else:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] {p['email']}: {status} {str(resp)[:100]}")
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(payloads)} (created={created}, updated={updated}, errors={errors})")
        time.sleep(0.05)  # Gentle on the API

    print(f"\n{'=' * 60}")
    print(f"Migration complete!")
    print(f"  Created:  {created}")
    print(f"  Updated:  {updated}")
    print(f"  Errors:   {errors}")
    print(f"  Total:    {len(payloads)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
