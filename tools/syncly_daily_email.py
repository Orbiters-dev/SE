"""
Syncly Daily Update Email
Sends a summary email after daily Syncly export + sync.
Called from daily_syncly_export.bat after US/JP sync completes.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

import gspread
from google.oauth2.service_account import Credentials

from send_gmail import send_email

SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
SA_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheet_stats():
    sa_path = SA_PATH
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    stats = {}
    for tab_name in ["US Posts Master", "US D+60 Tracker", "JP Posts Master", "JP D+60 Tracker"]:
        try:
            ws = sh.worksheet(tab_name)
            rows = ws.get_all_values()
            header_rows = 2 if "D+60" in tab_name else 1
            data_count = len(rows) - header_rows
            stats[tab_name] = data_count
        except Exception:
            stats[tab_name] = "N/A"

    return stats


def build_email_body(stats):
    today = datetime.now().strftime("%Y-%m-%d")

    rows_html = ""
    for tab, count in stats.items():
        rows_html += f"<tr><td style='padding:8px 16px;border-bottom:1px solid #eee'>{tab}</td>"
        rows_html += f"<td style='padding:8px 16px;border-bottom:1px solid #eee;text-align:right'>{count}</td></tr>"

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
        <div style="background:#1a1f2e;color:white;padding:20px 24px;border-radius:8px 8px 0 0">
            <h2 style="margin:0;font-size:18px">ONZENNA Affiliates Tracker - Daily Update</h2>
            <p style="margin:8px 0 0;opacity:0.8;font-size:14px">{today}</p>
        </div>

        <div style="background:white;padding:24px;border:1px solid #e5e5e5;border-top:none">
            <h3 style="margin:0 0 16px;font-size:15px;color:#333">Current Status</h3>
            <table style="width:100%;border-collapse:collapse;font-size:14px">
                <tr style="background:#f5f5f5">
                    <th style="padding:8px 16px;text-align:left">Tab</th>
                    <th style="padding:8px 16px;text-align:right">Rows</th>
                </tr>
                {rows_html}
            </table>

            <div style="margin-top:24px;text-align:center">
                <a href="{SHEET_URL}" style="display:inline-block;background:#1a73e8;color:white;
                   padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">
                    Open Spreadsheet
                </a>
            </div>

            <div style="margin-top:20px;font-size:12px;color:#888">
                <p style="margin:4px 0"><strong>US D+60 Tracker:</strong>
                    <a href="{SHEET_URL}#gid=199526745">Direct Link</a></p>
                <p style="margin:4px 0"><strong>JP D+60 Tracker:</strong>
                    <a href="{SHEET_URL}?gid=295191381#gid=295191381">Direct Link</a></p>
                <p style="margin:4px 0"><strong>US Posts Master:</strong>
                    <a href="{SHEET_URL}?gid=1472162449#gid=1472162449">Direct Link</a></p>
                <p style="margin:4px 0"><strong>JP Posts Master:</strong>
                    <a href="{SHEET_URL}?gid=842545840#gid=842545840">Direct Link</a></p>
            </div>
        </div>

        <div style="background:#f9f9f9;padding:12px 24px;border:1px solid #e5e5e5;border-top:none;
             border-radius:0 0 8px 8px;font-size:11px;color:#999;text-align:center">
            Automated daily report - KST 08:00
        </div>
    </div>
    """


def main():
    print("[EMAIL] Collecting sheet stats...")
    stats = get_sheet_stats()
    print(f"[EMAIL] Stats: {stats}")

    body = build_email_body(stats)
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"[Syncly] ONZENNA Affiliates Tracker Update - {today}"

    recipient = os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")
    print(f"[EMAIL] Sending to {recipient}...")
    send_email(to=recipient, subject=subject, body_html=body)
    print("[EMAIL] Done")


if __name__ == "__main__":
    main()
