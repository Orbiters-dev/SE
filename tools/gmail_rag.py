"""
Gmail RAG - Index, retrieve, and deduplicate Gmail conversations.

Uses Gemini Embeddings (3072-dim) + Pinecone (multimodal-embeddings index, gmail-rag namespace).

Supports two accounts:
  - hello@zezebaebae.com  (zezebaebae)
  - affiliates@onzenna.com (onzenna)

Usage:
    python tools/gmail_rag.py --backfill                          # Index all emails (both accounts)
    python tools/gmail_rag.py --backfill --account zezebaebae     # Single account
    python tools/gmail_rag.py --backfill --max-results 10         # Small test
    python tools/gmail_rag.py --sync                              # Incremental sync
    python tools/gmail_rag.py --query "sample shipment"           # Semantic search
    python tools/gmail_rag.py --query "sample" --account onzenna  # Search one account
    python tools/gmail_rag.py --check-contact "jane@example.com"  # Duplicate check
    python tools/gmail_rag.py --check-domain "example.com"        # Domain check
    python tools/gmail_rag.py --status                            # Index status
"""

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

# ── Constants ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAG_DIR = PROJECT_ROOT / ".tmp" / "gmail_rag"
CONTACTS_DB_PATH = RAG_DIR / "contacts.db"
STATE_FILE = RAG_DIR / "index_state.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDENTIALS_PATH = os.getenv(
    "GMAIL_OAUTH_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials" / "gmail_oauth_credentials.json")
)

# Account configs
ACCOUNTS = {
    "zezebaebae": {
        "email": "hello@zezebaebae.com",
        "token_path": str(PROJECT_ROOT / "credentials" / "zezebaebae_gmail_token.json"),
        "backfill_query": "collab OR collaboration",  # Only index collab-related emails
    },
    "onzenna": {
        "email": "affiliates@onzenna.com",
        "token_path": str(PROJECT_ROOT / "credentials" / "onzenna_gmail_token.json"),
        "backfill_query": "",  # Index all emails
    },
}

# Gemini Embedding
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMBED_MODEL = "gemini-embedding-001"  # 3072-dim
EMBED_BATCH_SIZE = 100  # Gemini batch limit

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "multimodal-embeddings")
PINECONE_NAMESPACE = "gmail-rag"

MAX_BODY_CHARS = 8000
SAVE_EVERY = 500  # save state every N messages


# ── Gmail Service ──────────────────────────────────────────────────────────────

def get_gmail_service(account_key: str):
    """Get Gmail API service for a specific account."""
    acct = ACCOUNTS[account_key]
    token_path = acct["token_path"]
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"ERROR: OAuth credentials not found at {CREDENTIALS_PATH}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            print(f"\nAuth required for {acct['email']}")
            print(f"A browser window will open - log in with {acct['email']}\n")
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── Email Parsing ──────────────────────────────────────────────────────────────

def extract_body_text(payload: dict) -> str:
    """Extract plain text from Gmail message payload (handles nested MIME)."""
    body_data = payload.get("body", {}).get("data")
    mime = payload.get("mimeType", "")

    if body_data and "text/plain" in mime:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if body_data and "text/html" in mime:
        html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)

    for part in parts:
        if part.get("mimeType", "").startswith("multipart/"):
            text = extract_body_text(part)
            if text:
                return text

    return ""


def parse_email_address(raw: str) -> str:
    """Extract clean email from 'Name <email>' format."""
    match = re.search(r"<([^>]+)>", raw)
    return match.group(1).lower() if match else raw.strip().lower()


