"""
Apify Content Pipeline - Daily IG + TikTok tracker
===================================================
6-tab Google Sheet: Posts Master / D+60 Tracker / Influencer Tracker x US, JP

Usage:
  # Full daily pipeline (IG tagged + TikTok + sheet update + email)
  python tools/fetch_apify_content.py --daily

  # US only
  python tools/fetch_apify_content.py --daily --region us

  # Skip email
  python tools/fetch_apify_content.py --daily --no-email

  # Dry run (no API calls, use cached JSON)
  python tools/fetch_apify_content.py --daily --dry-run
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "apify"
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Apify actors
IG_SCRAPER = "apify/instagram-scraper"
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"
TT_SCRAPER = "clockworks/free-tiktok-scraper"

# Brand tagged pages
US_TAGGED_URLS = [
    "https://www.instagram.com/onzenna.official/tagged/",
    "https://www.instagram.com/grosmimi_usa/tagged/",
]
JP_TAGGED_URLS = [
    "https://www.instagram.com/grosmimi_japan/tagged/",
]

# TikTok search queries (US only)
TT_QUERIES = ["onzenna", "grosmimi", "grosmimi_usa", "onzenna.official"]
TT_KEYWORDS = {
    "grosmimi", "onzenna", "zezebaebae", "chaandmom", "naeiae",
    "commemoi", "alpremio", "zzbb", "straw cup", "gros mimi",
}

# Exclude brand/store/reseller accounts (only collect UGC from real influencers)
# Our accounts: US(onzenna.official, grosmimi_usa), JP(grosmimi_japan)
EXCLUDE = {
    # -- Our brand accounts --
    "onzenna.official", "grosmimi_usa", "grosmimi_japan", "grosmimi_official",
    "grosmimi_korea", "onzenna", "grosmimi", "zezebaebae",
    # -- Other country brand accounts --
    "grosmimithailand", "grosmimi_thailand", "grosmimi_cambodia", "grosmimi_uae",
    "grosmimi.id", "grosmimi.indo", "grosmimi_malaysia",
    "grosmimivietnam.official", "grosmimi.vietnam",
    "grosmimiofficial_sg", "grosmimi_sk", "grosmimi_hu",
    # -- Sister brand country accounts --
    "chaandmom.vn", "commemoi.vietnam", "commemoi._.official",
    "naeiae.official", "naeiae",
    # -- Reseller/distributor accounts --
    "baby.boutique.official", "baby.boutique.kh", "chez.gros.mimi",
}

# Shopify PR/Sample influencer orders
import re as _re
INFLUENCER_ORDERS_PATH = PROJECT_ROOT / ".tmp" / "polar_data" / "q10_influencer_orders.json"
_IG_HANDLE_RE = _re.compile(r"IG\s*\(@?([^)\s]+)\)", _re.IGNORECASE)

# Instagram Graph API (replaces Apify for tagged post detection)
# IG Business User IDs per brand account
IG_GRAPH_ACCOUNTS = {
    "onzenna.official": os.getenv("IG_BUSINESS_USER_ID_ONZENNA", "17841458739542512"),
    "grosmimi_usa":     os.getenv("IG_BUSINESS_USER_ID_GROSMIMI_USA", ""),
    "grosmimi_japan":   os.getenv("IG_BUSINESS_USER_ID_GROSMIMI_JP", ""),
}


# ---------------------------------------------------------------------------
# Instagram Graph API — tagged post detection (FREE, replaces Apify scraper)
# ---------------------------------------------------------------------------

def fetch_ig_tagged_graph(account_ids: dict, token: str, limit: int = 500) -> list:
    """
    Fetch posts where brand accounts are tagged, via Instagram Graph API.
    Returns items in the same format as fetch_ig_tagged() for pipeline compatibility.
    account_ids: {username: ig_business_user_id}
    """
    all_items = []
    fields = "id,timestamp,like_count,comments_count,permalink,username,caption,media_type"

    for acct, ig_id in account_ids.items():
        if not ig_id:
            print(f"[GRAPH] @{acct}: no IG Business User ID - skipping")
            continue

        print(f"[GRAPH] @{acct}/tags (limit={limit})...")
        collected, next_url = [], None
        base = (
            f"https://graph.facebook.com/v21.0/{ig_id}/tags"
            f"?fields={fields}&limit=50&access_token={urllib.parse.quote(token)}"
        )
        url = base

        try:
            while len(collected) < limit:
                # Retry up to 3 times with exponential backoff for 5xx errors
                data = None
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(url, timeout=60) as r:
                            data = json.loads(r.read())
                        break
                    except urllib.error.HTTPError as e:
                        if e.code >= 500 and attempt < 2:
                            wait = 10 * (2 ** attempt)
                            print(f"  [RETRY] HTTP {e.code}, waiting {wait}s (attempt {attempt+1}/3)...")
                            time.sleep(wait)
                        else:
                            raise
                if data is None:
                    break
                posts = data.get("data", [])
                for p in posts:
                    permalink = p.get("permalink", "")
                    sc = permalink.rstrip("/").split("/")[-1] if permalink else p.get("id", "")
                    collected.append({
                        "shortCode":      sc,
                        "id":             p.get("id", ""),
                        "url":            permalink,
                        "ownerUsername":  p.get("username", ""),
                        "ownerFullName":  "",
                        "timestamp":      p.get("timestamp", ""),
                        "caption":        p.get("caption", ""),
                        "hashtags":       [],
                        "likesCount":     p.get("like_count") or 0,
                        "commentsCount":  p.get("comments_count") or 0,
                        "videoViewCount": 0,
                        "_tagged_account": acct,
                        "_source": "graph_api",
                    })
                next_url = data.get("paging", {}).get("next")
                if not next_url or len(collected) >= limit:
                    break
                url = next_url

            print(f"  @{acct}: {len(collected)} tagged posts")
            all_items.extend(collected)
        except Exception as e:
            print(f"  [WARN] @{acct} Graph API failed: {e}")

    return all_items


# ---------------------------------------------------------------------------
# Apify fetch functions
# ---------------------------------------------------------------------------

def get_client():
    load_env()
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_API_TOKEN not found")
        sys.exit(1)
    from apify_client import ApifyClient
    return ApifyClient(token)


def fetch_ig_tagged(client, urls, limit=2000):
    """Fetch IG tagged posts per brand account."""
    all_items = []
    for url in urls:
        acct = url.rstrip("/").split("/")[-2]
        print(f"[IG] @{acct}/tagged/ (limit={limit})...")
        try:
            run = client.actor(IG_SCRAPER).call(
                run_input={
                    "directUrls": [url],
                    "resultsLimit": limit,
                    "searchType": "user",
                },
                timeout_secs=600,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            for item in items:
                item["_tagged_account"] = acct
            print(f"  @{acct}: {len(items)} posts")
            all_items.extend(items)
        except Exception as e:
            print(f"  [WARN] @{acct} failed: {e}")
    return all_items


def fetch_tiktok(client):
    """Search TikTok for brand mentions."""
    print(f"[TT] Searching: {TT_QUERIES}")
    try:
        run = client.actor(TT_SCRAPER).call(
            run_input={
                "searchQueries": TT_QUERIES,
                "resultsPerPage": 100,
                "maxProfilesPerQuery": 1,
                "shouldDownloadCovers": False,
                "shouldDownloadVideos": False,
                "shouldDownloadSubtitles": False,
            },
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"[TT] Raw: {len(items)} results")
        return items
    except Exception as e:
        print(f"[TT] Failed: {e}")
        return []


def fetch_ig_by_urls(client, post_urls):
    """Scrape individual IG posts by URL for views + updated metrics.

    Graph API doesn't return views for tagged posts.
    This fills the gap by scraping each post URL via Apify.
    """
    if not post_urls:
        return []
    print(f"[IG-URL] Scraping {len(post_urls)} IG posts by URL...")
    try:
        run = client.actor(IG_SCRAPER).call(
            run_input={
                "directUrls": post_urls,
                "resultsLimit": len(post_urls),
                "resultsType": "posts",
            },
            timeout_secs=600,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"[IG-URL] Got {len(items)} results")
        return items
    except Exception as e:
        print(f"[IG-URL] Failed: {e}")
        return []


def fetch_tiktok_by_urls(client, post_urls):
    """Scrape individual TikTok posts by URL for D+60 metric tracking.

    Used when TikTok keyword search misses posts already in our tracker.
    These posts were previously discovered but didn't appear in today's search.
    """
    if not post_urls:
        return []
    print(f"[TT-URL] Scraping {len(post_urls)} TikTok posts by URL...")
    try:
        run = client.actor(TT_SCRAPER).call(
            run_input={
                "postURLs": post_urls,
                "shouldDownloadCovers": False,
                "shouldDownloadVideos": False,
                "shouldDownloadSubtitles": False,
            },
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"[TT-URL] Got {len(items)} results")
        return items
    except Exception as e:
        print(f"[TT-URL] Failed: {e}")
        return []


def get_missing_tiktok_urls(sh, tracker_tab, collected_data, max_d_plus=30):
    """Find TikTok posts in D+60 tracker that are missing from today's crawl.

    Returns list of TikTok URLs that need direct scraping.
    Only includes posts within D+0~max_d_plus range (active tracking window).
    """
    try:
        ws = sh.worksheet(tracker_tab)
        rows = ws.get_all_values()
    except Exception:
        return []

    if len(rows) <= 2:
        return []

    collected_pids = set(d["post_id"] for d in collected_data)
    missing_urls = []
    now = datetime.now()

    for row in rows[2:]:  # skip 2 header rows
        if not row or len(row) < 5:
            continue

        post_id = row[0]
        if post_id.startswith("=HYPERLINK"):
            parts = post_id.split('"')
            post_id = parts[3] if len(parts) > 3 else parts[1]

        if post_id in collected_pids:
            continue  # already in today's crawl

        platform = row[2].lower() if len(row) > 2 else ""
        if platform != "tiktok":
            continue  # only TikTok needs URL scraping (IG uses Graph API)

        post_date_str = row[4] if len(row) > 4 else ""
        if not post_date_str:
            continue
        try:
            pd = datetime.strptime(post_date_str, "%Y-%m-%d")
            d_plus = (now - pd).days
        except ValueError:
            continue

        if d_plus < 0 or d_plus > max_d_plus:
            continue  # outside active tracking window

        # Extract URL
        url_cell = row[1] if len(row) > 1 else ""
        if url_cell.startswith("=HYPERLINK"):
            parts = url_cell.split('"')
            url = parts[1] if len(parts) > 1 else ""
        else:
            url = url_cell

        if url and "tiktok.com" in url:
            missing_urls.append(url)

    return missing_urls


def get_active_ig_urls(sh, tracker_tab, max_d_plus=30):
    """Get ALL IG post URLs in D+0~max_d_plus range for view metric scraping.

    Unlike TikTok (where we only scrape missing posts), IG needs ALL posts
    scraped because Graph API doesn't return views.
    """
    try:
        ws = sh.worksheet(tracker_tab)
        rows = ws.get_all_values()
    except Exception:
        return []

    if len(rows) <= 2:
        return []

    ig_urls = []
    now = datetime.now()

    for row in rows[2:]:
        if not row or len(row) < 5:
            continue

        platform = row[2].lower() if len(row) > 2 else ""
        if platform != "instagram":
            continue

        post_date_str = row[4] if len(row) > 4 else ""
        if not post_date_str:
            continue
        try:
            pd = datetime.strptime(post_date_str, "%Y-%m-%d")
            d_plus = (now - pd).days
        except ValueError:
            continue

        if d_plus < 0 or d_plus > max_d_plus:
            continue

        url_cell = row[1] if len(row) > 1 else ""
        if url_cell.startswith("=HYPERLINK"):
            parts = url_cell.split('"')
            url = parts[1] if len(parts) > 1 else ""
        else:
            url = url_cell

        if url and "instagram.com" in url:
            ig_urls.append(url)

    return ig_urls


def fetch_ig_profiles(client, usernames):
    """Fetch follower counts for username list."""
    if not usernames:
        return {}
    print(f"[PROFILE] Fetching {len(usernames)} profiles...")
    try:
        run = client.actor(IG_PROFILE_SCRAPER).call(
            run_input={"usernames": list(usernames)},
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        fmap = {}
        for item in items:
            u = (item.get("username", "") or "").lower()
            fc = item.get("followersCount", item.get("followedByCount", 0)) or 0
            if u:
                fmap[u] = fc
        print(f"[PROFILE] Got {len(fmap)} profiles")
        return fmap
    except Exception as e:
        print(f"[PROFILE] Failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Normalize raw data to common format
# ---------------------------------------------------------------------------

# Language filter — keep only English/Japanese, skip Vietnamese/Thai/Arabic/Cyrillic
_NON_ENJP_RE = _re.compile(
    r'[\u0E00-\u0E7F]'          # Thai
    r'|[\u0600-\u06FF]'          # Arabic
    r'|[\u0400-\u04FF]'          # Cyrillic (Russian etc.)
    r'|[ơưăđĐ]'                 # Vietnamese-specific
    r'|[ầấẩẫậềếểễệờớởỡợừứửữựỳỷỹỵ]'  # Vietnamese diacritics
)

def _is_foreign_lang(text):
    """Return True if text contains non-English/Japanese characters."""
    if not text:
        return False
    return bool(_NON_ENJP_RE.search(text))


def normalize_ig(items, fmap=None):
    fmap = fmap or {}
    result, seen = [], set()
    for item in items:
        sc = item.get("shortCode", item.get("id", ""))
        uname = (item.get("ownerUsername", "") or "").lower()
        if not sc or sc in seen or not uname or uname in EXCLUDE:
            continue
        caption_raw = item.get("caption", "") or ""
        if _is_foreign_lang(caption_raw):
            continue
        seen.add(sc)
        ts = str(item.get("timestamp", "") or "")[:10]
        hashtags = item.get("hashtags", []) or []
        result.append({
            "post_id": sc,
            "url": item.get("url", "") or f"https://www.instagram.com/p/{sc}/",
            "platform": "instagram",
            "username": uname,
            "nickname": item.get("ownerFullName", "") or "",
            "followers": fmap.get(uname, 0),
            "caption": caption_raw[:500],
            "hashtags": ", ".join(
                h if isinstance(h, str) else h.get("name", "") for h in hashtags
            ),
            "tagged_account": item.get("_tagged_account", ""),
            "post_date": ts,
            "comments": item.get("commentsCount", 0) or 0,
            "likes": item.get("likesCount", 0) or 0,
            "views": item.get("videoViewCount", 0) or 0,
        })
    return result


def normalize_tt(items, skip_keyword_filter=False):
    result, seen = [], set()
    for item in items:
        vid = str(item.get("id", ""))
        am = item.get("authorMeta", {}) or {}
        uname = (am.get("name", "") or "").lower()
        if not vid or vid in seen or not uname or uname in EXCLUDE:
            continue
        caption_raw = item.get("text", "") or ""
        if _is_foreign_lang(caption_raw):
            continue
        # Relevance filter (skip for URL-scraped posts — already verified relevant)
        if not skip_keyword_filter:
            text = caption_raw.lower()
            ht_names = [h.get("name", "").lower() for h in (item.get("hashtags", []) or [])]
            all_text = text + " " + " ".join(ht_names)
            if not any(kw in all_text for kw in TT_KEYWORDS):
                continue
        seen.add(vid)
        result.append({
            "post_id": vid,
            "url": item.get("webVideoUrl", "") or f"https://www.tiktok.com/@{uname}/video/{vid}",
            "platform": "tiktok",
            "username": uname,
            "nickname": am.get("nickName", "") or "",
            "followers": am.get("fans", 0) or 0,
            "caption": caption_raw[:500],
            "hashtags": ", ".join(h.get("name", "") for h in (item.get("hashtags", []) or [])),
            "tagged_account": "",
            "post_date": (item.get("createTimeISO", "") or "")[:10],
            "comments": item.get("commentCount", 0) or 0,
            "likes": item.get("diggCount", 0) or 0,
            "views": item.get("playCount", 0) or 0,
        })
    return result


# ---------------------------------------------------------------------------
# Brand/Product Enrichment — Shopify orders cross-match
# ---------------------------------------------------------------------------

# Product type classification rules (from sync_sns_tab.py)
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

# Brand detection from product titles
BRAND_PRODUCT_RULES = [
    ("CHA&MOM",    ("cha&mom", "cha & mom", "phyto seline", "chamom")),
    ("Naeiae",     ("naeiae", "naeia", "rice puff", "rice snack")),
    ("Goongbe",    ("goongbe",)),
    ("Babyrabbit", ("babyrabbit", "baby rabbit")),
    ("Commemoi",   ("commemoi",)),
]

# Brand detection from caption/hashtag text (fallback)
# NOTE: "Onzenna" is the umbrella storefront, NOT a brand.
# Posts mentioning only @onzenna without a specific brand → use product keyword fallback.
_BRAND_REGEX = [
    ("Grosmimi",   _re.compile(r"grosmimi|growmimi|gros\s*mimi", _re.IGNORECASE)),
    ("CHA&MOM",    _re.compile(r"cha\s*&\s*mom|cha_mom|chaandmom|chamom|phyto.?seline", _re.IGNORECASE)),
    ("Naeiae",     _re.compile(r"naeiae|naeia|rice\s*puff|rice\s*snack|rice\s*cracker", _re.IGNORECASE)),
    ("Goongbe",    _re.compile(r"goongbe", _re.IGNORECASE)),
    ("Babyrabbit", _re.compile(r"babyrabbit|baby\s*rabbit", _re.IGNORECASE)),
    ("Commemoi",   _re.compile(r"commemoi", _re.IGNORECASE)),
]

# Product-keyword fallback: when only @onzenna/zezebaebae is mentioned
_PRODUCT_BRAND_REGEX = [
    ("Grosmimi",   _re.compile(r"straw\s*cup|tumbler|sippy|bottle|ppsu|stainless\s*steel\s*(cup|bottle|tumbler)", _re.IGNORECASE)),
    ("CHA&MOM",    _re.compile(r"lotion|cream|body\s*wash|moisturiz|skincare|hair\s*wash", _re.IGNORECASE)),
    ("Naeiae",     _re.compile(r"rice|snack|cracker|puff", _re.IGNORECASE)),
    ("Commemoi",   _re.compile(r"bookstand|stool|furniture|desk", _re.IGNORECASE)),
    ("Babyrabbit", _re.compile(r"legging|clothing|pajama|outfit|onesie", _re.IGNORECASE)),
]


def _norm_handle(s):
    """Normalize handle for fuzzy matching: remove @._- and lowercase."""
    return _re.sub(r"[@._\-]", "", (s or "")).lower()


def _detect_brand_from_items(line_items):
    """Detect brand from Shopify order line_items. Returns set of brands."""
    brands = set()
    for item in line_items:
        title = (item.get("title", "") or "").lower()
        matched = False
        for brand_name, keywords in BRAND_PRODUCT_RULES:
            if any(kw in title for kw in keywords):
                brands.add(brand_name)
                matched = True
                break
        if not matched and title:
            # Default: if product title exists but no non-Grosmimi keywords → Grosmimi
            brands.add("Grosmimi")
    return brands


def _classify_product_types(line_items):
    """Classify product types from Shopify line_items. Returns set of types."""
    types = set()
    for item in line_items:
        title = (item.get("title", "") or "").lower()
        for type_name, rule_fn in PRODUCT_TYPE_RULES:
            if rule_fn(title):
                types.add(type_name)
                break
    return types


def _detect_brand_from_text(text):
    """Detect brand from caption/hashtag text. Returns brand name or ''.

    Priority:
    1. Explicit brand name (Grosmimi, CHA&MOM, Naeiae, etc.)
    2. Product keyword fallback (straw cup → Grosmimi, lotion → CHA&MOM, etc.)
    """
    text = (text or "").lower()
    for brand_name, pattern in _BRAND_REGEX:
        if pattern.search(text):
            return brand_name
    # No explicit brand — try product keywords
    for brand_name, pattern in _PRODUCT_BRAND_REGEX:
        if pattern.search(text):
            return brand_name
    return ""


def enrich_posts_from_orders(posts):
    """Cross-match posts with Shopify PR orders to fill brand + product_types.

    Strategy:
    1. Load Shopify orders → extract IG/TikTok handle + brand + product types
    2. Build handle → {brands, product_types} map
    3. For each post: match username → handle → inherit brand + product_types
    4. Fallback: detect brand from caption/hashtags
    """
    # 1. Load orders
    if not INFLUENCER_ORDERS_PATH.exists():
        print("[ENRICH] No orders file — using caption/hashtag fallback only")
        for p in posts:
            if not p.get("brand"):
                text = f"{p.get('caption', '')} {p.get('hashtags', '')} {p.get('tagged_account', '')}"
                p["brand"] = _detect_brand_from_text(text)
            p.setdefault("product_types", "")
        return

    raw = json.loads(INFLUENCER_ORDERS_PATH.read_text(encoding="utf-8"))
    orders = raw.get("orders", raw) if isinstance(raw, dict) else raw

    # 2. Build handle map
    handle_map = {}  # normalized_handle → {brands: set, product_types: set}
    for order in orders:
        if not isinstance(order, dict):
            continue
        # Extract handle
        handle = ""
        for text in (order.get("tags", "") or "", order.get("note", "") or ""):
            m = _IG_HANDLE_RE.search(text)
            if m:
                handle = m.group(1).lower().strip()
                break
        if not handle:
            continue

        line_items = order.get("line_items", [])
        brands = _detect_brand_from_items(line_items)
        product_types = _classify_product_types(line_items)

        norm = _norm_handle(handle)
        if norm not in handle_map:
            handle_map[norm] = {"brands": set(), "product_types": set()}
        handle_map[norm]["brands"].update(brands)
        handle_map[norm]["product_types"].update(product_types)

    print(f"[ENRICH] Built handle map: {len(handle_map)} influencers from {len(orders)} orders")

    # 3. Match posts
    matched, fallback, unmatched = 0, 0, 0
    for p in posts:
        username = (p.get("username", "") or "").lower()
        norm_user = _norm_handle(username)

        # Try exact normalized match
        info = handle_map.get(norm_user)

        if info:
            # Caption/hashtag brand takes priority over order (influencer may
            # have bought via other channels or posted about a different brand)
            if not p.get("brand"):
                text = f"{p.get('caption', '')} {p.get('hashtags', '')} {p.get('tagged_account', '')}"
                caption_brand = _detect_brand_from_text(text)
                if caption_brand:
                    p["brand"] = caption_brand
                else:
                    # No brand in caption — fall back to order
                    p["brand"] = sorted(info["brands"])[0] if info["brands"] else ""
            if not p.get("product_types"):
                p["product_types"] = ",".join(sorted(info["product_types"]))
            matched += 1
        else:
            # No order match: detect from caption/hashtags
            if not p.get("brand"):
                text = f"{p.get('caption', '')} {p.get('hashtags', '')} {p.get('tagged_account', '')}"
                p["brand"] = _detect_brand_from_text(text)
            p.setdefault("product_types", "")
            if p["brand"]:
                fallback += 1
            else:
                unmatched += 1

    print(f"[ENRICH] Results: {matched} order-matched, {fallback} caption-detected, {unmatched} unmatched")


# ---------------------------------------------------------------------------
# Google Sheets update (6-tab structure)
# ---------------------------------------------------------------------------

def get_sheets():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh, creds


def safe_hl(url, display):
    d = str(display).replace('"', "'")[:100]
    return f'=HYPERLINK("{url}", "{d}")'


def profile_url(username, platform):
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{username}"
    return f"https://www.instagram.com/{username}/"


def get_post_id_to_row(ws):
    """Posts Master에서 post_id → 시트 행번호(1-indexed) 맵 반환."""
    vals = ws.get_all_values()
    result = {}
    for i, row in enumerate(vals[1:], start=2):  # 헤더 제외, 2행부터
        pid = row[0] if row else ""
        if pid:
            result[pid] = i
    return result


def update_posts_master(sh, data, tab_name):
    """Add new posts, update metrics for existing."""
    headers = [
        "Post ID", "URL", "Platform", "Username", "Nickname", "Followers",
        "Content", "Hashtags", "Tagged Account", "Post Date",
        "Comments", "Likes", "Views", "Brand",
    ]
    try:
        ws = sh.worksheet(tab_name)
        existing = ws.get_all_values()
        existing_ids = set(r[0] for r in existing[1:]) if len(existing) > 1 else set()
    except Exception:
        existing = []
        existing_ids = set()

    new_posts = [d for d in data if d["post_id"] not in existing_ids]
    if not new_posts and existing:
        # Just update metrics for existing posts
        _update_pm_metrics(ws, existing, data)
        print(f"[{tab_name}] Metrics updated, 0 new posts")
        return 0

    if not existing or len(existing) <= 1:
        # First run: write everything
        rows = []
        for d in data:
            rows.append([
                d["post_id"],
                safe_hl(d["url"], d["url"]),
                d["platform"],
                safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
                d["nickname"], d["followers"], d["caption"], d["hashtags"],
                d["tagged_account"], d["post_date"],
                d["comments"], d["likes"], d["views"],
                d.get("brand", ""),
            ])
        try:
            ws = sh.worksheet(tab_name)
            ws.clear()
        except Exception:
            ws = sh.add_worksheet(tab_name, rows=len(rows) + 5, cols=len(headers))
        ws.update(range_name="A1", values=[headers])
        for i in range(0, len(rows), 80):
            ws.update(range_name=f"A{i + 2}", values=rows[i:i+80],
                      value_input_option="USER_ENTERED")
            time.sleep(1)
        print(f"[{tab_name}] Full write: {len(rows)} rows")
        return len(rows)

    # Append new posts
    new_rows = []
    for d in new_posts:
        new_rows.append([
            d["post_id"],
            safe_hl(d["url"], d["url"]),
            d["platform"],
            safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
            d["nickname"], d["followers"], d["caption"], d["hashtags"],
            d["tagged_account"], d["post_date"],
            d["comments"], d["likes"], d["views"],
            d.get("brand", ""),
        ])
    if new_rows:
        next_row = len(existing) + 1
        required_rows = next_row + len(new_rows) - 1
        if required_rows > ws.row_count:
            ws.add_rows(required_rows - ws.row_count + 100)
        ws.update(range_name=f"A{next_row}", values=new_rows,
                  value_input_option="USER_ENTERED")
    _update_pm_metrics(ws, existing, data)
    print(f"[{tab_name}] +{len(new_rows)} new, metrics updated")
    return len(new_rows)


def _update_pm_metrics(ws, existing, data):
    """Update Comments/Likes/Views/Brand columns for existing posts."""
    if len(existing) <= 1:
        return
    lookup = {d["post_id"]: d for d in data}
    updates = []
    for row_idx, row in enumerate(existing[1:], start=2):
        pid = row[0]
        if pid in lookup:
            d = lookup[pid]
            # K=Comments(11), L=Likes(12), M=Views(13), N=Brand(14)
            updates.append({
                "range": f"'{ws.title}'!K{row_idx}:N{row_idx}",
                "values": [[d["comments"], d["likes"], d["views"], d.get("brand", "")]],
            })
    if updates:
        for i in range(0, len(updates), 200):
            ws.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": updates[i:i+200]}
            )
            time.sleep(1)


def update_d60_tracker(sh, data, tab_name, pm_tab_name=None, pm_pid_to_row=None):
    """Update D+60 tracker: fill today's D+N column for each post."""
    try:
        ws = sh.worksheet(tab_name)
        existing = ws.get_all_values()
    except Exception:
        existing = []

    # Posts Master GID (Post ID 하이퍼링크용)
    pm_gid = None
    if pm_tab_name:
        try:
            pm_ws = sh.worksheet(pm_tab_name)
            pm_gid = pm_ws.id
            if pm_pid_to_row is None:
                pm_pid_to_row = get_post_id_to_row(pm_ws)
        except Exception:
            pass

    if len(existing) <= 2:
        print(f"[{tab_name}] Empty, skipping D+60 update")
        return

    # Build lookup: post_id -> row index (0-based in existing)
    pid_to_row = {}
    for i, row in enumerate(existing[2:], start=2):  # skip 2 header rows
        pid = row[0] if row else ""
        if pid:
            pid_to_row[pid] = i

    data_lookup = {d["post_id"]: d for d in data}
    updates = []

    for pid, row_idx in pid_to_row.items():
        d = data_lookup.get(pid)
        if not d:
            continue

        post_date = d["post_date"]
        if not post_date:
            continue
        try:
            pd = datetime.strptime(post_date, "%Y-%m-%d")
            d_plus = (datetime.now() - pd).days
        except ValueError:
            continue

        # Update current status columns (G=7, H=8, I=9, J=10 -- 1-indexed)
        # Fixed: A=PostID, B=URL, C=Platform, D=Username, E=PostDate, F=TaggedAccount
        # Status: G=D+Days, H=CurrComment, I=CurrLike, J=CurrView
        updates.append({
            "range": f"'{tab_name}'!G{row_idx + 1}:J{row_idx + 1}",
            "values": [[d_plus, d["comments"], d["likes"], d["views"]]],
        })

        # Fill D+N snapshot column based on schedule:
        # D+0~D+30: daily, D+31~D+90: Monday only, D+90+: skip
        is_monday = datetime.now().weekday() == 0
        should_snapshot = (
            0 <= d_plus <= 30 or
            (31 <= d_plus <= 90 and is_monday)
        )
        if should_snapshot:
            # Fixed cols: A-F (6) + Status: G-J (4) = 10 total fixed columns
            # D+0 starts at col index 10 (K), D+1 at 13, etc.
            col_start = 10 + d_plus * 3  # 0-based
            col_letter_1 = _col_letter(col_start)
            col_letter_3 = _col_letter(col_start + 2)
            updates.append({
                "range": f"'{tab_name}'!{col_letter_1}{row_idx + 1}:{col_letter_3}{row_idx + 1}",
                "values": [[d["comments"], d["likes"], d["views"]]],
            })

    # Also append new posts not yet in tracker
    existing_pids = set(pid_to_row.keys())
    new_posts = [d for d in data if d["post_id"] not in existing_pids]
    if new_posts:
        next_row = len(existing) + 1
        new_rows = []
        for d in new_posts:
            d_plus = ""
            if d["post_date"]:
                try:
                    pd = datetime.strptime(d["post_date"], "%Y-%m-%d")
                    d_plus = (datetime.now() - pd).days
                except ValueError:
                    pass

            # Post ID: Posts Master로 HYPERLINK
            pid = d["post_id"]
            if pm_gid and pm_pid_to_row and pid in pm_pid_to_row:
                pm_row = pm_pid_to_row[pid]
                pid_cell = f'=HYPERLINK("#gid={pm_gid}&range=A{pm_row}","{pid}")'
            else:
                pid_cell = pid

            row = [
                pid_cell,
                safe_hl(d["url"], d["url"]),
                d["platform"],
                safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
                d["post_date"],
                d["tagged_account"],
                str(d_plus) if d_plus != "" else "",
                str(d["comments"]), str(d["likes"]), str(d["views"]),
            ]
            for dn in range(91):
                if isinstance(d_plus, int) and dn == d_plus and d_plus <= 90:
                    row += [str(d["comments"]), str(d["likes"]), str(d["views"])]
                else:
                    row += ["", "", ""]
            new_rows.append(row)

        # Auto-expand sheet if needed
        required_rows = next_row + len(new_rows) - 1
        current_rows = ws.row_count
        if required_rows > current_rows:
            ws.add_rows(required_rows - current_rows + 100)
            print(f"[{tab_name}] Expanded sheet to {current_rows + (required_rows - current_rows + 100)} rows")

        for i in range(0, len(new_rows), 40):
            ws.update(range_name=f"A{next_row + i}", values=new_rows[i:i+40],
                      value_input_option="USER_ENTERED")
            time.sleep(1)
        print(f"[{tab_name}] +{len(new_rows)} new posts appended")

    if updates:
        for i in range(0, len(updates), 200):
            ws.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": updates[i:i+200]}
            )
            time.sleep(1)
        print(f"[{tab_name}] D+N updated for {len(updates)//2} posts")
    else:
        print(f"[{tab_name}] No D+N updates needed")


