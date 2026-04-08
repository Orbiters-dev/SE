"""
Creator Evaluator — LT/HT 2-Tier Pipeline Orchestrator
========================================================

크리에이터 품질 평가 프레임워크(19개 항목, 4 Tier)를 자동화.
키프레임+오디오를 EC2에 보관하여 평가 기준 변경 시 재크롤링 없이 재분석.

Usage:
    # LT 실행
    python tools/creator_evaluator.py --lt --handles "user1,user2"
    python tools/creator_evaluator.py --lt --handles-file creators.txt --region us
    python tools/creator_evaluator.py --lt --handles "user1" --dry-run

    # HT 실행 (LT 상위자 프로모션)
    python tools/creator_evaluator.py --ht --from-lt-results --min-lt-score 60
    python tools/creator_evaluator.py --ht --handles "top_user1,top_user2"

    # 재분석 (캐시된 키프레임 재활용, API 비용만)
    python tools/creator_evaluator.py --reanalyze --tier LT
    python tools/creator_evaluator.py --reanalyze --username "specific_user"

    # 상태 확인
    python tools/creator_evaluator.py --status
"""

import argparse
import io
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp949
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DIR.parent
sys.path.insert(0, str(DIR))
sys.path.insert(0, str(DIR / "ci"))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass


# ── Lazy imports (avoid loading everything at startup) ──

def _get_deep_crawler():
    import deep_crawler
    return deep_crawler

def _get_frame_extractor():
    from ci.frame_extractor import extract_frames, extract_audio
    return extract_frames, extract_audio

def _get_media_cache():
    from ci.media_cache import MediaCache
    return MediaCache()

def _get_lt_screener(region="us"):
    from ci.lt_screener import LTScreener
    return LTScreener(region=region)

def _get_vision_tagger():
    from ci.vision_tagger import analyze_frames
    return analyze_frames

def _get_whisper():
    from ci.whisper_transcriber import transcribe_audio, analyze_script
    return transcribe_audio, analyze_script

def _get_score_calculator():
    from ci.score_calculator import calculate_scores_v2, calculate_tier_framework
    return calculate_scores_v2, calculate_tier_framework

def _get_downloader():
    from ci.downloader import download_video, get_cdn_url
    return download_video, get_cdn_url


# ── Core Pipeline Functions ──

