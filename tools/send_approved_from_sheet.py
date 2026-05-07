#!/usr/bin/env python3
"""
送信マン: Sheetsの「承認」列が入力済みの行にレビューメールを送信する。

Usage:
  python tools/send_approved_from_sheet.py --sheet 3月全注文
  python tools/send_approved_from_sheet.py --sheet 3月全注文 --dry-run
"""
import argparse
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "17lhDDC8X_54jwqsMa0WBJxCpYZUQUI7MfHRy0YUCk7g"
SERVICE_ACCOUNT_PATH = "credentials/google_service_account.json"
SENT_LOG_PATH = "logs/sent_orders.json"

RMS_LOGIN_ID = "lfinger11"
RMS_LOGIN_PASS = "Orbiters4040"
SSO_USERNAME = "mj.lee@orbiters.co.kr"
SSO_PASSWORD = "Orbiters@1010"

SUBJECT = "【お願い】ご購入商品のご感想をお聞かせください！"

BODY_TEMPLATE = """\
{customer_name} 様

この度はご購入いただき、誠にありがとうございます。

実際にお使いいただいたご感想を、よろしければ楽天のレビューにてお聞かせいただけましたら幸いです。

※だけの評価や、短いコメントでも大歓迎です！
お客様からのお声は、今後の商品づくり・サービス向上の大切な参考にさせていただきます。

お忙しいところ恐れ入りますが、お時間のある際にご協力いただけましたら嬉しいです。

【購入した商品名】
{item_name}
ショップ名：{shop_name}

レビューはこちらから
{review_link}

商品や発送などに関するご不明な点がございましたら、お気軽にお問い合わせください。
お問い合わせ先: littlefingerusa_2@shop.rakuten.co.jp

今後ともよろしくお願いいたします。
カスタマーサポート"""


def load_sent():
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(sent_set):
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(sent_set), f, ensure_ascii=False, indent=2)


def get_approved_rows(sheet_title):
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(sheet_title)
    all_values = ws.get_all_values()
    if not all_values:
        return [], ws

    header = all_values[0]
    col = {h: i for i, h in enumerate(header)}

    sent_set = load_sent()
    approved = []
    for i, row in enumerate(all_values[1:], start=2):
        def get(name):
            idx = col.get(name)
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        order_number = get("注文番号")
        approve = get("承認")
        status = get("レビュー送信状況")
        email = get("メール")

        if not approve:
            continue
        if status == "送信済み" or order_number in sent_set:
            print(f"  {order_number} → 送信済みスキップ")
            continue
        if not email or not (email.endswith("@fw.rakuten.ne.jp") or email.endswith("@pc.fw.rakuten.ne.jp")):
            print(f"  {order_number} → 楽天アドレス以外スキップ: {email[:30]}")
            continue

        approved.append({
            "row_index": i,
            "order_number": order_number,
            "email": email,
            "name": get("顧客名") or "お客様",
            "item_name": get("商品名") or "ご購入商品",
            "shop_name": get("ショップ名") or "LittleFingerUSA",
            "review_link": get("レビューリンク") or "",
        })

    return approved, ws


def update_sheet_status(ws, row_index, header):
    col = {h: i for i, h in enumerate(header)}
    status_col = col.get("レビュー送信状況")
    if status_col is not None:
        from gspread.utils import rowcol_to_a1
        cell = rowcol_to_a1(row_index, status_col + 1)
        ws.update(cell, "送信済み")


