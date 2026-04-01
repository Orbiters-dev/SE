"""
CI Downloader — Apify CDN URL 획득 + moviepy 오디오/프레임 추출
"""
import os
import sys
import json
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env
load_env()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
IG_SCRAPER = "apify/instagram-scraper"
TT_SCRAPER = "clockworks/free-tiktok-scraper"


def get_cdn_url(post_url: str, platform: str) -> str | None:
    """Apify로 CDN direct video URL 획득."""
    if not APIFY_TOKEN:
        return None
    try:
        from apify_client import ApifyClient
        client = ApifyClient(APIFY_TOKEN)

        if "instagram" in platform:
            run = client.actor(IG_SCRAPER).call(
                run_input={"directUrls": [post_url], "resultsLimit": 1, "resultsType": "posts"},
                timeout_secs=120,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            if not items:
                return None
            item = items[0]
            return item.get("videoUrl")
        else:
            # TikTok: use yt-dlp to get direct video URL
            return _get_tiktok_cdn(post_url)
    except Exception as e:
        print(f"  [CDN] Error: {e}")
        return None


def _get_tiktok_cdn(post_url: str) -> str | None:
    """Use yt-dlp to extract TikTok direct video URL."""
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--get-url", "-f", "best[ext=mp4]", post_url],
            capture_output=True, text=True, timeout=30
        )
        url = result.stdout.strip()
        if url and url.startswith("http"):
            return url
        # Fallback: try without format filter
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--get-url", post_url],
            capture_output=True, text=True, timeout=30
        )
        url = result.stdout.strip().split('\n')[0]
        return url if url and url.startswith("http") else None
    except Exception as e:
        print(f"  [TT-CDN] yt-dlp failed: {e}")
        return None


def _download_tiktok_video(post_url: str, tmp_dir: Path) -> Path | None:
    """Download TikTok video directly via yt-dlp (handles cookies/headers internally)."""
    import subprocess
    output_path = tmp_dir / "video.mp4"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp",
             "-f", "best[ext=mp4]",
             "-o", str(output_path),
             "--no-warnings", "--quiet",
             post_url],
            capture_output=True, text=True, timeout=60
        )
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
        # Fallback without format filter
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp",
             "-o", str(output_path),
             "--no-warnings", "--quiet",
             post_url],
            capture_output=True, text=True, timeout=60
        )
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path
        print(f"  [TT-DL] yt-dlp output empty: {result.stderr[:100]}")
        return None
    except Exception as e:
        print(f"  [TT-DL] yt-dlp download failed: {e}")
        return None


def extract_audio_and_frames(cdn_url: str, tmp_dir: Path, post_url: str = "", platform: str = "") -> tuple[Path | None, list[Path]]:
    """
    CDN URL에서 영상 다운로드 → mp3 오디오 + 키프레임 3장 추출.
    Returns: (audio_path, [frame_path_1, frame_path_2, frame_path_3])
    """
    import urllib.request

    # 1. 영상 다운로드
    video_path = tmp_dir / "video.mp4"

    # TikTok: use yt-dlp direct download (CDN URLs require auth headers)
    if "tiktok" in platform.lower() and post_url:
        dl_path = _download_tiktok_video(post_url, tmp_dir)
        if not dl_path:
            print("  [DL] TikTok yt-dlp download failed")
            return None, []
        video_path = dl_path
    else:
        try:
            req = urllib.request.Request(cdn_url)
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=120) as r, open(video_path, "wb") as f:
                f.write(r.read())
        except Exception as e:
            print(f"  [DL] Download failed: {e}")
            return None, []

    if not video_path.exists() or video_path.stat().st_size < 1000:
        print("  [DL] Empty file")
        return None, []

    # 2. moviepy로 오디오 + 프레임 추출
    try:
        from moviepy import VideoFileClip
        import numpy as np
        from PIL import Image

        clip = VideoFileClip(str(video_path))
        duration = clip.duration

        # 오디오 추출
        audio_path = tmp_dir / "audio.mp3"
        if clip.audio:
            clip.audio.write_audiofile(str(audio_path), logger=None)
        else:
            audio_path = None

        # 키프레임: 10%, 50%, 90% 시점
        frames = []
        for pct in [0.10, 0.50, 0.90]:
            t = duration * pct
            frame = clip.get_frame(t)
            img = Image.fromarray(frame.astype("uint8"))
            # 720px로 리사이즈 (GPT-4o low-res tier 충분)
            img.thumbnail((720, 720))
            fpath = tmp_dir / f"frame_{int(pct*100):03d}.jpg"
            img.save(fpath, "JPEG", quality=85)
            frames.append(fpath)

        clip.close()
        return audio_path, frames

    except Exception as e:
        print(f"  [EXTRACT] Failed: {e}")
        return None, []
