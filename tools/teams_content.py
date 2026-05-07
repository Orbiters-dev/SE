"""
WAT Tool: Post content ideas to Teams "Contents Planning" channel.
Two functions:
  1. Post content plan summary as Adaptive Card (webhook)
  2. Upload content plan Excel to channel SharePoint (Graph API)

Uses separate env vars (TEAMS_CONTENT_*) so it doesn't conflict with
the existing Twitter channel config.

Usage:
    python tools/teams_content.py --post-plan                     # post content_plan.json as card
    python tools/teams_content.py --post-plan --plan-file X.json  # from specific file
    python tools/teams_content.py --upload "file.xlsx"            # upload file to channel
    python tools/teams_content.py --upload "file.xlsx" --notify   # upload + notify
    python tools/teams_content.py --test                          # send test card
    python tools/teams_content.py --setup                         # find channel IDs
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

# ── Config (Contents Planning channel) ────────────────────────────────────────

TENANT_ID = os.getenv("TEAMS_TENANT_ID")
CLIENT_ID = os.getenv("TEAMS_GRAPH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TEAMS_GRAPH_CLIENT_SECRET")

# Contents Planning channel-specific
CONTENT_TEAM_ID = os.getenv("TEAMS_CONTENT_TEAM_ID")
CONTENT_CHANNEL_ID = os.getenv("TEAMS_CONTENT_CHANNEL_ID")
CONTENT_WEBHOOK_URL = os.getenv("TEAMS_CONTENT_WEBHOOK_URL")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

PROJECT_ROOT = Path(__file__).parent.parent
PLAN_PATH = PROJECT_ROOT / ".tmp" / "content_plan.json"

_cached_token = None
_token_expiry = None


# ── Auth (shared Graph API credentials) ──────────────────────────────────────

def _get_access_token() -> str:
    global _cached_token, _token_expiry
    if _cached_token and _token_expiry and datetime.now().timestamp() < _token_expiry:
        return _cached_token

    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        raise ValueError("Missing Graph API credentials in .env")

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


# ── Webhook: Post Adaptive Card ──────────────────────────────────────────────

def _post_card(body: list[dict], webhook_url: str = "") -> bool:
    url = webhook_url or CONTENT_WEBHOOK_URL
    if not url:
        logger.error("TEAMS_CONTENT_WEBHOOK_URL not set in .env")
        return False

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

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code in (200, 202):
            logger.info("Card posted to Contents Planning channel")
            return True
        else:
            logger.error(f"Webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False


def post_content_plan(plan_path: str = "") -> bool:
    """Post content plan summary as an Adaptive Card."""
    path = Path(plan_path) if plan_path else PLAN_PATH
    if not path.exists():
        logger.error(f"Plan file not found: {path}")
        return False

    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    posts = plan if isinstance(plan, list) else plan.get("posts", plan.get("items", [plan]))
    if not isinstance(posts, list):
        posts = [posts]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    body = [
        {
            "type": "TextBlock",
            "text": f"🎨 콘텐츠 아이디어 ({len(posts)}건)",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": f"작성: {now} | 소스: {Path(path).name}",
            "isSubtle": True,
            "spacing": "None",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
    ]

    for i, post in enumerate(posts[:10]):  # max 10 to stay within card limits
        # Flexible field extraction
        title = (post.get("title") or post.get("topic") or
                 post.get("theme") or f"Post {i+1}")
        caption = (post.get("caption") or post.get("text") or
                   post.get("content") or post.get("description") or "")
        format_type = (post.get("format") or post.get("type") or
                       post.get("content_type") or "")
        hashtags = post.get("hashtags", [])
        date = post.get("date") or post.get("scheduled_date") or ""

        # Post header
        format_icon = {"carousel": "🎠", "reel": "🎬", "story": "📱",
                       "single": "📸", "video": "🎥"}.get(format_type, "📌")

        header = f"{format_icon} **{title}**"
        if date:
            header += f" ({date})"

        body.append({
            "type": "TextBlock",
            "text": header,
            "weight": "Bolder",
            "spacing": "Medium",
            "wrap": True,
        })

        # Caption preview (truncated)
        if caption:
            preview = caption[:150] + ("..." if len(caption) > 150 else "")
            body.append({
                "type": "TextBlock",
                "text": preview,
                "wrap": True,
                "spacing": "Small",
            })

        # Hashtags
        if hashtags:
            tags = " ".join(hashtags[:8])
            body.append({
                "type": "TextBlock",
                "text": tags,
                "isSubtle": True,
                "spacing": "None",
                "wrap": True,
            })

    # Footer
    if len(posts) > 10:
        body.append({
            "type": "TextBlock",
            "text": f"... 외 {len(posts) - 10}건 더",
            "isSubtle": True,
            "spacing": "Medium",
        })

    body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})
    body.append({
        "type": "TextBlock",
        "text": "💬 피드백은 이 채널에 댓글로 남겨주세요",
        "isSubtle": True,
        "wrap": True,
    })

    return _post_card(body)


def post_ideas_card(ideas: list[dict]) -> bool:
    """Post a list of content ideas directly (without file).

    Each idea: {"title": str, "description": str, "format": str, "hashtags": list}
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    body = [
        {
            "type": "TextBlock",
            "text": f"💡 콘텐츠 아이디어 제안 ({len(ideas)}건)",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": f"생성: {now}",
            "isSubtle": True,
            "spacing": "None",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
    ]

    for i, idea in enumerate(ideas[:10]):
        title = idea.get("title", f"Idea {i+1}")
        desc = idea.get("description", "")
        fmt = idea.get("format", "")

        format_icon = {"carousel": "🎠", "reel": "🎬", "story": "📱",
                       "single": "📸", "video": "🎥"}.get(fmt, "💡")

        body.append({
            "type": "TextBlock",
            "text": f"{format_icon} **{i+1}. {title}**",
            "weight": "Bolder",
            "spacing": "Medium",
            "wrap": True,
        })

        if desc:
            body.append({
                "type": "TextBlock",
                "text": desc[:200],
                "wrap": True,
                "spacing": "Small",
            })

    return _post_card(body)


# ── Graph API: Upload file ───────────────────────────────────────────────────

def _get_channel_drive_folder():
    """Get SharePoint drive/folder for Contents Planning channel."""
    url = f"{GRAPH_BASE}/teams/{CONTENT_TEAM_ID}/channels/{CONTENT_CHANNEL_ID}/filesFolder"
    resp = requests.get(url, headers=_graph_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("parentReference", {}).get("driveId"), data.get("id")


def upload_file(file_path: str, target_folder: str = "",
                notify: bool = False, message: str = "") -> dict:
    """Upload a file to Contents Planning channel SharePoint."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not all([CONTENT_TEAM_ID, CONTENT_CHANNEL_ID]):
        raise ValueError("TEAMS_CONTENT_TEAM_ID / TEAMS_CONTENT_CHANNEL_ID not set in .env")

    file_size = path.stat().st_size
    filename = path.name
    upload_path = f"{target_folder}/{filename}" if target_folder else filename

    logger.info(f"Uploading: {filename} ({file_size:,} bytes) to Contents Planning")

    drive_id, folder_id = _get_channel_drive_folder()

    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    if file_size <= 4 * 1024 * 1024:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{upload_path}:/content"
        with open(path, "rb") as f:
            resp = requests.put(
                url,
                headers={**_graph_headers(), "Content-Type": content_type},
                data=f,
                timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
    else:
        # Resumable upload for large files
        session_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{upload_path}:/createUploadSession"
        session_resp = requests.post(
            session_url,
            headers={**_graph_headers(), "Content-Type": "application/json"},
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=15,
        )
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
                    break
                elif resp.status_code == 202:
                    logger.info(f"  Progress: {(end+1)/file_size*100:.0f}%")
                else:
                    resp.raise_for_status()
                offset += len(chunk)
            else:
                raise RuntimeError("Upload incomplete")

    result = {
        "file_id": data.get("id"),
        "name": data.get("name"),
        "web_url": data.get("webUrl"),
        "size": data.get("size"),
        "modified": data.get("lastModifiedDateTime"),
    }

    logger.info(f"Uploaded: {result.get('web_url', '')}")

    if notify:
        _notify_upload(result, message)

    return result


def _notify_upload(file_info: dict, message: str = ""):
    """Send upload notification card to channel."""
    name = file_info.get("name", "")
    url = file_info.get("web_url", "")
    size = file_info.get("size", 0)
    size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"

    body = [
        {"type": "TextBlock", "text": f"📁 파일 업로드: {name}", "weight": "Bolder", "size": "Medium"},
        {"type": "TextBlock", "text": f"{size_str} | {datetime.now():%Y-%m-%d %H:%M}", "isSubtle": True},
    ]
    if message:
        body.append({"type": "TextBlock", "text": message, "wrap": True, "spacing": "Medium"})
    if url:
        body.append({"type": "TextBlock", "text": f"[📎 파일 열기]({url})", "spacing": "Medium"})

    _post_card(body)


# ── Setup helper ─────────────────────────────────────────────────────────────

def setup_helper():
    """List teams and channels to find IDs."""
    print("=" * 50)
    print("Contents Planning Channel Setup")
    print("=" * 50)

    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print("\nGraph API credentials missing in .env")
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
            cur = " ← current" if team["id"] == CONTENT_TEAM_ID else ""
            print(f"  Team: {team['displayName']}")
            print(f"    ID={team['id']}{cur}")

        if CONTENT_TEAM_ID:
            print(f"\nChannels:")
            ch_resp = requests.get(
                f"{GRAPH_BASE}/teams/{CONTENT_TEAM_ID}/channels?$select=id,displayName",
                headers=_graph_headers(), timeout=15)
            ch_resp.raise_for_status()
            for ch in ch_resp.json().get("value", []):
                cur = " ← current" if ch["id"] == CONTENT_CHANNEL_ID else ""
                print(f"  {ch['displayName']}: {ch['id']}{cur}")
    except Exception as e:
        print(f"Failed: {e}")

    # Webhook reminder
    print(f"\n{'='*50}")
    print("Webhook 설정:")
    print("1. Teams → Contents Planning 채널 → 커넥터 → Incoming Webhook")
    print("2. Webhook URL을 .env의 TEAMS_CONTENT_WEBHOOK_URL에 추가")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content ideas → Teams")
    parser.add_argument("--post-plan", action="store_true", help="Post content plan as card")
    parser.add_argument("--plan-file", type=str, help="Path to plan JSON")
    parser.add_argument("--upload", type=str, help="Upload file to channel")
    parser.add_argument("--folder", default="", help="Target subfolder in SharePoint")
    parser.add_argument("--notify", action="store_true", help="Send notification after upload")
    parser.add_argument("--message", default="", help="Notification message")
    parser.add_argument("--test", action="store_true", help="Send test card")
    parser.add_argument("--setup", action="store_true", help="Setup helper")
    args = parser.parse_args()

    if args.setup:
        setup_helper()
    elif args.test:
        ok = post_ideas_card([
            {"title": "테스트 아이디어 1", "description": "이것은 테스트입니다", "format": "carousel"},
            {"title": "테스트 아이디어 2", "description": "콘텐츠 플래닝 채널 연동 확인", "format": "reel"},
        ])
        print("Test card sent!" if ok else "Failed to send test card")
    elif args.post_plan:
        ok = post_content_plan(args.plan_file or "")
        print("Plan posted!" if ok else "Failed to post plan")
    elif args.upload:
        result = upload_file(args.upload, target_folder=args.folder,
                           notify=args.notify, message=args.message)
        print(f"URL: {result['web_url']}")
    else:
        parser.print_help()
