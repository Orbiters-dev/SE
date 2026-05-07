#!/usr/bin/env python3
"""
Bulk send Rakuten review-request emails using Gmail API (OAuth).

Usage:
  python tools/send_rakuten_review_emails.py --input customers.csv --dry-run

CSV columns (header): email,shop_id,item_id,item_name,item_url

Requires: credentials/gmail_oauth_credentials.json (OAuth client) and a writeable token path.
"""
import argparse
import csv
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_credentials(creds_path, token_path):
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"OAuth credentials not found: {creds_path}")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def build_review_link(shop_id, item_id, item_url):
    if item_url:
        return item_url
    # Pattern discovered in repo: https://review.rakuten.co.jp/wd/2_{shop}_{item}_0/
    if shop_id and item_id:
        return f"https://review.rakuten.co.jp/wd/2_{shop_id}_{item_id}_0/?l2-id=item_review_write"
    return ""


def create_message_html(customer_name, item_name, review_link, shop_name=None):
        shop_line = f"<br>ショップ名：{shop_name}" if shop_name else ""
        html = f"""
        <div style="font-family:system-ui,Helvetica,Arial;line-height:1.5;color:#111;">
            <pre style="border-top:1px solid #ddd;border-bottom:1px solid #ddd;padding:8px;">----------------------------------------------------------------------
このメールはお客様の注文に関する大切なメールです。
お取引が完了するまで保存してください。
----------------------------------------------------------------------</pre>
            <p>{customer_name} 様</p>
            <p>実際にお使いいただいたご感想を、よろしければ楽天のレビューにてお聞かせいただけましたら幸いです。</p>
            <p>★だけの評価や、短いコメントでも大歓迎です！<br>お客様からのお声は、今後の商品づくり・サービス向上の大切な参考にさせていただきます。</p>
            <p>お忙しいところ恐れ入りますが、<br>お時間のある際にご協力いただけましたら嬉しいです。</p>

            <p><strong>【購入した商品名】</strong><br>{item_name}{shop_line}</p>
            <p><a href="{review_link}" target="_blank" style="display:inline-block;padding:10px 16px;background:#e60012;color:#fff;text-decoration:none;border-radius:4px;">レビューを書く</a></p>

            <p>商品や発送などに関するご不明な点がございましたら、お気軽にお問い合わせください。<br>
            ■お問い合わせ先→ <a href="mailto:littlefingerusa_2@shop.rakuten.co.jp">littlefingerusa_2@shop.rakuten.co.jp</a><br>
            お支払いに関するお問い合わせは、楽天市場までご連絡ください。<br>
            ■ヘルプ・問い合わせ　<a href="https://ichiba.faq.rakuten.net/">https://ichiba.faq.rakuten.net/</a></p>

            <p>今後ともよろしくお願いいたします。<br>— カスタマーサポート</p>
        </div>
        """
        return html


def send_email(service, sender, to_email, subject, html_body, dry_run=False):
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = {"raw": raw}
    if dry_run:
        print(f"DRY RUN: would send to {to_email} subject={subject}")
        return None
    sent = service.users().messages().send(userId="me", body=body).execute()
    return sent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="CSV file with customers")
    p.add_argument("--credentials", default=os.getenv("GMAIL_OAUTH_CREDENTIALS_PATH", "credentials/gmail_oauth_credentials.json"))
    p.add_argument("--token", default=os.getenv("GMAIL_TOKEN_PATH", "credentials/gmail_token.json"))
    p.add_argument("--from", dest="from_email", default=os.getenv("GORGIAS_EMAIL") or None)
    p.add_argument("--subject", default="【お願い】ご購入商品のご感想をお聞かせください！")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    creds = get_credentials(args.credentials, args.token)
    service = build("gmail", "v1", credentials=creds)

    sender = args.from_email or (creds.id_token.get("email") if hasattr(creds, "id_token") and creds.id_token else None)
    if not sender:
        sender = input("Send as (From) email: ").strip()

    with open(args.input, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            to_email = (row.get("email") or "").strip()
            if not to_email:
                print("skipping row with no email")
                continue
            customer_name = row.get("name") or "お客様"
            item_name = row.get("item_name") or "ご購入商品"
            shop_id = row.get("shop_id")
            item_id = row.get("item_id")
            item_url = row.get("item_url")
            review_link = build_review_link(shop_id, item_id, item_url)
            html = create_message_html(customer_name, item_name, review_link, shop_name=row.get("shop_name"))
            result = send_email(service, sender, to_email, args.subject, html, dry_run=args.dry_run)
            if result:
                print(f"Sent to {to_email}: id={result.get('id')}")


if __name__ == "__main__":
    main()
