#!/usr/bin/env python3
"""
Fetch shipped orders from Rakuten RMS, send review-request emails via Rakuten SMTP relay.

Usage:
  python tools/rakuten_review_workflow.py --dry-run
  python tools/rakuten_review_workflow.py --days 14
  python tools/rakuten_review_workflow.py --export            # 候補リストをCSVに出力（送信しない）
  python tools/rakuten_review_workflow.py --input-csv .tmp/pending.csv  # 承認済みCSVから送信
"""
import argparse
import csv
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Windows Korean locale fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SENT_LOG_PATH = "logs/sent_orders.json"


def load_sent(path: str) -> set:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(path: str, sent_set: set) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(sent_set), f, ensure_ascii=False, indent=2)
from rakuten_rms_client import RakutenRMSClient
from send_rakuten_review_emails import create_message_html, build_review_link
from track_delivery import check_delivered_with_date, get_tracking_info

JST = timezone(timedelta(hours=9))


# RMS order progress codes: 100=注文確認待ち, 200=楽天処理中, 300=発送待ち, 400=変更確定待ち, 500=発送済, 600=支払手続き中, 700=支払済
SHIPPED_PROGRESS = [500, 600, 700]


def extract_order_info(order: dict, shop_id: str) -> dict:
    """Pull relevant fields out of an RMS getOrder (version=3) response object."""
    # RMS API v2 version=3 uses PascalCase keys
    packages = order.get("PackageModelList") or []
    item = {}
    if packages:
        items = packages[0].get("ItemModelList") or []
        if items:
            item = items[0]

    orderer = order.get("OrdererModel") or {}
    email = orderer.get("emailAddress", "")
    family = orderer.get("familyName", "")
    first = orderer.get("firstName", "")
    name = (family + first).strip() or "お客様"

    item_id = str(item.get("itemId") or item.get("manageNumber") or "")
    item_name = item.get("itemName") or "ご購入商品"

    # Check if customer opted in to write a review
    opted_in = False
    for pkg in packages:
        for it in (pkg.get("ItemModelList") or []):
            choice = it.get("selectedChoice") or ""
            if "レビューを書く" in choice and "レビューを書かない" not in choice:
                opted_in = True
                break

    return {
        "order_number": order.get("orderNumber", ""),
        "email": email.strip(),
        "name": name,
        "item_id": item_id,
        "item_name": item_name,
        "item_url": "",
        "shop_id": shop_id,
        "opted_in": opted_in,
    }


def send_via_smtp(smtp_cfg: dict, sender: str, to_email: str, subject: str, html_body: str, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"    DRY RUN: would send to {to_email}")
        return True
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(smtp_cfg["user"], smtp_cfg["password"])
        server.sendmail(sender, to_email, msg.as_bytes())
    return True


EXPORT_CSV_PATH = ".tmp/pending_review_emails.csv"
EXPORT_CSV_FIELDS = ["order_number", "order_date", "shipping_date", "delivery_date", "email", "name", "item_name", "shop_name", "review_link"]


