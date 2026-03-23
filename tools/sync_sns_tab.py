"""Sync US SNS Tab - Shopify PR orders + Apify content metrics -> Google Sheet.

Reads:
  - .tmp/polar_data/q10_influencer_orders.json (Shopify PR/sample orders)
  - .tmp/polar_data/q11_paypal_transactions.json (PayPal transactions)
  - Apify content tracker Google Sheet (US Posts Master + US D+60 Tracker tabs)

Writes:
  - Target Google Sheet -> "US SNS" tab

Usage:
  python tools/sync_sns_tab.py
  python tools/sync_sns_tab.py --dry-run
  python tools/sync_sns_tab.py --since 2026-01-01
"""

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
DEFAULT_APIFY_SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
DEFAULT_TARGET_SHEET_ID = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
SNS_TAB = "US SNS"
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
    "No", "Channel", "Name", "Account",
    "Product Type1", "Product Type2", "Product Type3", "Product Type4",
    "Product Name", "Influencer Fee", "Shipping Date",
    "Content Link", "Approved for Cross-Market Use",
    "D+ Days", "Curr Comment", "Curr Like", "Curr View",
]

# ── Product Type classification ───────────────────────────────────────────
# Final 7 dropdown categories for Product Type columns
# "Stainless Steel" shortened to "Stainless"
# Flip Top is a feature, not a category — classify by material (PPSU/Stainless)
# KNOTTED Flip Top → PPSU Straw Cup
# Tray, Brush, Teether, Lunch Bag → Accessory
# Strap, Accessory Pack, Straw Kit → Replacement
PRODUCT_TYPE_RULES = [
    ("PPSU Straw Cup",      lambda t: "ppsu" in t and "straw cup" in t),
    ("PPSU Straw Cup",      lambda t: "knotted" in t and "flip top" in t),
    ("PPSU Tumbler",        lambda t: "ppsu" in t and "tumbler" in t and "accessory" not in t),
    ("PPSU Baby Bottle",    lambda t: "ppsu" in t and ("baby bottle" in t or "feeding bottle" in t or "bottle" in t) and "straw" not in t),
    ("Stainless Straw Cup", lambda t: "stainless" in t and "straw cup" in t),
    ("Stainless Tumbler",   lambda t: "stainless" in t and "tumbler" in t and "accessory" not in t),
    ("Accessory",           lambda t: any(kw in t for kw in ("tray", "brush", "teether", "lunch bag"))),
    ("Replacement",         lambda t: any(kw in t for kw in ("strap", "accessory pack", "straw kit", "replacement", "silicone tip"))),
]

# ── Syncly content filtering ─────────────────────────────────────────────
# Non-Grosmimi brand names (in Syncly Brand column)
NON_GROS_BRANDS = ("cha & mom", "cha and mom", "naeiae", "naeia",
                    "babyrabbit", "goongbe", "commemoi")
# Keywords in Syncly post content/caption that indicate non-Grosmimi content
# Even if Grosmimi is also tagged, these keywords mean the post is not Grosmimi-focused
NON_GROS_CONTENT_KW = ("naeiae", "naeia", "cha & mom", "cha and mom", "chaenmom",
                        "chamom", "chaandmom", "cha_mom", "phytoseline", "phyto seline",
                        "goongbe", "babyrabbit", "baby rabbit", "commemoi",
                        "lotion", "body wash", "rice puff", "rice snack")
# Promo/event keywords in Syncly post content
PROMO_CONTENT_KW = ("giveaway", "valentine", "promo", "sweepstake", "contest",
                     "bfcm", "black friday")


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


