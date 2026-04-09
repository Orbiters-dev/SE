"""
CI Frame Extractor — LT/HT/DY 키프레임 추출기

LT (10장): Hook 3장 (0.0s, 1.5s, 3.0s) + Body 7장 (15%/25%/35%/50%/65%/80%/95%)
HT (30장 고정):
  - Hook 7장 (0~3초, 0.5초 간격)
  - Body 23장:
    - ≤30초 영상: 3초부터 1초 간격
    - >30초 영상: 3초부터 균등 배분
DY (Dynamic — 댓글 수 기반):
  - <100 댓글: HT와 동일 (30장)
  - 100-299 댓글: 20장 (Hook 7@0.5s + Body 13 균등)
  - 300+ 댓글: 40장 (Hook 11@0.3s + Body 29 균등)

Usage:
    from tools.ci.frame_extractor import extract_frames
    frames = extract_frames(Path("video.mp4"), Path("output/"), tier="LT")
    # Dynamic tier
    frames = extract_frames(Path("video.mp4"), Path("output/"), tier="DY", comments=350)
"""
import math
from pathlib import Path


# Hook zone for LT: 첫 3초 고정 3장
HOOK_TIMESTAMPS_LT = [0.0, 1.5, 3.0]

# Hook zone for HT: 첫 3초 0.5초 간격 7장
HOOK_TIMESTAMPS_HT = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

HT_TOTAL_FRAMES = 30
HT_HOOK_COUNT = len(HOOK_TIMESTAMPS_HT)  # 7
HT_BODY_COUNT = HT_TOTAL_FRAMES - HT_HOOK_COUNT  # 23

# Body zone percentages for LT (3초 이후 구간의 %)
LT_BODY_PCTS = [0.15, 0.25, 0.35, 0.50, 0.65, 0.80, 0.95]

# Short video fallback (< 3초)
SHORT_VIDEO_PCTS = [0.0, 0.50, 1.0]


def extract_frames(
    video_path: Path,
    output_dir: Path,
    tier: str = "LT",
    comments: int = 0,
) -> list[Path]:
    """
    영상에서 키프레임 추출.

    Args:
        video_path: 입력 영상 경로
        output_dir: 프레임 저장 디렉토리 (없으면 생성)
        tier: "LT" (10장) or "HT" (30장) or "DY" (동적)
        comments: 댓글 수 (DY tier에서 프레임 수 결정용)

    Returns:
        저장된 프레임 경로 리스트 (타임스탬프 순)
    """
    from moviepy import VideoFileClip
    from PIL import Image
    import numpy as np

    output_dir.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    duration = clip.duration

    try:
        timestamps = _calc_timestamps(duration, tier, comments=comments)
        frames = []
        for idx, (ts, label) in enumerate(timestamps):
            # 영상 범위 내로 clamp
            ts_clamped = max(0.0, min(ts, duration - 0.01))
            frame_arr = clip.get_frame(ts_clamped)
            img = Image.fromarray(frame_arr.astype("uint8"))
            img.thumbnail((720, 720))

            fname = f"frame_{idx:03d}_{label}.jpg"
            fpath = output_dir / fname
            img.save(fpath, "JPEG", quality=85)
            frames.append(fpath)

        return frames
    finally:
        clip.close()


def extract_audio(video_path: Path, output_path: Path) -> Path | None:
    """
    영상에서 오디오(mp3) 추출.

    Returns:
        오디오 파일 경로 또는 None (오디오 없는 영상)
    """
    from moviepy import VideoFileClip

    output_path.parent.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    try:
        if clip.audio:
            clip.audio.write_audiofile(str(output_path), logger=None)
            return output_path if output_path.exists() else None
        return None
    finally:
        clip.close()


def _calc_timestamps(duration: float, tier: str, comments: int = 0) -> list[tuple[float, str]]:
    """
    프레임 추출 타임스탬프 계산.

    Args:
        duration: 영상 길이 (초)
        tier: "LT", "HT", or "DY"
        comments: 댓글 수 (DY tier용)

    Returns:
        [(timestamp_sec, label_str), ...] 타임스탬프 순 정렬
    """
    # 3초 미만 짧은 영상: 고정 3장
    if duration < 3.0:
        return [
            (duration * pct, f"{int(pct*100)}pct")
            for pct in SHORT_VIDEO_PCTS
        ]

    # DY tier: 댓글 수로 프레임 수/Hook 간격 결정
    tier_up = tier.upper()
    if tier_up == "DY":
        if comments >= 300:
            hook_interval = 0.3
            hook_timestamps = [round(i * hook_interval, 1) for i in range(int(3.0 / hook_interval) + 1)]
            body_count = 29
        elif comments >= 100:
            hook_interval = 0.5
            hook_timestamps = HOOK_TIMESTAMPS_HT  # 0~3s, 0.5s = 7장
            body_count = 13
        else:
            # <100 comments: HT와 동일
            hook_timestamps = HOOK_TIMESTAMPS_HT
            body_count = HT_BODY_COUNT  # 23
    elif tier_up == "HT":
        hook_timestamps = HOOK_TIMESTAMPS_HT
        body_count = HT_BODY_COUNT
    else:
        hook_timestamps = None  # LT uses different logic
        body_count = 0

    timestamps = []

    if tier_up in ("HT", "DY"):
        # Hook zone
        for ts in hook_timestamps:
            if ts <= duration:
                timestamps.append((ts, f"{ts:.1f}s"))
    else:
        # LT Hook: 0.0s, 1.5s, 3.0s (3장)
        for ts in HOOK_TIMESTAMPS_LT:
            if ts <= duration:
                timestamps.append((ts, f"{ts:.1f}s"))

    # Body zone: 3초 이후 구간
    body_start = 3.0
    body_duration = duration - body_start

    if body_duration <= 0:
        return timestamps

    if tier_up in ("HT", "DY"):
        # 균등 배분
        for i in range(body_count):
            t = body_start + body_duration * (i + 1) / (body_count + 1)
            timestamps.append((t, f"{t:.1f}s"))
    else:
        # LT: body 구간의 % 지점
        for pct in LT_BODY_PCTS:
            t = body_start + (body_duration * pct)
            timestamps.append((t, f"{int(pct*100)}pct"))

    # 타임스탬프 순 정렬 + 중복 제거
    timestamps.sort(key=lambda x: x[0])
    # DY 300+ uses 0.3s interval → need tighter dedup threshold
    dedup_threshold = 0.2 if (tier_up == "DY" and comments >= 300) else 0.3
    deduped = []
    for ts, label in timestamps:
        if not deduped or abs(ts - deduped[-1][0]) > dedup_threshold:
            deduped.append((ts, label))

    return deduped


def get_frame_count(duration: float, tier: str, comments: int = 0) -> int:
    """프레임 수 사전 계산 (다운로드 전 예상치)."""
    return len(_calc_timestamps(duration, tier, comments=comments))


if __name__ == "__main__":
    # Quick test
    import sys
    if len(sys.argv) < 2:
        print("Usage: python frame_extractor.py <video_path> [tier]")
        sys.exit(1)

    video = Path(sys.argv[1])
    tier = sys.argv[2] if len(sys.argv) > 2 else "LT"
    out = video.parent / f"frames_{tier.lower()}"

    frames = extract_frames(video, out, tier=tier)
    print(f"Extracted {len(frames)} frames ({tier}):")
    for f in frames:
        print(f"  {f.name}")
