#!/usr/bin/env python3
"""
Sync Gmail Sent recipients → gk_gmail_contacts (OrbiTools PostgreSQL)
====================================================================
Scans the Sent folder of both sender accounts and upserts recipients
into gk_gmail_contacts for RAG Email Dedup.

Accounts:
  - affiliates@onzenna.com
  - affiliates@zezebaebae.com

Usage:
    python tools/sync_gmail_sent_to_pg.py                     # Incremental sync (both accounts)
    python tools/sync_gmail_sent_to_pg.py --account onzenna   # Single account
    python tools/sync_gmail_sent_to_pg.py --backfill          # Full backfill (all sent emails)
    python tools/sync_gmail_sent_to_pg.py --dry-run           # Preview without writing
    python tools/sync_gmail_sent_to_pg.py --stats             # Show current stats
"""

import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
sys.path.insert(0, str(DIR))

JEEHOO_ENV = Path("/Volumes/Orbiters/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/Jeehoo/.env")
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass
if not os.getenv("ORBITOOLS_USER") and JEEHOO_ENV.exists():
    for line in JEEHOO_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if not os.getenv(k.strip()):
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "admin")
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

ACCOUNTS = {
    "onzenna": {
        "email": "affiliates@onzenna.com",
        "token_path": str(ROOT / "credentials" / "onzenna_gmail_token.json"),
    },
    "zezebaebae": {
        "email": "affiliates@zezebaebae.com",
        "token_path": str(ROOT / "credentials" / "zezebaebae_gmail_token.json"),
    },
}

STATE_FILE = ROOT / ".tmp" / "gmail_rag" / "sent_sync_state.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BATCH_SIZE = 200  # API upsert batch
GMAIL_PAGE_SIZE = 100  # Gmail list page size

# Exclude our own addresses + test addresses from dedup
EXCLUDE_EMAILS = {
    "affiliates@onzenna.com", "affiliates@zezebaebae.com",
    "hello@zezebaebae.com", "noreply@onzenna.com",
    "william@pathlightai.io",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _orbi_headers():
    creds = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


def orbi_post(path, data, timeout=60):
    url = f"{ORBITOOLS_URL}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers=_orbi_headers())
    resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
    return json.loads(resp.read())


def orbi_get(path, timeout=30):
    url = f"{ORBITOOLS_URL}{path}"
    req = urllib.request.Request(url, headers=_orbi_headers())
    resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
    return json.loads(resp.read())


def get_gmail_service(account_key):
    acct = ACCOUNTS[account_key]
    token_path = acct["token_path"]
    if not os.path.exists(token_path):
        print(f"  [ERROR] Token not found: {token_path}")
        return None
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def extract_emails_from_header(header_value):
    """Extract email addresses from To/Cc/Bcc header."""
    if not header_value:
        return []
    emails = re.findall(r'[\w.+-]+@[\w.-]+\.\w+', header_value.lower())
    return [e for e in emails if e not in EXCLUDE_EMAILS]


# ── Core: Scan Gmail Sent ────────────────────────────────────────────────────
def scan_sent_emails(service, account_key, after_epoch=None, max_results=None):
    """Scan Sent folder, return {email: {name, total_sent, first_date, last_date, last_subject}}."""
    query = "in:sent"
    if after_epoch:
        query += f" after:{after_epoch}"

    contacts = {}  # email → {name, total_sent, first_date, last_date, last_subject}
    page_token = None
    total_scanned = 0

    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=GMAIL_PAGE_SIZE, pageToken=page_token
        ).execute()

        messages = resp.get("messages", [])
        if not messages:
            break

        for msg_meta in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_meta["id"], format="metadata",
                    metadataHeaders=["To", "Cc", "Bcc", "Subject", "Date"]
                ).execute()
            except Exception:
                continue

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            to_emails = extract_emails_from_header(headers.get("To", ""))
            cc_emails = extract_emails_from_header(headers.get("Cc", ""))
            bcc_emails = extract_emails_from_header(headers.get("Bcc", ""))
            all_recipients = to_emails + cc_emails + bcc_emails
            subject = headers.get("Subject", "")
            date_str = headers.get("Date", "")

            # Parse date
            msg_date = None
            try:
                internal_ts = int(msg.get("internalDate", 0)) / 1000
                if internal_ts:
                    msg_date = datetime.fromtimestamp(internal_ts, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                pass

            for email in all_recipients:
                if email not in contacts:
                    contacts[email] = {
                        "total_sent": 0,
                        "first_date": msg_date,
                        "last_date": msg_date,
                        "last_subject": subject[:500],
                    }
                c = contacts[email]
                c["total_sent"] += 1
                if msg_date:
                    if not c["first_date"] or msg_date < c["first_date"]:
                        c["first_date"] = msg_date
                    if not c["last_date"] or msg_date > c["last_date"]:
                        c["last_date"] = msg_date
                        c["last_subject"] = subject[:500]

            total_scanned += 1
            if total_scanned % 200 == 0:
                print(f"    Scanned {total_scanned} messages, {len(contacts)} unique recipients...")

        if max_results and total_scanned >= max_results:
            break

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.2)  # rate limit

    return contacts, total_scanned