def parse_message(msg: dict, account_email: str) -> dict:
    """Parse a Gmail API message into a flat dict for indexing."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    from_raw = headers.get("from", "")
    to_raw = headers.get("to", "")
    cc_raw = headers.get("cc", "")
    subject = headers.get("subject", "")
    date_str = headers.get("date", "")

    from_email = parse_email_address(from_raw)
    to_email = parse_email_address(to_raw)

    direction = "sent" if from_email == account_email.lower() else "received"

    body = extract_body_text(msg.get("payload", {}))[:MAX_BODY_CHARS]

    doc_text = f"Subject: {subject}\nFrom: {from_raw}\nTo: {to_raw}\nDate: {date_str}\n\n{body}"

    return {
        "message_id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "subject": subject,
        "from_email": from_email,
        "from_raw": from_raw,
        "to_email": to_email,
        "to_raw": to_raw,
        "cc_raw": cc_raw,
        "date": date_str,
        "direction": direction,
        "body": body,
        "doc_text": doc_text,
        "internal_date": int(msg.get("internalDate", 0)),
        "labels": ",".join(msg.get("labelIds", [])),
        "account": account_email,
    }


# ── Gemini Embeddings ─────────────────────────────────────────────────────────

def get_gemini_client():
    from google import genai
    return genai.Client(api_key=GEMINI_API_KEY)


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a list of texts using Gemini. Handles batching."""
    client = get_gemini_client()
    all_embeddings = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        # Truncate very long texts
        batch = [t[:10000] for t in batch]

        from google.genai import types
        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        for emb in result.embeddings:
            all_embeddings.append(emb.values)

        if len(texts) > EMBED_BATCH_SIZE:
            print(f"  Embedded {min(i + EMBED_BATCH_SIZE, len(texts))}/{len(texts)}")

    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single query text."""
    client = get_gemini_client()
    from google.genai import types
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text[:10000],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values


# ── Pinecone ───────────────────────────────────────────────────────────────────

def get_pinecone_index():
    """Get the Pinecone index."""
    from pinecone import Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)


# ── SQLite Contacts DB ─────────────────────────────────────────────────────────

def init_contacts_db():
    """Initialize the contacts SQLite database."""
    CONTACTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CONTACTS_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            email TEXT PRIMARY KEY,
            name TEXT,
            first_contact_date TEXT,
            last_contact_date TEXT,
            last_subject TEXT,
            total_sent INTEGER DEFAULT 0,
            total_received INTEGER DEFAULT 0,
            domain TEXT,
            account TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts(domain)")
    conn.commit()
    return conn


def upsert_contact(conn: sqlite3.Connection, email: str, name: str, date_str: str,
                   subject: str, direction: str, account: str):
    """Insert or update a contact record."""
    domain = email.split("@")[-1] if "@" in email else ""
    if email in [a["email"].lower() for a in ACCOUNTS.values()]:
        return

    existing = conn.execute("SELECT * FROM contacts WHERE email = ?", (email,)).fetchone()
    if existing:
        sent_delta = 1 if direction == "sent" else 0
        recv_delta = 1 if direction == "received" else 0
        conn.execute("""
            UPDATE contacts SET
                last_contact_date = MAX(last_contact_date, ?),
                last_subject = ?,
                total_sent = total_sent + ?,
                total_received = total_received + ?
            WHERE email = ?
        """, (date_str, subject, sent_delta, recv_delta, email))
    else:
        conn.execute("""
            INSERT INTO contacts (email, name, first_contact_date, last_contact_date,
                                  last_subject, total_sent, total_received, domain, account)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, name, date_str, date_str, subject,
              1 if direction == "sent" else 0,
              1 if direction == "received" else 0,
              domain, account))


# ── State Management ───────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Core Operations ────────────────────────────────────────────────────────────

def fetch_all_message_ids(service, query: str = "", max_results: int = 0) -> list[str]:
    """Fetch all message IDs matching query via pagination."""
    msg_ids = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        batch = result.get("messages", [])
        msg_ids.extend([m["id"] for m in batch])

        if max_results and len(msg_ids) >= max_results:
            msg_ids = msg_ids[:max_results]
            break

        page_token = result.get("nextPageToken")
        if not page_token:
            break

        print(f"  Fetched {len(msg_ids)} message IDs...")

    return msg_ids


