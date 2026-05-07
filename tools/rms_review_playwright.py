#!/usr/bin/env python3
"""
楽天RMS「楽天あんしんメルアド簡易送信」経由でレビュー依頼メールを送信。

Usage:
  python tools/rms_review_playwright.py --input .tmp/approved_review_emails.csv --dry-run
  python tools/rms_review_playwright.py --input .tmp/approved_review_emails.csv
  python tools/rms_review_playwright.py --input .tmp/approved_review_emails.csv --headless

CSV columns: order_number, email, name, item_name, shop_name, review_link

ログイン構成:
  Step1 (glogin.rms.rakuten.co.jp): login_id=lfinger11 / passwd=Orbiters4040
  Step2 (login.account.rakuten.com SSO): username=mj.lee@orbiters.co.kr / password=Orbiters@1010

注意:
  - 送信先は @fw.rakuten.ne.jp / @pc.fw.rakuten.ne.jp のみ
  - 送信履歴はCC(k.yamaguchi@orbiters.co.kr等)に届くメールで確認
  - 1件ずつ送信
"""
import argparse
import csv
import json
import os
import sys
import time

# Windows Korean locale fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SENT_LOG_PATH = "logs/sent_orders.json"

# RMS ログイン情報
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


def load_sent(path: str) -> set:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(path: str, sent_set: set) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(sent_set), f, ensure_ascii=False, indent=2)


def do_login(page):
    """フルRMSログインフロー（5ステップ）"""
    # Step 1: glogin.rms.rakuten.co.jp のフォーム
    print("  Step1: RMSログインフォーム...")
    page.goto("https://glogin.rms.rakuten.co.jp", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    page.fill('#rlogin-username-ja', RMS_LOGIN_ID)
    page.fill('#rlogin-password-ja', RMS_LOGIN_PASS)
    page.click("button.rf-button-primary")
    time.sleep(4)

    # Step 2: Rakuten Account SSO
    print("  Step2: Rakuten Account SSO...")
    page.fill('input[name="username"]', SSO_USERNAME)
    page.press('input[name="username"]', "Enter")
    time.sleep(3)
    page.locator('input[name="password"]').click()
    page.keyboard.type(SSO_PASSWORD)
    page.keyboard.press("Enter")
    page.wait_for_url("https://glogin.rms.rakuten.co.jp/**", timeout=30000)
    time.sleep(2)

    # Step 3: 通知ページの「次へ」をクリック（SSO再認証）
    print("  Step3: 通知ページ「次へ」...")
    page.locator("button.rf-button-primary").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    time.sleep(3)

    # Step 4: R-Loginダッシュボードの「ＲＭＳ」リンクをクリック
    print("  Step4: RMSリンクをクリック...")
    page.click('a[href*="mainmenu.rms.rakuten.co.jp"]')
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    time.sleep(2)

    # Step 5: コンプライアンス確認 + 案内ページ処理
    print("  Step5: コンプライアンス確認...")
    # 確認ボタン（上記を遵守...）
    confirm = page.locator("button, input[type=submit]").first
    confirm.click()
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2)

    # チェックボックスがあれば確認
    checkbox = page.locator("input[type=checkbox][name=confirm]")
    if checkbox.count() > 0:
        checkbox.click()
        time.sleep(0.5)
        proceed_btn = page.locator("button, input[type=submit]")
        for btn in proceed_btn.all():
            text = (btn.text_content() or btn.get_attribute("value") or "").strip()
            if "RMS" in text or "進む" in text:
                btn.click()
                break
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        time.sleep(2)

    print(f"  ログイン完了: {page.url}")


