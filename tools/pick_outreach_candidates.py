#!/usr/bin/env python3
"""
Pick Outreach Candidates from Discovery Posts
==============================================
PG discovery_posts에서 아웃리치 후보 Top N 선발.

Usage:
  # Top 10 by views (default)
  python tools/pick_outreach_candidates.py

  # Top 10 by followers
  python tools/pick_outreach_candidates.py --sort followers

  # Top 20 by views, IG only
  python tools/pick_outreach_candidates.py --sort views --count 20 --platform instagram

  # Filter: min 1000 followers
  python tools/pick_outreach_candidates.py --min-followers 1000

  # Mark selected as "shortlisted"
  python tools/pick_outreach_candidates.py --sort views --mark

  # Preview specific batch
  python tools/pick_outreach_candidates.py --batch "Mar24-Mar31"
"""

import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
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


def _auth():
    return "Basic " + base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()


def _get(endpoint, params=None):
    url = f"{ORBITOOLS_URL}/api/onzenna/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth())
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _put(endpoint, data):
    url = f"{ORBITOOLS_URL}/api/onzenna/{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", _auth())
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def pick_candidates(sort_by, count, region, platform, batch,
                    min_followers, min_views, mark):
    """Query PG and display top candidates."""

    params = {
        "region": region,
        "status": "discovered",  # only new, un-contacted posts
        "order_by": sort_by,
        "limit": count,
    }
    if platform:
        params["platform"] = platform
    if batch:
        params["batch"] = batch
    if min_followers:
        params["min_followers"] = min_followers
    if min_views:
        params["min_views"] = min_views

    # Fetch more than needed to account for handle dedup
    params["limit"] = count * 3
    data = _get("discovery/posts/", params)
    raw_posts = data.get("results", [])
    total = data.get("total", 0)

    # Dedup by handle — keep best post per creator
    seen_handles = set()
    posts = []
    for p in raw_posts:
        h = p.get("handle", "").lower()
        if h in seen_handles:
            continue
        seen_handles.add(h)
        posts.append(p)
        if len(posts) >= count:
            break

    sort_label = {"views": "Views", "followers": "Followers", "likes": "Likes", "date": "Date"}
    print(f"{'='*70}")
    print(f"  OUTREACH CANDIDATES — Top {count} by {sort_label.get(sort_by, sort_by)}")
    print(f"  Region: {region} | Platform: {platform or 'all'} | Total pool: {total}")
    print(f"{'='*70}")
    print()

    if not posts:
        print("  No candidates found.")
        return []

    # Header
    print(f"  {'#':>3} {'Handle':<22} {'Platform':<10} {'Followers':>10} {'Views':>10} {'Likes':>8} {'Date':<12} {'Caption'}")
    print(f"  {'—'*3} {'—'*22} {'—'*10} {'—'*10} {'—'*10} {'—'*8} {'—'*12} {'—'*30}")

    for i, p in enumerate(posts, 1):
        handle = p.get("handle", "")[:20]
        plat = p.get("platform", "")[:8]
        followers = p.get("followers") or 0
        views = p.get("views") or 0
        likes = p.get("likes") or 0
        date = (p.get("post_date") or "")[:10]
        caption = (p.get("caption") or "")[:40].replace("\n", " ")

        # Highlight sort column
        if sort_by == "views":
            views_str = f"*{views:>9,}"
        else:
            views_str = f"{views:>10,}"
        if sort_by == "followers":
            fol_str = f"*{followers:>9,}"
        else:
            fol_str = f"{followers:>10,}"

        print(f"  {i:>3} @{handle:<21} {plat:<10} {fol_str} {views_str} {likes:>8,} {date:<12} {caption}")

    print()

    # URL list for quick access
    print(f"  — URLs —")
    for i, p in enumerate(posts, 1):
        print(f"  {i:>3}. {p.get('url', '')}")

    # Mark as shortlisted
    if mark:
        print(f"\n  Marking {len(posts)} posts as 'shortlisted'...")
        for p in posts:
            pid = p.get("id")
            try:
                _put(f"discovery/posts/{pid}/", {"outreach_status": "shortlisted"})
            except Exception as e:
                print(f"  Error marking {pid}: {e}")
        print(f"  Done! {len(posts)} posts marked as shortlisted.")

    return posts


def main():
    parser = argparse.ArgumentParser(description="Pick outreach candidates from Discovery")
    parser.add_argument("--sort", default="views", choices=["views", "followers", "likes", "date"],
                        help="Sort by: views (default) | followers | likes | date")
    parser.add_argument("--count", type=int, default=10, help="Number of candidates (default: 10)")
    parser.add_argument("--region", default="jp", help="Region: jp or us")
    parser.add_argument("--platform", help="Filter: instagram or tiktok")
    parser.add_argument("--batch", help="Filter by discovery batch name")
    parser.add_argument("--min-followers", type=int, help="Minimum followers filter")
    parser.add_argument("--min-views", type=int, help="Minimum views filter")
    parser.add_argument("--mark", action="store_true", help="Mark selected as 'shortlisted' in PG")
    args = parser.parse_args()

    if not ORBITOOLS_PASS:
        print("ERROR: ORBITOOLS_PASS not set")
        sys.exit(1)

    pick_candidates(
        sort_by=args.sort,
        count=args.count,
        region=args.region,
        platform=args.platform,
        batch=args.batch,
        min_followers=args.min_followers,
        min_views=args.min_views,
        mark=args.mark,
    )


if __name__ == "__main__":
    main()
