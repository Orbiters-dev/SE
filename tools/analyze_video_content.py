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

ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")


def _auth():
    return "Basic " + base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()


def fetch_video_posts(region: str) -> list[dict]:
    """PG에서 영상 포스트 가져오기 (content_type=Video, ci_processed_at IS NULL)."""
    url = f"{ORBITOOLS_URL}/api/onzenna/discovery/posts/?region={region}&limit=5000"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth())
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    posts = data.get("results", [])

    video_posts = [
        p for p in posts
        if (p.get("content_type") or "").lower() in ("video", "reel")
        and not p.get("transcript")  # 아직 처리 안 된 것만
        and p.get("url")
        and p.get("platform", "").lower() == "instagram"  # IG만 (TikTok CDN URL 없음)
    ]
    print(f"[FETCH] {len(posts)} total posts, {len(video_posts)} IG videos to analyze")
    return video_posts


def push_results(post_url: str, results: dict, dry_run: bool) -> bool:
    """분석 결과를 PG에 upsert."""
    if dry_run:
        print(f"  [DRY-RUN] Would update: {json.dumps(results, ensure_ascii=False)[:100]}")
        return True

    # Core CI fields (individual columns)
    post_payload = {
        "url": post_url,
        "transcript": results.get("transcript", ""),
        "scene_fit": results.get("scene_fit", ""),
        "has_subtitles": results.get("has_subtitles", False),
        "brand_fit_score": results.get("brand_fit_score", 0),
        "scene_tags": ",".join(results.get("scene_tags", [])),
        "product_mention": results.get("product_mention", False),
        "subject_age": results.get("subject_age", ""),
    }
    # Extended analysis → ci_analysis JSON
    ci = {}
    for k in ("hook_score", "hook_type", "storytelling_score", "authenticity_score",
              "delivery_score", "emotional_tone", "demo_present", "cta_present",
              "delivery_verbal_score", "hook_text", "persuasion_type",
              "key_message", "script_structure", "vocabulary_level",
              "repeat_watchability", "reasoning"):
        if k in results:
            ci[k] = results[k]
    if ci:
        post_payload["ci_analysis"] = ci
    if results.get("handle"):
        post_payload["handle"] = results["handle"]
    if results.get("views") is not None:
        post_payload["views"] = results["views"]
    body = json.dumps({"posts": [post_payload]}).encode()

    req = urllib.request.Request(
        f"{ORBITOOLS_URL}/api/onzenna/discovery/posts/",
        data=body, method="POST"
    )
    req.add_header("Authorization", _auth())
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 300
    except Exception as e:
        print(f"  [PG] Update failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="jp")
    parser.add_argument("--max", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-views", type=int, default=0, help="Only process posts with views >= N (cost filter)")
    args = parser.parse_args()

    lang = "ja" if args.region == "jp" else "en"
    posts = fetch_video_posts(args.region)
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

            # Step 1: Apify CDN URL
            cdn_url = get_cdn_url(url, "instagram")
            if not cdn_url:
                print("  SKIP: no CDN URL")
                skip += 1
                continue

            # Step 2: 오디오 + 키프레임 추출
            post_tmp = tmp / f"post_{i}"
            post_tmp.mkdir()
            audio, frames = extract_audio_and_frames(cdn_url, post_tmp)

            results = {
                "handle": post.get("handle", ""),
                "views": post.get("views"),
            }

            # Step 3: Whisper
            if audio:
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