def col_letter(idx):
    """Convert 0-based column index to spreadsheet letter (0='A', 25='Z', 26='AA', ...)."""
    result = ""
    while True:
        result = chr(65 + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


# ── Data Loading ───────────────────────────────────────────────────────────

def load_orders(path=Q10_PATH):
    if not os.path.exists(path):
        print(f"[WARN] Orders file not found: {path} -- skipping order data")
        return []
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
    """Read Apify sheet: US Posts Master + US D+60 Tracker."""
    sh = gc.open_by_key(sheet_id)

    # Posts Master: PostID[0], URL[1], Platform[2], Username[3], Nickname[4],
    #   Followers[5], Content[6], Hashtags[7], TaggedAccount[8], PostDate[9],
    #   Comments[10], Likes[11], Views[12]
    pm_ws = sh.worksheet("US Posts Master")
    pm_rows = pm_ws.get_all_values()
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
            "content": row[6] if len(row) > 6 else "",
            "hashtags": row[7] if len(row) > 7 else "",
            "brand": "",
            "post_date": row[9] if len(row) > 9 else "",
        })

    # D+60 Tracker: PostID[0], URL[1], Platform[2], Username[3], PostDate[4],
    #   TaggedAccount[5], D+Days[6], CurrComment[7], CurrLike[8], CurrView[9]
    tr_ws = sh.worksheet("US D+60 Tracker")
    tr_rows = tr_ws.get_all_values()
    tracker = []
    for row in tr_rows[2:]:  # skip 2 header rows
        if not row[0]:
            continue
        tracker.append({
            "post_id": row[0],
            "url": row[1],
            "username": row[3] if len(row) > 3 else "",
            "post_date": row[4] if len(row) > 4 else "",
            "d_plus_days": safe_int(row[6]) if len(row) > 6 else 0,
            "curr_comment": safe_int(row[7]) if len(row) > 7 else 0,
            "curr_like": safe_int(row[8]) if len(row) > 8 else 0,
            "curr_view": safe_int(row[9]) if len(row) > 9 else 0,
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
        return "TikTok", order.get("customer_name", "").strip()
    email = order.get("customer_email", "") or ""
    if TIKTOK_EMAIL_RE.search(email):
        return "TikTok", order.get("customer_name", "").strip()

    return "Unknown", order.get("customer_name", "").strip()


def has_grosmimi(order):
    """Check if order contains at least one Grosmimi product."""
    for item in order.get("line_items", []):
        if "grosmimi" in item.get("title", "").lower():
            return True
    return False


# Keywords in tags/note that indicate giveaway/event orders (not regular PR)
GIVEAWAY_KW = ("giveaway", "valentine", "bfcm", "black friday", "christmas")

# Test order customer names (case-insensitive substring match)
TEST_ORDER_NAMES = ("test", "flowtest")


def is_giveaway_event(order):
    """Check if order is a giveaway/event order (not regular PR)."""
    text = f"{order.get('tags', '')} {order.get('note', '') or ''}".lower()
    return any(kw in text for kw in GIVEAWAY_KW)


def is_test_order(order):
    """Check if order is a test order (not a real influencer)."""
    name = order.get("customer_name", "").lower()
    return any(kw in name for kw in TEST_ORDER_NAMES)


def _split_product_names(product_str):
    """Split comma-separated product names, respecting parentheses.

    E.g. 'Grosmimi Tumbler Multi Accessory Pack (Tumbler Cap, Silicone Tip & Hand Strap)'
    should NOT be split at the comma inside parentheses.
    """
    parts = []
    depth = 0
    current = []
    for ch in product_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


# Keywords in product titles that indicate non-Grosmimi products
NON_GROS_PRODUCT_KW = ("cha&mom", "cha & mom", "naeiae", "rice snack", "rice puff",
                        "goongbe", "babyrabbit", "lotion", "body wash", "intense cream",
                        "phyto seline", "commemoi")


def _is_grosmimi_item(title):
    """Check if a line item title is a Grosmimi product (not CHA&MOM/Naeiae/etc)."""
    tl = title.lower()
    for kw in NON_GROS_PRODUCT_KW:
        if kw in tl:
            return False
    return True


def classify_product_type(order):
    """Classify line items into Product Type dropdown values (max 4, in order).

    Only includes Grosmimi products — CHA&MOM, Naeiae, etc. are excluded.

    Returns (types_list, product_name_str):
      - types_list: up to 4 unique Product Type values in item order
      - product_name_str: comma-separated raw product names (for Product Name col)
    """
    items = order.get("line_items", [])
    raw_names = []
    types_seen = []
    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        if not _is_grosmimi_item(title):
            continue
        raw_names.append(title)
        tl = title.lower()
        for type_name, rule_fn in PRODUCT_TYPE_RULES:
            if rule_fn(tl) and type_name not in types_seen:
                types_seen.append(type_name)
                break
    # Cap at 4
    types_seen = types_seen[:4]
    return types_seen, ", ".join(raw_names)


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

GROSMIMI_HASHTAG_RE = re.compile(r"grosmimi|grossmimi|grosmimi_usa", re.IGNORECASE)


def _is_excluded_syncly_post(post_master_entry):
    """Check if a Syncly post should be excluded (non-Grosmimi or promo content).

    Inclusion rule: post MUST have #grosmimi (or variant) in hashtags.
    Exclusion rule: non-Grosmimi brand/keywords or promo content.

    Returns (should_exclude, reason) tuple.
    """
    brand = post_master_entry.get("brand", "").lower()
    hashtags = post_master_entry.get("hashtags", "").lower()
    content = post_master_entry.get("content", "").lower()
    text = content + " " + hashtags

    # POST-LEVEL CHECK: must have #grosmimi hashtag to be included
    if not GROSMIMI_HASHTAG_RE.search(hashtags):
        return True, "no #grosmimi hashtag"

    # Check non-Grosmimi content keywords (even if Grosmimi is also tagged)
    for kw in NON_GROS_CONTENT_KW:
        if kw in text:
            return True, f"non-Gros content kw: {kw}"

    # Check promo/event keywords
    for kw in PROMO_CONTENT_KW:
        if kw in text:
            return True, f"promo content: {kw}"

    # Check brand: any non-Grosmimi brand present → exclude (even if Grosmimi also tagged)
    if brand:
        has_nongros = any(b in brand for b in NON_GROS_BRANDS)
        if has_nongros:
            return True, f"non-Gros brand: {brand}"

    return False, ""


def build_syncly_index(syncly_data):
    """Build username -> posts index from Syncly data."""
    # Platform mapping from Posts Master
    platform_map = {}  # username_lower -> platform
    for post in syncly_data["posts_master"]:
        uname = post["username"].lower().strip()
        if uname:
            platform_map[uname] = post["platform"].lower()

    # URL -> Posts Master entry (for content filtering)
    url_to_pm = {}
    for post in syncly_data["posts_master"]:
        url = post["url"].strip()
        if url:
            url_to_pm[url] = post

    # Posts by username from D+60 Tracker
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
        "url_to_pm": url_to_pm,
    }


def _normalize_handle(s):
    """Remove dots, underscores, dashes for fuzzy handle matching."""
    import re
    return re.sub(r'[_.\-]', '', s.lower())


def match_to_syncly(account_type, handle, customer_name, syncly_idx):
    """Match an order to Syncly content posts. Returns (username, posts)."""
    by_username = syncly_idx["by_username"]

    if account_type == "Instagram" and handle:
        key = handle.lower().strip()
        if key in by_username:
            return key, by_username[key]

    # Fuzzy handle match: normalize dots/underscores/dashes
    if handle:
        norm = _normalize_handle(handle)
        for uname in by_username:
            if _normalize_handle(uname) == norm and uname != handle.lower().strip():
                return uname, by_username[uname]

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
        if is_test_order(order):
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
            if is_test_order(order):
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
        product_types, product_name = classify_product_type(order)

        cust_name = order.get("customer_name", "").strip()
        cust_email = order.get("customer_email", "").lower().strip()

        # Shipping date (closed_at or created_at fallback)
        shipping_date = ""
        closed = order.get("closed_at", "")
        if closed:
            shipping_date = closed[:10]
        else:
            shipping_date = order.get("created_at", "")[:10]

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
                channel = "TikTok"

        # Account display (only show @handle for IG/TikTok with actual handles)
        if matched_uname:
            account_display = f"@{matched_uname}"
        elif acct_type == "Instagram" and handle:
            account_display = f"@{handle}"
        else:
            account_display = ""

        # Influencer fee
        fee = ""
        key = (cust_name.lower(), cust_email)
        if key in paid_people:
            fee_amount = person_fees.get(cust_name.lower(), 0)
            if fee_amount > 0:
                fee = f"${fee_amount:,.0f}"

        # Content link + metrics (separate columns)
        # Filter out excluded posts (non-Grosmimi content, promo/valentine)
        content_link = ""
        d_days_val = ""
        cmt_val = ""
        like_val = ""
        view_val = ""
        url_to_pm = syncly_idx.get("url_to_pm", {})
        if matched_posts:
            # Filter: exclude non-Grosmimi / promo posts
            valid_posts = []
            for p in matched_posts:
                pm_entry = url_to_pm.get(p["url"], {})
                excluded, reason = _is_excluded_syncly_post(pm_entry) if pm_entry else (False, "")
                if not excluded:
                    valid_posts.append(p)

            if not valid_posts:
                # All posts are excluded → skip this row entirely
                stats["no_content"] += 1
                continue

            best = max(valid_posts, key=lambda p: p.get("post_date", ""))
            url = best["url"]
            post_count = len(valid_posts)
            label = "View Post"
            if post_count > 1:
                label = f"View Post (+{post_count - 1})"
            content_link = f'=HYPERLINK("{url}","{label}")'
            d_days_val = best["d_plus_days"]
            cmt_val = best["curr_comment"]
            like_val = best["curr_like"]
            view_val = best["curr_view"]
            stats["matched"] += 1

            # Override channel from content link URL (most accurate signal)
            if "tiktok.com" in url:
                channel = "TikTok"
            elif "instagram.com" in url:
                channel = "Instagram"
            elif "youtube.com" in url or "youtu.be" in url:
                channel = "YouTube"
        else:
            stats["no_content"] += 1

        stats["total"] += 1

        # Pad product_types to exactly 4 slots
        pt = product_types + [""] * (4 - len(product_types))

        rows.append([
            "",           # A: No (filled later)
            channel,      # B: Channel
            cust_name,    # C: Name
            account_display,  # D: Account
            pt[0],        # E: Product Type1
            pt[1],        # F: Product Type2
            pt[2],        # G: Product Type3
            pt[3],        # H: Product Type4
            product_name, # I: Product Name
            fee,          # J: Influencer Fee
            shipping_date,  # K: Shipping Date
            content_link, # L: Content Link
            "",           # M: Approved for Cross-Market Use
            d_days_val,   # N: D+ Days
            cmt_val,      # O: Curr Comment
            like_val,     # P: Curr Like
            view_val,     # Q: Curr View
        ])

    # Fill sequential No
    for i, row in enumerate(rows, 1):
        row[0] = i

    return rows, stats


# ── Diff / Summary ────────────────────────────────────────────────────────

SUMMARY_PATH = PROJECT_ROOT / ".tmp" / "sns_sync_summary.json"


def read_existing_sns(gc, target_sheet_id):
    """Read current SNS tab rows. Returns list of row lists (data only, no header)."""
    try:
        sh = gc.open_by_key(target_sheet_id)
        ws = sh.worksheet(SNS_TAB)
        all_vals = ws.get_all_values()
        # Data starts at row 3 (index 2): row 0 = blank, row 1 = headers
        return all_vals[2:] if len(all_vals) > 2 else []
    except Exception:
        return []


def compute_diff(old_rows, new_rows):
    """Compare old vs new SNS rows.

    Returns dict with:
      - new_shipments: list of (Name, Account, ShipDate) not in old
      - newly_matched: list of (Name, Account, ContentLink) that had no link before
      - total_old / total_new / total_matched_old / total_matched_new
    """
    # Build old index: (name, account) -> has_content_link
    old_index = {}
    for row in old_rows:
        if len(row) < 12:
            continue
        name = str(row[2]).strip()
        account = str(row[3]).strip()
        link = str(row[11]).strip()
        key = (name.lower(), account.lower())
        old_index[key] = bool(link and link != "" and "HYPERLINK" in link.upper())

    new_shipments = []
    newly_matched = []
    total_matched_new = 0

    for row in new_rows:
        name = str(row[2]).strip()
        account = str(row[3]).strip()
        link = str(row[11]).strip()
        ship_date = str(row[10]).strip()
        key = (name.lower(), account.lower())
        has_link = bool(link and link != "" and "HYPERLINK" in link.upper())

        if has_link:
            total_matched_new += 1

        if key not in old_index:
            new_shipments.append({"name": name, "account": account, "ship_date": ship_date,
                                  "has_content": has_link})
        elif has_link and not old_index[key]:
            newly_matched.append({"name": name, "account": account, "link": link})

    total_matched_old = sum(1 for v in old_index.values() if v)

    return {
        "total_old": len(old_rows),
        "total_new": len(new_rows),
        "total_matched_old": total_matched_old,
        "total_matched_new": total_matched_new,
        "new_shipments": new_shipments,
        "newly_matched": newly_matched,
    }


def write_summary(diff, stats, xc_issues=None):
    """Write summary JSON for email reporting."""
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pipeline_stats": stats,
        "diff": {
            "total_old": diff["total_old"],
            "total_new": diff["total_new"],
            "content_matched_old": diff["total_matched_old"],
            "content_matched_new": diff["total_matched_new"],
            "new_shipments_count": len(diff["new_shipments"]),
            "new_shipments": diff["new_shipments"][:20],  # cap for readability
            "newly_matched_count": len(diff["newly_matched"]),
            "newly_matched": diff["newly_matched"][:20],
        },
    }
    if xc_issues:
        xc_summary = {}
        for key, items in xc_issues.items():
            if items:
                xc_summary[key] = {"count": len(items), "samples": items[:5]}
        summary["cross_check"] = {
            "total_issues": sum(len(v) for v in xc_issues.values()),
            "issues": xc_summary,
        }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[SUMMARY] Written to {SUMMARY_PATH}")
    return summary


