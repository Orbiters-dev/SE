#!/usr/bin/env python3
"""
前日の楽天注文件数・売上をTeams RAKUTENチャンネルに送信するツール。

Usage:
    python tools/rakuten_order_report.py                  # 前日のレポート送信
    python tools/rakuten_order_report.py --date 2026-03-11  # 特定日のレポート
    python tools/rakuten_order_report.py --dry-run         # データ取得のみ（送信しない）
"""
import argparse
import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from rakuten_rms_client import RakutenRMSClient

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

RAKUTEN_WEBHOOK = os.getenv("TEAMS_RAKUTEN_WEBHOOK_URL")
CONFIG_PATH     = str(Path(__file__).parent.parent / "credentials" / "rakuten_rms_config.json")


def post_to_teams(text: str) -> bool:
    if not RAKUTEN_WEBHOOK:
        logger.error("TEAMS_RAKUTEN_WEBHOOK_URL が .env に未設定です")
        return False
    try:
        import json as _json
        resp = requests.post(
            RAKUTEN_WEBHOOK,
            data=_json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        if resp.status_code in (200, 202):
            logger.info("Teamsへの送信成功")
            return True
        else:
            logger.error(f"Teams送信失敗: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Teams送信エラー: {e}")
        return False


def _rms_post(path: str, body: dict) -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    auth = cfg["auth"]["value"]
    resp = requests.post(
        f"https://api.rms.rakuten.co.jp{path}",
        headers={
            "Authorization": auth,
            "Content-Type": "application/json;charset=UTF-8",
        },
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_orders(target_date: datetime) -> list:
    start = target_date.strftime("%Y-%m-%dT00:00:00+0900")
    end   = target_date.strftime("%Y-%m-%dT23:59:59+0900")
    logger.info(f"注文検索: {start} 〜 {end}")

    # Step 1: searchOrder → orderNumberList
    all_numbers = []
    page = 1
    while True:
        data = _rms_post("/es/2.0/order/searchOrder", {
            "dateType": 1,
            "startDatetime": start,
            "endDatetime": end,
            "PaginationRequestModel": {"requestRecordsAmount": 1000, "requestPage": page},
        })
        numbers = data.get("orderNumberList") or []
        all_numbers.extend(numbers)
        pagination = data.get("PaginationResponseModel") or {}
        total_pages = pagination.get("totalPages", 1) or 1
        logger.info(f"  ページ {page}/{total_pages}: {len(numbers)} 件")
        if page >= total_pages:
            break
        page += 1

    logger.info(f"注文番号合計: {len(all_numbers)} 件")
    if not all_numbers:
        return []

    # Step 2: getOrder → full order details (max 100 per request)
    orders = []
    chunk_size = 100
    for i in range(0, len(all_numbers), chunk_size):
        chunk = all_numbers[i:i + chunk_size]
        data = _rms_post("/es/2.0/order/getOrder", {
            "orderNumberList": chunk,
            "version": 8,
        })
        order_list = data.get("OrderModelList") or []
        orders.extend(order_list)
        logger.info(f"  詳細取得: {len(order_list)} 件")

    logger.info(f"注文詳細合計: {len(orders)} 件")
    return orders


def calc_summary(orders: list) -> dict:
    count = len(orders)
    total_sales = 0
    for o in orders:
        price = o.get("goodsPrice") or o.get("totalPrice") or 0
        try:
            total_sales += int(price)
        except (TypeError, ValueError):
            pass
    return {"count": count, "sales": total_sales}


def build_message(target_date: datetime, summary: dict) -> str:
    date_str  = target_date.strftime("%Y/%m/%d")
    weekday   = ["月", "火", "水", "木", "金", "土", "日"][target_date.weekday()]
    count     = summary["count"]
    sales     = summary["sales"]
    return (
        f"📦 楽天 注文日報 [{date_str}（{weekday}）]\n"
        f"注文件数: {count} 件\n"
        f"売上合計: ¥{sales:,}"
    )


def main():
    p = argparse.ArgumentParser(description="楽天 前日注文報告 → Teams")
    p.add_argument("--date", help="対象日 (YYYY-MM-DD)。未指定=前日")
    p.add_argument("--dry-run", action="store_true", help="取得のみ、送信しない")
    p.add_argument("--config", default=CONFIG_PATH, help="RMS設定ファイルパス")
    args = p.parse_args()

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target = datetime.now() - timedelta(days=1)

    orders  = fetch_orders(target)
    summary = calc_summary(orders)

    logger.info(f"注文件数: {summary['count']} / 売上: ¥{summary['sales']:,}")

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    message = build_message(target, summary)
    post_to_teams(message)


if __name__ == "__main__":
    main()
