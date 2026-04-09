"""
Discovery Evaluator — Background HT analysis for discovery search results
==========================================================================

Reads manifest.json from a discovery job, runs HT 30-frame Vision + Whisper +
Gemini audio analysis on each post, updates manifest progress, and syncs
scores back to gk_content_posts.

Usage:
    python tools/run_discovery_evaluator.py --job-id <uuid>
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time
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

JOBS_DIR = PROJECT_ROOT / ".tmp" / "discovery" / "jobs"


def atomic_write_json(path: Path, data: dict):
    """Atomic JSON write via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        shutil.move(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run_evaluator(job_id: str):
    """Main evaluation loop."""
    job_dir = JOBS_DIR / job_id
    manifest_path = job_dir / "manifest.json"

    if not manifest_path.exists():
        print(f"[ERROR] Manifest not found: {manifest_path}")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    posts = manifest.get("posts", [])

    if not posts:
        manifest["status"] = "complete"
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(manifest_path, manifest)
        print("[DONE] No posts to evaluate")
        return

    # Lazy imports for heavy modules
    from ci.frame_extractor import extract_frames, extract_audio
    from ci.media_cache import MediaCache
    from ci.downloader import download_video, get_cdn_url
    from ci.vision_tagger import analyze_frames
    from ci.score_calculator import calculate_scores_v2

    try:
        from ci.whisper_transcriber import transcribe, analyze_script
        has_whisper = True
    except ImportError:
        has_whisper = False
        print("  [WARN] Whisper not available")

    try:
        from ci.audio_analyzer import analyze_audio
        has_gemini_audio = True
    except ImportError:
        has_gemini_audio = False
        print("  [WARN] Gemini audio analyzer not available")

    media_cache = MediaCache()
    results = []

    for idx, post in enumerate(posts):
        username = post.get("username", "")
        post_url = post.get("post_url", "")
        platform = post.get("platform", "")
        post_id = post_url.rstrip("/").split("/")[-1].split("?")[0] if post_url else f"disc_{idx}"

        comment_count = post.get("comments", 0)

        print(f"\n--- [{idx+1}/{len(posts)}] @{username} ({platform}) ---")
        print(f"  URL: {post_url[:80]}")

        try:
            frames = None
            audio_path = None
            duration_sec = 0

            # Check cache first
            if media_cache.has_frames(username, post_id, tier="HT"):
                print(f"  [CACHE HIT] Reusing frames")
                frames = media_cache.load_frames(username, post_id)
                audio_path = media_cache.get_audio_path(username, post_id)
                if not audio_path.exists():
                    audio_path = None
                meta = media_cache.load_meta(username, post_id)
                if meta:
                    duration_sec = meta.get("duration_sec", 0)
            else:
                # Download + extract
                tmp_dir = tempfile.mkdtemp()
                tmp = Path(tmp_dir)
                try:
                    video_path = None
                    if platform == "tiktok":
                        from ci.downloader import _download_tiktok_video
                        video_path = _download_tiktok_video(post_url, tmp)
                    else:
                        cdn_url = post.get("video_url", "")
                        if not cdn_url:
                            cdn_url = get_cdn_url(post_url, "instagram") or ""
                        if cdn_url:
                            video_path = tmp / "video.mp4"
                            dl = download_video(cdn_url, video_path, post_url, "instagram")
                            if not dl:
                                video_path = None

                    if not video_path or not video_path.exists():
                        print(f"  [SKIP] Download failed")
                        manifest["progress"]["failed"] = manifest["progress"].get("failed", 0) + 1
                        atomic_write_json(manifest_path, manifest)
                        continue

                    # Duration
                    try:
                        from moviepy import VideoFileClip
                        clip = VideoFileClip(str(video_path))
                        duration_sec = clip.duration
                        clip.close()
                    except Exception:
                        duration_sec = 0

                    # Extract DY frames (dynamic based on comments)
                    frames_dir = tmp / "frames"
                    frames = extract_frames(video_path, frames_dir, tier="DY", comments=comment_count)
                    print(f"  [FRAMES] Extracted {len(frames)} DY keyframes (comments={comment_count})")

                    # Extract audio
                    audio_out = tmp / "audio.mp3"
                    audio_path = extract_audio(video_path, audio_out)

                    # Save to cache
                    media_cache.save_frames(username, post_id, frames, tier="HT",
                                            duration_sec=duration_sec, platform=platform)
                    if audio_path:
                        media_cache.save_audio(username, post_id, audio_path)

                    # Reload from cache
                    frames = media_cache.load_frames(username, post_id)
                    cached_audio = media_cache.get_audio_path(username, post_id)
                    audio_path = cached_audio if cached_audio.exists() else None

                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            if not frames:
                print(f"  [SKIP] No frames available")
                manifest["progress"]["failed"] = manifest["progress"].get("failed", 0) + 1
                atomic_write_json(manifest_path, manifest)
                continue

            # Vision DY analysis
            print(f"  [VISION] DY analysis ({len(frames)} frames)")
            vision_result = analyze_frames(frames, tier="DY")

            # Whisper
            whisper_result = {}
            if has_whisper and audio_path and audio_path.exists():
                try:
                    transcript = transcribe(audio_path, language="en")
                    script_analysis = analyze_script(transcript) if transcript else {}
                    whisper_result = {"transcript": transcript, **script_analysis}
                    print(f"  [WHISPER] Transcribed ({len(transcript or '')} chars)")
                except Exception as e:
                    print(f"  [WHISPER] Error: {e}")

            # Gemini audio tone
            audio_analysis = None
            if has_gemini_audio and audio_path and audio_path.exists():
                try:
                    print(f"  [AUDIO] Gemini tone analysis...")
                    audio_analysis = analyze_audio(audio_path, duration_sec)
                except Exception as e:
                    print(f"  [AUDIO] Error: {e}")

            # Merge CI results
            ci_results = {**vision_result, **whisper_result}
            if audio_analysis:
                ci_results["audio_analysis"] = audio_analysis

            # Score v2
            v2_scores = calculate_scores_v2(
                ci_results,
                followers=post.get("followers", 0),
                views=post.get("views", 0),
                likes=post.get("likes", 0),
                comments=post.get("comments", 0),
                enrichment={"duration_seconds": duration_sec},
                audio_analysis=audio_analysis,
            )

            result = {
                "username": username,
                "post_url": post_url,
                "platform": platform,
                "vision": vision_result,
                "transcript": whisper_result.get("transcript"),
                "audio_analysis": audio_analysis,
                "scores": v2_scores,
            }
            results.append(result)

            # Update PG
            _pg_update_scores(post_url, v2_scores, ci_results, whisper_result.get("transcript"))

            # Update manifest progress
            manifest["progress"]["done"] = manifest["progress"].get("done", 0) + 1
            manifest["results"] = results
            atomic_write_json(manifest_path, manifest)

            print(f"  [SCORE] composite={v2_scores.get('composite_score', 0):.1f}")

        except Exception as e:
            print(f"  [ERROR] {e}")
            manifest["progress"]["failed"] = manifest["progress"].get("failed", 0) + 1
            atomic_write_json(manifest_path, manifest)

    # Finalize
    manifest["status"] = "complete"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["results"] = results
    atomic_write_json(manifest_path, manifest)

    done = manifest["progress"].get("done", 0)
    failed = manifest["progress"].get("failed", 0)
    print(f"\n[COMPLETE] {done} evaluated, {failed} failed out of {len(posts)} total")


def _pg_update_scores(post_url: str, scores: dict, ci_results: dict, transcript: str | None):
    """Update gk_content_posts with evaluation scores."""
    try:
        import psycopg2

        db_host = os.getenv("DB_HOST", "172.31.13.240")
        db_name = os.getenv("DB_NAME", "export_calculator_db")
        db_user = os.getenv("DB_USER", "es_db_user")
        db_pass = os.getenv("DB_PASSWORD", "orbit1234")

        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_pass)
        cur = conn.cursor()

        brand_fit = scores.get("brand_fit_score", scores.get("composite_score", 0))
        content_quality = scores.get("content_quality_score", scores.get("composite_score", 0))
        scene_fit = scores.get("scene_fit", 0)
        scene_tags = json.dumps(ci_results.get("scene_tags", []), ensure_ascii=False)
        ci_json = json.dumps(scores, ensure_ascii=False, default=str)

        cur.execute("""
            UPDATE gk_content_posts SET
                brand_fit_score = %s,
                scene_fit = %s,
                scene_tags = %s,
                content_quality_score = %s,
                ci_analysis = %s,
                transcript = COALESCE(%s, transcript)
            WHERE url = %s
        """, [brand_fit, scene_fit, scene_tags, content_quality, ci_json, transcript, post_url])

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [PG] Update failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discovery Evaluator — background HT analysis")
    parser.add_argument("--job-id", required=True, help="Job UUID from discovery search")
    args = parser.parse_args()

    run_evaluator(args.job_id)