def build_candidate_list(client, args):
    """RMSから送信候補を取得して返す（送信はしない）"""
    shop_id = client.cfg.get("shop_id", "")
    shop_name = client.cfg.get("shop_name", "")

    print(f"Fetching shipped orders (last {args.days} days)...")
    orders = client.list_orders(days=args.days, order_progress=SHIPPED_PROGRESS)
    print(f"Found {len(orders)} orders")

    cutoff = datetime.now(JST) - timedelta(days=args.min_ship_days)
    sent_set = load_sent(SENT_LOG_PATH)
    candidates = []

    for o in orders:
        order_number = o.get("orderNumber", "")

        if order_number in sent_set:
            print(f"  Skipping {order_number} (already sent)")
            continue

        shipped_str = o.get("shippingCmplRptDatetime") or ""
        if shipped_str:
            try:
                if datetime.fromisoformat(shipped_str) > cutoff:
                    print(f"  Skipping {order_number} (shipped {shipped_str[:10]}, waiting {args.min_ship_days}d)")
                    continue
            except ValueError:
                pass

        tracking_list = get_tracking_info(o)
        delivery_date = ""
        if tracking_list:
            t = tracking_list[0]
            delivered, delivery_date = check_delivered_with_date(t["carrier_code"], t["tracking_number"])
            delivery_date = delivery_date or ""
            if delivered is False:
                print(f"  Skipping {order_number} (not yet delivered, tracking={t['tracking_number']})")
                continue
            elif delivered is None:
                print(f"  Skipping {order_number} (tracking check failed, tracking={t['tracking_number']})")
                continue
        else:
            print(f"  Skipping {order_number} (no tracking info)")
            continue

        info = extract_order_info(o, shop_id)
        if not info["email"]:
            print(f"  Skipping {order_number} (no email)")
            continue
        if not info["opted_in"]:
            print(f"  Skipping {order_number} (did not opt in to review)")
            continue

        order_date = (o.get("orderDatetime") or o.get("orderDate") or "")[:10]
        shipping_date = (shipped_str or "")[:10]

        review_link = build_review_link(info["shop_id"], info["item_id"], info["item_url"])
        candidates.append({
            "order_number": order_number,
            "order_date": order_date,
            "shipping_date": shipping_date,
            "delivery_date": delivery_date,
            "email": info["email"],
            "name": info["name"],
            "item_name": info["item_name"],
            "shop_name": shop_name,
            "review_link": review_link,
        })
        print(f"  Candidate: {info['name']} / {info['item_name']} ({order_number})")

    return candidates


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="credentials/rakuten_rms_config.json")
    p.add_argument("--days", type=int, default=30, help="Search orders from last N days")
    p.add_argument("--min-ship-days", type=int, default=3, help="Only send to orders shipped at least N days ago (default: 3)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export", action="store_true", help="候補リストをCSVに出力して終了（送信しない）")
    p.add_argument("--export-path", default=EXPORT_CSV_PATH, help="出力先CSVパス")
    p.add_argument("--input-csv", default=None, help="承認済みCSVから送信（RMSを参照しない）")
    p.add_argument("--from", dest="from_email", default=os.getenv("RAKUTEN_FROM_EMAIL") or None)
    p.add_argument("--subject", default="【お願い】ご購入商品のご感想をお聞かせください！")
    args = p.parse_args()

    client = RakutenRMSClient(args.config)
    smtp_cfg = client.cfg.get("smtp") or {}

    if not smtp_cfg.get("host"):
        raise ValueError("smtp config missing in rakuten_rms_config.json")

    # --- モード1: 候補リストをCSVに出力 ---
    if args.export:
        candidates = build_candidate_list(client, args)
        if not candidates:
            print("送信候補がありません。")
            return
        os.makedirs(os.path.dirname(args.export_path), exist_ok=True)
        with open(args.export_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=EXPORT_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(candidates)
        print(f"\n候補 {len(candidates)} 件を {args.export_path} に出力しました。")
        print("不要な行を削除してから --input-csv で送信してください。")
        return

    sender = args.from_email or client.cfg.get("from_email")
    if not sender:
        sender = input("Send as (From) email: ").strip()

    # --- モード2: 承認済みCSVから送信 ---
    if args.input_csv:
        sent_set = load_sent(SENT_LOG_PATH)
        sent = 0
        skipped = 0
        with open(args.input_csv, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                order_number = row.get("order_number", "")
                to_email = row.get("email", "").strip()
                if not to_email:
                    continue
                if order_number in sent_set:
                    print(f"  Skipping {order_number} (already sent)")
                    skipped += 1
                    continue
                html = create_message_html(
                    row.get("name") or "お客様",
                    row.get("item_name") or "ご購入商品",
                    row.get("review_link") or "",
                    shop_name=row.get("shop_name") or None,
                )
                print(f"  {'[DRY]' if args.dry_run else 'Sending'} -> {to_email} ({order_number})")
                try:
                    send_via_smtp(smtp_cfg, sender, to_email, args.subject, html, dry_run=args.dry_run)
                    sent += 1
                    if not args.dry_run:
                        print(f"    Sent OK")
                        sent_set.add(order_number)
                        save_sent(SENT_LOG_PATH, sent_set)
                except Exception as e:
                    print(f"    ERROR: {e}")
                    skipped += 1
        print(f"\nDone. sent={sent}, skipped={skipped}")
        return

    # --- モード3: 従来の自動送信 ---
    candidates = build_candidate_list(client, args)
    if not candidates:
        print("No orders to process.")
        return

    sent_set = load_sent(SENT_LOG_PATH)
    sent = 0
    skipped = 0
    for c in candidates:
        html = create_message_html(c["name"], c["item_name"], c["review_link"], shop_name=c["shop_name"])
        print(f"  {'[DRY]' if args.dry_run else 'Sending'} -> {c['email']} ({c['order_number']})")
        try:
            send_via_smtp(smtp_cfg, sender, c["email"], args.subject, html, dry_run=args.dry_run)
            sent += 1
            if not args.dry_run:
                print(f"    Sent OK")
                sent_set.add(c["order_number"])
                save_sent(SENT_LOG_PATH, sent_set)
        except Exception as e:
            print(f"    ERROR: {e}")
            skipped += 1

    print(f"\nDone. sent={sent}, skipped={skipped}")


if __name__ == "__main__":
    main()