def send_review_mail(page, order_number: str, to_email: str, customer_name: str,
                     item_name: str, shop_name: str, review_link: str, dry_run: bool = False) -> bool:
    """楽天あんしんメルアド簡易送信で1件送信"""
    body = BODY_TEMPLATE.format(
        customer_name=customer_name,
        item_name=item_name,
        shop_name=shop_name,
        review_link=review_link,
    )

    if dry_run:
        print(f"    [DRY RUN] To: {to_email}")
        print(f"    件名: {SUBJECT}")
        print(f"    本文先頭: {body[:80].strip()}...")
        return True

    # 送信ページを開く
    page.goto("https://message.rms.rakuten.co.jp/rmsgsend/?app=edit",
              wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)

    # セッション切れチェック
    if "login" in page.url.lower() or "glogin" in page.url.lower():
        print("    セッション切れ。再ログイン不要（呼び出し元でハンドル）")
        return False

    # フォーム入力
    page.fill('#inp_subject', SUBJECT)
    page.fill('#inp_to_address', to_email)
    page.fill('#inp_mail_body', body)
    time.sleep(0.5)

    # 送信ボタン
    page.click('#send_button')
    time.sleep(3)

    # 送信確認ダイアログ or リダイレクト
    current_url = page.url
    page_text = page.inner_text("body")

    if ("受付完了" in page_text or "送信しました" in page_text or "送信完了" in page_text
            or "app=list" in current_url
            or (current_url.endswith("/rmsgsend/") and "受付" in page_text)):
        print(f"    送信完了")
        return True
    elif "確認" in page_text and ("はい" in page_text or "OK" in page_text):
        # 確認ダイアログが出た場合
        confirm_btn = page.locator("button, input[type=submit]")
        for btn in confirm_btn.all():
            text = (btn.text_content() or btn.get_attribute("value") or "")
            if "送信" in text or "はい" in text or "OK" in text:
                btn.click()
                time.sleep(3)
                break
        page_text2 = page.inner_text("body")
        if "送信しました" in page_text2 or "app=list" in page.url:
            print(f"    ✓ 送信完了（確認後）")
            return True

    # スクリーンショットで確認
    ss_path = f".tmp/rms_send_{order_number}.png"
    page.screenshot(path=ss_path)
    print(f"    送信結果不明。{ss_path} で確認してください")
    print(f"    URL: {page.url}")
    return False


def run(input_csv: str, dry_run: bool = False, headless: bool = False):
    from playwright.sync_api import sync_playwright

    with open(input_csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSVが空です。")
        return

    sent_set = load_sent(SENT_LOG_PATH)
    results = {"sent": 0, "skipped": 0, "error": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        print("=== RMSログイン ===")
        do_login(page)

        print("\n=== メール送信開始 ===")
        for row in rows:
            order_number = (row.get("order_number") or "").strip()
            to_email = (row.get("email") or "").strip()
            customer_name = row.get("name") or "お客様"
            item_name = row.get("item_name") or "ご購入商品"
            shop_name = row.get("shop_name") or ""
            review_link = row.get("review_link") or ""

            if not order_number:
                print("  注文番号なし → スキップ")
                results["skipped"] += 1
                continue

            if order_number in sent_set:
                print(f"  {order_number} → 送信済みスキップ")
                results["skipped"] += 1
                continue

            if not to_email:
                print(f"  {order_number} → メールアドレスなし → スキップ")
                results["skipped"] += 1
                continue

            # 楽天あんしんメルアドのみ受付チェック
            if not (to_email.endswith("@fw.rakuten.ne.jp") or to_email.endswith("@pc.fw.rakuten.ne.jp")):
                print(f"  {order_number} → 楽天アドレス以外は送信不可: {to_email[:30]} → スキップ")
                results["skipped"] += 1
                continue

            print(f"  {order_number} / {customer_name}")
            success = send_review_mail(
                page, order_number, to_email, customer_name,
                item_name, shop_name, review_link, dry_run=dry_run
            )

            if success:
                results["sent"] += 1
                if not dry_run:
                    sent_set.add(order_number)
                    save_sent(SENT_LOG_PATH, sent_set)
            else:
                results["error"] += 1

            time.sleep(2)

        browser.close()

    print(f"\n完了: 送信={results['sent']}, スキップ={results['skipped']}, エラー={results['error']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="承認済みCSV")
    p.add_argument("--dry-run", action="store_true", help="メール内容表示のみ（送信しない）")
    p.add_argument("--headless", action="store_true", help="ヘッドレスモード")
    args = p.parse_args()
    run(input_csv=args.input, dry_run=args.dry_run, headless=args.headless)


if __name__ == "__main__":
    main()