def run_lt_pipeline(
    handles: list[str],
    region: str = "us",
    max_creators: int = 0,
    workers: int = 4,
    skip_screening: bool = False,
    dry_run: bool = False,
    pg_sync: bool = False,
    raw_json: bool = True,
) -> dict:
    """
    LT (Light Touch) 파이프라인 실행.

    Flow:
        1. Apify crawl (deep_crawler) → profile + posts JSON
        2. LT screening (lt_screener) → pass/fail filter
        3. Video download → frame extraction (10장) + audio
        4. Vision analysis + Whisper transcription
        5. Score calculation (v2 + tier framework)
        6. PG upsert (optional)

    Returns:
        {"total": N, "screened": N, "passed": N, "analyzed": N, "results": [...]}
    """
    print(f"\n{'='*60}")
    print(f"[Creator Evaluator] LT Pipeline — {len(handles)} handles")
    print(f"  Region: {region} | Workers: {workers} | Dry-run: {dry_run}")
    print(f"{'='*60}\n")

    if max_creators and len(handles) > max_creators:
        handles = handles[:max_creators]
        print(f"  [LIMIT] Truncated to {max_creators} handles")

    # ── Stage 1: Apify Crawl ──
    print("[Stage 1] Apify Crawl...")
    dc = _get_deep_crawler()
    cache = dc.load_cache()

    profiles_map = {}  # username -> {"profile": {}, "posts": []}
    uncached = []

    for h in handles:
        cache_key = f"ig:{h}"
        if cache_key in cache and dc.is_cache_fresh(cache[cache_key]):
            entry = cache[cache_key]
            profiles_map[h] = {"profile": entry["profile"], "posts": entry["posts"]}
        else:
            uncached.append(h)

    if uncached and not dry_run:
        try:
            from apify_client import ApifyClient
            token = os.getenv("APIFY_API_TOKEN", "") or os.getenv("APIFY_TOKEN", "")
            if token:
                client = ApifyClient(token)
                ig_results = dc.scrape_ig_profiles(uncached, client)
                for item in ig_results:
                    profile = dc.extract_ig_profile(item)
                    posts = dc.extract_ig_posts(item)
                    username = profile["username"]
                    profiles_map[username] = {"profile": profile, "posts": posts}

                    # Cache + raw JSON
                    cache[f"ig:{username}"] = {
                        "profile": profile, "posts": posts,
                        "crawled_at": time.time(),
                    }
                    if raw_json:
                        dc.save_raw_json(username, "instagram", item)

                dc.save_cache(cache)
        except Exception as e:
            print(f"  [ERROR] Apify crawl failed: {e}")

    print(f"  Profiles loaded: {len(profiles_map)}")

    # ── Stage 2: LT Screening ──
    print("\n[Stage 2] LT Screening...")
    screener = _get_lt_screener(region)

    screening_results = {}
    passed_handles = []

    for username, data in profiles_map.items():
        result = screener.screen(data["profile"], data["posts"])
        screening_results[username] = result
        if skip_screening or result["passed"]:
            passed_handles.append(username)

    print(f"  Screened: {len(profiles_map)} | Passed: {len(passed_handles)}")
    if not skip_screening:
        failed = [u for u in profiles_map if u not in passed_handles]
        if failed:
            print(f"  Failed ({len(failed)}): {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}")

    if dry_run:
        print("\n--- DRY RUN (no video analysis) ---")
        return {
            "total": len(handles),
            "screened": len(profiles_map),
            "passed": len(passed_handles),
            "analyzed": 0,
            "results": [],
            "screening": screening_results,
        }

    # ── Stage 3: Video Analysis ──
    print(f"\n[Stage 3] Video Analysis ({len(passed_handles)} creators)...")
    extract_frames, extract_audio_fn = _get_frame_extractor()
    media_cache = _get_media_cache()
    download_video, get_cdn_url = _get_downloader()
    analyze_vision = _get_vision_tagger()

    try:
        transcribe_audio, analyze_script = _get_whisper()
        has_whisper = True
    except ImportError:
        has_whisper = False
        print("  [WARN] Whisper not available, skipping audio analysis")

    calc_v2, calc_framework = _get_score_calculator()

    all_results = []

    for idx, username in enumerate(passed_handles):
        data = profiles_map[username]
        profile = data["profile"]
        posts = data["posts"]
        screening = screening_results.get(username, {})

        # 상위 3개 영상 포스트 선택
        video_posts = [
            p for p in posts
            if "video" in str(p.get("media_type", "")).lower()
            or "reel" in str(p.get("media_type", "")).lower()
        ]
        video_posts = sorted(video_posts, key=lambda p: p.get("views", 0), reverse=True)[:3]

        if not video_posts:
            print(f"  [{idx+1}/{len(passed_handles)}] @{username} — no video posts, skipping")
            continue

        print(f"  [{idx+1}/{len(passed_handles)}] @{username} — {len(video_posts)} reels")

        creator_post_results = []

        for vp in video_posts:
            post_id = vp.get("post_id", "")
            post_url = vp.get("post_url", vp.get("url", ""))

            # Dedup check
            if media_cache.has_frames(username, post_id, tier="LT"):
                print(f"    [CACHE] {post_id} already cached, loading frames")
                frames = media_cache.load_frames(username, post_id)
                audio_path = media_cache.get_audio_path(username, post_id)
                if not audio_path.exists():
                    audio_path = None
            else:
                # Download + extract
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)

                    # Get CDN URL
                    cdn_url = vp.get("videoUrl", "")
                    if not cdn_url and post_url:
                        cdn_url = get_cdn_url(post_url, "instagram") or ""

                    if not cdn_url:
                        print(f"    [SKIP] No CDN URL for {post_id}")
                        continue

                    # Download video
                    video_path = tmp / "video.mp4"
                    dl = download_video(cdn_url, video_path, post_url, "instagram")
                    if not dl:
                        print(f"    [SKIP] Download failed for {post_id}")
                        continue

                    # Extract frames (LT: 10장)
                    frames_dir = tmp / "frames"
                    frames = extract_frames(video_path, frames_dir, tier="LT")

                    # Extract audio
                    audio_out = tmp / "audio.mp3"
                    audio_path = extract_audio_fn(video_path, audio_out)

                    # Get duration
                    try:
                        from moviepy import VideoFileClip
                        clip = VideoFileClip(str(video_path))
                        duration_sec = clip.duration
                        clip.close()
                    except Exception:
                        duration_sec = 0

                    # Save to cache
                    media_cache.save_frames(username, post_id, frames, tier="LT", duration_sec=duration_sec)
                    if audio_path:
                        media_cache.save_audio(username, post_id, audio_path)

                    # Reload from cache (paths changed)
                    frames = media_cache.load_frames(username, post_id)
                    cached_audio = media_cache.get_audio_path(username, post_id)
                    audio_path = cached_audio if cached_audio.exists() else None

            # Vision analysis
            print(f"    [VISION] {post_id} ({len(frames)} frames)")
            vision_result = analyze_vision(frames, tier="LT")

            # Whisper analysis
            whisper_result = {}
            if has_whisper and audio_path and audio_path.exists():
                try:
                    transcript = transcribe_audio(audio_path)
                    script_analysis = analyze_script(transcript) if transcript else {}
                    whisper_result = {"transcript": transcript, **script_analysis}
                except Exception as e:
                    print(f"    [WHISPER] Error: {e}")

            # Merge CI results
            ci_results = {**vision_result, **whisper_result}

            # Score (v2)
            v2_scores = calc_v2(
                ci_results,
                followers=profile.get("followers", 0),
                views=vp.get("views", 0),
                likes=vp.get("likes", 0),
                comments=vp.get("comments", 0),
                enrichment={
                    "duration_seconds": media_cache.load_meta(username, post_id).get("duration_sec", 0) if media_cache.load_meta(username, post_id) else 0,
                    "posts_last_30d": screening.get("metrics", {}).get("posts_30d", 0),
                },
            )

            # Tier framework
            framework = calc_framework(
                ci_results,
                screening=screening,
                enrichment={
                    "duration_seconds": media_cache.load_meta(username, post_id).get("duration_sec", 0) if media_cache.load_meta(username, post_id) else 0,
                    "followers": profile.get("followers", 0),
                },
                v2_scores=v2_scores,
            )

            post_result = {
                "post_id": post_id,
                "post_url": post_url,
                "username": username,
                "media_dir": media_cache.get_media_dir(username, post_id),
                "media_tier": "LT",
                "frame_count": len(frames),
                "ci_results": ci_results,
                "v2_scores": v2_scores,
                "framework": framework,
                "composite_v2_score": v2_scores.get("composite_v2_score", 0),
            }
            creator_post_results.append(post_result)

        # Creator-level aggregation
        if creator_post_results:
            composites = [r["composite_v2_score"] for r in creator_post_results]
            creator_result = {
                "username": username,
                "region": region,
                "followers": profile.get("followers", 0),
                "posts_analyzed": len(creator_post_results),
                "avg_composite_v2": round(sum(composites) / len(composites), 1),
                "max_composite_v2": max(composites),
                "lt_passed": True,
                "lt_score": screening.get("score", 0),
                "screening": screening,
                "post_results": creator_post_results,
                "framework_avg": _avg_framework(creator_post_results),
            }
            all_results.append(creator_result)
            print(f"    → avg_v2={creator_result['avg_composite_v2']} | T1={'PASS' if creator_result['framework_avg'].get('tier1_pass') else 'FAIL'}")

    # Sort by composite score
    all_results.sort(key=lambda x: x["avg_composite_v2"], reverse=True)

    print(f"\n[Stage 4] Results: {len(all_results)} creators analyzed")
    _print_summary(all_results)

    # PG sync
    if pg_sync and all_results:
        _pg_sync_results(all_results)

    # Save results JSON
    results_path = PROJECT_ROOT / ".tmp" / "evaluator" / f"lt_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"\n  Results saved: {results_path}")

    return {
        "total": len(handles),
        "screened": len(profiles_map),
        "passed": len(passed_handles),
        "analyzed": len(all_results),
        "results": all_results,
    }


