"""
create_exhibition_schedule_notion.py

博覧会スケジュールをNotionデータベースとして作成するツール。
指定したNotionページの下にデータベースを作成し、タスクを登録する。

Usage:
    python tools/create_exhibition_schedule_notion.py --parent-id <PAGE_ID>

Output:
    - Notion Database URL
"""

import os
import sys
import argparse
import requests
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

KAZUKI_USER_ID = "2fbd872b-594c-810d-82e9-00023406983d"

SCHEDULE = [
    {"task": "부스 디자인 확인",        "deadline": "2026-04-06"},
    {"task": "카탈로그 최종 확인",       "deadline": "2026-04-10"},
    {"task": "일본판 명함 확인",         "deadline": "2026-04-10"},
    {"task": "웹사이트 디자인 확인",     "deadline": "2026-04-15"},
    {"task": "당일 복장 체크",           "deadline": "2026-04-15"},
    {"task": "참가 기업 리스트 확인",    "deadline": "2026-04-17"},
    {"task": "🎉 박람회 당일",           "deadline": "2026-06-24"},
]


def create_database(parent_id: str) -> dict:
    url = "https://api.notion.com/v1/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "title": [{"type": "text", "text": {"content": "박람회 스케줄 2026"}}],
        "icon": {"type": "emoji", "emoji": "📅"},
        "properties": {
            "Task": {"title": {}},
            "Assigned at": {"date": {}},
            "Assignee": {"people": {}},
            "Priority": {
                "select": {
                    "options": [
                        {"name": "High", "color": "red"},
                        {"name": "Medium", "color": "yellow"},
                        {"name": "Low", "color": "gray"},
                    ]
                }
            },
            "Deadline": {"date": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Not Started", "color": "gray"},
                        {"name": "In Progress", "color": "blue"},
                        {"name": "Done", "color": "green"},
                    ]
                }
            },
            "Tag assigner": {"rich_text": {}},
        },
        "views": [
            {"type": "calendar", "name": "캘린더"},
            {"type": "table", "name": "테이블"},
        ],
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    res.raise_for_status()
    return res.json()


def add_page(db_id: str, item: dict) -> dict:
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Task": {"title": [{"text": {"content": item["task"]}}]},
            "Deadline": {"date": {"start": item["deadline"]}},
            "Assignee": {"people": [{"object": "user", "id": KAZUKI_USER_ID}]},
            "Status": {"select": {"name": "Not Started"}},
        },
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    res.raise_for_status()
    return res.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-id", required=True, help="Notion parent page ID")
    args = parser.parse_args()

    print(f"📅 Notion 데이터베이스 생성 중...")
    db = create_database(args.parent_id)
    db_id = db["id"]
    db_url = db.get("url", f"https://www.notion.so/{db_id.replace('-', '')}")
    print(f"✅ データベース作成完了: {db_url}")

    print(f"\n📝 タスク登録中...")
    for item in SCHEDULE:
        add_page(db_id, item)
        print(f"  ✓ {item['task']} ({item['deadline']})")

    print(f"\n🎉 完了！")
    print(f"URL: {db_url}")


if __name__ == "__main__":
    main()