def print_report(diff):
    """Print human-readable diff report."""
    print("\n" + "=" * 60)
    print("  GROSMIMI CONTENT TRACKER - Daily Report")
    print("=" * 60)
    print(f"  Total rows:  {diff['total_old']} -> {diff['total_new']}")
    print(f"  Content matched:  {diff['total_matched_old']} -> {diff['total_matched_new']}")
    print(f"  New sample shipments:  +{len(diff['new_shipments'])}")
    print(f"  Newly matched content:  +{len(diff['newly_matched'])}")

    if diff["new_shipments"]:
        print(f"\n--- New Sample Shipments ({len(diff['new_shipments'])}) ---")
        for s in diff["new_shipments"][:15]:
            icon = "[CONTENT]" if s["has_content"] else "[PENDING]"
            print(f"  {icon} {s['name']} ({s['account']}) - shipped {s['ship_date']}")
        if len(diff["new_shipments"]) > 15:
            print(f"  ... +{len(diff['new_shipments']) - 15} more")

    if diff["newly_matched"]:
        print(f"\n--- Newly Matched Content ({len(diff['newly_matched'])}) ---")
        for m in diff["newly_matched"][:15]:
            print(f"  [NEW LINK] {m['name']} ({m['account']})")
        if len(diff["newly_matched"]) > 15:
            print(f"  ... +{len(diff['newly_matched']) - 15} more")

    if not diff["new_shipments"] and not diff["newly_matched"]:
        print("\n  No changes since last sync.")
    print("=" * 60 + "\n")