def upsert_to_db(contacts, account_key, dry_run=False):
    """Upload contacts to gk_gmail_contacts via API."""
    records = []
    for email, data in contacts.items():
        records.append({
            "email": email,
            "name": "",
            "domain": email.split("@")[1] if "@" in email else "",
            "account": account_key,
            "first_contact_date": data.get("first_date"),
            "last_contact_date": data.get("last_date"),
            "last_subject": data.get("last_subject", ""),
            "total_sent": data.get("total_sent", 0),
            "total_received": 0,
        })

    if dry_run:
        print(f"  [DRY RUN] Would upsert {len(records)} contacts")
        return {"created": 0, "updated": 0, "total": len(records)}

    total_created = 0
    total_updated = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        try:
            result = orbi_post("/api/onzenna/gmail-rag/sync/", {"contacts": batch})
            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            print(f"    Batch {i // BATCH_SIZE + 1}: +{result.get('created', 0)} new, ~{result.get('updated', 0)} updated")
        except Exception as e:
            print(f"    [ERROR] Batch {i // BATCH_SIZE + 1}: {e}")

    return {"created": total_created, "updated": total_updated, "total": len(records)}


# ── Main ──────────────────────────────────────────────────────────────────────
def run_sync(account_filter=None, backfill=False, dry_run=False, max_results=None):
    print(f"\n{'=' * 60}")
    print(f"  Gmail Sent → gk_gmail_contacts Sync")
    print(f"  Mode: {'BACKFILL' if backfill else 'INCREMENTAL'} {'(DRY RUN)' if dry_run else ''}")
    print(f"{'=' * 60}")

    state = load_state()
    accounts_to_sync = [account_filter] if account_filter else list(ACCOUNTS.keys())

    for acct_key in accounts_to_sync:
        acct = ACCOUNTS[acct_key]
        print(f"\n  [{acct_key}] {acct['email']}")

        service = get_gmail_service(acct_key)
        if not service:
            continue

        # Determine start point
        after_epoch = None
        if not backfill:
            last_sync = state.get(f"{acct_key}_last_sync_epoch")
            if last_sync:
                after_epoch = last_sync
                print(f"    Incremental: after epoch {after_epoch}")
            else:
                print(f"    No previous sync → full scan")

        # Scan
        print(f"    Scanning Sent folder...")
        contacts, scanned = scan_sent_emails(service, acct_key, after_epoch, max_results)
        print(f"    Scanned {scanned} messages → {len(contacts)} unique recipients")

        if not contacts:
            print(f"    Nothing new to sync")
            continue

        # Upsert
        result = upsert_to_db(contacts, acct_key, dry_run)
        print(f"    Result: {result['created']} created, {result['updated']} updated")

        # Update state
        if not dry_run:
            state[f"{acct_key}_last_sync_epoch"] = int(datetime.now(timezone.utc).timestamp())
            state[f"{acct_key}_last_sync_contacts"] = len(contacts)
            save_state(state)

    # Summary
    print(f"\n{'=' * 60}")
    try:
        tables = orbi_get("/api/onzenna/tables/")
        total = tables.get("tables", {}).get("gk_gmail_contacts", "?")
        print(f"  gk_gmail_contacts total: {total}")
    except Exception:
        pass
    print(f"{'=' * 60}\n")


def show_stats():
    print(f"\n  Gmail Sent Sync Stats")
    state = load_state()
    for acct_key in ACCOUNTS:
        last = state.get(f"{acct_key}_last_sync_epoch")
        contacts = state.get(f"{acct_key}_last_sync_contacts", 0)
        if last:
            dt = datetime.fromtimestamp(last, tz=timezone.utc).isoformat()[:19]
            print(f"  {acct_key}: last sync {dt}, {contacts} contacts")
        else:
            print(f"  {acct_key}: never synced")
    try:
        tables = orbi_get("/api/onzenna/tables/")
        total = tables.get("tables", {}).get("gk_gmail_contacts", "?")
        print(f"\n  gk_gmail_contacts total: {total}")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Gmail Sent → gk_gmail_contacts")
    parser.add_argument("--account", choices=["onzenna", "zezebaebae"], help="Single account")
    parser.add_argument("--backfill", action="store_true", help="Full backfill (ignore last sync)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--max-results", type=int, help="Limit messages to scan")
    parser.add_argument("--stats", action="store_true", help="Show sync stats")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        run_sync(args.account, args.backfill, args.dry_run, args.max_results)
