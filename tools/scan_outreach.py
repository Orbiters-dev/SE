"""
Scan Gmail sent folders + ManyChat to detect previously contacted creators.
Updates onz_pipeline_creators with contact history to prevent duplicate outreach.

Accounts checked:
  - affiliates@onzenna.com
  - hello@zezebaebae.com
  - ManyChat JP / US (if API key available)

Usage:
    python tools/scan_outreach.py                    # Full scan + update DB
    python tools/scan_outreach.py --dry-run           # Scan only, no DB writes
    python tools/scan_outreach.py --days 90           # Last 90 days only
    python tools/scan_outreach.py --status            # Show current stats
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

import psycopg2

# ── Config ──────────────────────────────────────────────────────────────────

DB_HOST = os.getenv("PG_HOST", "172.31.13.240")
DB_NAME = os.getenv("PG_DB", "export_calculator_db")
DB_USER = os.getenv("PG_USER", "es_db_user")
DB_PASS = os.getenv("PG_PASS", "orbit1234")
# If running locally, use EC2 tunnel or public endpoint
DB_HOST_LOCAL = os.getenv("PG_HOST_LOCAL", "orbitools.orbiters.co.kr")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CACHE_DIR = PROJECT_ROOT / ".tmp" / "outreach_scan"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_CREDENTIALS_PATH = os.getenv(
    "GMAIL_OAUTH_CREDENTIALS_PATH",
    str(CREDENTIALS_DIR / "gmail_oauth_credentials.json"),
)

ACCOUNTS = {
    "onzenna": {
        "email": "affiliates@onzenna.com",
        "token_path": str(CREDENTIALS_DIR / "onzenna_gmail_token.json"),
    },
    "zezebaebae": {
        "email": "hello@zezebaebae.com",
        "token_path": str(CREDENTIALS_DIR / "zezebaebae_gmail_token.json"),
    },
}

EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')


# ── Gmail ───────────────────────────────────────────────────────────────────

def get_gmail_service(account_key: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    acct = ACCOUNTS[account_key]
    token_path = acct["token_path"]
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_PATH, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def scan_sent_emails(account_key: str, days: int = 180) -> dict:
    """Scan sent folder, return {recipient_email: {first_date, last_date, count, account}}."""
    print(f"\n  Scanning {ACCOUNTS[account_key]['email']} (last {days} days)...")

    cache_file = CACHE_DIR / f"sent_{account_key}_{days}d.json"

    # Use cache if fresh (< 1 hour old)
    if cache_file.exists():
        age_h = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age_h < 1:
            print(f"    Using cache ({age_h:.1f}h old)")
            with open(cache_file) as f:
                return json.load(f)

    service = get_gmail_service(account_key)
    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"in:sent after:{after_date}"

    contacts = {}  # email -> {first_date, last_date, count}
    page_token = None
    total_msgs = 0

    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=500, pageToken=page_token
        ).execute()
        messages = resp.get("messages", [])
        if not messages:
            break

        # Batch get headers only (METADATA format is fast)
        for msg_ref in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["To", "Cc", "Bcc", "Date"]
                ).execute()
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                recipients = set()
                for field in ["to", "cc", "bcc"]:
                    if headers.get(field):
                        for email in EMAIL_RE.findall(headers[field].lower()):
                            recipients.add(email)
                msg_date = headers.get("date", "")
                # Parse date loosely
                date_str = ""
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(msg_date)
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = datetime.now().strftime("%Y-%m-%d")

                for email in recipients:
                    if email in contacts:
                        contacts[email]["count"] += 1
                        if date_str < contacts[email]["first_date"]:
                            contacts[email]["first_date"] = date_str
                        if date_str > contacts[email]["last_date"]:
                            contacts[email]["last_date"] = date_str
                    else:
                        contacts[email] = {
                            "first_date": date_str,
                            "last_date": date_str,
                            "count": 1,
                        }
            except Exception as e:
                pass  # Skip errored messages

            total_msgs += 1
            if total_msgs % 200 == 0:
                print(f"    Processed {total_msgs} messages, {len(contacts)} unique recipients...")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"    Done: {total_msgs} messages, {len(contacts)} unique recipients")

    # Cache results
    with open(cache_file, "w") as f:
        json.dump(contacts, f)

    return contacts


# ── DB ──────────────────────────────────────────────────────────────────────

def get_db_connection():
    """Try EC2 internal first, then public endpoint."""
    for host in [DB_HOST, DB_HOST_LOCAL]:
        try:
            conn = psycopg2.connect(
                host=host, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
                connect_timeout=5
            )
            return conn
        except Exception:
            continue
    raise Exception("Cannot connect to PostgreSQL")


def get_creators():
    """Get all creators with their email and handles."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ig_handle, tiktok_handle, email, name,
               first_contacted_at, gmail_total_sent, gmail_accounts
        FROM onz_pipeline_creators
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def update_creators(updates: list, dry_run: bool = False):
    """Bulk update creator contact history.
    updates: [{id, first_contacted_at, last_contacted_at, gmail_total_sent, gmail_accounts}]
    """
    if not updates:
        print("\n  No updates needed.")
        return

    if dry_run:
        print(f"\n  [DRY RUN] Would update {len(updates)} creators:")
        for u in updates[:20]:
            print(f"    ID {u['id']}: sent={u['gmail_total_sent']}, "
                  f"first={u['first_contacted_at']}, accounts={u['gmail_accounts']}")
        if len(updates) > 20:
            print(f"    ... and {len(updates) - 20} more")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    count = 0
    for u in updates:
        cur.execute("""
            UPDATE onz_pipeline_creators
            SET first_contacted_at = COALESCE(%s, first_contacted_at),
                last_contacted_at = COALESCE(%s, last_contacted_at),
                gmail_total_sent = %s,
                gmail_accounts = %s,
                contact_count = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (
            u["first_contacted_at"],
            u["last_contacted_at"],
            u["gmail_total_sent"],
            json.dumps(u["gmail_accounts"]),
            u["gmail_total_sent"],
            u["id"],
        ))
        count += 1
    conn.commit()
    conn.close()
    print(f"\n  Updated {count} creators in DB.")


# ── Main ────────────────────────────────────────────────────────────────────

def run_scan(days: int = 180, dry_run: bool = False):
    print("=" * 60)
    print("  Outreach History Scanner")
    print("=" * 60)

    # 1. Scan Gmail sent folders
    all_sent = {}  # email -> {first_date, last_date, count, accounts: []}
    for acct_key, acct in ACCOUNTS.items():
        try:
            contacts = scan_sent_emails(acct_key, days)
            for email, info in contacts.items():
                if email in all_sent:
                    existing = all_sent[email]
                    existing["count"] += info["count"]
                    if info["first_date"] < existing["first_date"]:
                        existing["first_date"] = info["first_date"]
                    if info["last_date"] > existing["last_date"]:
                        existing["last_date"] = info["last_date"]
                    if acct["email"] not in existing["accounts"]:
                        existing["accounts"].append(acct["email"])
                else:
                    all_sent[email] = {
                        "first_date": info["first_date"],
                        "last_date": info["last_date"],
                        "count": info["count"],
                        "accounts": [acct["email"]],
                    }
        except Exception as e:
            print(f"    Error scanning {acct_key}: {e}")

    print(f"\n  Total unique recipients across all accounts: {len(all_sent)}")

    # 2. Get creators from DB
    print("\n  Loading creators from DB...")
    creators = get_creators()
    print(f"    {len(creators)} creators loaded")

    # 3. Build email -> creator mapping
    email_to_creators = defaultdict(list)
    for c in creators:
        if c["email"] and "@discovered." not in c["email"]:
            email_to_creators[c["email"].lower()].append(c)

    # 4. Match and prepare updates
    updates = []
    matched_emails = set()
    for email, sent_info in all_sent.items():
        if email in email_to_creators:
            for creator in email_to_creators[email]:
                matched_emails.add(email)
                updates.append({
                    "id": creator["id"],
                    "first_contacted_at": sent_info["first_date"],
                    "last_contacted_at": sent_info["last_date"],
                    "gmail_total_sent": sent_info["count"],
                    "gmail_accounts": sent_info["accounts"],
                })

    print(f"\n  Matched {len(matched_emails)} emails → {len(updates)} creator records")

    # 5. Update DB
    update_creators(updates, dry_run=dry_run)

    # 6. Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Gmail recipients scanned:  {len(all_sent)}")
    print(f"  Creators in pool:          {len(creators)}")
    print(f"  Creators with real email:  {len(email_to_creators)}")
    print(f"  Matched (previously sent): {len(updates)}")
    print(f"  Dry run:                   {dry_run}")
    print()

    # Save report
    report = {
        "scan_date": datetime.now().isoformat(),
        "days_scanned": days,
        "total_recipients": len(all_sent),
        "total_creators": len(creators),
        "matched_updates": len(updates),
        "dry_run": dry_run,
        "matched_emails": list(matched_emails)[:100],
    }
    report_path = CACHE_DIR / f"scan_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved: {report_path}")

    return report


def show_status():
    """Show current outreach coverage stats."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE gmail_total_sent > 0")
    contacted = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE is_manychat_contact = true")
    manychat = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE first_contacted_at IS NOT NULL")
    has_contact_date = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM onz_pipeline_creators
        WHERE email IS NOT NULL AND email != '' AND email NOT LIKE '%@discovered.%'
    """)
    has_real_email = cur.fetchone()[0]

    conn.close()

    print("\n=== Outreach Coverage ===\n")
    print(f"  Total creators:          {total}")
    print(f"  With real email:         {has_real_email}")
    print(f"  Gmail contacted:         {contacted}")
    print(f"  ManyChat contact:        {manychat}")
    print(f"  Has contact date:        {has_contact_date}")
    print(f"  Never contacted:         {total - has_contact_date}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan Gmail/ManyChat outreach history")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no DB writes")
    parser.add_argument("--days", type=int, default=180, help="Days to scan back (default: 180)")
    parser.add_argument("--status", action="store_true", help="Show current stats")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        run_scan(days=args.days, dry_run=args.dry_run)
