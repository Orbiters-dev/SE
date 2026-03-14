"""
Drive State Sync
================
.tmp/ 상태 파일을 Google Drive에 저장/복원.
데스크탑-랩탑 간 content_detection_log / usa_llm_prev 유실 방지.

Usage:
  python tools/save_to_drive.py --push          # .tmp/ -> Drive
  python tools/save_to_drive.py --pull          # Drive -> .tmp/ (merge, never overwrite newer)
  python tools/save_to_drive.py --push --force  # 무조건 덮어쓰기
  python tools/save_to_drive.py --pull --force  # Drive 버전으로 무조건 덮어쓰기
  python tools/save_to_drive.py --status        # Drive 현황만 출력

Drive folder: "ORBI-State-Sync" (자동 생성)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

load_env()

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDS_PATH = PROJECT_ROOT / "credentials" / "google_service_account.json"
DRIVE_FOLDER_NAME = "ORBI-State-Sync"

# Files to sync: (local path, drive filename)
SYNC_FILES = [
    (PROJECT_ROOT / ".tmp" / "content_detection_log.json", "content_detection_log.json"),
    (PROJECT_ROOT / ".tmp" / "usa_llm_prev.json",          "usa_llm_prev.json"),
    (PROJECT_ROOT / ".tmp" / "sns_sync_summary.json",       "sns_sync_summary.json"),
    (PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json",     "usa_llm_highlights.json"),
]


def get_service():
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_or_create_folder(service, name):
    """Get or create a Drive folder by name (in root)."""
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    res = service.files().list(q=q, fields="files(id, name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=meta, fields="id").execute()
    print(f"  [Drive] Created folder '{name}': {folder['id']}")
    return folder["id"]


def list_drive_files(service, folder_id):
    """Return {filename: file_id} for all files in folder."""
    q = f"'{folder_id}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id, name, modifiedTime, size)").execute()
    return {f["name"]: f for f in res.get("files", [])}


def upload_file(service, local_path: Path, drive_filename: str, folder_id: str, existing_id=None):
    """Upload or update a file in Drive."""
    media = MediaFileUpload(str(local_path), mimetype="application/json", resumable=False)
    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        print(f"  [PUSH] Updated {drive_filename}")
    else:
        meta = {"name": drive_filename, "parents": [folder_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()
        print(f"  [PUSH] Created {drive_filename}")


def download_file(service, file_id: str, local_path: Path):
    """Download a Drive file to local path."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(buf.getvalue())


def merge_detection_log(local_path: Path, drive_data: dict) -> dict:
    """Merge detection logs: keep the earlier first-seen date per URL."""
    local = {}
    if local_path.exists():
        try:
            local = json.loads(local_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    merged = dict(drive_data)
    for url, date in local.items():
        if url not in merged or date < merged[url]:
            merged[url] = date
    return merged


def push(service, folder_id, force=False):
    existing = list_drive_files(service, folder_id)
    for local_path, drive_filename in SYNC_FILES:
        if not local_path.exists():
            print(f"  [PUSH] Skip {drive_filename} (not found locally)")
            continue
        ex = existing.get(drive_filename)
        upload_file(service, local_path, drive_filename, folder_id, existing_id=ex["id"] if ex else None)


def pull(service, folder_id, force=False):
    existing = list_drive_files(service, folder_id)
    for local_path, drive_filename in SYNC_FILES:
        ex = existing.get(drive_filename)
        if not ex:
            print(f"  [PULL] Skip {drive_filename} (not in Drive)")
            continue

        # Download to temp buffer first
        request = service.files().get_media(fileId=ex["id"])
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        drive_content = buf.getvalue().decode("utf-8")

        # For detection_log: merge to keep earliest first-seen dates
        if drive_filename == "content_detection_log.json" and not force:
            drive_data = json.loads(drive_content)
            merged = merge_detection_log(local_path, drive_data)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            added = len(merged) - len(json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {})
            print(f"  [PULL] Merged {drive_filename}: {len(merged)} URLs total")
        else:
            if not force and local_path.exists():
                # Compare modification times — keep newer
                local_mtime = local_path.stat().st_mtime
                drive_mtime_str = ex.get("modifiedTime", "")
                if drive_mtime_str:
                    drive_mtime = datetime.fromisoformat(
                        drive_mtime_str.replace("Z", "+00:00")
                    ).timestamp()
                    if local_mtime >= drive_mtime:
                        print(f"  [PULL] Skip {drive_filename} (local is newer or same)")
                        continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(drive_content, encoding="utf-8")
            print(f"  [PULL] Downloaded {drive_filename}")


def status(service, folder_id):
    existing = list_drive_files(service, folder_id)
    print(f"\nDrive folder: {DRIVE_FOLDER_NAME} ({folder_id})")
    print(f"{'File':<40} {'Drive':<22} {'Local':<22} {'Sync'}")
    print("-" * 95)
    for local_path, drive_filename in SYNC_FILES:
        ex = existing.get(drive_filename)
        drive_str = ex["modifiedTime"][:19].replace("T", " ") + " UTC" if ex else "(not in Drive)"
        if local_path.exists():
            lm = datetime.fromtimestamp(local_path.stat().st_mtime, tz=timezone.utc)
            local_str = lm.strftime("%Y-%m-%d %H:%M UTC")
        else:
            local_str = "(missing)"
        sync_str = ""
        if ex and local_path.exists():
            drive_ts = datetime.fromisoformat(ex["modifiedTime"].replace("Z", "+00:00")).timestamp()
            local_ts = local_path.stat().st_mtime
            diff = abs(local_ts - drive_ts)
            if diff < 60:
                sync_str = "OK"
            elif local_ts > drive_ts:
                sync_str = "local newer"
            else:
                sync_str = "drive newer"
        print(f"{drive_filename:<40} {drive_str:<22} {local_str:<22} {sync_str}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push",   action="store_true", help="Upload .tmp/ files to Drive")
    parser.add_argument("--pull",   action="store_true", help="Download Drive files to .tmp/")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    parser.add_argument("--force",  action="store_true", help="Overwrite without date check")
    args = parser.parse_args()

    if not any([args.push, args.pull, args.status]):
        parser.print_help()
        return

    print("Connecting to Google Drive...")
    service = get_service()
    folder_id = get_or_create_folder(service, DRIVE_FOLDER_NAME)

    if args.status:
        status(service, folder_id)
    if args.push:
        print("\nPushing to Drive...")
        push(service, folder_id, force=args.force)
    if args.pull:
        print("\nPulling from Drive...")
        pull(service, folder_id, force=args.force)

    print("\nDone.")


if __name__ == "__main__":
    main()
