"""
YouTube to Teams — 유튜브 채널 영상 순차 공유 툴
================================================
yt-dlp를 사용해 API 키 없이 채널 전체 영상을 수집하고,
평일 1개씩 오래된 순으로 Teams에 발송한다.

설치:
    pip install yt-dlp requests

Usage:
    python tools/run_youtube_daily.py --init        # 최초 큐 초기화
    python tools/run_youtube_daily.py               # 일일 발송 (평일 체크 포함)
    python tools/run_youtube_daily.py --dry-run     # 발송 없이 선택 영상 확인
    python tools/run_youtube_daily.py --sync        # 신규 영상 큐에 추가
    python tools/run_youtube_daily.py --status      # 큐 현황 출력
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

from env_loader import load_env

# Windows UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_env()

_raw_channel_url = os.getenv("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@nateherk")
# yt-dlp는 @handle URL에 /videos 경로가 있어야 전체 영상 목록을 수집함
CHANNEL_URL = _raw_channel_url.rstrip("/") + "/videos" if not _raw_channel_url.rstrip("/").endswith("/videos") else _raw_channel_url
# GitHub Actions 환경에서는 QUEUE_PATH 환경변수로 경로 지정 (예: data/youtube_queue.json)
QUEUE_PATH = os.getenv("QUEUE_PATH", os.path.join(".tmp", "youtube_queue.json"))


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------

def fetch_all_videos(after_date: str = None) -> list:
    """
    yt-dlp로 채널 전체 영상 목록을 수집한다.

    Args:
        after_date: 'YYYYMMDD' 형식 — 이 날짜 이후 영상만 수집 (sync용)

    Returns:
        list of dicts: [{video_id, title, published_at, url}, ...] (오래된 순)
    """
    try:
        import yt_dlp
    except ImportError:
        print("[ERROR] yt-dlp가 설치되지 않았습니다. pip install yt-dlp 를 실행하세요.")
        sys.exit(1)

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    print(f"    채널 URL: {CHANNEL_URL}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)

    if not info or "entries" not in info:
        raise ValueError("채널 영상 목록을 가져올 수 없습니다.")

    raw_entries = [e for e in info["entries"] if e and e.get("id")]
    total = len(raw_entries)

    videos = []
    for idx, entry in enumerate(raw_entries):
        video_id = entry.get("id", "")
        title = entry.get("title", "(제목 없음)")
        upload_date = entry.get("upload_date") or ""  # extract_flat에서는 null일 수 있음

        # after_date 필터 (sync 모드) — upload_date 없으면 스킵
        if after_date:
            if not upload_date or upload_date <= after_date:
                continue

        # upload_date 없으면 플레이리스트 역순 인덱스로 대체
        # YouTube 플레이리스트는 최신순이므로 역순 = 오래된 순
        if not upload_date:
            sort_key = f"idx_{total - idx:05d}"
            published_at = "unknown"
        else:
            sort_key = upload_date
            published_at = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"

        videos.append({
            "video_id": video_id,
            "title": title,
            "published_at": published_at,
            "upload_date": upload_date,
            "_sort_key": sort_key,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "sent": False,
            "sent_at": None,
        })

    # 오래된 순 정렬
    videos.sort(key=lambda v: v["_sort_key"])
    for v in videos:
        del v["_sort_key"]
    return videos


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def load_queue() -> dict:
    if not os.path.exists(QUEUE_PATH):
        return None
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: dict):
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Teams notification
# ---------------------------------------------------------------------------

def send_video_to_teams(video: dict, dry_run: bool = False):
    """영상 정보를 Teams에 발송한다."""
    sys.path.insert(0, os.path.dirname(__file__))
    from send_teams_message import notify_teams

    title = "📺 새 영상 공유"
    body = "새 영상이 업로드되어 공유드립니다."
    details = {
        "제목": video["title"],
        "링크": video["url"],
        "업로드일": video["published_at"][:10],
    }

    return notify_teams(
        "tool_success", title, body, details=details, dry_run=dry_run
    )


def send_error_to_teams(message: str):
    """에러 알림을 Teams에 발송한다."""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from send_teams_message import notify_teams
        notify_teams("tool_error", "YouTube to Teams 오류", message)
    except Exception as e:
        print(f"[WARN] Teams 에러 알림 실패: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init():
    """최초 큐 초기화 — 채널 전체 영상 수집."""
    print("[1] 채널 전체 영상 수집 중 (수백 개면 1~2분 소요)...")
    videos = fetch_all_videos()
    print(f"    수집된 영상: {len(videos)}개")

    queue = {
        "channel_url": CHANNEL_URL,
        "last_fetched": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "videos": videos,
    }
    save_queue(queue)

    print(f"\n[OK] 큐 저장 완료: {QUEUE_PATH}")
    print(f"     총 {len(videos)}개 영상, 오래된 순 정렬")
    if videos:
        print(f"     첫 번째 발송 예정: [{videos[0]['published_at'][:10]}] {videos[0]['title']}")


def sync_claude_videos(queue: dict) -> int:
    """
    채널에서 'Claude' 제목 신규 영상을 찾아 큐에 추가한다.
    추가된 영상 수를 반환한다.
    """
    try:
        import yt_dlp
    except ImportError:
        print("[WARN] yt-dlp 없음, sync 스킵")
        return 0

    existing_ids = {v["video_id"] for v in queue["videos"]}

    # Step 1: extract_flat으로 전체 목록 (빠름) → 제목에 Claude 포함된 것만 추출
    opts = {"extract_flat": True, "quiet": True, "no_warnings": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)

    if not info or "entries" not in info:
        print("[WARN] 채널 영상 목록 수집 실패")
        return 0

    candidates = [
        e for e in info["entries"]
        if e and "Claude" in e.get("title", "") and e.get("id") not in existing_ids
    ]

    if not candidates:
        print("    신규 Claude 영상 없음.")
        queue["last_fetched"] = datetime.now(timezone.utc).strftime("%Y%m%d")
        save_queue(queue)
        return 0

    print(f"    신규 Claude 영상 후보 {len(candidates)}개 — 날짜 확인 중...")

    # Step 2: 후보만 개별 fetch로 upload_date 획득 — last_fetched 이후만 추가
    last_fetched = queue.get("last_fetched", "")
    added = []
    opts2 = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts2) as ydl:
        for e in candidates:
            detail = ydl.extract_info(f"https://www.youtube.com/watch?v={e['id']}", download=False)
            if not detail:
                continue
            upload_date = detail.get("upload_date", "")
            # last_fetched 이전 영상은 스킵 (이미 큐 초기화 시점에 처리됨)
            if last_fetched and upload_date and upload_date <= last_fetched:
                continue
            published_at = (
                f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"
                if upload_date else "unknown"
            )
            added.append({
                "video_id": e["id"],
                "title": detail.get("title", e.get("title")),
                "published_at": published_at,
                "upload_date": upload_date,
                "url": f"https://www.youtube.com/watch?v={e['id']}",
                "sent": False,
                "sent_at": None,
            })

    # 오래된 순 정렬 후 큐 끝에 추가
    added.sort(key=lambda v: v["upload_date"] or "99999999")
    queue["videos"].extend(added)
    queue["last_fetched"] = datetime.now(timezone.utc).strftime("%Y%m%d")
    save_queue(queue)

    for v in added:
        print(f"     + [{v['upload_date']}] {v['title']}")
    return len(added)


def cmd_sync():
    """신규 Claude 영상만 큐에 추가한다."""
    queue = load_queue()
    if not queue:
        print("[ERROR] 큐가 없습니다. 먼저 --init을 실행하세요.")
        sys.exit(1)

    print(f"[1] 신규 Claude 영상 확인 중...")
    added = sync_claude_videos(queue)
    print(f"[OK] {added}개 영상 추가됨.")


def cmd_status():
    """큐 현황을 출력한다."""
    queue = load_queue()
    if not queue:
        print("[ERROR] 큐가 없습니다. --init을 먼저 실행하세요.")
        sys.exit(1)

    total = len(queue["videos"])
    sent = sum(1 for v in queue["videos"] if v["sent"])
    pending = total - sent

    print("=" * 50)
    print("YouTube 큐 현황")
    print("=" * 50)
    print(f"채널: {queue.get('channel_url', CHANNEL_URL)}")
    print(f"전체: {total}개 | 발송완료: {sent}개 | 대기: {pending}개")
    print(f"마지막 수집: {queue.get('last_fetched', 'N/A')}")

    pending_videos = [v for v in queue["videos"] if not v["sent"]]
    if pending_videos:
        print(f"\n다음 발송 예정:")
        for v in pending_videos[:5]:
            print(f"  - [{v['published_at'][:10]}] {v['title']}")
        if len(pending_videos) > 5:
            print(f"  ... 외 {len(pending_videos) - 5}개")
    else:
        print("\n[!] 대기 중인 영상이 없습니다.")
    print("=" * 50)


def is_korean_holiday(dt: datetime) -> tuple[bool, str]:
    """주말 또는 한국 공휴일이면 (True, 사유)를 반환한다."""
    day_names = ['월', '화', '수', '목', '금', '토', '일']
    if dt.weekday() >= 5:
        return True, f"{day_names[dt.weekday()]}요일"
    try:
        import holidays
        kr_holidays = holidays.Korea(years=dt.year)
        # 근로자의 날 (5/1) — 법정공휴일이나 holidays 패키지 미반영
        from datetime import date as date_cls
        kr_holidays.update({date_cls(dt.year, 5, 1): "근로자의 날"})
        if dt.date() in kr_holidays:
            return True, kr_holidays[dt.date()]
    except ImportError:
        pass
    return False, ""


def cmd_run(dry_run: bool = False):
    """평일+공휴일 여부를 확인하고 다음 영상을 Teams에 발송한다."""
    today = datetime.now()
    skip, reason = is_korean_holiday(today)
    if skip:
        print(f"[SKIP] 오늘은 {reason}입니다. 평일(공휴일 제외)만 실행합니다.")
        sys.exit(0)

    queue = load_queue()
    if not queue:
        print("[INFO] 큐가 없습니다. 자동으로 초기화합니다...")
        cmd_init()
        queue = load_queue()

    # 신규 Claude 영상 자동 sync
    print("[SYNC] 신규 Claude 영상 확인 중...")
    sync_claude_videos(queue)
    queue = load_queue()  # sync 후 갱신된 큐 재로드

    # 미발송 중 가장 오래된 영상 선택
    pending = [v for v in queue["videos"] if not v["sent"]]
    if not pending:
        print("[SKIP] 발송할 Claude 영상이 없습니다. 새 영상 업로드 시 자동으로 추가됩니다.")
        sys.exit(0)

    video = pending[0]
    print(f"[선택] [{video['published_at'][:10]}] {video['title']}")
    print(f"       {video['url']}")

    success, error = send_video_to_teams(video, dry_run=dry_run)

    if success:
        if not dry_run:
            video["sent"] = True
            video["sent_at"] = datetime.now(timezone.utc).isoformat()
            save_queue(queue)
            remaining = len(pending) - 1
            print(f"\n[OK] 발송 완료. 남은 영상: {remaining}개")
        else:
            print("\n[DRY RUN] 실제 발송하지 않았습니다.")
    else:
        msg = f"Teams 발송 실패: {error}"
        print(f"\n[ERROR] {msg}")
        send_error_to_teams(msg)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="YouTube to Teams 순차 공유 툴")
    parser.add_argument("--init", action="store_true", help="채널 전체 영상 수집 및 큐 초기화")
    parser.add_argument("--sync", action="store_true", help="신규 영상만 큐에 추가")
    parser.add_argument("--status", action="store_true", help="큐 현황 출력")
    parser.add_argument("--dry-run", action="store_true", help="발송 없이 선택 영상만 확인")
    args = parser.parse_args()

    print("=" * 50)
    print("YouTube to Teams")
    print("=" * 50)

    if args.init:
        cmd_init()
    elif args.sync:
        cmd_sync()
    elif args.status:
        cmd_status()
    else:
        cmd_run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()