def fetch_messages_batch(service, msg_ids: list[str]) -> list[dict]:
    """Fetch full message details for a batch of IDs."""
    messages = []
    for mid in msg_ids:
        try:
            msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            messages.append(msg)
        except Exception as e:
            print(f"  WARN: Failed to fetch {mid}: {e}")
    return messages


def backfill(account_keys: list[str], max_results: int = 0):
    """Full backfill: fetch all emails and index them."""
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    index = get_pinecone_index()
    contacts_conn = init_contacts_db()
    state = load_state()

    for acct_key in account_keys:
        acct = ACCOUNTS[acct_key]
        print(f"\n{'='*60}")
        print(f"Backfilling: {acct['email']}")
        print(f"{'='*60}")

        service = get_gmail_service(acct_key)
        acct_state_key = f"{acct_key}_last_internal_date"

        # Fetch message IDs (with optional query filter per account)
        query = acct.get("backfill_query", "")
        print(f"Fetching message IDs...{f' (query: {query})' if query else ''}")
        msg_ids = fetch_all_message_ids(service, query=query, max_results=max_results)
        print(f"Found {len(msg_ids)} messages")

        if not msg_ids:
            print("Nothing to index.")
            continue

        # Process in batches
        total_indexed = 0
        for batch_start in range(0, len(msg_ids), SAVE_EVERY):
            batch_ids = msg_ids[batch_start:batch_start + SAVE_EVERY]
            print(f"\nProcessing batch {batch_start//SAVE_EVERY + 1} ({len(batch_ids)} messages)...")

            # Fetch full messages
            print("  Fetching message details...")
            raw_messages = fetch_messages_batch(service, batch_ids)

            # Parse
            parsed = []
            for msg in raw_messages:
                try:
                    p = parse_message(msg, acct["email"])
                    parsed.append(p)
                except Exception as e:
                    print(f"  WARN: Parse error for {msg.get('id', '?')}: {e}")

            if not parsed:
                continue

            # Embed
            print(f"  Embedding {len(parsed)} messages...")
            doc_texts = [p["doc_text"] for p in parsed]
            embeddings = embed_texts(doc_texts)

            # Upsert to Pinecone
            print("  Upserting to Pinecone...")
            vectors = []
            for i, p in enumerate(parsed):
                metadata = {
                    "thread_id": p["thread_id"],
                    "from_email": p["from_email"],
                    "to_email": p["to_email"],
                    "subject": p["subject"][:200],  # Pinecone metadata limit
                    "date": p["date"][:50],
                    "direction": p["direction"],
                    "labels": p["labels"][:200],
                    "internal_date": p["internal_date"],
                    "account": p["account"],
                    "doc_text": p["doc_text"][:1000],  # Store snippet for retrieval
                }
                vectors.append({
                    "id": p["message_id"],
                    "values": embeddings[i],
                    "metadata": metadata,
                })

            # Pinecone upsert in sub-batches of 100
            for j in range(0, len(vectors), 100):
                sub_batch = vectors[j:j + 100]
                index.upsert(vectors=sub_batch, namespace=PINECONE_NAMESPACE)

            # Update contacts
            for p in parsed:
                contact_email = p["to_email"] if p["direction"] == "sent" else p["from_email"]
                contact_name = p["to_raw"] if p["direction"] == "sent" else p["from_raw"]
                name = re.sub(r"\s*<[^>]+>", "", contact_name).strip().strip('"')
                upsert_contact(contacts_conn, contact_email, name, p["date"],
                              p["subject"], p["direction"], acct["email"])

            contacts_conn.commit()
            total_indexed += len(parsed)

            # Update state
            max_internal = max(p["internal_date"] for p in parsed)
            state[acct_state_key] = max(state.get(acct_state_key, 0), max_internal)
            state[f"{acct_key}_total_indexed"] = state.get(f"{acct_key}_total_indexed", 0) + len(parsed)
            state["last_sync"] = datetime.now(timezone.utc).isoformat()
            save_state(state)

            print(f"  Batch done. Total indexed this run: {total_indexed}")
            time.sleep(0.5)  # Rate limit courtesy

        print(f"\n{acct['email']}: Indexed {total_indexed} new messages")

    contacts_conn.close()
    print(f"\nBackfill complete. State saved to {STATE_FILE}")


