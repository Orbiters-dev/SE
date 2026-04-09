"""
CI Media Cache — EC2/로컬 키프레임 + 오디오 파일 저장소 관리

디렉토리 구조:
    ci_cache/
      {username}/
        {post_id}/
          frames/
            frame_000_0.0s.jpg
            frame_001_1.5s.jpg
            ...
          audio.mp3
          meta.json  ← {"tier","frame_count","extracted_at","duration_sec"}

PG 매칭:
    gk_content_posts.media_dir = "{username}/{post_id}"
    → ci_cache/{media_dir}/frames/  에서 키프레임 로드
"""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

# EC2 경로
EC2_CACHE_ROOT = Path("/home/ubuntu/export_calculator/media/ci_cache")

# 로컬 dev 경로
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_CACHE_ROOT = PROJECT_ROOT / ".tmp" / "ci_cache"


class MediaCache:
    """크리에이터 키프레임 + 오디오 파일 캐시 매니저."""

    def __init__(self, root: Path | None = None):
        if root:
            self.root = root
        elif EC2_CACHE_ROOT.exists():
            self.root = EC2_CACHE_ROOT
        else:
            self.root = LOCAL_CACHE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    # ── 경로 헬퍼 ──

    def get_post_dir(self, username: str, post_id: str) -> Path:
        return self.root / username.lower() / post_id

    def get_frames_dir(self, username: str, post_id: str) -> Path:
        return self.get_post_dir(username, post_id) / "frames"

    def get_audio_path(self, username: str, post_id: str) -> Path:
        return self.get_post_dir(username, post_id) / "audio.mp3"

    def get_meta_path(self, username: str, post_id: str) -> Path:
        return self.get_post_dir(username, post_id) / "meta.json"

    def get_media_dir(self, username: str, post_id: str) -> str:
        """PG media_dir 컬럼에 저장할 상대 경로."""
        return f"{username.lower()}/{post_id}"

    # ── 존재 확인 (dedup) ──

    def has_frames(self, username: str, post_id: str, tier: str = "LT") -> bool:
        """이미 이 포스트의 프레임이 캐시에 있는지 확인."""
        meta_path = self.get_meta_path(username, post_id)
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            cached_tier = meta.get("tier", "")
            # HT가 이미 있으면 LT 요청도 True (상위 호환)
            if cached_tier == "HT":
                return True
            # LT가 있고 LT 요청이면 True
            if cached_tier == "LT" and tier.upper() == "LT":
                return True
            return False
        except Exception:
            return False

    def has_audio(self, username: str, post_id: str) -> bool:
        return self.get_audio_path(username, post_id).exists()

    # ── 저장 ──

    def save_frames(
        self,
        username: str,
        post_id: str,
        frame_paths: list[Path],
        tier: str = "LT",
        duration_sec: float = 0.0,
        platform: str = "instagram",
    ) -> Path:
        """
        프레임 파일을 캐시 디렉토리로 복사.

        Returns:
            캐시 frames 디렉토리 경로
        """
        frames_dir = self.get_frames_dir(username, post_id)
        frames_dir.mkdir(parents=True, exist_ok=True)

        # 기존 프레임 삭제 (tier 업그레이드 시)
        for old in frames_dir.glob("*.jpg"):
            old.unlink()

        for src in frame_paths:
            if src.exists():
                dst = frames_dir / src.name
                shutil.copy2(src, dst)

        # 메타데이터 저장
        self._save_meta(username, post_id, tier, len(frame_paths), duration_sec, platform)

        return frames_dir

    def save_audio(self, username: str, post_id: str, audio_path: Path) -> Path | None:
        """오디오 파일을 캐시로 복사."""
        if not audio_path or not audio_path.exists():
            return None
        dst = self.get_audio_path(username, post_id)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio_path, dst)
        return dst

    def _save_meta(
        self, username: str, post_id: str, tier: str, frame_count: int, duration_sec: float,
        platform: str = "instagram",
    ):
        meta = {
            "tier": tier.upper(),
            "frame_count": frame_count,
            "duration_sec": round(duration_sec, 2),
            "platform": platform,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path = self.get_meta_path(username, post_id)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ── 로드 ──

    def load_frames(self, username: str, post_id: str) -> list[Path]:
        """캐시된 프레임 경로를 파일명 순 반환."""
        frames_dir = self.get_frames_dir(username, post_id)
        if not frames_dir.exists():
            return []
        return sorted(frames_dir.glob("*.jpg"), key=lambda p: p.name)

    def load_meta(self, username: str, post_id: str) -> dict | None:
        meta_path = self.get_meta_path(username, post_id)
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ── 크리에이터 단위 조회 ──

    def get_creator_posts(self, username: str) -> list[str]:
        """같은 크리에이터의 모든 캐시된 post_id 목록."""
        creator_dir = self.root / username.lower()
        if not creator_dir.exists():
            return []
        return [d.name for d in creator_dir.iterdir() if d.is_dir()]

    def get_all_creators(self) -> list[str]:
        """캐시된 모든 크리에이터 username 목록."""
        if not self.root.exists():
            return []
        return [d.name for d in self.root.iterdir() if d.is_dir()]

    # ── 통계 ──

    def get_disk_usage(self) -> dict:
        """캐시 디스크 사용량 통계."""
        total_bytes = 0
        creator_count = 0
        post_count = 0
        lt_count = 0
        ht_count = 0

        if not self.root.exists():
            return {"total_mb": 0, "creator_count": 0, "post_count": 0,
                    "lt_count": 0, "ht_count": 0}

        for creator_dir in self.root.iterdir():
            if not creator_dir.is_dir():
                continue
            creator_count += 1
            for post_dir in creator_dir.iterdir():
                if not post_dir.is_dir():
                    continue
                post_count += 1
                # 용량 계산
                for f in post_dir.rglob("*"):
                    if f.is_file():
                        total_bytes += f.stat().st_size
                # tier 확인
                meta_path = post_dir / "meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        if meta.get("tier") == "HT":
                            ht_count += 1
                        else:
                            lt_count += 1
                    except Exception:
                        lt_count += 1

        return {
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "creator_count": creator_count,
            "post_count": post_count,
            "lt_count": lt_count,
            "ht_count": ht_count,
        }

    # ── 삭제 ──

    def delete_post(self, username: str, post_id: str) -> bool:
        """특정 포스트의 캐시 삭제."""
        post_dir = self.get_post_dir(username, post_id)
        if post_dir.exists():
            shutil.rmtree(post_dir)
            return True
        return False

    def delete_creator(self, username: str) -> bool:
        """크리에이터 전체 캐시 삭제."""
        creator_dir = self.root / username.lower()
        if creator_dir.exists():
            shutil.rmtree(creator_dir)
            return True
        return False


if __name__ == "__main__":
    cache = MediaCache()
    stats = cache.get_disk_usage()
    print(f"Cache root: {cache.root}")
    print(f"Total: {stats['total_mb']} MB")
    print(f"Creators: {stats['creator_count']}")
    print(f"Posts: {stats['post_count']} (LT: {stats['lt_count']}, HT: {stats['ht_count']})")
