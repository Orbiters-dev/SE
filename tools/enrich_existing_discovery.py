#!/usr/bin/env python3
"""
Backfill enrichment for existing JP discovery posts.
=====================================================
Fetches existing posts from PG API, runs RapidAPI (likes/comments)
+ Apify (videoViewCount) enrichment, and re-syncs to PG.

Usage:
  # Full backfill (all IG posts without views)
  python tools/enrich_existing_discovery.py --region jp

  # Dry run (enrich but don't sync to PG)
  python tools/enrich_existing_discovery.py --region jp --dry-run

  # Limit handles (for testing)
  python tools/enrich_existing_discovery.py --region jp --max-handles 10
"""

import argparse
import base64
import io
import json
import os
import sys
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

ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "discovery"


def _auth_header():
    cred = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return f"Basic {cred}"


def fetch_existing_posts(region: str) -> list[dict]:
    """Fetch all discovery posts from PG API."""
    url = f"{ORBITOOLS_URL}/api/onzenna/discovery/posts/?region={region}&limit=5000"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header())

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    posts = data.get("results", []) if isinstance(data, dict) else data
    print(f"[FETCH] Got {len(posts)} posts from PG (region={region})")
    return posts


def pg_to_discovery_format(posts: list[dict]) -> list[dict]:
    """Convert PG API format back to fetch_jp_discovery format for enrichment."""
    converted = []
    for p in posts:
        converted.append({
            "Handle": p.get("handle", ""),
            "Full Name": p.get("full_name", ""),
            "Platform": p.get("platform", ""),
            "URL": p.get("url", ""),
            "Date": p.get("post_date", ""),
            "Type": p.get("content_type", ""),
            "Source": p.get("source", ""),
            "Followers": p.get("followers") or 0,
            "Views": p.get("views") or 0,
            "Likes": p.get("likes") or 0,
            "Comments Count": p.get("comments_count") or 0,
            "Hashtags": p.get("hashtags", ""),
            "Mentions": p.get("mentions", ""),
            "Caption": p.get("caption", ""),
            "Transcript": p.get("transcript", ""),
            "_post_id": (p.get("url", "").rstrip("/").split("/")[-1]) if p.get("url") else "",
        })
    return converted


def main():
    parser = argparse.ArgumentParser(description="Backfill enrichment for existing discovery posts")
    parser.add_argument("--region", default="jp")
    parser.add_argument("--dry-run", action="store_true", help="Enrich but don't sync to PG")
    parser.add_argument("--max-handles", type=int, default=0, help="Limit handles for testing (0=all)")
    parser.add_argument("--skip-views", action="store_true", default=False, help="Skip Apify view enrichment")
    parser.add_argument("--reels-only", action="store_true", help="Only enrich Reel posts for views (saves Apify credits)")
    parser.add_argument("--only-missing", action="store_true", help="Only enrich posts with likes=0 (skip already enriched)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between RapidAPI calls (seconds)")
    args = parser.parse_args()

    # Import enrichment functions
    from fetch_jp_discovery import enrich_ig_posts, enrich_ig_views

    # Step 1: Fetch existing posts from PG
    pg_posts = fetch_existing_posts(args.region)
    if not pg_posts:
        print("No posts found")
        return

    # Step 2: Convert to enrichment format
    discovery_posts = pg_to_discovery_format(pg_posts)
    ig_posts = [p for p in discovery_posts if p["Platform"] == "instagram"]
    tt_posts = [p for p in discovery_posts if p["Platform"] != "instagram"]

    print(f"\n[STATS] IG: {len(ig_posts)}, TikTok: {len(tt_posts)}")
    print(f"  IG with views>0:    {sum(1 for p in ig_posts if (p['Views'] or 0) > 0)}")
    print(f"  IG with likes>0:    {sum(1 for p in ig_posts if (p['Likes'] or 0) > 0)}")
    print(f"  IG with comments>0: {sum(1 for p in ig_posts if (p['Comments Count'] or 0) > 0)}")

    # Filter to only missing if requested
    already_enriched = []
    if args.only_missing:
        needs_enrich = [p for p in ig_posts if (p["Likes"] or 0) == 0]
        already_enriched = [p for p in ig_posts if (p["Likes"] or 0) > 0]
        print(f"\n[FILTER] --only-missing: {len(needs_enrich)} posts need enrichment, {len(already_enriched)} already have likes")
        ig_posts = needs_enrich

    # Limit handles for testing
    if args.max_handles > 0:
        handles = list(set(p["Handle"] for p in ig_posts))[:args.max_handles]
        ig_posts = [p for p in ig_posts if p["Handle"] in handles]
        print(f"\n[TEST] Limited to {args.max_handles} handles ({len(ig_posts)} posts)")

    # Step 3: RapidAPI enrichment (likes + comments)
    ig_posts = enrich_ig_posts(ig_posts, delay=args.delay)

    # Step 4: Apify view enrichment (videoViewCount)
    if not args.skip_views:
        target_posts = ig_posts
        if args.reels_only:
            video_posts = [p for p in ig_posts if (p.get("Type") or "").lower() in ("video", "reel")]
            non_video = [p for p in ig_posts if (p.get("Type") or "").lower() not in ("video", "reel")]
            print(f"[VIEWS] --reels-only: {len(video_posts)} video/reel posts, {len(non_video)} image/sidecar skipped")
            video_posts = enrich_ig_views(video_posts)
            ig_posts = video_posts + non_video
        else:
            ig_posts = enrich_ig_views(ig_posts)
    else:
        print("[VIEWS] Skipped (--skip-views)")

    # Stats after enrichment
    print(f"\n[AFTER] IG posts enriched:")
    print(f"  views>0:    {sum(1 for p in ig_posts if (p['Views'] or 0) > 0)}/{len(ig_posts)}")
    print(f"  likes>0:    {sum(1 for p in ig_posts if (p['Likes'] or 0) > 0)}/{len(ig_posts)}")
    print(f"  comments>0: {sum(1 for p in ig_posts if (p['Comments Count'] or 0) > 0)}/{len(ig_posts)}")

    # Merge back already-enriched posts (only sync newly enriched to PG)
    if args.only_missing and already_enriched:
        ig_posts_to_sync = ig_posts  # only newly enriched
        ig_posts = ig_posts + already_enriched  # full set for JSON
    else:
        ig_posts_to_sync = ig_posts

    # Step 5: Save enriched JSON
    all_posts = ig_posts + tt_posts
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = OUTPUT_DIR / f"{today}_jp_ig_discovery_enriched.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ig_posts, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[SAVE] {out_path.name} ({len(ig_posts)} posts)")

    # Step 6: Sync to PG
    if not args.dry_run:
        print(f"\n[SYNC] Re-syncing enriched data to PG...")
        from sync_discovery_to_pg import sync_to_pg
        sync_to_pg(ig_posts_to_sync + tt_posts, region=args.region, batch=f"backfill-{today}")
        print("[SYNC] Done!")
    else:
        print("[DRY-RUN] Skipping PG sync")

    print(f"\n✓ Backfill enrichment complete!")


if __name__ == "__main__":
    main()
