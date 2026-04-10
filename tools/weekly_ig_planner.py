"""
WAT Tool: Weekly Instagram content planner (automated).
Runs every Friday 14:00 KST via Windows Task Scheduler.

Pipeline:
  1. Scrape JP trends + generate 10 plans (meme:5, brand:5)
  2. Save Excel to Shared/인스타그램 포스팅 기획안/{월}_W{N}/
  3. Send email with Excel attachment to se.heo@orbiters.co.kr
  4. Send Teams notification (Contents Planning channel)

Usage:
    python tools/weekly_ig_planner.py           # run now
    python tools/weekly_ig_planner.py --dry-run # skip email + Teams notify
"""

import os
import sys
import shutil
import logging
import argparse
import subprocess
import base64
from datetime import datetime, date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

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

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
SHARED_ROOT = PROJECT_ROOT / "인스타그램 기획안"
TMP_DIR = PROJECT_ROOT / ".tmp"


# ── Week label ────────────────────────────────────────────────────────────────

def get_week_label(d: date = None) -> str:
    """Return folder name like '3월_W2' for a given date."""
    if d is None:
        d = date.today()
    month = d.month
    # Week number within month (1-indexed, starts from first Monday)
    day = d.day
    week_num = (day - 1) // 7 + 1
    return f"{month}월_W{week_num}"


# ── Step 1: Generate plans ────────────────────────────────────────────────────

def run_planner() -> Path:
    """Run plan_weekly_content.py and return path to generated Excel."""
    ts = datetime.now().strftime("%Y%m%d")
    output_path = TMP_DIR / f"weekly_content_plan_{ts}.xlsx"

    logger.info("Running plan_weekly_content.py (meme:10, brand:10)...")
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "tools" / "plan_weekly_content.py"),
            "--distribution", "meme:10,brand:10",
            "--output", str(output_path),
        ],
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"plan_weekly_content.py failed (exit {result.returncode})")

    if not output_path.exists():
        raise FileNotFoundError(f"Expected output not found: {output_path}")

    logger.info(f"Plans generated: {output_path}")
    return output_path


# ── Step 2: Save to Shared folder ────────────────────────────────────────────

def save_to_shared(excel_path: Path) -> Path:
    """Copy Excel to Shared/인스타그램 포스팅 기획안/{월}_W{N}/."""
    week_label = get_week_label()
    dest_dir = SHARED_ROOT / week_label
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / excel_path.name
    shutil.copy2(excel_path, dest_path)
    logger.info(f"Saved to Shared: {dest_path}")
    return dest_path


# ── Step 3: Email notification ────────────────────────────────────────────────

GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_OAUTH_CREDENTIALS_PATH", "credentials/gmail_oauth_credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH",
                              os.getenv("ZEZEBAEBAE_GMAIL_TOKEN_PATH", "credentials/gmail_token.json"))
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")
SEEUN_EMAIL = "se.heo@orbiters.co.kr"


def get_gmail_service():
    """Build Gmail API service using OAuth2 credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    creds = None

    if os.path.exists(GMAIL_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GMAIL_CREDENTIALS_PATH):
                logger.error(f"Gmail OAuth credentials not found: {GMAIL_CREDENTIALS_PATH}")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(GMAIL_TOKEN_PATH), exist_ok=True)
        with open(GMAIL_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email_notification(excel_path: Path, week_label: str) -> bool:
    """Send Excel file as email attachment to se.heo@orbiters.co.kr."""
    try:
        service = get_gmail_service()
        if not service:
            logger.error("Gmail service unavailable — skipping email")
            return False

        today = date.today().strftime("%Y-%m-%d")
        subject = f"[인스타그램 기획안] {week_label} 콘텐츠 플랜 ({today})"

        body_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2 style="color: #405DE6;">📋 인스타그램 포스팅 기획안</h2>
            <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">주차</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{week_label}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">생성일</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{today}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">기획안</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">밈/바이럴 10개 + 브랜드 제품 10개 (경쟁사 분석 반영)</td></tr>
            </table>
            <p>첨부된 엑셀 파일을 확인 후 사용할 기획안을 선택해 주세요 ✅</p>
            <p style="color: #888; font-size: 12px;">Shared 폴더 백업: 인스타그램 기획안/{week_label}/</p>
        </div>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = GMAIL_SENDER
        msg["To"] = SEEUN_EMAIL
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        # Attach Excel file
        with open(excel_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{excel_path.name}"')
        msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

        logger.info(f"Email sent to {SEEUN_EMAIL} ✅ (Message ID: {result.get('id')})")
        return True

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


# ── Step 4: Teams notification ────────────────────────────────────────────────

def send_teams_notification(excel_path: Path, week_label: str) -> bool:
    """Send Adaptive Card to 세은 personal Teams DM."""
    import requests

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL_SEEUN")
    if not webhook_url:
        logger.warning("TEAMS_CONTENT_WEBHOOK_URL not set — skipping Teams notification")
        return False

    today = date.today().strftime("%Y-%m-%d")
    file_name = excel_path.name
    folder_path = f"Shared/인스타그램 포스팅 기획안/{week_label}/{file_name}"

    body = [
        {
            "type": "TextBlock",
            "text": f"📋 인스타그램 포스팅 기획안 생성 완료",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "주차", "value": week_label},
                {"title": "생성일", "value": today},
                {"title": "기획안", "value": "밈/바이럴 10개 + 브랜드 제품 10개 (경쟁사 분석 반영)"},
                {"title": "파일", "value": folder_path},
            ],
        },
        {
            "type": "TextBlock",
            "text": "Shared 폴더에서 확인 후 사용할 기획안을 선택해 주세요 ✅",
            "wrap": True,
            "color": "Default",
            "size": "Small",
        },
    ]

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
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code in (200, 202):
            logger.info("Teams notification sent ✅")
            return True
        else:
            logger.error(f"Teams webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Weekly IG content planner (automated)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate and save, but skip Teams notification")
    parser.add_argument("--excel", type=str, default=None,
                        help="Use existing Excel file (skip generation)")
    args = parser.parse_args()

    week_label = get_week_label()
    logger.info(f"=== Weekly IG Planner | {week_label} ===")

    # Step 1: Generate (or use existing)
    if args.excel:
        excel_path = Path(args.excel)
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {excel_path}")
        logger.info(f"Using existing Excel: {excel_path}")
    else:
        excel_path = run_planner()

    # Step 2: Save to Shared
    saved_path = save_to_shared(excel_path)

    # Step 3: Email with attachment
    if not args.dry_run:
        send_email_notification(saved_path, week_label)
    else:
        logger.info("Dry-run: Email notification skipped")

    # Step 4: Teams notify
    if not args.dry_run:
        send_teams_notification(saved_path, week_label)
    else:
        logger.info("Dry-run: Teams notification skipped")

    print(f"\n✅ Done!")
    print(f"   파일: {saved_path}")
    print(f"   주차: {week_label}")


if __name__ == "__main__":
    main()