def sync(account_keys: list[str]):
    """Incremental sync: fetch only new emails since last sync."""
    state = load_state()
    index = get_pinecone_index()
    contacts_conn = init_contacts_db()

    for acct_key in account_keys:
        acct = ACCOUNTS[acct_key]
        acct_state_key = f"{acct_key}_last_internal_date"
        last_epoch = state.get(acct_state_key, 0)

        if not last_epoch:
            print(f"{acct['email']}: No previous sync found. Run --backfill first.")
            continue

        print(f"\nSyncing: {acct['email']} (since epoch {last_epoch})")

        service = get_gmail_service(acct_key)
        epoch_sec = last_epoch // 1000
        query = f"after:{epoch_sec}"

        msg_ids = fetch_all_message_ids(service, query=query)
        print(f"Found {len(msg_ids)} messages since last sync")

        if not msg_ids:
            print("Up to date.")
            continue

        # Fetch, parse, embed, upsert
        raw_messages = fetch_messages_batch(service, msg_ids)
        parsed = []
        for msg in raw_messages:
            try:
                parsed.append(parse_message(msg, acct["email"]))
            except Exception as e:
                print(f"  WARN: {e}")

        if parsed:
            doc_texts = [p["doc_text"] for p in parsed]
            embeddings = embed_texts(doc_texts)

            vectors = []
            for i, p in enumerate(parsed):
                vectors.append({
                    "id": p["message_id"],
                    "values": embeddings[i],
                    "metadata": {
                        "thread_id": p["thread_id"],
                        "from_email": p["from_email"],
                        "to_email": p["to_email"],
                        "subject": p["subject"][:200],
                        "date": p["date"][:50],
                        "direction": p["direction"],
                        "labels": p["labels"][:200],
                        "internal_date": p["internal_date"],
                        "account": p["account"],
                        "doc_text": p["doc_text"][:1000],
                    },
                })

            for j in range(0, len(vectors), 100):
                index.upsert(vectors=vectors[j:j + 100], namespace=PINECONE_NAMESPACE)

            for p in parsed:
                contact_email = p["to_email"] if p["direction"] == "sent" else p["from_email"]
                contact_name = p["to_raw"] if p["direction"] == "sent" else p["from_raw"]
                name = re.sub(r"\s*<[^>]+>", "", contact_name).strip().strip('"')
                upsert_contact(contacts_conn, contact_email, name, p["date"],
                              p["subject"], p["direction"], acct["email"])
            contacts_conn.commit()

            max_internal = max(p["internal_date"] for p in parsed)
            state[acct_state_key] = max(state.get(acct_state_key, 0), max_internal)
            state[f"{acct_key}_total_indexed"] = state.get(f"{acct_key}_total_indexed", 0) + len(parsed)
            state["last_sync"] = datetime.now(timezone.utc).isoformat()
            save_state(state)

            print(f"Synced {len(parsed)} new messages for {acct['email']}")

    contacts_conn.close()


def query_emails(query_text: str, top_k: int = 10, account_filter: str = None) -> list[dict]:
    """Semantic search over indexed emails."""
    index = get_pinecone_index()
    query_embedding = embed_query(query_text)

    filter_dict = None
    if account_filter:
        acct = ACCOUNTS.get(account_filter)
        if acct:
            filter_dict = {"account": {"$eq": acct["email"]}}

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=PINECONE_NAMESPACE,
        filter=filter_dict,
        include_metadata=True,
    )

    output = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        output.append({
            "message_id": match["id"],
            "thread_id": meta.get("thread_id", ""),
            "subject": meta.get("subject", ""),
            "from_email": meta.get("from_email", ""),
            "to_email": meta.get("to_email", ""),
            "date": meta.get("date", ""),
            "direction": meta.get("direction", ""),
            "account": meta.get("account", ""),
            "score": match.get("score", 0),
            "snippet": meta.get("doc_text", "")[:300],
        })

    return output


