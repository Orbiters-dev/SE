#!/usr/bin/env python3
"""
選定マン: 送信候補をGoogle Sheetsに書き込み、Teamsに通知する。

Usage:
  python tools/selector_notify.py
  python tools/selector_notify.py --csv .tmp/pending_review_emails.csv
"""
import argparse
import csv
import os
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TEAMS_WEBHOOK_URL = (
    "https://default30da627c046841a5aee2f86a7bd40c.be.environment.api.powerplatform.com:443"
    "/powerautomate/automations/direct/workflows/c7757684d6a04087a9684946b7165eba"
    "/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=Q3ZmKD4UkKj95CY2TAEx4QPMeov5moA0eZyCwWsf9tA"
)
SERVICE_ACCOUNT_PATH = "credentials/google_service_account.json"
SHEET_ID = "17lhDDC8X_54jwqsMa0WBJxCpYZUQUI7MfHRy0YUCk7g"
CSV_PATH = ".tmp/pending_review_emails.csv"

HEADERS_JP = ["注文番号", "注文日", "発送日", "配達完了日", "メール", "顧客名", "商品名", "ショップ名", "レビューリンク"]
FIELDS = ["order_number", "order_date", "shipping_date", "delivery_date", "email", "name", "item_name", "shop_name", "review_link"]


def get_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SHEET_ID)
    return gc, spreadsheet


def write_candidates_to_sheet(spreadsheet, rows):
    ws = spreadsheet.sheet1
    ws.clear()
    ws.update_title("送信候補")
    ws.append_row(HEADERS_JP)
    for row in rows:
        ws.append_row([row.get(f, "") for f in FIELDS])
    print(f"  {len(rows)}件 書き込み完了")
    return ws


def notify_teams(sheet_url, count):
    body = {
        "text": (
            f"【選定マン】レビューメール候補 {count}件 が準備できました。\n\n"
            f"不要な行を削除して確認してください。\n{sheet_url}\n\n"
            f"承認後、送信マンに「送って」と指示してください。"
        )
    }
    resp = requests.post(TEAMS_WEBHOOK_URL, json=body, timeout=15)
    if resp.status_code in (200, 202):
        print("  Teams通知送信完了")
    else:
        print(f"  Teams通知失敗: {resp.status_code} {resp.text[:200]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=CSV_PATH)
    args = p.parse_args()

    if not os.path.exists(args.csv):
        print(f"CSVが見つかりません: {args.csv}")
        return

    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("候補がありません。通知をスキップします。")
        return

    print(f"=== 選定マン ===")
    print(f"候補 {len(rows)}件 をGoogle Sheetsに書き込み中...")
    _, spreadsheet = get_sheet()
    write_candidates_to_sheet(spreadsheet, rows)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"  URL: {sheet_url}")

    print("Teamsに通知中...")
    notify_teams(sheet_url, len(rows))
    print("完了")


if __name__ == "__main__":
    main()