# ── Cross-check validation ────────────────────────────────────────────────

def cross_check(rows):
    """Validate data integrity across row fields.

    Returns dict of issue_type -> list of {row_no, name, account, detail}.
    """
    issues = {
        "metrics_no_link": [],             # Metrics nonzero but Content Link empty
        "link_account_mismatch": [],       # Content Link username != Account handle
        "channel_link_mismatch": [],       # Channel vs Content Link domain mismatch
        "link_no_metrics": [],             # Content Link exists but all metrics zero
    }

    for row in rows:
        row_no = row[0]
        channel = str(row[1]).strip()
        name = str(row[2]).strip()
        account = str(row[3]).strip()       # @handle
        content_link = str(row[11]).strip()  # =HYPERLINK("url","label")
        d_days = row[13]
        cmt = row[14]
        like = row[15]
        view = row[16]

        # Parse content link URL from HYPERLINK formula
        link_url = ""
        link_match = re.search(r'HYPERLINK\("([^"]+)"', content_link, re.IGNORECASE)
        if link_match:
            link_url = link_match.group(1)

        has_link = bool(link_url)
        has_metrics = any(safe_int(v) > 0 for v in [d_days, cmt, like, view])
        has_account = bool(account and account != "@")

        info = {"row_no": row_no, "name": name, "account": account}

        # 1. Metrics nonzero but no Content Link
        if has_metrics and not has_link:
            issues["metrics_no_link"].append({
                **info, "detail": f"D+={d_days} cmt={cmt} like={like} view={view}"})

        # 2. Content Link username != Account handle
        if has_link and has_account:
            link_user = ""
            tiktok_m = re.search(r"tiktok\.com/@([^/?]+)", link_url)
            if tiktok_m:
                link_user = tiktok_m.group(1).lower()

            acct_handle = account.lstrip("@").lower()
            if link_user and acct_handle and link_user != acct_handle:
                # Skip if normalized handles match (cross-platform: _ vs .)
                if _normalize_handle(link_user) != _normalize_handle(acct_handle):
                    issues["link_account_mismatch"].append({
                        **info, "detail": f"link_user=@{link_user} vs account={account}"})

        # 3. Channel vs Content Link domain mismatch
        if has_link and channel:
            is_ig_link = "instagram.com" in link_url
            is_tt_link = "tiktok.com" in link_url
            is_yt_link = "youtube.com" in link_url or "youtu.be" in link_url
            ch_lower = channel.lower()
            if is_ig_link and "instagram" not in ch_lower:
                issues["channel_link_mismatch"].append({
                    **info, "detail": f"channel={channel} but link is Instagram"})
            elif is_tt_link and "tiktok" not in ch_lower:
                issues["channel_link_mismatch"].append({
                    **info, "detail": f"channel={channel} but link is TikTok"})
            elif is_yt_link and "youtube" not in ch_lower:
                issues["channel_link_mismatch"].append({
                    **info, "detail": f"channel={channel} but link is YouTube"})

        # 4. Content Link exists but all metrics zero
        if has_link and not has_metrics:
            issues["link_no_metrics"].append({
                **info, "detail": f"D+={d_days} cmt={cmt} like={like} view={view}"})

    return issues