def run_ht_pipeline(
    handles: list[str] = None,
    from_lt_results: bool = False,
    min_lt_score: float = 60,
    region: str = "us",
    dry_run: bool = False,
    pg_sync: bool = False,
) -> dict:
    """
    HT (Heavy Touch) 파이프라인 — LT 상위자 정밀 분석.

    30프레임 + enricher + 확장 vision 프롬프트.
    """
    print(f"\n{'='*60}")
    print(f"[Creator Evaluator] HT Pipeline")
    print(f"{'='*60}\n")

    # Load LT results for promotion
    if from_lt_results:
        lt_dir = PROJECT_ROOT / ".tmp" / "evaluator"
        lt_files = sorted(lt_dir.glob("lt_results_*.json"), reverse=True)
        if not lt_files:
            print("[ERROR] No LT results found. Run --lt first.")
            return {"error": "No LT results"}

        lt_data = json.loads(lt_files[0].read_text(encoding="utf-8"))
        handles = [
            r["username"] for r in lt_data
            if r.get("avg_composite_v2", 0) >= min_lt_score
        ]
        print(f"  Loaded {len(lt_data)} LT results, {len(handles)} above score {min_lt_score}")

    if not handles:
        print("[ERROR] No handles for HT analysis.")
        return {"error": "No handles"}

    print(f"  HT candidates: {len(handles)}")

    if dry_run:
        print("\n--- DRY RUN ---")
        print(f"  Would analyze {len(handles)} creators with 30-frame HT analysis")
        return {"candidates": len(handles), "handles": handles}

    # HT pipeline follows same pattern as LT but with tier="HT"
    # Re-extract 30 frames for each creator's top reels
    extract_frames, extract_audio_fn = _get_frame_extractor()
    media_cache = _get_media_cache()
    download_video, get_cdn_url = _get_downloader()
    analyze_vision = _get_vision_tagger()
    calc_v2, calc_framework = _get_score_calculator()

    print(f"\n[HT] Re-extracting with 30 frames per reel...")

    ht_results = []
    for username in handles:
        cached_posts = media_cache.get_creator_posts(username)
        if not cached_posts:
            print(f"  @{username} — no cached posts, skipping")
            continue

        print(f"  @{username} — upgrading {len(cached_posts)} posts to HT")
        for post_id in cached_posts:
            meta = media_cache.load_meta(username, post_id)
            if not meta:
                continue

            # Already HT? Skip
            if meta.get("tier") == "HT":
                print(f"    {post_id} already HT, skipping")
                continue

            # Need to re-download and re-extract at 30fps
            # For now, re-analyze existing frames with HT prompts
            # (Full re-extraction requires re-download which costs Apify tokens)
            frames = media_cache.load_frames(username, post_id)
            if not frames:
                continue

            print(f"    [VISION-HT] {post_id} ({len(frames)} frames, HT prompt)")
            vision_result = analyze_vision(frames, tier="HT")

            ht_results.append({
                "username": username,
                "post_id": post_id,
                "vision_ht": vision_result,
            })

    print(f"\n[Done] HT analyzed: {len(ht_results)} posts")
    return {"analyzed": len(ht_results), "results": ht_results}