def get_thread_messages(thread_id: str) -> list[dict]:
    """Retrieve all indexed messages in a thread from Pinecone."""
    index = get_pinecone_index()

    # Query by thread_id metadata filter with a dummy vector (all zeros won't work well,
    # so we use a real query to find thread messages)
    results = index.query(
        vector=[0.0] * 3072,  # dummy vector
        top_k=50,
        namespace=PINECONE_NAMESPACE,
        filter={"thread_id": {"$eq": thread_id}},
        include_metadata=True,
    )

    messages = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        messages.append({
            "message_id": match["id"],
            "subject": meta.get("subject", ""),
            "from_email": meta.get("from_email", ""),
            "to_email": meta.get("to_email", ""),
            "date": meta.get("date", ""),
            "direction": meta.get("direction", ""),
            "document": meta.get("doc_text", ""),
            "internal_date": meta.get("internal_date", 0),
        })

    messages.sort(key=lambda m: m.get("internal_date", 0))
    return messages


def check_contact(email: str) -> dict | None:
    """Check if we've previously contacted this email."""
    if not CONTACTS_DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(CONTACTS_DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM contacts WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def check_domain(domain: str) -> list[dict]:
    """Check all contacts from a domain."""
    if not CONTACTS_DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(CONTACTS_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM contacts WHERE domain = ? ORDER BY last_contact_date DESC",
        (domain.lower(),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def show_status():
    """Show current index status."""
    state = load_state()
    print("\n=== Gmail RAG Status ===\n")

    if not state:
        print("No index data. Run --backfill first.")
        return

    print(f"Last sync: {state.get('last_sync', 'never')}")
    print()

    for acct_key, acct in ACCOUNTS.items():
        total = state.get(f"{acct_key}_total_indexed", 0)
        last_epoch = state.get(f"{acct_key}_last_internal_date", 0)
        last_date = ""
        if last_epoch:
            last_date = datetime.fromtimestamp(last_epoch / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"  {acct['email']}:")
        print(f"    Indexed: {total:,} messages")
        print(f"    Latest:  {last_date or 'N/A'}")

    # Pinecone stats
    try:
        index = get_pinecone_index()
        stats = index.describe_index_stats()
        ns_stats = stats.get("namespaces", {}).get(PINECONE_NAMESPACE, {})
        print(f"\n  Pinecone '{PINECONE_NAMESPACE}': {ns_stats.get('vector_count', 0):,} vectors")
    except Exception as e:
        print(f"\n  Pinecone: Error - {e}")

    # Contacts stats
    if CONTACTS_DB_PATH.exists():
        conn = sqlite3.connect(str(CONTACTS_DB_PATH))
        total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        total_sent = conn.execute("SELECT COUNT(*) FROM contacts WHERE total_sent > 0").fetchone()[0]
        conn.close()
        print(f"  Contacts: {total_contacts:,} unique ({total_sent:,} we've sent to)")

    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gmail RAG - Index, search, and dedup emails")
    parser.add_argument("--backfill", action="store_true", help="Full backfill indexing")
    parser.add_argument("--sync", action="store_true", help="Incremental sync")
    parser.add_argument("--query", type=str, help="Semantic search query")
    parser.add_argument("--check-contact", type=str, help="Check if email was already contacted")
    parser.add_argument("--check-domain", type=str, help="Check all contacts from a domain")
    parser.add_argument("--thread", type=str, help="Get all messages in a thread")
    parser.add_argument("--status", action="store_true", help="Show index status")
    parser.add_argument("--account", type=str, choices=list(ACCOUNTS.keys()),
                        help="Limit to specific account")
    parser.add_argument("--max-results", type=int, default=0, help="Max messages for backfill (0=all)")
    parser.add_argument("--top-k", type=int, default=10, help="Number of search results")
    args = parser.parse_args()

    account_keys = [args.account] if args.account else list(ACCOUNTS.keys())

    if args.status:
        show_status()

    elif args.backfill:
        if not GEMINI_API_KEY:
            print("ERROR: GEMINI_API_KEY not set in ~/.wat_secrets")
            sys.exit(1)
        if not PINECONE_API_KEY:
            print("ERROR: PINECONE_API_KEY not set in ~/.wat_secrets")
            sys.exit(1)
        backfill(account_keys, max_results=args.max_results)

    elif args.sync:
        if not GEMINI_API_KEY or not PINECONE_API_KEY:
            print("ERROR: GEMINI_API_KEY and PINECONE_API_KEY required")
            sys.exit(1)
        sync(account_keys)

    elif args.query:
        if not GEMINI_API_KEY or not PINECONE_API_KEY:
            print("ERROR: GEMINI_API_KEY and PINECONE_API_KEY required")
            sys.exit(1)
        results = query_emails(args.query, top_k=args.top_k, account_filter=args.account)
        if not results:
            print("No matching emails found.")
            return

        print(f"\nFound {len(results)} results for: \"{args.query}\"\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['direction'].upper()}] {r['subject']}")
            print(f"     From: {r['from_email']}  To: {r['to_email']}")
            print(f"     Date: {r['date']}  Score: {r['score']:.3f}")
            print(f"     Account: {r['account']}")
            print(f"     Thread: {r['thread_id']}")
            print(f"     {r['snippet'][:150]}...")
            print()

        json_path = RAG_DIR / "last_query_results.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    elif args.check_contact:
        contact = check_contact(args.check_contact)
        if contact:
            print(f"\n  Contact found: {args.check_contact}")
            print(f"    Name: {contact['name']}")
            print(f"    First contact: {contact['first_contact_date']}")
            print(f"    Last contact:  {contact['last_contact_date']}")
            print(f"    Last subject:  {contact['last_subject']}")
            print(f"    Sent: {contact['total_sent']}  Received: {contact['total_received']}")
            print(f"    Domain: {contact['domain']}")
            print(f"    Account: {contact['account']}")

            domain = contact["domain"]
            domain_contacts = check_domain(domain)
            if len(domain_contacts) > 1:
                print(f"\n  Other contacts at @{domain}:")
                for dc in domain_contacts:
                    if dc["email"] != args.check_contact.lower():
                        print(f"    - {dc['email']} ({dc['name']}) | "
                              f"sent:{dc['total_sent']} recv:{dc['total_received']}")
        else:
            print(f"\n  No prior contact with: {args.check_contact}")
            domain = args.check_contact.split("@")[-1] if "@" in args.check_contact else ""
            if domain:
                domain_contacts = check_domain(domain)
                if domain_contacts:
                    print(f"  But found contacts at @{domain}:")
                    for dc in domain_contacts:
                        print(f"    - {dc['email']} ({dc['name']}) | "
                              f"sent:{dc['total_sent']} recv:{dc['total_received']}")

    elif args.check_domain:
        contacts = check_domain(args.check_domain)
        if contacts:
            print(f"\n  Contacts at @{args.check_domain}: {len(contacts)}")
            for dc in contacts:
                print(f"    - {dc['email']} ({dc['name']}) | "
                      f"sent:{dc['total_sent']} recv:{dc['total_received']} | "
                      f"last: {dc['last_contact_date']}")
        else:
            print(f"\n  No contacts found at @{args.check_domain}")

    elif args.thread:
        if not PINECONE_API_KEY:
            print("ERROR: PINECONE_API_KEY required")
            sys.exit(1)
        messages = get_thread_messages(args.thread)
        if messages:
            print(f"\nThread {args.thread}: {len(messages)} messages\n")
            for m in messages:
                print(f"  [{m['direction'].upper()}] {m['from_email']} -> {m['to_email']}")
                print(f"  Subject: {m['subject']}")
                print(f"  Date: {m['date']}")
                print(f"  {m['document'][:200]}...")
                print()
        else:
            print(f"No messages found for thread {args.thread}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
