"""Sync Gmail RAG contacts from local SQLite → OrbiTools PostgreSQL.

Reads contacts.db (built by gmail_rag tools) and batch-upserts them
into the gk_gmail_contacts table via the OrbiTools API.

Usage:
    python tools/sync_gmail_contacts_to_pg.py
    python tools/sync_gmail_contacts_to_pg.py --dry-run
"""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from env_loader import load_env

load_env()

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "gmail_rag", "contacts.db")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
BATCH_SIZE = 200


def read_sqlite_contacts():
    """Read all contacts from SQLite."""
    db_path = os.path.normpath(SQLITE_PATH)
    if not os.path.exists(db_path):
        print(f"  [ERROR] SQLite DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def sync_batch(contacts, dry_run=False):
    """POST a batch of contacts to OrbiTools sync endpoint."""
    url = f"{ORBITOOLS_URL}/api/onzenna/gmail-rag/sync/"
    payload = json.dumps({"contacts": contacts}).encode("utf-8")

    if dry_run:
        print(f"  [DRY RUN] Would sync {len(contacts)} contacts to {url}")
        return {"created": 0, "updated": 0, "total": len(contacts)}

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    # Basic auth
    import base64
    creds = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")

    try:
        ctx = __import__("ssl").create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = __import__("ssl").CERT_NONE
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {body[:500]}")
        raise


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"\n{'='*60}")
    print(f"  Gmail RAG → PostgreSQL Sync")
    print(f"{'='*60}")
    print(f"  SQLite: {os.path.normpath(SQLITE_PATH)}")
    print(f"  Target: {ORBITOOLS_URL}")
    if dry_run:
        print(f"  Mode: DRY RUN")

    contacts = read_sqlite_contacts()
    print(f"\n  Total contacts in SQLite: {len(contacts)}")
    sent_contacts = [c for c in contacts if c.get("total_sent", 0) > 0]
    print(f"  Contacts with sent emails: {len(sent_contacts)}")

    total_created = 0
    total_updated = 0

    for i in range(0, len(contacts), BATCH_SIZE):
        batch = contacts[i:i + BATCH_SIZE]
        print(f"\n  Syncing batch {i // BATCH_SIZE + 1} ({len(batch)} contacts) ...")
        result = sync_batch(batch, dry_run=dry_run)
        total_created += result.get("created", 0)
        total_updated += result.get("updated", 0)

    print(f"\n{'='*60}")
    print(f"  Sync complete!")
    print(f"  Created: {total_created}")
    print(f"  Updated: {total_updated}")
    print(f"  Total: {len(contacts)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
