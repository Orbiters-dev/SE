"""
Gmail Send Tool
Sends HTML emails via Gmail API using OAuth2.
Usage:
    python tools/send_gmail.py --to recipient@email.com --subject "Subject" --body "HTML body"
    python tools/send_gmail.py --to recipient@email.com --subject "Subject" --body-file report.html
"""

import argparse
import base64
import json
import os
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

CREDENTIALS_PATH = os.getenv("GMAIL_OAUTH_CREDENTIALS_PATH", "credentials/gmail_oauth_credentials.json")
TOKEN_PATH = os.getenv("ZEZEBAEBAE_GMAIL_TOKEN_PATH", "credentials/zezebaebae_gmail_token.json")
DEFAULT_SENDER = os.getenv("GMAIL_SENDER", "hello@zezebaebae.com")
DEFAULT_RECIPIENT = os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")


def get_gmail_service():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"ERROR: OAuth credentials not found at {CREDENTIALS_PATH}")
                print("Please set up Google OAuth credentials first.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            print(f"\nAuthentication required for {DEFAULT_SENDER}")
            print("A browser window will open - log in with hello@zezebaebae.com\n")
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        try:
            os.chmod(TOKEN_PATH, 0o600)
        except OSError:
            pass  # Windows may not support chmod

    return build("gmail", "v1", credentials=creds)


def send_email(to: str, subject: str, body_html: str, sender: str = DEFAULT_SENDER,
               attachment: str = None) -> dict:
    service = get_gmail_service()

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    if attachment:
        path = Path(attachment)
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    print(f"Email sent successfully!")
    print(f"  From: {sender}")
    print(f"  To:   {to}")
    print(f"  Subject: {subject}")
    print(f"  Message ID: {result.get('id')}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Send email via Gmail API")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help="Recipient email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", help="HTML body content")
    parser.add_argument("--body-file", help="Path to HTML file for body")
    parser.add_argument("--attachment", help="Path to file to attach")
    parser.add_argument("--sender", default=DEFAULT_SENDER, help="Sender email")
    args = parser.parse_args()

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            body = f.read()
    elif args.body:
        body = args.body
    else:
        print("ERROR: Provide --body or --body-file")
        sys.exit(1)

    send_email(to=args.to, subject=args.subject, body_html=body, sender=args.sender,
               attachment=args.attachment)


if __name__ == "__main__":
    main()