def print_cross_check(issues):
    """Print cross-check validation report."""
    labels = {
        "metrics_no_link": "Metrics nonzero but no Content Link",
        "link_account_mismatch": "Content Link username != Account handle",
        "channel_link_mismatch": "Channel vs Content Link domain mismatch",
        "link_no_metrics": "Content Link exists but all metrics = 0",
    }

    total_issues = sum(len(v) for v in issues.values())
    print("\n" + "=" * 60)
    print("  CROSS-CHECK VALIDATION")
    print("=" * 60)

    if total_issues == 0:
        print("  All checks passed! No data inconsistencies found.")
        print("=" * 60 + "\n")
        return

    print(f"  Total issues: {total_issues}\n")

    for key, label in labels.items():
        items = issues[key]
        if not items:
            continue
        print(f"  [{len(items)}] {label}")
        for item in items[:10]:
            print(f"    Row {item['row_no']}: {item['name']} ({item['account']}) - {item['detail']}")
        if len(items) > 10:
            print(f"    ... +{len(items) - 10} more")
        print()

    print("=" * 60 + "\n")


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
        ws = sh.add_worksheet(title=SNS_TAB, rows=max(len(rows) + 10, 100), cols=len(SNS_HEADERS))

    # Ensure enough rows/cols
    needed_rows = len(rows) + 3  # header rows + data
    needed_cols = len(SNS_HEADERS)
    if ws.row_count < needed_rows:
        ws.resize(rows=needed_rows)
    if ws.col_count < needed_cols:
        ws.resize(cols=needed_cols)

    # Write last updated timestamp in Row 1
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.update(values=[[f"Last Updated: {updated_at}"]], range_name="A1", value_input_option="RAW")

    # Write headers in Row 2
    end_hdr = col_letter(len(SNS_HEADERS) - 1)
    ws.update(values=[SNS_HEADERS], range_name=f"A2:{end_hdr}2", value_input_option="RAW")

    # Clear existing data rows (Row 3+)
    if ws.row_count > 2:
        end_col = col_letter(needed_cols - 1)
        clear_range = f"A3:{end_col}{ws.row_count}"
        ws.batch_clear([clear_range])

    # Write data rows starting at Row 3
    if rows:
        end_col = col_letter(len(rows[0]) - 1)
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

    # Column widths: No, Channel, Name, Account, PT1-4, ProdName, Fee, ShipDate, Link, Approved, D+, Cmt, Like, View, ProfileURL
    col_widths = [40, 80, 130, 160, 120, 120, 120, 120, 250, 100, 90, 140, 160, 65, 80, 80, 80, 180]
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
        description="Sync US SNS tab: Shopify orders + PayPal + Apify content metrics"
    )
    parser.add_argument(
        "--target-sheet-id", default=DEFAULT_TARGET_SHEET_ID,
        help="Target Google Sheet ID"
    )
    parser.add_argument(
        "--syncly-sheet-id", default=DEFAULT_APIFY_SHEET_ID,
        help="Apify content tracker Sheet ID"
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

    print("[3/5] Loading Syncly D+60 Tracker...")
    creds = get_credentials()
    gc = gspread.authorize(creds)
    syncly_data = load_syncly(gc, args.syncly_sheet_id)
    print(f"  Posts Master: {len(syncly_data['posts_master'])} posts")
    print(f"  D+60 Tracker: {len(syncly_data['tracker'])} posts")

    print("[4/5] Reading existing SNS tab for comparison...")
    old_rows = read_existing_sns(gc, args.target_sheet_id)
    print(f"  Existing rows: {len(old_rows)}")

    print("[5/5] Building SNS rows...")
    rows, stats = build_rows(orders, paypal_txns, syncly_data, since_date=args.since)
    print(f"  Total rows: {stats['total']}")
    print(f"  Matched to content: {stats['matched']}")
    print(f"  No content yet: {stats['no_content']}")

    # Compute diff and print report
    diff = compute_diff(old_rows, rows)
    print_report(diff)

    # Cross-check validation
    xc_issues = cross_check(rows)
    print_cross_check(xc_issues)

    write_summary(diff, stats, xc_issues)

    write_to_sheet(gc, args.target_sheet_id, rows, dry_run=args.dry_run)

    # ── Push influencer orders to PostgreSQL ──
    if not args.dry_run:
        try:
            from push_content_to_pg import push_influencer_orders

            pg_orders = []
            for row in rows:
                # row is a list matching SNS tab columns
                # [No, Channel, Name, Account, PT1-4, ProductName, Fee, ShipDate, Link, Approved, D+, Cmt, Like, View, ProfileURL]
                pg_orders.append({
                    "order_id": str(row[0]) if row[0] else "",  # No as temp ID
                    "order_name": "",
                    "customer_name": row[2] if len(row) > 2 else "",
                    "customer_email": "",
                    "account_handle": row[3] if len(row) > 3 else "",
                    "channel": row[1] if len(row) > 1 else "",
                    "product_types": ", ".join(filter(None, row[4:8])) if len(row) > 7 else "",
                    "product_names": row[8] if len(row) > 8 else "",
                    "influencer_fee": str(row[9]).replace("$", "").replace(",", "") if len(row) > 9 and row[9] else "0",
                    "shipping_date": row[10] if len(row) > 10 and row[10] else None,
                    "fulfillment_status": "fulfilled",
                    "brand": "Grosmimi",
                    "tags": "",
                })

            # Use account_handle as unique key since No is sequential
            for po in pg_orders:
                if po["account_handle"] and po["shipping_date"]:
                    po["order_id"] = f"{po['account_handle']}_{po['shipping_date']}"

            pg_orders = [po for po in pg_orders if po.get("order_id")]
            if pg_orders:
                push_influencer_orders(pg_orders)
                print(f"[PG] Pushed {len(pg_orders)} influencer orders")
        except Exception as e:
            print(f"[PG WARN] Push failed (non-fatal): {e}")


if __name__ == "__main__":
    main()