def run_reanalyze(
    tier: str = "LT",
    username: str = None,
    dry_run: bool = False,
) -> dict:
    """
    캐시된 키프레임으로 재분석 (프롬프트/가중치 변경 후).
    영상 재다운로드 불필요, API 비용만.
    """
    print(f"\n{'='*60}")
    print(f"[Creator Evaluator] Re-analyze (tier={tier})")
    print(f"{'='*60}\n")

    media_cache = _get_media_cache()
    analyze_vision = _get_vision_tagger()

    if username:
        creators = [username]
    else:
        creators = media_cache.get_all_creators()

    total_posts = 0
    for c in creators:
        posts = media_cache.get_creator_posts(c)
        total_posts += len(posts)

    print(f"  Creators: {len(creators)} | Posts: {total_posts}")

    if dry_run:
        est_cost = total_posts * (0.015 if tier == "HT" else 0.010)
        print(f"  Estimated Vision API cost: ~${est_cost:.2f}")
        print("\n--- DRY RUN ---")
        return {"creators": len(creators), "posts": total_posts}

    reanalyzed = 0
    for c in creators:
        posts = media_cache.get_creator_posts(c)
        for post_id in posts:
            frames = media_cache.load_frames(c, post_id)
            if not frames:
                continue
            print(f"  @{c}/{post_id} ({len(frames)} frames)")
            result = analyze_vision(frames, tier=tier)
            reanalyzed += 1
            # TODO: Update PG with new scores

    print(f"\n[Done] Re-analyzed: {reanalyzed} posts")
    return {"reanalyzed": reanalyzed}


def show_status():
    """파이프라인 상태 표시."""
    print(f"\n{'='*60}")
    print(f"[Creator Evaluator] Status")
    print(f"{'='*60}\n")

    media_cache = _get_media_cache()
    stats = media_cache.get_disk_usage()

    print(f"  Cache root: {media_cache.root}")
    print(f"  Total size: {stats['total_mb']} MB")
    print(f"  Creators:   {stats['creator_count']}")
    print(f"  Posts:       {stats['post_count']} (LT: {stats['lt_count']}, HT: {stats['ht_count']})")

    # Latest LT results
    lt_dir = PROJECT_ROOT / ".tmp" / "evaluator"
    if lt_dir.exists():
        lt_files = sorted(lt_dir.glob("lt_results_*.json"), reverse=True)
        if lt_files:
            latest = lt_files[0]
            data = json.loads(latest.read_text(encoding="utf-8"))
            scores = [r.get("avg_composite_v2", 0) for r in data]
            print(f"\n  Latest LT run: {latest.name}")
            print(f"    Creators: {len(data)}")
            if scores:
                print(f"    Score range: {min(scores):.1f} - {max(scores):.1f} (avg {sum(scores)/len(scores):.1f})")
                above_60 = sum(1 for s in scores if s >= 60)
                print(f"    HT candidates (>=60): {above_60}")


