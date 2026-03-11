"""
Gmail Send & Read Tool
Sends HTML emails and searches inbox via Gmail API using OAuth2.
Usage:
    python tools/send_gmail.py --to recipient@email.com --subject "Subject" --body "HTML body"
    python tools/send_gmail.py --to recipient@email.com --subject "Subject" --body-file report.html
    python tools/send_gmail.py --search "subject:[Amazon PPC] from:user@example.com newer_than:1d"
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

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

CREDENTIALS_PATH = os.getenv("GMAIL_OAUTH_CREDENTIALS_PATH", "credentials/gmail_oauth_credentials.json")
TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH",
                        os.getenv("ZEZEBAEBAE_GMAIL_TOKEN_PATH", "credentials/gmail_token.json"))
DEFAULT_SENDER = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")
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
            print(f"A browser window will open - log in with {DEFAULT_SENDER}\n")
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
               attachment: str = None, cc: str = None) -> dict:
    service = get_gmail_service()

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc

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


def search_emails(query: str, max_results: int = 10) -> list:
    """Search Gmail inbox and return matching messages with id, subject, snippet, body text."""
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return []

    output = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract plain text body
        body_text = ""
        payload = msg.get("payload", {})
        parts = payload.get("parts", [])
        if not parts and payload.get("body", {}).get("data"):
            body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        else:
            for part in parts:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
            if not body_text:
                for part in parts:
                    if part.get("mimeType") == "multipart/alternative":
                        for sub in part.get("parts", []):
                            if sub.get("mimeType") == "text/plain" and sub.get("body", {}).get("data"):
                                body_text = base64.urlsafe_b64decode(sub["body"]["data"]).decode("utf-8", errors="replace")
                                break

        output.append({
            "id": msg_ref["id"],
            "threadId": msg.get("threadId"),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body_text,
        })

    return output


def main():
    parser = argparse.ArgumentParser(description="Send/Search email via Gmail API")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help="Recipient email")
    parser.add_argument("--subject", help="Email subject (required for send)")
    parser.add_argument("--body", help="HTML body content")
    parser.add_argument("--body-file", help="Path to HTML file for body")
    parser.add_argument("--attachment", help="Path to file to attach")
    parser.add_argument("--sender", default=DEFAULT_SENDER, help="Sender email")
    parser.add_argument("--cc", default=None, help="CC email address")
    parser.add_argument("--search", help="Gmail search query (read mode)")
    parser.add_argument("--max-results", type=int, default=5, help="Max search results")
    args = parser.parse_args()

    # Search mode
    if args.search:
        import io, sys as _sys
        _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
        results = search_emails(args.search, args.max_results)
        if not results:
            print("No messages found.")
        for m in results:
            print(f"\n{'='*60}")
            print(f"  From: {m['from']}")
            print(f"  Subject: {m['subject']}")
            print(f"  Date: {m['date']}")
            snippet = m['snippet'][:200]
            print(f"  Snippet: {snippet}")
            body_preview = m['body'][:300].replace('\n', ' ').strip()
            if body_preview:
                print(f"  Body: {body_preview}")
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Send mode
    if not args.subject:
        print("ERROR: --subject is required for sending")
        sys.exit(1)

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            body = f.read()
    elif args.body:
        body = args.body
    else:
        print("ERROR: Provide --body or --body-file")
        sys.exit(1)

    send_email(to=args.to, subject=args.subject, body_html=body, sender=args.sender,
               attachment=args.attachment, cc=args.cc)


if __name__ == "__main__":
    main()
