#!/usr/bin/env python3
"""
Seed test creator data into the Pipeline CRM database via EC2 API.

Usage:
    python tools/seed_pipeline_creators.py            # POST all 15 creators
    python tools/seed_pipeline_creators.py --dry-run   # Show what would be posted
    python tools/seed_pipeline_creators.py --clear      # Show clearing warning
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse
import json
import math
import urllib3

# Suppress InsecureRequestWarning for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE = "https://orbitools.orbiters.co.kr/api/onzenna/pipeline"
AUTH = ("admin", "admin")

# ---------------------------------------------------------------------------
# Test creator data (15 diverse entries)
# ---------------------------------------------------------------------------
CREATORS = [
    {
        "email": "sarah.momlife@gmail.com",
        "ig_handle": "sarah_momlife",
        "full_name": "Sarah Johnson",
        "platform": "Instagram",
        "pipeline_status": "Not Started",
        "brand": "Grosmimi",
        "outreach_type": "HT",
        "source": "outbound",
        "followers": 245000,
        "initial_discovery_date": "2025-11-02",
        "notes": "Seed data - momlife content creator, strong engagement with baby product reviews",
    },
    {
        "email": "tiny.steps@gmail.com",
        "ig_handle": "",
        "tiktok_handle": "tinysteps_mom",
        "full_name": "Emily Chen",
        "platform": "TikTok",
        "pipeline_status": "Not Started",
        "brand": "Grosmimi",
        "outreach_type": "HT",
        "source": "outbound",
        "followers": 520000,
        "initial_discovery_date": "2025-11-15",
        "notes": "Seed data - viral TikTok mom, known for product unboxings",
    },
    {
        "email": "jessica.b@outlook.com",
        "ig_handle": "jess_babystyle",
        "full_name": "Jessica Brown",
        "platform": "Instagram",
        "pipeline_status": "Draft Ready",
        "brand": "Grosmimi",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 32000,
        "initial_discovery_date": "2025-12-01",
        "notes": "Seed data - micro-influencer, aesthetic baby flat-lays",
    },
    {
        "email": "maria.garcia@gmail.com",
        "ig_handle": "mariamamabear",
        "full_name": "Maria Garcia",
        "platform": "Instagram",
        "pipeline_status": "Sent",
        "brand": "CHA&MOM",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 18000,
        "initial_discovery_date": "2026-01-10",
        "notes": "Seed data - bilingual (EN/ES) mom content, CHA&MOM skincare focus",
    },
    {
        "email": "ashley.k@gmail.com",
        "ig_handle": "ashleykmom",
        "full_name": "Ashley Kim",
        "platform": "Instagram",
        "pipeline_status": "Replied",
        "brand": "CHA&MOM",
        "outreach_type": "HT",
        "source": "outbound",
        "followers": 175000,
        "initial_discovery_date": "2026-01-20",
        "notes": "Seed data - Korean-American mom, beauty + baby routines",
    },
    {
        "email": "olivia.newmom@gmail.com",
        "ig_handle": "olivia_newmom",
        "full_name": "Olivia Taylor",
        "platform": "Instagram",
        "pipeline_status": "Accepted",
        "brand": "Grosmimi",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 28000,
        "initial_discovery_date": "2026-02-01",
        "notes": "Seed data - first-time mom journey, relatable content",
    },
    {
        "email": "rachel.w@gmail.com",
        "ig_handle": "rachelwbaby",
        "full_name": "Rachel Wang",
        "platform": "Instagram",
        "pipeline_status": "Not Started",
        "brand": "Naeiae",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 15000,
        "initial_discovery_date": "2026-02-15",
        "notes": "Seed data - baby food recipes, Naeiae snack reviews",
    },
    {
        "email": "momof3.life@gmail.com",
        "ig_handle": "",
        "tiktok_handle": "momof3life",
        "full_name": "Amanda Lee",
        "platform": "TikTok",
        "pipeline_status": "Sample Sent",
        "brand": "Naeiae",
        "outreach_type": "HT",
        "source": "inbound",
        "followers": 310000,
        "initial_discovery_date": "2026-02-20",
        "notes": "Seed data - inbound inquiry, mom-of-three daily vlogs",
    },
    {
        "email": "babyreviewer@gmail.com",
        "ig_handle": "babyreviews_daily",
        "full_name": "Megan Scott",
        "platform": "Instagram",
        "pipeline_status": "Declined",
        "brand": "Grosmimi",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 42000,
        "initial_discovery_date": "2026-02-28",
        "notes": "Seed data - declined due to exclusivity contract with competitor",
    },
    {
        "email": "kidsn.things@gmail.com",
        "ig_handle": "kidsnthings",
        "full_name": "Nicole Park",
        "platform": "Instagram",
        "pipeline_status": "Sample Shipped",
        "brand": "CHA&MOM",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 55000,
        "initial_discovery_date": "2026-03-01",
        "notes": "Seed data - kids product reviewer, organizes giveaways",
    },
    {
        "email": "first.mommy@gmail.com",
        "ig_handle": "firsttimemommy22",
        "full_name": "Sophia Martinez",
        "platform": "Instagram",
        "pipeline_status": "Needs Review",
        "brand": "Grosmimi",
        "outreach_type": "LT",
        "source": "inbound",
        "followers": 9500,
        "initial_discovery_date": "2026-03-05",
        "notes": "Seed data - inbound application, nano-influencer with high engagement rate",
    },
    {
        "email": "thetottribe@gmail.com",
        "ig_handle": "thetottribe",
        "full_name": "Christina Hall",
        "platform": "Instagram",
        "pipeline_status": "Sample Delivered",
        "brand": "Grosmimi",
        "outreach_type": "HT",
        "source": "outbound",
        "followers": 189000,
        "initial_discovery_date": "2026-03-10",
        "notes": "Seed data - parenting tribe community leader, PPSU bottle content",
    },
    {
        "email": "lena.babyfood@gmail.com",
        "ig_handle": "lena_babyfood",
        "full_name": "Lena Nguyen",
        "platform": "Instagram",
        "pipeline_status": "Posted",
        "brand": "Naeiae",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 67000,
        "initial_discovery_date": "2025-11-20",
        "notes": "Seed data - baby food specialist, posted Naeiae snack review reel",
    },
    {
        "email": "casey.motherhood@gmail.com",
        "ig_handle": "",
        "tiktok_handle": "casey_motherhood",
        "full_name": "Casey Adams",
        "platform": "TikTok",
        "pipeline_status": "Not Started",
        "brand": "Grosmimi",
        "outreach_type": "HT",
        "source": "outbound",
        "followers": 420000,
        "initial_discovery_date": "2026-03-15",
        "notes": "Seed data - comedic motherhood skits, huge reach potential",
    },
    {
        "email": "zara.babygear@gmail.com",
        "ig_handle": "zara_babygear",
        "full_name": "Zara Patel",
        "platform": "Instagram",
        "pipeline_status": "Not Started",
        "brand": "Naeiae",
        "outreach_type": "LT",
        "source": "outbound",
        "followers": 23000,
        "initial_discovery_date": "2026-03-18",
        "notes": "Seed data - baby gear + snack haul content",
    },
]


def _calc_avg_views(platform: str, followers: int) -> int:
    """IG: followers * 0.08, TikTok: followers * 0.15"""
    rate = 0.15 if platform == "TikTok" else 0.08
    return math.floor(followers * rate)


def _build_payload(creator: dict) -> dict:
    """Build the API payload for a single creator."""
    payload = {
        "email": creator["email"],
        "ig_handle": creator.get("ig_handle", ""),
        "tiktok_handle": creator.get("tiktok_handle", ""),
        "full_name": creator["full_name"],
        "platform": creator["platform"],
        "pipeline_status": creator["pipeline_status"],
        "brand": creator["brand"],
        "outreach_type": creator["outreach_type"],
        "source": creator["source"],
        "followers": creator["followers"],
        "avg_views": _calc_avg_views(creator["platform"], creator["followers"]),
        "initial_discovery_date": creator["initial_discovery_date"],
        "notes": creator["notes"],
    }
    return payload


def seed_creators(dry_run: bool = False) -> None:
    """POST each creator to the Pipeline CRM API."""
    url = f"{API_BASE}/creators/"
    success, fail, skip = 0, 0, 0

    for i, creator in enumerate(CREATORS, 1):
        payload = _build_payload(creator)
        label = f"[{i:02d}/{len(CREATORS)}] {creator['full_name']} ({creator['ig_handle'] or creator.get('tiktok_handle', '')})"

        if dry_run:
            print(f"  [DRY-RUN] {label}")
            print(f"            Status: {creator['pipeline_status']} | Brand: {creator['brand']} | "
                  f"Followers: {creator['followers']:,} | Avg Views: {payload['avg_views']:,}")
            print(f"            Payload: {json.dumps(payload, indent=None)}")
            print()
            continue

        try:
            resp = requests.post(url, json=payload, auth=AUTH, verify=False, timeout=15)
            if resp.status_code in (200, 201):
                data = resp.json()
                creator_id = data.get("id", "?")
                print(f"  OK  {label} -> id={creator_id}")
                success += 1
            elif resp.status_code == 400:
                # Likely duplicate email
                detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                print(f"  SKIP {label} -> 400: {detail}")
                skip += 1
            else:
                print(f"  FAIL {label} -> {resp.status_code}: {resp.text[:200]}")
                fail += 1
        except requests.RequestException as e:
            print(f"  ERR  {label} -> {e}")
            fail += 1

    if not dry_run:
        print(f"\n--- Summary: {success} created, {skip} skipped, {fail} failed ---")


def fetch_stats() -> None:
    """GET pipeline creator stats and print."""
    url = f"{API_BASE}/creators/stats/"
    print("\n=== Pipeline Creator Stats ===")
    try:
        resp = requests.get(url, auth=AUTH, verify=False, timeout=15)
        if resp.status_code == 200:
            stats = resp.json()
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print(f"  Failed to fetch stats: {resp.status_code} {resp.text[:300]}")
    except requests.RequestException as e:
        print(f"  Error fetching stats: {e}")


def main():
    parser = argparse.ArgumentParser(description="Seed test creators into Pipeline CRM")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted without sending")
    parser.add_argument("--clear", action="store_true", help="Show warning about clearing data")
    args = parser.parse_args()

    if args.clear:
        print("WARNING: Bulk clearing is not supported via the API.")
        print("To remove test data, delete individual creators via the admin panel:")
        print("  https://orbitools.orbiters.co.kr/admin/onzenna/pipelinecreator/")
        print("Or contact the DB admin to truncate the table.")
        return

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Seeding {len(CREATORS)} test creators into Pipeline CRM...\n")
    seed_creators(dry_run=args.dry_run)

    if not args.dry_run:
        fetch_stats()


if __name__ == "__main__":
    main()