def do_login(page):
    print("  Step1: RMSログイン...")
    page.goto("https://glogin.rms.rakuten.co.jp", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    page.fill("#rlogin-username-ja", RMS_LOGIN_ID)
    page.fill("#rlogin-password-ja", RMS_LOGIN_PASS)
    page.click("button.rf-button-primary")
    time.sleep(4)

    print("  Step2: SSO...")
    page.fill('input[name="username"]', SSO_USERNAME)
    page.press('input[name="username"]', "Enter")
    time.sleep(3)
    page.locator('input[name="password"]').click()
    page.keyboard.type(SSO_PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_url("https://glogin.rms.rakuten.co.jp/**", timeout=30000)
    time.sleep(2)

    print("  Step3: 通知ページ...")
    page.locator("button.rf-button-primary").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    time.sleep(3)

    print("  Step4: RMSリンク...")
    page.click('a[href*="mainmenu.rms.rakuten.co.jp"]')
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    time.sleep(2)

    print("  Step5: コンプライアンス確認...")
    page.locator("button, input[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2)

    checkbox = page.locator("input[type=checkbox][name=confirm]")
    if checkbox.count() > 0:
        checkbox.click()
        time.sleep(0.5)
        for btn in page.locator("button, input[type=submit]").all():
            text = (btn.text_content() or btn.get_attribute("value") or "").strip()
            if "RMS" in text or "進む" in text:
                btn.click()
                break
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        time.sleep(2)

    print(f"  ログイン完了: {page.url}")


def send_one(page, row, dry_run):
    body = BODY_TEMPLATE.format(
        customer_name=row["name"],
        item_name=row["item_name"],
        shop_name=row["shop_name"],
        review_link=row["review_link"],
    )
    if dry_run:
        print(f"    [DRY RUN] → {row['email']}")
        return True

    page.goto("https://message.rms.rakuten.co.jp/rmsgsend/?app=edit",
              wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)

    if "login" in page.url.lower() or "glogin" in page.url.lower():
        return False

    page.fill("#inp_subject", SUBJECT)
    page.fill("#inp_to_address", row["email"])
    page.fill("#inp_mail_body", body)
    time.sleep(0.5)
    page.click("#send_button")
    time.sleep(3)

    page_text = page.inner_text("body")
    current_url = page.url

    if ("受付完了" in page_text or "送信しました" in page_text or "送信完了" in page_text
            or "app=list" in current_url
            or (current_url.endswith("/rmsgsend/") and "受付" in page_text)):
        print(f"    送信完了")
        return True
    elif "確認" in page_text and ("はい" in page_text or "OK" in page_text):
        for btn in page.locator("button, input[type=submit]").all():
            text = (btn.text_content() or btn.get_attribute("value") or "")
            if "送信" in text or "はい" in text or "OK" in text:
                btn.click()
                time.sleep(3)
                break
        if "送信しました" in page.inner_text("body") or "app=list" in page.url:
            print(f"    送信完了（確認後）")
            return True

    ss_path = f".tmp/rms_send_{row['order_number']}.png"
    page.screenshot(path=ss_path)
    print(f"    送信結果不明。{ss_path} を確認してください")
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sheet", required=True, help="シート名（例: 3月全注文）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--headless", action="store_true")
    args = p.parse_args()

    print(f"=== 送信マン: {args.sheet} の承認済み行を処理 ===")
    approved, ws = get_approved_rows(args.sheet)

    if not approved:
        print("承認済みの未送信行がありません。")
        return

    print(f"承認済み: {len(approved)}件")

    sent_set = load_sent()
    header = ws.row_values(1)
    results = {"sent": 0, "skipped": 0, "error": 0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=args.headless)
        page = browser.new_context().new_page()

        print("\n=== RMSログイン ===")
        do_login(page)

        print("\n=== メール送信 ===")
        for row in approved:
            print(f"  {row['order_number']} / {row['name']}")
            success = send_one(page, row, dry_run=args.dry_run)

            if success:
                results["sent"] += 1
                if not args.dry_run:
                    sent_set.add(row["order_number"])
                    save_sent(sent_set)
                    update_sheet_status(ws, row["row_index"], header)
            else:
                results["error"] += 1

            time.sleep(2)

        browser.close()

    print(f"\n完了: 送信={results['sent']}, エラー={results['error']}")


if __name__ == "__main__":
    main()