def update_influencer_tracker(sh, data, tab_name, pm_tab_name=None):
    """크리에이터별 집계 탭. 최근 포스트 기준 내림차순 정렬."""
    if not data:
        print(f"[{tab_name}] No data - skipping (existing data preserved)")
        return

    headers = [
        "Username", "Nickname", "Platform", "Followers",
        "Last Post", "First Post", "Post Count",
        "Total Views", "Total Likes", "Total Comments",
    ]

    # 크리에이터별 집계
    creators = {}
    for d in data:
        u = d["username"]
        if u not in creators:
            creators[u] = {
                "nickname": d["nickname"] or "",
                "platform": d["platform"],
                "followers": d["followers"] or 0,
                "posts": [],
            }
        creators[u]["posts"].append(d)
        # 팔로워는 최신값으로 갱신
        if d["followers"]:
            creators[u]["followers"] = d["followers"]

    # Posts Master GID (Username → Posts Master 링크용)
    pm_gid = None
    if pm_tab_name:
        try:
            pm_ws = sh.worksheet(pm_tab_name)
            pm_gid = pm_ws.id
        except Exception:
            pass

    # 집계 + 정렬 (최근 포스트 내림차순)
    rows = []
    for username, info in creators.items():
        posts = info["posts"]
        dates = [p["post_date"] for p in posts if p["post_date"]]
        last_post = max(dates) if dates else ""
        first_post = min(dates) if dates else ""
        rows.append({
            "username": username,
            "nickname": info["nickname"],
            "platform": info["platform"],
            "followers": info["followers"],
            "last_post": last_post,
            "first_post": first_post,
            "post_count": len(posts),
            "total_views": sum(p["views"] or 0 for p in posts),
            "total_likes": sum(p["likes"] or 0 for p in posts),
            "total_comments": sum(p["comments"] or 0 for p in posts),
        })
    rows.sort(key=lambda x: x["last_post"] or "", reverse=True)

    # 시트 작성 (매번 전체 덮어쓰기 — 정렬 유지)
    try:
        ws = sh.worksheet(tab_name)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(tab_name, rows=len(rows) + 10, cols=len(headers))

    sheet_rows = [headers]
    for r in rows:
        u = r["username"]
        if pm_gid:
            username_cell = f'=HYPERLINK("#gid={pm_gid}&range=A1","{u}")'
        else:
            username_cell = u
        sheet_rows.append([
            username_cell,
            r["nickname"],
            r["platform"],
            r["followers"],
            r["last_post"],
            r["first_post"],
            r["post_count"],
            r["total_views"],
            r["total_likes"],
            r["total_comments"],
        ])

    required_rows = max(len(sheet_rows) + 5, ws.row_count)
    if len(sheet_rows) + 5 > ws.row_count:
        ws.add_rows(len(sheet_rows) + 5 - ws.row_count)

    for i in range(0, len(sheet_rows), 80):
        ws.update(range_name=f"A{i + 1}", values=sheet_rows[i:i + 80],
                  value_input_option="USER_ENTERED")
        time.sleep(0.5)
    print(f"[{tab_name}] {len(rows)} creators, sorted by last post")