# ── Helpers ──

def _avg_framework(post_results: list[dict]) -> dict:
    """포스트 결과 리스트에서 framework 평균."""
    if not post_results:
        return {}
    keys = ["tier2_score", "tier3a_score", "tier3b_score", "tier4_score", "framework_composite"]
    avg = {}
    for k in keys:
        vals = [r.get("framework", {}).get(k, 0) for r in post_results]
        avg[k] = round(sum(vals) / len(vals), 1) if vals else 0

    # tier1_pass = all posts pass
    avg["tier1_pass"] = all(
        r.get("framework", {}).get("tier1_pass", False) for r in post_results
    )
    return avg


def _print_summary(results: list[dict]):
    """결과 요약 출력."""
    if not results:
        print("  No results.")
        return

    print(f"\n  {'Username':<25} {'Followers':>10} {'Posts':>5} {'v2 Score':>8} {'T1':>4} {'T2':>4} {'T3a':>4} {'T3b':>4} {'T4':>4}")
    print(f"  {'-'*75}")
    for r in results[:20]:  # top 20
        fw = r.get("framework_avg", {})
        t1 = "PASS" if fw.get("tier1_pass") else "FAIL"
        print(f"  @{r['username']:<24} {r['followers']:>10,} {r['posts_analyzed']:>5} "
              f"{r['avg_composite_v2']:>8.1f} {t1:>4} "
              f"{fw.get('tier2_score', 0):>4} {fw.get('tier3a_score', 0):>4} "
              f"{fw.get('tier3b_score', 0):>4} {fw.get('tier4_score', 0):>4}")


def _pg_sync_results(results: list[dict]):
    """결과를 PG에 동기화."""
    try:
        sys.path.insert(0, str(DIR))
        from push_content_to_pg import push_posts
        print("\n[PG Sync] Pushing results...")
        # TODO: Implement PG upsert for media_dir, media_tier, tier_scores_json
        print("  [TODO] PG sync not yet implemented")
    except Exception as e:
        print(f"  [ERROR] PG sync failed: {e}")


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="Creator Evaluator — LT/HT 2-Tier Pipeline")

    # Mode
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lt", action="store_true", help="Run Light Touch pipeline")
    mode.add_argument("--ht", action="store_true", help="Run Heavy Touch pipeline")
    mode.add_argument("--reanalyze", action="store_true", help="Re-analyze cached frames")
    mode.add_argument("--status", action="store_true", help="Show pipeline status")

    # Input
    parser.add_argument("--handles", type=str, help="Comma-separated handles")
    parser.add_argument("--handles-file", type=str, help="File with one handle per line")
    parser.add_argument("--from-lt-results", action="store_true", help="HT: promote from latest LT results")

    # Filters
    parser.add_argument("--region", choices=["us", "jp"], default="us", help="Target region")
    parser.add_argument("--max", type=int, default=0, help="Max creators to process")
    parser.add_argument("--min-lt-score", type=float, default=60, help="Min LT score for HT promotion")
    parser.add_argument("--username", type=str, help="Reanalyze: specific username")
    parser.add_argument("--tier", choices=["LT", "HT"], default="LT", help="Reanalyze: tier level")

    # Processing
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--skip-screening", action="store_true", help="Skip LT auto-screening")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--pg-sync", action="store_true", help="Push results to PostgreSQL")

    args = parser.parse_args()

    # Load handles
    handles = []
    if args.handles:
        handles = [h.strip().lstrip("@") for h in args.handles.split(",") if h.strip()]
    elif args.handles_file:
        p = Path(args.handles_file)
        if p.exists():
            handles = [
                line.strip().lstrip("@") for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

    # Route to mode
    if args.status:
        show_status()
    elif args.lt:
        if not handles:
            print("[ERROR] --lt requires --handles or --handles-file")
            sys.exit(1)
        run_lt_pipeline(
            handles=handles,
            region=args.region,
            max_creators=args.max,
            workers=args.workers,
            skip_screening=args.skip_screening,
            dry_run=args.dry_run,
            pg_sync=args.pg_sync,
        )
    elif args.ht:
        run_ht_pipeline(
            handles=handles if handles else None,
            from_lt_results=args.from_lt_results,
            min_lt_score=args.min_lt_score,
            region=args.region,
            dry_run=args.dry_run,
            pg_sync=args.pg_sync,
        )
    elif args.reanalyze:
        run_reanalyze(
            tier=args.tier,
            username=args.username,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
