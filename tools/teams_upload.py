"""
WAT Tool: Upload files to Microsoft Teams channel via Graph API.

Teams channels store files in SharePoint — automatic version control.
Same filename uploaded again = new version (not duplicate).

Setup:
    1. https://portal.azure.com → Azure AD → App registrations → New
    2. API permissions → Microsoft Graph → Files.ReadWrite.All, Sites.ReadWrite.All
    3. Certificates & secrets → New client secret
    4. Add to .env (see below)

Usage:
    python tools/teams_upload.py "path/to/file.xlsx"
    python tools/teams_upload.py "path/to/file.xlsx" --notify
    python tools/teams_upload.py --list
    python tools/teams_upload.py --setup
"""

import os
import sys
import json
import argparse
import logging
import mimetypes
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

TENANT_ID = os.getenv("TEAMS_TENANT_ID")
CLIENT_ID = os.getenv("TEAMS_GRAPH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TEAMS_GRAPH_CLIENT_SECRET")
TEAM_ID = os.getenv("TEAMS_TEAM_ID")
CHANNEL_ID = os.getenv("TEAMS_CHANNEL_ID")
WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

_cached_token = None
_token_expiry = None


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_access_token() -> str:
    """Get Graph API access token via client credentials flow."""
    global _cached_token, _token_expiry

    if _cached_token and _token_expiry and datetime.now().timestamp() < _token_expiry:
        return _cached_token

    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        raise ValueError(
            "Missing credentials. Set TEAMS_TENANT_ID, "
            "TEAMS_GRAPH_CLIENT_ID, TEAMS_GRAPH_CLIENT_SECRET in .env"
        )

    resp = requests.post(
        TOKEN_URL.format(tenant=TENANT_ID),
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    _cached_token = data["access_token"]
    _token_expiry = datetime.now().timestamp() + data.get("expires_in", 3600) - 60
    return _cached_token


def _graph_headers() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def _get_channel_drive_folder():
    """Get the SharePoint drive and folder for the Teams channel."""
    url = f"{GRAPH_BASE}/teams/{TEAM_ID}/channels/{CHANNEL_ID}/filesFolder"
    resp = requests.get(url, headers=_graph_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    drive_id = data.get("parentReference", {}).get("driveId")
    folder_id = data.get("id")
    return drive_id, folder_id


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_file(file_path: str, target_folder: str = "", notify: bool = False, message: str = "") -> dict:
    """Upload a file to the Teams channel's SharePoint folder.

    Same filename = SharePoint auto-creates new version.

    Returns: dict with web_url, file_id, name, size
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = path.stat().st_size
    filename = path.name
    upload_path = f"{target_folder}/{filename}" if target_folder else filename

    logger.info(f"Uploading: {filename} ({file_size:,} bytes)")

    drive_id, folder_id = _get_channel_drive_folder()

    if file_size <= 4 * 1024 * 1024:
        result = _simple_upload(drive_id, folder_id, upload_path, path)
    else:
        result = _session_upload(drive_id, folder_id, upload_path, path, file_size)

    logger.info(f"Done: {result.get('web_url', '')}")

    # Create organization-wide edit link so team can edit (not read-only)
    edit_url = _create_edit_link(drive_id, result.get("file_id", ""))
    if edit_url:
        result["edit_url"] = edit_url

    if notify and WEBHOOK_URL:
        _send_upload_notification(result, message)

    return result


def _simple_upload(drive_id, folder_id, upload_path, path):
    """PUT upload for files under 4MB."""
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{upload_path}:/content"

    with open(path, "rb") as f:
        resp = requests.put(url, headers={**_graph_headers(), "Content-Type": content_type},
                           data=f, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return {
        "file_id": data.get("id"), "name": data.get("name"),
        "web_url": data.get("webUrl"), "size": data.get("size"),
        "modified": data.get("lastModifiedDateTime"),
    }


def _session_upload(drive_id, folder_id, upload_path, path, file_size):
    """Resumable upload for files over 4MB."""
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{upload_path}:/createUploadSession"
    session_resp = requests.post(url, headers={**_graph_headers(), "Content-Type": "application/json"},
                                json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}, timeout=15)
    session_resp.raise_for_status()
    upload_url = session_resp.json()["uploadUrl"]

    chunk_size = 10 * 1024 * 1024
    with open(path, "rb") as f:
        offset = 0
        while offset < file_size:
            chunk = f.read(chunk_size)
            end = offset + len(chunk) - 1
            resp = requests.put(upload_url, headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end}/{file_size}",
            }, data=chunk, timeout=120)

            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "file_id": data.get("id"), "name": data.get("name"),
                    "web_url": data.get("webUrl"), "size": data.get("size"),
                    "modified": data.get("lastModifiedDateTime"),
                }
            elif resp.status_code == 202:
                logger.info(f"  Progress: {(end+1)/file_size*100:.0f}%")
            else:
                resp.raise_for_status()
            offset += len(chunk)

    raise RuntimeError("Upload incomplete")


def _create_edit_link(drive_id: str, file_id: str) -> str:
    """Create an organization-scoped edit link for the uploaded file.

    This ensures team members can edit (not read-only) when opening from Teams.
    """
    if not file_id:
        return ""
    try:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{file_id}/createLink"
        resp = requests.post(
            url,
            headers={**_graph_headers(), "Content-Type": "application/json"},
            json={"type": "edit", "scope": "organization"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            edit_url = resp.json().get("link", {}).get("webUrl", "")
            logger.info(f"Edit link created: {edit_url}")
            return edit_url
    except Exception as e:
        logger.warning(f"Edit link creation failed: {e}")
    return ""


def _send_upload_notification(file_info, message=""):
    """Post upload notification to Teams via webhook."""
    name = file_info.get("name", "")
    url = file_info.get("web_url", "")
    size = file_info.get("size", 0)
    size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"

    edit_url = file_info.get("edit_url", "")

    body = [
        {"type": "TextBlock", "text": f"📁 {name}", "weight": "Bolder", "size": "Medium"},
        {"type": "TextBlock", "text": f"{size_str} | {datetime.now():%Y-%m-%d %H:%M}", "isSubtle": True},
    ]
    if message:
        body.append({"type": "TextBlock", "text": message, "wrap": True, "spacing": "Medium"})
    # Prefer edit link (editable) over web_url (read-only)
    open_url = edit_url or url
    if open_url:
        body.append({"type": "TextBlock", "text": f"[📝 편집하기 (Open & Edit)]({open_url})", "spacing": "Medium"})

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body,
            },
        }],
    }
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    if resp.status_code == 202:
        logger.info("Upload notification sent to Teams")
    else:
        logger.warning(f"Teams notification failed: {resp.status_code}")


# ── Plan JSON upload/download (for 企画マン → ツイート投稿 pipeline) ────────────

PLANS_FOLDER = "plans"


def upload_plan_json(local_path: str, date_str: str) -> dict:
    """Upload a daily tweet plan JSON to SharePoint plans/ folder."""
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {local_path}")
    return upload_file(local_path, target_folder=PLANS_FOLDER)


def download_plan_json(date_str: str, dest_path: str) -> bool:
    """Download a daily tweet plan JSON from SharePoint plans/ folder."""
    filename = f"daily_tweet_plan_{date_str}.json"
    drive_id, folder_id = _get_channel_drive_folder()
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{PLANS_FOLDER}/{filename}:/content"
    try:
        resp = requests.get(url, headers=_graph_headers(), timeout=30)
        resp.raise_for_status()
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(resp.content)
        logger.info(f"Downloaded plan: {filename} → {dest}")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"Plan not found on SharePoint: {filename}")
        else:
            logger.warning(f"Plan download failed: {e}")
        return False


# ── Utility ───────────────────────────────────────────────────────────────────

def list_channel_files(subfolder: str = "") -> list[dict]:
    """List files in the Teams channel folder."""
    drive_id, folder_id = _get_channel_drive_folder()
    if subfolder:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{subfolder}:/children"
    else:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}/children"

    resp = requests.get(url, headers=_graph_headers(), timeout=15)
    resp.raise_for_status()
    return [
        {"name": item.get("name"), "web_url": item.get("webUrl"),
         "size": item.get("size", 0), "modified": item.get("lastModifiedDateTime"),
         "is_folder": "folder" in item}
        for item in resp.json().get("value", [])
    ]


def check_credentials() -> dict:
    """Check if credentials are configured."""
    missing = []
    if not TENANT_ID: missing.append("TEAMS_TENANT_ID")
    if not CLIENT_ID: missing.append("TEAMS_GRAPH_CLIENT_ID")
    if not CLIENT_SECRET: missing.append("TEAMS_GRAPH_CLIENT_SECRET")
    if not TEAM_ID: missing.append("TEAMS_TEAM_ID")
    if not CHANNEL_ID: missing.append("TEAMS_CHANNEL_ID")
    return {"is_configured": len(missing) == 0, "missing_vars": missing}


def setup_helper():
    """Find Team ID and Channel ID via Graph API."""
    print("=" * 50)
    print("Teams Upload Setup")
    print("=" * 50)

    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print("\n.env에 아래 값을 먼저 추가하세요:")
        print("  TEAMS_TENANT_ID=")
        print("  TEAMS_GRAPH_CLIENT_ID=")
        print("  TEAMS_GRAPH_CLIENT_SECRET=")
        print("\nhttps://portal.azure.com → Azure AD → App registrations")
        return

    try:
        _get_access_token()
        print("Auth OK\n")
    except Exception as e:
        print(f"Auth FAILED: {e}")
        return

    # List teams
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/groups?$filter=resourceProvisioningOptions/Any(x:x eq 'Team')&$select=id,displayName",
            headers=_graph_headers(), timeout=15)
        resp.raise_for_status()
        for team in resp.json().get("value", []):
            print(f"  Team: {team['displayName']}")
            print(f"    TEAMS_TEAM_ID={team['id']}")

        if TEAM_ID:
            print(f"\nChannels for current team:")
            ch_resp = requests.get(
                f"{GRAPH_BASE}/teams/{TEAM_ID}/channels?$select=id,displayName",
                headers=_graph_headers(), timeout=15)
            ch_resp.raise_for_status()
            for ch in ch_resp.json().get("value", []):
                cur = " ← current" if ch["id"] == CHANNEL_ID else ""
                print(f"  {ch['displayName']}: TEAMS_CHANNEL_ID={ch['id']}{cur}")
    except Exception as e:
        print(f"Failed: {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload files to Teams")
    parser.add_argument("file", nargs="?", help="File to upload")
    parser.add_argument("--folder", default="", help="Target subfolder")
    parser.add_argument("--notify", action="store_true", help="Send notification")
    parser.add_argument("--message", default="", help="Notification message")
    parser.add_argument("--list", action="store_true", help="List channel files")
    parser.add_argument("--setup", action="store_true", help="Setup helper")
    args = parser.parse_args()

    if args.setup:
        setup_helper()
    elif args.list:
        for f in list_channel_files():
            icon = "📁" if f["is_folder"] else "📄"
            print(f"  {icon} {f['name']}  {f.get('modified', '')[:10]}")
    elif args.file:
        result = upload_file(args.file, target_folder=args.folder,
                           notify=args.notify, message=args.message)
        print(f"\nURL: {result['web_url']}")
    else:
        parser.print_help()
