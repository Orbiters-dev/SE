#!/usr/bin/env python3
"""
Content Intelligence Pipeline — Orchestrator
=============================================
JP/US Discovery 영상 분석: Whisper(transcript) + GPT-4o Vision(scene_fit, brand_fit_score)

Usage:
  python tools/analyze_video_content.py --region jp
  python tools/analyze_video_content.py --region jp --max 5        # 테스트
  python tools/analyze_video_content.py --region jp --dry-run      # 다운로드만, PG 업서트 없음
  python tools/analyze_video_content.py --region us --max 10
"""
import argparse
import base64
import io
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env
load_env()

from ci.downloader import get_cdn_url, extract_audio_and_frames
from ci.whisper_transcriber import transcribe, detect_product_mention, analyze_script
from ci.vision_tagger import analyze_frames

DB_HOST = os.getenv("DB_HOST", "172.31.13.240")
DB_NAME = os.getenv("DB_NAME", "export_calculator_db")
DB_USER = os.getenv("DB_USER", "es_db_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "orbit1234")


def _get_conn():
    import psycopg2
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)


def fetch_video_posts(region: str, vision_only: bool = False) -> list[dict]:
    """PG에서 영상 포스트 가져오기 (direct DB query)."""
    conn = _get_conn()
    cur = conn.cursor()

    if vision_only:
        cur.execute("""
            SELECT post_id, username, url, views_30d, post_date, platform, transcript
            FROM gk_content_posts
            WHERE region = %s
              AND transcript IS NOT NULL AND LENGTH(transcript) > 0
              AND (brand_fit_score IS NULL OR brand_fit_score = 0)
              AND url IS NOT NULL AND url != ''
            ORDER BY views_30d DESC NULLS LAST
        """, (region,))
    else:
        cur.execute("""
            SELECT post_id, username, url, views_30d, post_date, platform, transcript
            FROM gk_content_posts
            WHERE region = %s
              AND (transcript IS NULL OR transcript = '')
              AND url IS NOT NULL AND url != ''
            ORDER BY views_30d DESC NULLS LAST
        """, (region,))

    rows = cur.fetchall()
    conn.close()

    posts = []
    for post_id, username, url, views, post_date, platform, transcript in rows:
        posts.append({
            "post_id": post_id,
            "handle": username or "",
            "url": url,
            "views": views or 0,
            "post_date": str(post_date) if post_date else None,
            "platform": platform or "instagram",
            "transcript": transcript or "",
        })

    if vision_only:
        print(f"[FETCH] {len(posts)} posts with transcript but no brand_fit (Vision-only)")
    else:
        print(f"[FETCH] {len(posts)} posts needing transcript")
    return posts


