"""Sync SNS Tab - Shopify PR orders + Syncly D+30 content metrics -> Google Sheet.

Reads:
  - .tmp/polar_data/q10_influencer_orders.json (Shopify PR/sample orders)
  - .tmp/polar_data/q11_paypal_transactions.json (PayPal transactions)
  - Syncly D+30 Tracker Google Sheet (Posts Master + D+30 Tracker tabs)

Writes:
  - Target Google Sheet -> "SNS" tab

Usage:
  python tools/sync_sns_tab.py
  python tools/sync_sns_tab.py --dry-run
  python tools/sync_sns_tab.py --since 2026-01-01
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from env_loader import load_env

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / ".tmp" / "polar_data"
Q10_PATH = DATA_DIR / "q10_influencer_orders.json"
Q11_PATH = DATA_DIR / "q11_paypal_transactions.json"

# ── Sheet IDs ──────────────────────────────────────────────────────────────
DEFAULT_SYNCLY_SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
DEFAULT_TARGET_SHEET_ID = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
SNS_TAB = "SNS"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Regex ──────────────────────────────────────────────────────────────────
IG_HANDLE_RE = re.compile(r"IG\s*\(@?([^)\s]+)\)", re.IGNORECASE)
TIKTOK_ORDER_RE = re.compile(r"TikTokOrderID:\s*(\d+)", re.IGNORECASE)
TIKTOK_EMAIL_RE = re.compile(r"@scs\.tiktokw\.us$", re.IGNORECASE)

# ── PayPal filtering (same as polar_financial_model.py) ────────────────────
PP_EXCLUDE_KW = ("ads", "marketing", "missing item", "invoice")
MANUAL_INF_PAYMENTS = [
    {"payer_name": "Emily Krausz",               "date": "2026-01-05", "amount": -4500.00},
    {"payer_name": "Emily Krausz",               "date": "2025-10-14", "amount": -1000.00},
    {"payer_name": "Kathlyn Marie Sanga Flores", "date": "2025-12-05", "amount": -275.00},
    {"payer_name": "Ehwa Lindsay",               "date": "2025-11-07", "amount": -300.00},
    {"payer_name": "Ehwa Lindsay",               "date": "2025-07-22", "amount": -100.00},
    {"payer_name": "Ehwa Lindsay",               "date": "2025-07-17", "amount": -100.00},
    {"payer_name": "Jessica Lim",                "date": "2025-01-21", "amount": -500.00},
]

# ── SNS tab headers ────────────────────────────────────────────────────────
# Row 1 is blank in the target sheet; Row 2 = headers
SNS_HEADERS = [
    "No", "Channel", "Account", "Product Type",
    "Influencer Fee", "Content Link",
    "Approved for Cross-Market Use",
    "D+ Days", "Curr Comment", "Curr Like", "Curr View",
]


# ── Helpers ────────────────────────────────────────────────────────────────

def get_credentials():
    load_env()
    sa_path = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json"
    )
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)
    return Credentials.from_service_account_file(sa_path, scopes=SCOPES)


def safe_int(val):
    if not val or val in ("N/A", "TBU", ""):
        return 0
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return 0


def fmt_number(n):
    """Format number with comma separator."""
    if n >= 1000:
        return f"{n:,}"
    return str(n)


# ── Data Loading ───────────────────────────────────────────────────────────

def load_orders(path=Q10_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("orders", [])


def load_paypal(path=Q11_PATH):
    if not os.path.exists(path):
        print(f"[WARN] PayPal file not found: {path} -- skipping fee data")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("transactions", [])


def load_syncly(gc, sheet_id):
    """Read Syncly sheet: Posts Master + D+30 Tracker."""
    sh = gc.open_by_key(sheet_id)

    # Posts Master: platform mapping
    pm_ws = sh.worksheet("Posts Master")
    pm_rows = pm_ws.get_all_values()
    pm_header = pm_rows[0] if pm_rows else []
    posts_master = []
    for row in pm_rows[1:]:
        if not row[0]:
            continue
        posts_master.append({
            "post_id": row[0],
            "url": row[1] if len(row) > 1 else "",
            "platform": row[2] if len(row) > 2 else "",
            "username": row[3] if len(row) > 3 else "",
            "nickname": row[4] if len(row) > 4 else "",
            "followers": row[5] if len(row) > 5 else "",
            "post_date": row[12] if len(row) > 12 else "",
        })

    # D+30 Tracker: metrics
    tr_ws = sh.worksheet("D+30 Tracker")
    tr_rows = tr_ws.get_all_values()
    tracker = []
    for row in tr_rows[2:]:  # skip 2 header rows
        if not row[0]:
            continue
        tracker.append({
            "post_id": row[0],
            "url": row[1],
            "username": row[2],
            "post_date": row[3],
            "d_plus_days": safe_int(row[4]),
            "curr_comment": safe_int(row[5]),
            "curr_like": safe_int(row[6]),
            "curr_view": safe_int(row[7]),
        })

    return {"posts_master": posts_master, "tracker": tracker}


# ── Account extraction ─────────────────────────────────────────────────────

def extract_account_info(order):
    """Extract (account_type, handle) from Shopify order tags/note."""
    tags = order.get("tags", "")
    note = order.get("note", "") or ""

    # Try Instagram handle
    for text in (tags, note):
        m = IG_HANDLE_RE.search(text)
        if m:
            return "Instagram", m.group(1).lower().strip()

    # Try TikTok
    if TIKTOK_ORDER_RE.search(tags):
        return "Tiktok", order.get("customer_name", "").strip()
    email = order.get("customer_email", "") or ""
    if TIKTOK_EMAIL_RE.search(email):
        return "Tiktok", order.get("customer_name", "").strip()

    return "Unknown", order.get("customer_name", "").strip()


def has_grosmimi(order):
    """Check if order contains at least one Grosmimi product."""
    for item in order.get("line_items", []):
        if "grosmimi" in item.get("title", "").lower():
            return True
    return False


# Keywords in tags/note that indicate giveaway/event orders (not regular PR)
GIVEAWAY_KW = ("giveaway", "valentine", "bfcm", "black friday", "christmas")


def is_giveaway_event(order):
    """Check if order is a giveaway/event order (not regular PR)."""
    text = f"{order.get('tags', '')} {order.get('note', '') or ''}".lower()
    return any(kw in text for kw in GIVEAWAY_KW)


def classify_product_type(order):
    """Get Grosmimi product names from line items (non-Grosmimi filtered out)."""
    items = order.get("line_items", [])
    names = []
    for item in items:
        title = item.get("title", "")
        if title and "grosmimi" in title.lower():
            names.append(title)
    return ", ".join(names) if names else ""


# ── PayPal paid/non-paid classification ────────────────────────────────────

def _is_inf_payment(txn):
    name = txn.get("payer_name", "").strip()
    note = (txn.get("note", "") or "").lower()
    subj = (txn.get("subject", "") or "").lower()
    text = f"{note} {subj}"
    for kw in PP_EXCLUDE_KW:
        if kw in text:
            return False
    if name:
        return True
    if not text.strip():
        return False
    pp_inf_kw = ("collab", "influencer", "supporter", "paid", "commission",
                 "content", "video", "whitelisting")
    for kw in pp_inf_kw:
        if kw in text:
            return True
    if re.search(r"\bpr\b", text):
        return True
    return False


def build_paid_set(orders, paypal_txns):
    """Build (name, email) set of paid influencers + per-person fee totals."""
    # Collect PayPal names/emails
    paypal_names = set()
    paypal_emails = set()
    person_fees = defaultdict(float)  # name -> total fee

    all_txns = list(paypal_txns) + MANUAL_INF_PAYMENTS
    for txn in all_txns:
        amt = txn.get("amount", 0)
        if amt >= 0:
            continue
        if "payer_name" in txn and not _is_inf_payment(txn):
            if txn not in MANUAL_INF_PAYMENTS:
                continue
        name = txn.get("payer_name", "").strip()
        email = txn.get("payer_email", "").lower().strip() if "payer_email" in txn else ""
        if name:
            paypal_names.add(name.lower())
            person_fees[name.lower()] += abs(amt)
        if email:
            paypal_emails.add(email)

    # Fuzzy name index
    paypal_last_first = {}
    for pn in paypal_names:
        parts = pn.split()
        if len(parts) >= 2:
            paypal_last_first.setdefault(parts[-1], set()).add(parts[0])

    # Build inf_people from orders
    inf_people = {}
    for order in orders:
        fs = order.get("fulfillment_status") or ""
        if fs not in ("fulfilled", "shipped"):
            continue
        cust_name = order.get("customer_name", "").lower().strip()
        cust_email = order.get("customer_email", "").lower().strip()
        key = (cust_name, cust_email)
        inf_people[key] = True

    # Match
    paid_people = set()
    for (name, email) in inf_people:
        if name in paypal_names or email in paypal_emails:
            paid_people.add((name, email))
            continue
        parts = name.split()
        if len(parts) >= 2:
            last = parts[-1]
            first = parts[0]
            pp_firsts = paypal_last_first.get(last, set())
            for pf in pp_firsts:
                if pf == first or (len(pf) >= 3 and len(first) >= 3 and pf[:3] == first[:3]):
                    paid_people.add((name, email))
                    break

    return paid_people, person_fees


# ── Syncly matching ────────────────────────────────────────────────────────

def build_syncly_index(syncly_data):
    """Build username -> posts index from Syncly data."""
    # Platform mapping from Posts Master
    platform_map = {}  # username_lower -> platform
    for post in syncly_data["posts_master"]:
        uname = post["username"].lower().strip()
        if uname:
            platform_map[uname] = post["platform"].lower()

    # Posts by username from D+30 Tracker
    by_username = defaultdict(list)
    for post in syncly_data["tracker"]:
        uname = post["username"].lower().strip()
        if uname:
            by_username[uname].append(post)

    # Nickname mapping from Posts Master (for TikTok matching)
    nick_to_username = {}
    for post in syncly_data["posts_master"]:
        nick = post["nickname"].strip()
        uname = post["username"].lower().strip()
        if nick and uname:
            nick_to_username[nick.lower()] = uname

    return {
        "by_username": dict(by_username),
        "platform_map": platform_map,
        "nick_to_username": nick_to_username,
    }


def match_to_syncly(account_type, handle, customer_name, syncly_idx):
    """Match an order to Syncly content posts. Returns (username, posts)."""
    by_username = syncly_idx["by_username"]

    if account_type == "Instagram" and handle:
        key = handle.lower().strip()
        if key in by_username:
            return key, by_username[key]

    # TikTok or Unknown: try customer name against nicknames
    if customer_name:
        cn_lower = customer_name.lower().strip()
        nick_map = syncly_idx["nick_to_username"]
        if cn_lower in nick_map:
            uname = nick_map[cn_lower]
            if uname in by_username:
                return uname, by_username[uname]

        # Fuzzy: try first name + last name partial
        cn_parts = cn_lower.split()
        if len(cn_parts) >= 2:
            for nick, uname in nick_map.items():
                nick_parts = nick.split()
                if len(nick_parts) >= 2:
                    if cn_parts[-1] == nick_parts[-1] and cn_parts[0][:3] == nick_parts[0][:3]:
                        if uname in by_username:
                            return uname, by_username[uname]

    return None, []


# ── Row building ───────────────────────────────────────────────────────────

def build_rows(orders, paypal_txns, syncly_data, since_date=None):
    """Build SNS tab rows (Grosmimi only)."""
    paid_people, person_fees = build_paid_set(orders, paypal_txns)
    syncly_idx = build_syncly_index(syncly_data)

    # Filter orders: shipped only, Grosmimi only, no giveaway/events, since date
    filtered = []
    for order in orders:
        fs = order.get("fulfillment_status") or ""
        if fs not in ("fulfilled", "shipped"):
            continue
        if not has_grosmimi(order):
            continue
        if is_giveaway_event(order):
            continue
        created = order.get("created_at", "")[:10]
        if since_date and created < since_date:
            continue
        filtered.append(order)

    # Also find older orders with Syncly content posted since since_date
    # (covers 2025-shipped orders with 2026 content, and PayPal-paid ones)
    if since_date:
        syncly_usernames_since = set()
        for post in syncly_data["tracker"]:
            pd = post.get("post_date", "")[:10]
            if pd >= since_date:
                syncly_usernames_since.add(post["username"].lower().strip())

        existing_ids = {o["id"] for o in filtered}
        for order in orders:
            if order["id"] in existing_ids:
                continue
            fs = order.get("fulfillment_status") or ""
            if fs not in ("fulfilled", "shipped"):
                continue
            if not has_grosmimi(order):
                continue
            if is_giveaway_event(order):
                continue
            created = order.get("created_at", "")[:10]
            if created >= since_date:
                continue  # already included
            # Check if this order's account has content posted since since_date
            acct_type, handle = extract_account_info(order)
            if acct_type == "Instagram" and handle:
                if handle.lower() in syncly_usernames_since:
                    filtered.append(order)
                    continue
            cust_name = order.get("customer_name", "").strip()
            nick_map = syncly_idx["nick_to_username"]
            cn_lower = cust_name.lower().strip()
            if cn_lower in nick_map and nick_map[cn_lower] in syncly_usernames_since:
                filtered.append(order)

    # Sort by created_at desc
    filtered.sort(key=lambda o: o.get("created_at", ""), reverse=True)

    rows = []
    stats = {"total": 0, "matched": 0, "no_content": 0}

    for order in filtered:
        acct_type, handle = extract_account_info(order)
        product_type = classify_product_type(order)

        cust_name = order.get("customer_name", "").strip()
        cust_email = order.get("customer_email", "").lower().strip()

        # Match to Syncly
        matched_uname, matched_posts = match_to_syncly(
            acct_type, handle, cust_name, syncly_idx
        )

        # Determine channel from Syncly platform (more accurate)
        channel = acct_type
        if matched_uname and matched_uname in syncly_idx["platform_map"]:
            plat = syncly_idx["platform_map"][matched_uname]
            if "instagram" in plat:
                channel = "Instagram"
            elif "tiktok" in plat:
                channel = "Tiktok"

        # Account display
        if matched_uname:
            account_display = f"@{matched_uname}"
        elif handle:
            account_display = f"@{handle}" if acct_type == "Instagram" else handle
        else:
            account_display = cust_name

        # Influencer fee
        fee = ""
        key = (cust_name.lower(), cust_email)
        if key in paid_people:
            fee_amount = person_fees.get(cust_name.lower(), 0)
            if fee_amount > 0:
                fee = f"${fee_amount:,.0f}"

        # Content link + metrics (separate columns)
        content_link = ""
        d_days_val = ""
        cmt_val = ""
        like_val = ""
        view_val = ""
        if matched_posts:
            best = max(matched_posts, key=lambda p: p.get("post_date", ""))
            url = best["url"]
            post_count = len(matched_posts)
            label = "View Post"
            if post_count > 1:
                label = f"View Post (+{post_count - 1})"
            content_link = f'=HYPERLINK("{url}","{label}")'
            d_days_val = best["d_plus_days"]
            cmt_val = best["curr_comment"]
            like_val = best["curr_like"]
            view_val = best["curr_view"]
            stats["matched"] += 1
        else:
            stats["no_content"] += 1

        stats["total"] += 1

        rows.append([
            "",  # No (filled later)
            channel,
            account_display,
            product_type,
            fee,
            content_link,
            "",  # Approved for Cross-Market Use
            d_days_val,
            cmt_val,
            like_val,
            view_val,
        ])

    # Fill sequential No
    for i, row in enumerate(rows, 1):
        row[0] = i

    return rows, stats


# ── Sheet writing ──────────────────────────────────────────────────────────

def write_to_sheet(gc, target_sheet_id, rows, dry_run=False):
    """Write rows to the SNS tab."""
    if dry_run:
        print(f"\n[DRY-RUN] Would write {len(rows)} rows to SNS tab")
        print(f"[DRY-RUN] Target sheet: {target_sheet_id}")
        print(f"\n--- Sample rows (first 10) ---")
        for row in rows[:10]:
            # Truncate long fields for display
            display = []
            for cell in row:
                s = str(cell)
                if len(s) > 50:
                    s = s[:47] + "..."
                display.append(s)
            print(f"  {display}")
        return

    sh = gc.open_by_key(target_sheet_id)

    # Get or find SNS worksheet
    try:
        ws = sh.worksheet(SNS_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SNS_TAB, rows=max(len(rows) + 10, 100), cols=10)

    # Ensure enough rows/cols
    needed_rows = len(rows) + 3  # header rows + data
    needed_cols = len(SNS_HEADERS)
    if ws.row_count < needed_rows:
        ws.resize(rows=needed_rows)
    if ws.col_count < needed_cols:
        ws.resize(cols=needed_cols)

    # Write headers in Row 2 (Row 1 stays blank per existing pattern)
    end_hdr = chr(ord("A") + len(SNS_HEADERS) - 1)
    ws.update(values=[SNS_HEADERS], range_name=f"A2:{end_hdr}2", value_input_option="RAW")

    # Clear existing data rows (Row 3+)
    if ws.row_count > 2:
        end_col = chr(ord("A") + needed_cols - 1)
        clear_range = f"A3:{end_col}{ws.row_count}"
        ws.batch_clear([clear_range])

    # Write data rows starting at Row 3
    if rows:
        end_col = chr(ord("A") + len(rows[0]) - 1)
        data_range = f"A3:{end_col}{len(rows) + 2}"
        ws.update(values=rows, range_name=data_range, value_input_option="USER_ENTERED")

    # Apply formatting
    format_sns_tab(sh, ws, len(rows))

    url = f"https://docs.google.com/spreadsheets/d/{target_sheet_id}/edit#gid={ws.id}"
    print(f"[DONE] SNS tab updated: {url}")
    return url


def format_sns_tab(sh, ws, num_rows):
    """Apply formatting to the SNS tab."""
    requests = []

    # Header row 2: dark bg, white bold text
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 1, "endRowIndex": 2,
                "startColumnIndex": 0, "endColumnIndex": len(SNS_HEADERS),
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
                    "textFormat": {
                        "bold": True, "fontSize": 10,
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat",
        }
    })

    # Column widths: No, Channel, Account, Product Type, Fee, Link, Approved, D+, Cmt, Like, View
    col_widths = [40, 80, 160, 250, 100, 140, 160, 65, 80, 80, 80]
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": i, "endIndex": i + 1,
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # Freeze rows 1-2
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 2}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Alternating row colors for data
    if num_rows > 0:
        try:
            requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 2, "endRowIndex": num_rows + 2,
                            "startColumnIndex": 0, "endColumnIndex": len(SNS_HEADERS),
                        },
                        "rowProperties": {
                            "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                            "secondBandColor": {"red": 0.95, "green": 0.96, "blue": 0.98},
                        },
                    }
                }
            })
        except Exception:
            pass  # banding might already exist

    try:
        sh.batch_update({"requests": requests})
    except Exception as e:
        # Retry without banding if it conflicts
        if "addBanding" in str(e) or "already" in str(e).lower():
            requests_no_band = [r for r in requests if "addBanding" not in r]
            if requests_no_band:
                sh.batch_update({"requests": requests_no_band})
        else:
            raise


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync SNS tab: Shopify orders + PayPal + Syncly metrics"
    )
    parser.add_argument(
        "--target-sheet-id", default=DEFAULT_TARGET_SHEET_ID,
        help="Target Google Sheet ID"
    )
    parser.add_argument(
        "--syncly-sheet-id", default=DEFAULT_SYNCLY_SHEET_ID,
        help="Syncly D+30 Tracker Sheet ID"
    )
    parser.add_argument("--q10", default=str(Q10_PATH), help="q10 JSON path")
    parser.add_argument("--q11", default=str(Q11_PATH), help="q11 JSON path")
    parser.add_argument(
        "--since", default="2026-01-01",
        help="Include orders from this date (YYYY-MM-DD)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    print("[1/4] Loading Shopify influencer orders...")
    orders = load_orders(Path(args.q10))
    print(f"  Loaded {len(orders)} total orders")

    print("[2/4] Loading PayPal transactions...")
    paypal_txns = load_paypal(Path(args.q11))
    print(f"  Loaded {len(paypal_txns)} transactions")

    print("[3/4] Loading Syncly D+30 Tracker...")
    creds = get_credentials()
    gc = gspread.authorize(creds)
    syncly_data = load_syncly(gc, args.syncly_sheet_id)
    print(f"  Posts Master: {len(syncly_data['posts_master'])} posts")
    print(f"  D+30 Tracker: {len(syncly_data['tracker'])} posts")

    print("[4/4] Building SNS rows...")
    rows, stats = build_rows(orders, paypal_txns, syncly_data, since_date=args.since)
    print(f"  Total rows: {stats['total']}")
    print(f"  Matched to content: {stats['matched']}")
    print(f"  No content yet: {stats['no_content']}")

    write_to_sheet(gc, args.target_sheet_id, rows, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