def _col_letter(idx):
    result = ""
    while idx >= 0:
        result = chr(idx % 26 + 65) + result
        idx = idx // 26 - 1
    return result


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def send_email(summary):
    """Send completion email via send_gmail.py."""
    try:
        from send_gmail import send_email as gmail_send
        subject = f"[Apify Content Tracker] Daily Report {TODAY}"
        body = f"Apify Content Pipeline - {TODAY}\n\n"
        body += "== Pipeline Results ==\n"
        for region, info in summary.items():
            body += f"\n{region.upper()}:\n"
            body += f"  IG posts: {info.get('ig_count', 0)}\n"
            if "tt_count" in info:
                body += f"  TikTok posts: {info['tt_count']}\n"
            body += f"  Total: {info.get('total', 0)} posts, {info.get('creators', 0)} creators\n"
            body += f"  New posts added: {info.get('new_posts', 0)}\n"
            body += f"  D+60 updated: {info.get('d60_updated', True)}\n"
        body += f"\nSheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        gmail_send(
            to="wj.choi@orbiters.co.kr",
            subject=subject,
            body=body,
        )
        print(f"[EMAIL] Sent to wj.choi@orbiters.co.kr")
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def save_json(data, name):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{TODAY}_{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[SAVE] {path.name}")
    return path


def update_reference_tab(sh, summary):
    """Write a Reference tab with data freshness for every tab (PST timestamps)."""
    from datetime import timezone, timedelta
    pst = timezone(timedelta(hours=-8))
    now_pst = datetime.now(pst)
    now_str = now_pst.strftime("%Y-%m-%d %H:%M PST")

    rows = [
        ["Data Source", "Tab", "Rows", "Latest Post Date", "Last Updated (PST)", "Status"],
    ]

    tab_configs = [
        ("US Posts Master", "us"),
        ("US D+60 Tracker", "us"),
        ("US Influencer Tracker", "us"),
        ("JP Posts Master", "jp"),
        ("JP D+60 Tracker", "jp"),
        ("JP Influencer Tracker", "jp"),
    ]

    for tab_name, region_key in tab_configs:
        try:
            ws = sh.worksheet(tab_name)
            vals = ws.get_all_values()
            row_count = max(0, len(vals) - 1)  # exclude header

            latest_date = ""
            if "Posts Master" in tab_name and len(vals) > 1:
                # Post Date is col 10 (index 9)
                dates = [r[9] for r in vals[1:] if len(r) > 9 and r[9]]
                if dates:
                    latest_date = max(dates)

            status = "OK"
            if region_key in summary:
                s = summary[region_key]
                status = f"+{s.get('new_posts', 0)} new"
            else:
                status = "skipped"

            rows.append([tab_name, region_key.upper(), str(row_count), latest_date, now_str, status])
        except Exception as e:
            rows.append([tab_name, region_key.upper(), "?", "", now_str, f"error: {e}"])

    # Downstream sheets info
    rows.append(["", "", "", "", "", ""])
    rows.append(["--- Downstream Sheets ---", "", "", "", "", ""])
    downstream = [
        ("Grosmimi SNS", "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA",
         "US SNS", "https://docs.google.com/spreadsheets/d/1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"),
        ("CHA&MOM SNS", "16XUPd-VMoh6LEjSvupsmhkd1vEQNOTcoEhRCnPqkA_I",
         "SNS", "https://docs.google.com/spreadsheets/d/16XUPd-VMoh6LEjSvupsmhkd1vEQNOTcoEhRCnPqkA_I"),
    ]
    for name, sid, tab, url in downstream:
        rows.append([name, tab, "", "", now_str, safe_hl(url, "Open")])

    # Links section
    rows.append(["", "", "", "", "", ""])
    rows.append(["--- Quick Links ---", "", "", "", "", ""])
    rows.append(["Content Dashboard", "", "", "", "",
                 safe_hl("https://orbiters-dev.github.io/WJ-Test1/content-dashboard/index.html", "Open Dashboard")])
    rows.append(["GitHub Actions", "", "", "", "",
                 safe_hl("https://github.com/Orbiters-dev/WJ-Test1/actions/workflows/apify_daily.yml", "View Runs")])
    rows.append(["Apify Console", "", "", "", "",
                 safe_hl("https://console.apify.com/", "Open Apify")])
    rows.append(["OrbiTools Admin", "", "", "", "",
                 safe_hl("https://orbitools.orbiters.co.kr/admin/", "Open Admin")])
    rows.append(["Pipeline Visual", "", "", "", "",
                 safe_hl("https://orbiters-dev.github.io/WJ-Test1/content-dashboard/pipeline.html", "View Architecture")])

    # Write to Reference tab
    try:
        ws = sh.worksheet("Reference")
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Reference", rows=30, cols=6)

    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")

    # Format header row
    try:
        from gspread_formatting import format_cell_range, CellFormat, TextFormat, Color
        header_fmt = CellFormat(
            textFormat=TextFormat(bold=True, fontSize=10),
            backgroundColor=Color(0.13, 0.13, 0.16),
            textFormat__foregroundColorStyle=None,
        )
        # Simple bold header - skip complex formatting to avoid dep issues
    except ImportError:
        pass

    print(f"[REF] Reference tab updated: {len(rows)-1} rows at {now_str}")


def run_daily(region="all", dry_run=False, send_mail=True):
    summary = {}
    load_env()
    graph_token = os.environ.get("META_GRAPH_IG_TOKEN", "")
    use_graph = bool(graph_token)
    client = None if dry_run else get_client()

    # --- US ---
    if region in ("all", "us"):
        print("\n===== US Pipeline =====")

        # IG tagged — Graph API (free) or Apify fallback
        if dry_run:
            ig_path = max(OUTPUT_DIR.glob("*_us_tagged*.json"), key=os.path.getmtime, default=None)
            ig_raw = json.load(open(ig_path, encoding="utf-8")) if ig_path else []
            print(f"[DRY] Loaded {len(ig_raw)} from {ig_path}")
        elif use_graph:
            us_accounts = {k: v for k, v in IG_GRAPH_ACCOUNTS.items()
                           if k in ("onzenna.official", "grosmimi_usa")}
            ig_raw = fetch_ig_tagged_graph(us_accounts, graph_token)
            save_json(ig_raw, "us_tagged_raw")
        else:
            ig_raw = fetch_ig_tagged(client, US_TAGGED_URLS, limit=2000)
            save_json(ig_raw, "us_tagged_raw")

        # TikTok
        if dry_run:
            tt_path = max(OUTPUT_DIR.glob("*_us_tiktok*.json"), key=os.path.getmtime, default=None)
            tt_raw = json.load(open(tt_path, encoding="utf-8")) if tt_path else []
            print(f"[DRY] Loaded {len(tt_raw)} TikTok from {tt_path}")
        else:
            tt_raw = fetch_tiktok(client)
            save_json(tt_raw, "us_tiktok_raw")

        # IG profiles for follower data — new creators only
        ig_norm = normalize_ig(ig_raw)
        ig_usernames = set(d["username"] for d in ig_norm)
        fmap_path = max(OUTPUT_DIR.glob("*_us_follower_map.json"), key=os.path.getmtime, default=None)
        fmap = json.load(open(fmap_path, encoding="utf-8")) if fmap_path else {}
        if not dry_run and ig_usernames:
            new_usernames = ig_usernames - set(fmap.keys())
            if new_usernames:
                print(f"[PROFILE] {len(new_usernames)} new creators (skip {len(ig_usernames)-len(new_usernames)} known)")
                new_fmap = fetch_ig_profiles(client, new_usernames)
                fmap.update(new_fmap)
                save_json(fmap, "us_follower_map")
            else:
                print(f"[PROFILE] All {len(ig_usernames)} creators known - skipping Apify")

        # Re-normalize with follower data
        ig_norm = normalize_ig(ig_raw, fmap)
        tt_norm = normalize_tt(tt_raw)

        us_data = ig_norm + tt_norm
        us_data.sort(key=lambda x: x["post_date"] or "", reverse=True)
        us_creators = set(d["username"] for d in us_data)
        print(f"[US] Total: {len(us_data)} posts ({len(ig_norm)} IG + {len(tt_norm)} TT), {len(us_creators)} creators")

        # Fetch metrics for tracked posts via direct URL scraping
        # D+0~D+30: daily, D+31~D+90: Monday only (matches snapshot schedule)
        sh, creds = get_sheets()
        is_monday = datetime.now().weekday() == 0
        scrape_max_d = 90 if is_monday else 30
        if is_monday:
            print(f"[URL-SCRAPE] Monday -> expanded range D+0~D+{scrape_max_d}")
        if not dry_run:
            # TikTok: scrape posts missing from keyword search
            missing_tt_urls = get_missing_tiktok_urls(sh, "US D+60 Tracker", us_data, max_d_plus=scrape_max_d)
            if missing_tt_urls:
                tt_url_raw = fetch_tiktok_by_urls(client, missing_tt_urls)
                tt_url_norm = normalize_tt(tt_url_raw, skip_keyword_filter=True)
                us_data.extend(tt_url_norm)
                print(f"[US] +{len(tt_url_norm)} TikTok via URL scrape (gap fill, D+0~D+{scrape_max_d})")
            else:
                print(f"[US] No missing TikTok posts in D+0~D+{scrape_max_d} range")

            # IG: scrape ALL active posts for views (Graph API doesn't return views)
            active_ig_urls = get_active_ig_urls(sh, "US D+60 Tracker", max_d_plus=scrape_max_d)
            if active_ig_urls:
                ig_url_raw = fetch_ig_by_urls(client, active_ig_urls)
                ig_url_norm = normalize_ig(ig_url_raw, fmap)
                # Merge: update views for IG posts already in us_data
                existing_pids = {d["post_id"]: d for d in us_data}
                ig_url_added = 0
                for d in ig_url_norm:
                    if d["post_id"] in existing_pids:
                        existing_pids[d["post_id"]]["views"] = d["views"]
                        existing_pids[d["post_id"]]["likes"] = d["likes"]
                        existing_pids[d["post_id"]]["comments"] = d["comments"]
                    else:
                        us_data.append(d)
                        ig_url_added += 1
                print(f"[US] IG URL scrape: {len(ig_url_norm)} scraped, "
                      f"{len(ig_url_norm) - ig_url_added} updated, +{ig_url_added} new")
            else:
                print(f"[US] No active IG posts in D+0~D+{scrape_max_d} range")

        # Update sheets
        new_pm = update_posts_master(sh, us_data, "US Posts Master")
        time.sleep(1)
        pm_ws_us = sh.worksheet("US Posts Master")
        pm_pid_map_us = get_post_id_to_row(pm_ws_us)
        update_d60_tracker(sh, us_data, "US D+60 Tracker",
                           pm_tab_name="US Posts Master", pm_pid_to_row=pm_pid_map_us)
        time.sleep(1)
        update_influencer_tracker(sh, us_data, "US Influencer Tracker",
                                  pm_tab_name="US Posts Master")

        summary["us"] = {
            "ig_count": len(ig_norm), "tt_count": len(tt_norm),
            "total": len(us_data), "creators": len(us_creators),
            "new_posts": new_pm, "d60_updated": True,
        }

    # --- JP ---
    if region in ("all", "jp"):
        print("\n===== JP Pipeline =====")

        if dry_run:
            jp_path = max(OUTPUT_DIR.glob("*_jp_tagged*.json"), key=os.path.getmtime, default=None)
            jp_raw = json.load(open(jp_path, encoding="utf-8")) if jp_path else []
            print(f"[DRY] Loaded {len(jp_raw)} from {jp_path}")
        else:
            jp_raw = fetch_ig_tagged(client, JP_TAGGED_URLS, limit=500)
            save_json(jp_raw, "jp_tagged_raw")

        jp_norm = normalize_ig(jp_raw)
        jp_creators = set(d["username"] for d in jp_norm)
        print(f"[JP] Total: {len(jp_norm)} posts, {len(jp_creators)} creators")

        sh, creds = get_sheets()
        new_pm = update_posts_master(sh, jp_norm, "JP Posts Master")
        time.sleep(1)
        pm_ws_jp = sh.worksheet("JP Posts Master")
        pm_pid_map_jp = get_post_id_to_row(pm_ws_jp)
        update_d60_tracker(sh, jp_norm, "JP D+60 Tracker",
                           pm_tab_name="JP Posts Master", pm_pid_to_row=pm_pid_map_jp)
        time.sleep(1)
        update_influencer_tracker(sh, jp_norm, "JP Influencer Tracker",
                                  pm_tab_name="JP Posts Master")

        summary["jp"] = {
            "ig_count": len(jp_norm), "total": len(jp_norm),
            "creators": len(jp_creators), "new_posts": new_pm,
            "d60_updated": True,
        }

    # ── Brand/Product Enrichment ──
    print("\n===== Brand/Product Enrichment =====")
    all_posts_for_enrich = []
    if "us" in summary:
        all_posts_for_enrich.extend(us_data)
    if "jp" in summary:
        all_posts_for_enrich.extend(jp_norm)
    enrich_posts_from_orders(all_posts_for_enrich)

    # ── Push to PostgreSQL ──
    print("\n===== Push to PostgreSQL =====")
    try:
        from push_content_to_pg import push_posts, push_metrics

        all_posts = []
        all_metrics = []

        if "us" in summary:
            for p in us_data:
                p["region"] = "us"
                p["source"] = "apify"
                all_posts.append(p)
                all_metrics.append({
                    "post_id": p["post_id"],
                    "date": TODAY,
                    "comments": p.get("comments", 0),
                    "likes": p.get("likes", 0),
                    "views": p.get("views", 0),
                })

        if "jp" in summary:
            for p in jp_norm:
                p["region"] = "jp"
                p["source"] = "apify"
                all_posts.append(p)
                all_metrics.append({
                    "post_id": p["post_id"],
                    "date": TODAY,
                    "comments": p.get("comments", 0),
                    "likes": p.get("likes", 0),
                    "views": p.get("views", 0),
                })

        if all_posts:
            push_posts(all_posts)
            push_metrics(all_metrics)
            print(f"[PG] Pushed {len(all_posts)} posts + {len(all_metrics)} metrics")
        else:
            print("[PG] No posts to push")
    except Exception as e:
        print(f"[PG WARN] Push failed (non-fatal): {e}")

    # Reference tab (data freshness for all tabs)
    try:
        if not dry_run:
            update_reference_tab(sh, summary)
    except Exception as e:
        print(f"[REF WARN] Reference tab update failed (non-fatal): {e}")

    # Summary
    print("\n===== Daily Summary =====")
    print(f"Date: {TODAY}")
    for k, v in summary.items():
        print(f"  {k.upper()}: {v['total']} posts, {v['creators']} creators, +{v['new_posts']} new")

    # Email
    if send_mail and summary:
        send_email(summary)

    return summary


# ---------------------------------------------------------------------------
# Influencer upload scanner (Airtable → Apify → Posts Master)
# ---------------------------------------------------------------------------

def fetch_shopify_pr_handles() -> list:
    """Return unique IG handles from Shopify PR/sample orders (q10_influencer_orders.json)."""
    if not INFLUENCER_ORDERS_PATH.exists():
        print(f"[SHOPIFY] {INFLUENCER_ORDERS_PATH.name} not found - skipping")
        return []

    raw = json.loads(INFLUENCER_ORDERS_PATH.read_text(encoding="utf-8"))
    orders = raw.get("orders", raw) if isinstance(raw, dict) else raw

    handles = set()
    for order in orders:
        if not isinstance(order, dict):
            continue
        for text in (order.get("tags", "") or "", order.get("note", "") or ""):
            m = _IG_HANDLE_RE.search(text)
            if m:
                handles.add(m.group(1).lower().strip())
                break

    result = sorted(handles)
    print(f"[SHOPIFY] {len(result)} unique IG handles from PR/sample orders")
    return result


def normalize_ig_profile_posts(profile_items) -> list:
    """Normalize latestPosts from profile-scraper into the shared post format."""
    result, seen = [], set()
    for profile in profile_items:
        uname = (profile.get("username", "") or "").lower()
        followers = profile.get("followersCount", profile.get("followedByCount", 0)) or 0

        for post in (profile.get("latestPosts", []) or []):
            sc = post.get("shortCode", post.get("id", ""))
            if not sc or sc in seen or not uname or uname in EXCLUDE:
                continue
            seen.add(sc)
            ts = str(post.get("timestamp", "") or "")[:10]
            hashtags = post.get("hashtags", []) or []
            result.append({
                "post_id": sc,
                "url": post.get("url", "") or f"https://www.instagram.com/p/{sc}/",
                "platform": "instagram",
                "username": uname,
                "nickname": profile.get("fullName", "") or "",
                "followers": followers,
                "caption": (post.get("caption", "") or "")[:500],
                "hashtags": ", ".join(
                    h if isinstance(h, str) else h.get("name", "") for h in hashtags
                ),
                "tagged_account": "influencer_monitor",
                "post_date": ts,
                "comments": post.get("commentsCount", 0) or 0,
                "likes": post.get("likesCount", 0) or 0,
                "views": post.get("videoViewCount", 0) or 0,
            })
    return result


def run_influencer_scan(dry_run: bool = False) -> dict:
    """Scan Airtable active influencer profiles and add new posts to US Posts Master."""
    print("\n===== Influencer Upload Scan =====")
    load_env()

    # 1. Get handles from Airtable
    cache_path = OUTPUT_DIR / "influencer_handles_cache.json"
    if dry_run:
        handles = json.load(open(cache_path, encoding="utf-8")) if cache_path.exists() else []
        print(f"[DRY] {len(handles)} handles from cache")
    else:
        handles = fetch_shopify_pr_handles()
        if handles:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(handles, f)

    if not handles:
        print("[INFLUENCER] No active handles - done")
        return {"handles": 0, "new_posts": 0}

    # 2. Fetch recent posts via Apify (profile scraper, batches of 20)
    raw_cache = OUTPUT_DIR / f"{TODAY}_influencer_profiles.json"
    if dry_run:
        raw = json.load(open(raw_cache, encoding="utf-8")) if raw_cache.exists() else []
        print(f"[DRY] {len(raw)} profiles from cache")
    else:
        client = get_client()
        raw = []
        BATCH = 20
        for i in range(0, len(handles), BATCH):
            batch = handles[i:i + BATCH]
            print(f"[INFLUENCER] Profiles {i + 1}-{min(i + BATCH, len(handles))}/{len(handles)}...")
            try:
                run = client.actor(IG_PROFILE_SCRAPER).call(
                    run_input={"usernames": batch},
                    timeout_secs=300,
                )
                items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
                raw.extend(items)
                time.sleep(2)
            except Exception as e:
                print(f"[INFLUENCER] Batch {i // BATCH + 1} failed: {e}")
        save_json(raw, "influencer_profiles")

    # 3. Normalize into post format
    posts = normalize_ig_profile_posts(raw)
    print(f"[INFLUENCER] {len(posts)} posts extracted from {len(raw)} profiles")

    if not posts:
        return {"handles": len(handles), "new_posts": 0}

    # 4. Get existing post_ids from US Posts Master
    sh, _ = get_sheets()
    try:
        pm_ws = sh.worksheet("US Posts Master")
        existing_ids = set(pm_ws.col_values(1)[1:])  # col A, skip header
    except Exception as e:
        print(f"[INFLUENCER] Could not read US Posts Master: {e}")
        existing_ids = set()

    new_posts = [p for p in posts if p["post_id"] not in existing_ids]
    print(f"[INFLUENCER] {len(new_posts)} new posts not yet in Posts Master")

    if not new_posts:
        return {"handles": len(handles), "new_posts": 0}

    # 5. Add to US Posts Master + D+60 Tracker
    new_count = update_posts_master(sh, new_posts, "US Posts Master")
    time.sleep(1)
    pm_ws = sh.worksheet("US Posts Master")
    pm_pid_map = get_post_id_to_row(pm_ws)
    update_d60_tracker(sh, new_posts, "US D+60 Tracker",
                       pm_tab_name="US Posts Master", pm_pid_to_row=pm_pid_map)

    print(f"[INFLUENCER] Done: +{new_count} new posts added")
    return {"handles": len(handles), "new_posts": new_count}


def main():
    parser = argparse.ArgumentParser(description="Apify Content Pipeline")
    parser.add_argument("--daily", action="store_true", help="Run daily pipeline")
    parser.add_argument("--influencer-scan", action="store_true",
                        help="Scan active Airtable influencers for new posts")
    parser.add_argument("--region", default="all", choices=["all", "us", "jp"])
    parser.add_argument("--dry-run", action="store_true", help="Use cached JSON, no API calls")
    parser.add_argument("--no-email", action="store_true", help="Skip email notification")
    args = parser.parse_args()

    if args.daily:
        run_daily(region=args.region, dry_run=args.dry_run, send_mail=not args.no_email)
    elif args.influencer_scan:
        run_influencer_scan(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