def push_results(post_url: str, results: dict, dry_run: bool) -> bool:
    """분석 결과를 PG에 upsert (direct DB update)."""
    if dry_run:
        print(f"  [DRY-RUN] Would update: {json.dumps(results, ensure_ascii=False)[:100]}")
        return True

    # Build ci_analysis JSON
    ci = {}
    for k in ("hook_score", "hook_type", "storytelling_score", "authenticity_score",
              "delivery_score", "emotional_tone", "demo_present", "cta_present",
              "delivery_verbal_score", "hook_text", "persuasion_type",
              "key_message", "script_structure", "vocabulary_level",
              "repeat_watchability", "reasoning"):
        if k in results:
            ci[k] = results[k]

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE gk_content_posts SET
                transcript = %s,
                scene_fit = %s,
                has_subtitles = %s,
                brand_fit_score = %s,
                scene_tags = %s,
                product_mention = %s,
                subject_age = %s,
                ci_analysis = %s
            WHERE url = %s
        """, (
            results.get("transcript", ""),
            results.get("scene_fit", ""),
            results.get("has_subtitles", False),
            results.get("brand_fit_score", 0),
            ",".join(results.get("scene_tags", [])),
            results.get("product_mention", False),
            results.get("subject_age", ""),
            json.dumps(ci, ensure_ascii=False) if ci else None,
            post_url,
        ))
        conn.commit()
        updated = cur.rowcount > 0
        conn.close()
        return updated
    except Exception as e:
        print(f"  [PG] Update failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="jp")
    parser.add_argument("--max", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-views", type=int, default=0, help="Only process posts with views >= N (cost filter)")
    parser.add_argument("--vision-only", action="store_true", help="Run Vision on posts that have transcript but no brand_fit_score")
    args = parser.parse_args()

    lang = "ja" if args.region == "jp" else "en"
    posts = fetch_video_posts(args.region, vision_only=args.vision_only)
    if args.min_views > 0:
        before = len(posts)
        posts = [p for p in posts if (p.get("views") or 0) >= args.min_views]
        print(f"[FILTER] views >= {args.min_views}: {len(posts)}/{before} posts")
    if args.max > 0:
        posts = posts[:args.max]

    success, fail, skip = 0, 0, 0
    total_cost_est = 0.0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for i, post in enumerate(posts, 1):
            url = post["url"]
            handle = post.get("handle", "?")
            print(f"\n[{i}/{len(posts)}] @{handle} — {url[:55]}")

            # Step 1: CDN URL (Apify for IG, yt-dlp for TikTok)
            platform = (post.get("platform") or "instagram").lower()
            cdn_url = get_cdn_url(url, platform)
            if not cdn_url:
                print("  SKIP: no CDN URL")
                skip += 1
                continue

            # Step 2: 오디오 + 키프레임 추출
            post_tmp = tmp / f"post_{i}"
            post_tmp.mkdir()
            audio, frames = extract_audio_and_frames(cdn_url, post_tmp, post_url=url, platform=platform)

            results = {
                "handle": post.get("handle", ""),
                "views": post.get("views"),
            }

            # Step 3: Whisper (skip if vision-only — transcript already exists)
            if args.vision_only:
                results["transcript"] = post.get("transcript", "")
                results["product_mention"] = detect_product_mention(results["transcript"], args.region)
                print(f"  Whisper: SKIP (vision-only, existing {len(results['transcript'])} chars)")
            elif audio:
                transcript = transcribe(audio, language=lang)
                results["transcript"] = transcript or ""
                results["product_mention"] = detect_product_mention(transcript or "", args.region)
                cost_w = (audio.stat().st_size / (1024*1024)) / 10 * 0.006  # rough estimate
                total_cost_est += cost_w
                kw = "✅" if results["product_mention"] else "—"
                print(f"  Whisper: {len(transcript or '')} chars | product_mention: {kw}")
            else:
                results["transcript"] = ""
                results["product_mention"] = False
                print("  Whisper: skipped (no audio)")

            # Step 4: GPT-4o Vision (expanded HVA analysis)
            if frames:
                vision = analyze_frames(frames)
                results.update(vision)
                total_cost_est += len(frames) * 0.000085  # low-res per frame
                print(f"  Vision: fit={vision['scene_fit']} score={vision['brand_fit_score']}/10 hook={vision.get('hook_score',0)}/10 | {vision['reasoning'][:60]}")
            else:
                results.update({"scene_fit": "LOW", "has_subtitles": False,
                                 "brand_fit_score": 0, "scene_tags": []})
                print("  Vision: skipped (no frames)")

            # Step 5: Script analysis (transcript-based)
            if results.get("transcript"):
                script = analyze_script(results["transcript"], language=lang)
                results.update(script)
                total_cost_est += 0.0002  # gpt-4o-mini is cheap
                print(f"  Script: delivery={script['delivery_verbal_score']}/10 persuasion={script['persuasion_type']} | {script.get('key_message','')[:60]}")
            else:
                print("  Script: skipped (no transcript)")

            # Step 6: PG upsert
            if push_results(url, results, args.dry_run):
                success += 1
            else:
                fail += 1

    print(f"\n{'='*50}")
    print(f"✓ Done: {success} analyzed, {skip} skipped, {fail} failed")
    print(f"  Estimated API cost: ${total_cost_est:.3f}")
    print(f"  brand_fit HIGH: check dashboard → Influencer Sheet")


if __name__ == "__main__":
    main()
