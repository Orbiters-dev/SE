"""
Quick test: v2 scoring pipeline on sample creators from PG.
Tests score_calculator v2 + enricher (Apify + GPT comment classification).

Usage:
    python tools/ci/test_v2_scoring.py --dry-run          # show what would be enriched
    python tools/ci/test_v2_scoring.py --limit 5           # enrich 5 creators
    python tools/ci/test_v2_scoring.py --limit 5 --no-apify  # v2 scores with dummy enrichment
"""

import os, sys, json, io
from pathlib import Path

# Fix encoding
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
TOOLS_DIR = DIR.parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

from score_calculator import calculate_scores_v2
from enricher import enrich_creator


def fetch_sample_creators(limit=10):
    """Get creators with existing CI scores from PG."""
    import requests
    user = os.getenv("ORBITOOLS_USER", "admin")
    pw = os.getenv("ORBITOOLS_PASS", "orbit1234")
    base = "https://orbitools.orbiters.co.kr/api/datakeeper"

    # Get content posts with scores
    resp = requests.get(
        f"{base}/query/",
        params={"table": "content_posts", "limit": str(limit * 3)},
        auth=(user, pw),
        timeout=30,
        verify=False,
    )
    if not resp.ok:
        print(f"  PG query failed: {resp.status_code}")
        return []

    rows = resp.json().get("rows", [])

    # Filter to those with views (v1 scores optional)
    scored = []
    seen_users = set()
    for r in rows:
        username = r.get("username", "")
        if not username or username in seen_users:
            continue
        views = int(r.get("views_30d", 0) or 0)
        if views >= 1000:
            seen_users.add(username)
            scored.append(r)
            if len(scored) >= limit:
                break

    # Sort by views descending
    scored.sort(key=lambda x: int(x.get("views_30d", 0) or 0), reverse=True)
    return scored


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-apify", action="store_true", help="Skip Apify, use dummy enrichment")
    args = parser.parse_args()

    print(f"=== CI v2 Scoring Test ({args.limit} creators) ===\n")

    # Step 1: Get sample creators
    print("Step 1: Fetching sample creators from PG...")
    creators = fetch_sample_creators(args.limit)
    if not creators:
        print("  No scored creators found in PG. Exiting.")
        return

    print(f"  Found {len(creators)} creators with v1 scores\n")

    if args.dry_run:
        for c in creators:
            print(f"  {c.get('username', '?'):20s}  "
                  f"v1_quality={c.get('content_quality_score', '?'):>3}  "
                  f"v1_fit={c.get('creator_fit_score', '?'):>3}  "
                  f"url={c.get('url', '')[:60]}")
        print(f"\n  Would enrich {len(creators)} creators via Apify.")
        print("  Run without --dry-run to execute.")
        return

    # Step 2: Enrich + Score
    results = []
    for i, c in enumerate(creators, 1):
        username = c.get("username", "")
        post_url = c.get("url", "")
        platform = "tiktok" if "tiktok" in (post_url or "") else "instagram"

        print(f"\n--- [{i}/{len(creators)}] {username} ---")
        print(f"  Post: {post_url[:80]}")
        print(f"  v1 scores: quality={c.get('content_quality_score')}, fit={c.get('creator_fit_score')}")

        # Enrichment
        if args.no_apify:
            enrichment = {
                "duration_seconds": 28,
                "posts_last_30d": 12,
                "sponsored_count": 2,
                "total_posts_checked": 30,
                "avg_likes": 150,
                "avg_comments": 8,
                "platforms": [platform],
                "total_comments": 20,
                "meaningful_comments": 12,
                "bot_comments": 3,
            }
            print("  [no-apify] Using dummy enrichment data")
        else:
            enrichment = enrich_creator(username, post_url, platform)

        # Build CI results from existing v1 data
        ci_results = {}
        ci_analysis = c.get("ci_analysis")
        if ci_analysis:
            if isinstance(ci_analysis, str):
                try:
                    ci_results = json.loads(ci_analysis)
                except Exception:
                    pass
            elif isinstance(ci_analysis, dict):
                ci_results = ci_analysis

        # Add other known fields
        for field in ("scene_fit", "has_subtitles", "brand_fit_score", "scene_tags",
                      "product_mention", "subject_age"):
            if c.get(field) is not None:
                ci_results[field] = c[field]

        followers = enrichment.get("followers") or c.get("followers", 0) or 0
        views = c.get("views_30d", 0) or 0
        likes = c.get("likes_30d", 0) or 0
        comments = c.get("comments_30d", 0) or 0

        # v2 scoring
        v2 = calculate_scores_v2(
            ci_results, followers, views, likes, comments,
            enrichment=enrichment,
        )

        print(f"  v2 composite: {v2['composite_v2_score']}")
        print(f"  tier_scores: {v2['tier_scores']}")
        print(f"  duration: {v2['duration']}")
        print(f"  comment_quality: {v2['comment_quality']}")
        print(f"  bot_detection: {v2['bot_detection']}")
        print(f"  posting_frequency: {v2['posting_frequency']}")
        print(f"  collab_history: {v2['collab_history']}")
        print(f"  audio_tone: {v2.get('audio_tone', 'N/A')}")
        print(f"  audio_bonus: {v2.get('audio_bonus', 0)}")

        results.append({
            "username": username,
            "post_url": post_url,
            "v1_quality": c.get("content_quality_score"),
            "v1_fit": c.get("creator_fit_score"),
            "v2_composite": v2["composite_v2_score"],
            "v2_tier_scores": v2["tier_scores"],
            "v2_detail": {k: v for k, v in v2.items()
                         if k not in ("engagement_rate", "virality_coeff",
                                      "content_quality_score", "creator_fit_score",
                                      "scoring_version", "tier_scores", "composite_v2_score")},
        })

    # Step 3: Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} creators scored with v2")
    print(f"{'='*60}")
    print(f"{'Username':20s} {'v1_Q':>5} {'v1_F':>5} {'v2':>5} {'Content':>8} {'Fit':>8} {'Audience':>8} {'Perf':>8}")
    print("-" * 80)
    for r in results:
        ts = r["v2_tier_scores"]
        print(f"{r['username']:20s} {r.get('v1_quality','?'):>5} {r.get('v1_fit','?'):>5} "
              f"{r['v2_composite']:>5} {ts['content']:>8} {ts['fit']:>8} "
              f"{ts['audience']:>8} {ts['performance']:>8}")

    # Save results
    out_path = PROJECT_ROOT / ".tmp" / "ci_v2_test_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
