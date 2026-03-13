"""Data Keeper - Unified data collection gateway.

Runs twice daily (PST 0:00, 12:00). Collects ALL advertising and sales data
from external APIs, saves to PostgreSQL via orbitools API, and caches locally.

All consumer tools (PPC daily, Meta daily, financial model, etc.) read from
the Data Keeper cache/DB instead of calling APIs directly.

Usage:
    python tools/data_keeper.py                    # Collect all channels
    python tools/data_keeper.py --channel amazon   # Amazon only
    python tools/data_keeper.py --channel meta     # Meta only
    python tools/data_keeper.py --days 60          # Override lookback window
    python tools/data_keeper.py --skip-pg          # Local cache only (no PG push)
    python tools/data_keeper.py --status           # Show collection status
"""

import os
import sys
import json
import time
import gzip
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env
load_env()

# ── Config ────────────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(DIR, "..", ".tmp", "datakeeper")
os.makedirs(CACHE_DIR, exist_ok=True)

# Shared folder for team-wide access (Synology Drive syncs this)
SHARED_DIR = os.path.join(DIR, "..", "..", "Shared", "datakeeper", "latest")
SIGNALS_DIR = os.path.join(DIR, "..", "..", "Shared", "datakeeper", "data_signals")

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

PST = timezone(timedelta(hours=-8))
DEFAULT_LOOKBACK_DAYS = 35  # cover 30d + buffer

# ── Grosmimi Price History ─────────────────────────────────────────────────
# Grosmimi had a retail price increase around Feb-March 2025.
# For Amazon channel orders BEFORE this date, use old Shopify prices.
# All other brands and all D2C orders always use current Shopify prices.
# Source: Wholesale Price by Brand(Grosmimi).csv (2023 baseline retail prices)
GROSMIMI_PRICE_CUTOFF = "2025-03-01"

GROSMIMI_OLD_PRICES = {
    # PPSU Baby Bottle 10oz (300ml): $18.60 → $19.60
    45019086586178: 18.60,  # Olive White
    45019086618946: 18.60,  # Bear Pure Gold
    45019086651714: 18.60,  # Bear White
    45019086684482: 18.60,  # Cherry Pure Gold
    45019086717250: 18.60,  # Cherry Rose Gold
    # PPSU Baby Bottle 6oz (200ml): $17.40 → $18.40
    45019081539906: 17.40,  # Olive White
    45019081572674: 17.40,  # Bear Pure Gold
    45019081605442: 17.40,  # Bear White
    45019081638210: 17.40,  # Cherry Pure Gold
    45019081670978: 17.40,  # Cherry Rose Gold
    # PPSU Straw Cup 10oz (6M+): $21.90 → $24.90 (most colors)
    45018985595202: 21.90,  # Skyblue
    45018985529666: 21.90,  # Aquagreen
    45018985562434: 21.90,  # Pink
    45373972513090: 21.90,  # Butter
    45373972545858: 21.90,  # Peach
    # PPSU Straw Cup 10oz (6M+): $22.80 → $25.80 (White/Beige/Charcoal)
    45018985431362: 22.80,  # White
    45018985464130: 22.80,  # Beige
    45018985496898: 22.80,  # Charcoal
    # PPSU Straw Cup 6oz (6M+): $19.80 → $22.80 (most colors)
    45011792003394: 19.80,  # Skyblue
    45011792036162: 19.80,  # Pink
    45011792134466: 19.80,  # Aquagreen
    45373979197762: 19.80,  # Butter
    45373979230530: 19.80,  # Peach
    # PPSU Straw Cup 6oz (6M+): $20.79 → $23.80 (White/Beige/Charcoal)
    45011791970626: 20.79,  # White
    45011792101698: 20.79,  # Beige
    45011792068930: 20.79,  # Charcoal
    # PPSU Straw Cup with Flip Top 6oz (12M+): $24.90 → $25.90
    45751370711362: 24.90,  # Ocean Beige
    45751370744130: 24.90,  # Space White
    # Replacement Straw Kit Stage 1/2: $12.50 → $15.50
    45019595505986: 12.50,  # Stage 1
    45019590623554: 12.50,  # Stage 2
    # Replacement Straw Multipack Stage 2: $21.00 → $22.00
    45176565793090: 21.00,
    # Replacement Straw Nipple 4-counts Stage 2: $19.00 → $22.00
    45020465561922: 19.00,
    # Stainless Steel Food Tray 3 Compartment
    47142768738626: 11.50,  # Without suction ($11.50 → $14.30)
    47142768771394: 16.99,  # With suction ($16.99 → $20.30)
    # Stainless Steel Food Tray 5 Compartment
    45020423651650: 13.50,  # Without suction ($13.50 → $17.00)
    45020423618882: 18.99,  # With suction ($18.99 → $23.00)
    # Stainless Steel Straw Cup 10oz: $43.00 → $46.80
    47142838042946: 43.00,  # Cherry Peach
    47142887981378: 43.00,  # Olive Pistachio
    47142838010178: 43.00,  # Bear Butter
    # Stainless Steel Straw Cup 6oz: $33.90 → $38.90
    47142890668354: 33.90,  # Cherry Peach
    47142890733890: 33.90,  # Olive Pistachio
    47142890701122: 33.90,  # Bear Butter
    # Weighted Straw kit: $9.50 → $12.50
    45020599288130:  9.50,  # Stage 1
    45020622717250:  9.50,  # twin pack
    45020599845186:  9.50,  # with Nipple Stage 4
    45751602315586:  9.50,  # with Spout
}

# ── Credentials ───────────────────────────────────────────────────────────
# Amazon Ads
AMZ_ADS_CLIENT_ID = os.getenv("AMZ_ADS_CLIENT_ID", "")
AMZ_ADS_CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET", "")
AMZ_ADS_REFRESH_TOKEN = os.getenv("AMZ_ADS_REFRESH_TOKEN", "")

# Amazon SP-API
AMZ_SP_CLIENT_ID = os.getenv("AMZ_SP_CLIENT_ID", "")
AMZ_SP_CLIENT_SECRET = os.getenv("AMZ_SP_CLIENT_SECRET", "")
AMZ_SP_MARKETPLACE_ID = os.getenv("AMZ_SP_MARKETPLACE_ID", "ATVPDKIKX0DER")

SELLER_CONFIGS = [
    {
        "name": "Grosmimi USA", "brand": "Grosmimi",
        "refresh_token": os.getenv("AMZ_SP_REFRESH_TOKEN_GROSMIMI", ""),
        "client_id": os.getenv("AMZ_SP_GROSMIMI_CLIENT_ID") or AMZ_SP_CLIENT_ID,
        "client_secret": os.getenv("AMZ_SP_GROSMIMI_CLIENT_SECRET") or AMZ_SP_CLIENT_SECRET,
        "seller_id": "A3IA0XWP2WCD15",
    },
    {
        "name": "Fleeters", "brand": "Naeiae",
        "refresh_token": os.getenv("AMZ_SP_REFRESH_TOKEN_FLEETERS", ""),
        "client_id": AMZ_SP_CLIENT_ID,
        "client_secret": AMZ_SP_CLIENT_SECRET,
        "seller_id": "A2RE0E056TH6H3",
    },
    {
        "name": "Orbitool", "brand": "CHA&MOM",
        "refresh_token": os.getenv("AMZ_SP_REFRESH_TOKEN_ORBITOOL",
                                   os.getenv("AMZ_SP_REFRESH_TOKEN", "")),
        "client_id": AMZ_SP_CLIENT_ID,
        "client_secret": AMZ_SP_CLIENT_SECRET,
        "seller_id": "A3H2CLSAX0BTX6",
    },
]

# Meta Ads
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")

# Google Ads
GOOGLE_ADS_DEV_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "8625697405")

# GA4
GA4_CLIENT_ID = os.getenv("GA4_CLIENT_ID", "")
GA4_CLIENT_SECRET = os.getenv("GA4_CLIENT_SECRET", "")
GA4_REFRESH_TOKEN = os.getenv("GA4_REFRESH_TOKEN", "")
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")

# GSC (Google Search Console) — service account
GSC_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
GSC_SITES = [
    "https://onzenna.com/",
    "sc-domain:zezebaebae.com",
]

# DataForSEO
DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN", "")
DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD", "")

# DataForSEO keyword targets per brand (for ranking + volume tracking)
DATAFORSEO_KEYWORDS = {
    "Onzenna": [
        "onzenna", "onzenna sunscreen", "onzenna skincare", "korean sunscreen",
        "tinted sunscreen", "mineral sunscreen spf50",
    ],
    "Naeiae": [
        "pop rice snack", "naeiae pop rice snack", "baby rice crackers",
        "korean baby snack", "korean snacks", "pop rice", "rice snack baby",
        "떡뻥", "baby teething snacks", "organic rice puff",
    ],
    "Grosmimi": [
        "grosmimi", "baby teether", "silicone baby teether", "baby teething toy",
        "grosmimi teether", "baby chew toy",
    ],
    "CHA&MOM": [
        "cha and mom", "korean baby food", "korean infant snack", "chamom",
    ],
}

# Klaviyo
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")

# Shopify
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

# Amazon Ads profile -> brand mapping
PROFILE_BRAND_MAP = {
    "GROSMIMI USA": "Grosmimi",
    "Fleeters Inc": "Naeiae",
    "Orbitool": "CHA&MOM",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _save_cache(channel: str, data: list[dict]):
    """Save collected data to local JSON cache."""
    path = os.path.join(CACHE_DIR, f"{channel}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, ensure_ascii=False)
    print(f"  [Cache] {channel}: {len(data)} rows -> {path}")


def _load_cache(channel: str) -> list[dict]:
    """Load data from local cache."""
    path = os.path.join(CACHE_DIR, f"{channel}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _push_to_pg(table: str, rows: list[dict]):
    """Push rows to PostgreSQL via orbitools API."""
    if not rows:
        return
    # Chunk to avoid huge payloads
    chunk_size = 1000
    total_created = 0
    total_updated = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        try:
            resp = requests.post(
                f"{ORBITOOLS_BASE}/save/",
                json={"table": table, "rows": chunk},
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            if result.get("errors"):
                print(f"  [PG WARN] {table}: {len(result['errors'])} errors in chunk")
        except Exception as e:
            print(f"  [PG ERROR] {table} chunk {i//chunk_size}: {e}")
    print(f"  [PG] {table}: +{total_created} new, ~{total_updated} updated")


def _export_to_shared():
    """Export collected data + manifest to Shared folder for team access."""
    shared_parent = os.path.join(SHARED_DIR, "..")
    if not os.path.isdir(shared_parent):
        print("  [Shared] Shared/datakeeper/ not found, skipping export")
        return

    os.makedirs(SHARED_DIR, exist_ok=True)
    manifest = {"last_updated": datetime.now(timezone.utc).isoformat(), "channels": {}}

    for channel, (table, _) in CHANNEL_COLLECTORS.items():
        cache_path = os.path.join(CACHE_DIR, f"{table}.json")
        if not os.path.exists(cache_path):
            continue

        with open(cache_path, "r", encoding="utf-8") as f:
            rows = json.load(f)

        if not rows:
            continue

        # Copy to shared
        shared_path = os.path.join(SHARED_DIR, f"{table}.json")
        with open(shared_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, default=str, ensure_ascii=False)

        # Build manifest entry
        dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
        brands = sorted(set(r.get("brand", "") for r in rows if r.get("brand")))
        manifest["channels"][table] = {
            "status": "collecting",
            "last_collected": datetime.now(timezone.utc).isoformat(),
            "row_count": len(rows),
            "date_range": [dates[0], dates[-1]] if dates else [],
            "brands": brands,
        }

        print(f"  [Shared] {table}: {len(rows)} rows exported")

    # Write manifest
    manifest_path = os.path.join(SHARED_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str, ensure_ascii=False)
    print(f"  [Shared] manifest.json updated ({len(manifest['channels'])} channels)")


def _scan_signals():
    """Scan Shared/datakeeper/data_signals/ for new channel requests."""
    if not os.path.isdir(SIGNALS_DIR):
        return []

    signals = []
    for fname in os.listdir(SIGNALS_DIR):
        if not fname.endswith((".yaml", ".yml")):
            continue
        fpath = os.path.join(SIGNALS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # Simple YAML parsing (no PyYAML dependency)
            sig = {}
            for line in content.strip().split("\n"):
                if ":" in line and not line.strip().startswith("#") and not line.strip().startswith("-"):
                    key, val = line.split(":", 1)
                    sig[key.strip()] = val.strip()
            if sig.get("status") == "pending":
                signals.append({"file": fname, **sig})
        except Exception as e:
            print(f"  [Signal] Error reading {fname}: {e}")

    return signals


def _get_pst_today():
    return datetime.now(PST).date()


# ── Amazon Ads Token ──────────────────────────────────────────────────────

_amz_ads_token_cache = {"token": None, "expires": 0}

def _get_amz_ads_token():
    now = time.time()
    if _amz_ads_token_cache["token"] and now < _amz_ads_token_cache["expires"]:
        return _amz_ads_token_cache["token"]
    resp = requests.post("https://api.amazon.com/auth/o2/token", data={
        "grant_type": "refresh_token",
        "client_id": AMZ_ADS_CLIENT_ID,
        "client_secret": AMZ_ADS_CLIENT_SECRET,
        "refresh_token": AMZ_ADS_REFRESH_TOKEN,
    }, timeout=30)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    _amz_ads_token_cache["token"] = token
    _amz_ads_token_cache["expires"] = now + 2700  # 45min (Amazon tokens expire at 60min)
    return token


# ══════════════════════════════════════════════════════════════════════════
# CHANNEL COLLECTORS
# ══════════════════════════════════════════════════════════════════════════

def _fresh_amz_ads_headers():
    """Get Amazon Ads headers with a fresh access token."""
    token = _get_amz_ads_token()
    return {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def collect_amazon_ads(date_from: str, date_to: str) -> list[dict]:
    """Collect Amazon Ads campaign daily metrics (all profiles)."""
    print("[Amazon Ads] Collecting...")
    headers = _fresh_amz_ads_headers()

    # 1. Get profiles
    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
    print(f"  Profiles: {len(profiles)}")

    # 2. Get campaign names (for ID->name mapping)
    campaign_names = {}
    for p in profiles:
        pid = str(p["profileId"])
        pname = p.get("accountInfo", {}).get("name", pid)
        try:
            h = {**headers, "Amazon-Advertising-API-Scope": pid,
                 "Content-Type": "application/vnd.spCampaign.v3+json",
                 "Accept": "application/vnd.spCampaign.v3+json"}
            r = requests.post(
                "https://advertising-api.amazon.com/sp/campaigns/list",
                headers=h, json={"maxResults": 5000}, timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            camps = data if isinstance(data, list) else data.get("campaigns", [])
            for c in camps:
                cid = str(c.get("campaignId", ""))
                campaign_names[cid] = c.get("name", cid)
        except Exception as e:
            print(f"  [WARN] Campaign list for {pname}: {e}")

    # 3. Fetch daily reports (chunked)
    #    Amazon Ads async reports: max 60 days per report.
    #    Use 30-day chunks for backfill (>60 days), 7-day for normal runs.
    all_rows = []
    d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    total_days = (d_to - d_from).days
    chunk_days = 30 if total_days > 60 else 6  # bigger chunks for backfill

    for p in profiles:
        pid = str(p["profileId"])
        pname = p.get("accountInfo", {}).get("name", pid)
        brand = PROFILE_BRAND_MAP.get(pname, pname)
        # Refresh token for each profile to avoid expiry during long runs
        headers = _fresh_amz_ads_headers()
        h = {**headers, "Amazon-Advertising-API-Scope": pid}

        cur = d_from
        while cur <= d_to:
            chunk_end = min(cur + timedelta(days=chunk_days), d_to)
            report_rows = _fetch_amz_ads_report(
                h, pid, cur.isoformat(), chunk_end.isoformat()
            )
            for row in report_rows:
                cid = str(row.get("campaignId", ""))
                all_rows.append({
                    "date": row.get("date", ""),
                    "profile_id": pid,
                    "brand": brand,
                    "campaign_id": cid,
                    "campaign_name": campaign_names.get(cid, cid),
                    "ad_type": "SP",
                    "impressions": int(row.get("impressions", 0)),
                    "clicks": int(row.get("clicks", 0)),
                    "spend": float(row.get("cost", 0)),
                    "sales": float(row.get("sales14d", 0)),
                    "purchases": int(row.get("purchases14d", 0)),
                })
            cur = chunk_end + timedelta(days=1)
        print(f"  {pname} ({brand}): {sum(1 for r in all_rows if r['profile_id'] == pid)} rows")

    return all_rows


def _fetch_amz_ads_report(headers, profile_id, start, end):
    """Submit, poll, download a single Amazon Ads report chunk."""
    body = {
        "reportDate": None,
        "startDate": start,
        "endDate": end,
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["campaign"],
            "columns": ["date", "campaignId", "impressions", "clicks",
                        "cost", "sales14d", "purchases14d"],
            "reportTypeId": "spCampaigns",
            "timeUnit": "DAILY",
            "format": "GZIP_JSON",
        },
    }
    try:
        r = requests.post(
            "https://advertising-api.amazon.com/reporting/reports",
            headers=headers, json=body, timeout=30,
        )
        r.raise_for_status()
        report_id = r.json().get("reportId")

        # Poll (refresh headers each iteration to avoid token expiry)
        for _ in range(40):  # 40 * 15s = 10min max
            time.sleep(15)
            headers = {**_fresh_amz_ads_headers(),
                       "Amazon-Advertising-API-Scope": profile_id}
            r2 = requests.get(
                f"https://advertising-api.amazon.com/reporting/reports/{report_id}",
                headers=headers, timeout=30,
            )
            r2.raise_for_status()
            status = r2.json().get("status")
            if status == "COMPLETED":
                url = r2.json().get("url")
                r3 = requests.get(url, timeout=60)
                r3.raise_for_status()
                raw = gzip.decompress(r3.content)
                return json.loads(raw)
            elif status == "FAILURE":
                print(f"    [WARN] Report failed: {start}~{end}")
                return []
        print(f"    [WARN] Report timeout: {start}~{end}")
        return []
    except Exception as e:
        print(f"    [ERROR] Report {start}~{end}: {e}")
        return []


def collect_amazon_sales(date_from: str, date_to: str) -> list[dict]:
    """Collect Amazon SP-API sales (all sellers)."""
    print("[Amazon Sales] Collecting...")
    all_rows = []

    for seller in SELLER_CONFIGS:
        if not seller["refresh_token"]:
            print(f"  [SKIP] {seller['name']}: no refresh token")
            continue

        # Get SP-API access token
        try:
            r = requests.post("https://api.amazon.com/auth/o2/token", data={
                "grant_type": "refresh_token",
                "client_id": seller["client_id"],
                "client_secret": seller["client_secret"],
                "refresh_token": seller["refresh_token"],
            }, timeout=30)
            r.raise_for_status()
            sp_token = r.json()["access_token"]
        except Exception as e:
            print(f"  [ERROR] {seller['name']} token: {e}")
            continue

        sp_headers = {
            "x-amz-access-token": sp_token,
            "Content-Type": "application/json",
        }

        # Fetch flat-file orders report (30-day chunks)
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        cur = d_from
        seller_rows = []

        while cur <= d_to:
            chunk_end = min(cur + timedelta(days=29), d_to)
            rows = _fetch_sp_orders(sp_headers, cur.isoformat(), chunk_end.isoformat(),
                                     seller, AMZ_SP_MARKETPLACE_ID)
            seller_rows.extend(rows)
            cur = chunk_end + timedelta(days=1)

        all_rows.extend(seller_rows)
        print(f"  {seller['name']} ({seller['brand']}): {len(seller_rows)} rows")

    return all_rows


def _fetch_sp_orders(headers, start, end, seller, marketplace_id):
    """Fetch SP-API flat-file orders report for a date range."""
    try:
        body = {
            "reportType": "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL",
            "dataStartTime": f"{start}T00:00:00Z",
            "dataEndTime": f"{end}T23:59:59Z",
            "marketplaceIds": [marketplace_id],
        }
        r = requests.post(
            "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
            headers=headers, json=body, timeout=30,
        )
        if r.status_code >= 400:
            print(f"    [ERROR] SP report {start}~{end}: {r.status_code} {r.text[:200]}")
            return []
        r.raise_for_status()
        report_id = r.json().get("reportId")

        # Poll for completion
        for _ in range(60):
            time.sleep(10)
            r2 = requests.get(
                f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports/{report_id}",
                headers=headers, timeout=30,
            )
            r2.raise_for_status()
            status = r2.json().get("processingStatus")
            if status == "DONE":
                doc_id = r2.json().get("reportDocumentId")
                break
            elif status in ("CANCELLED", "FATAL"):
                return []
        else:
            return []

        # Download document
        r3 = requests.get(
            f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/documents/{doc_id}",
            headers=headers, timeout=30,
        )
        r3.raise_for_status()
        doc = r3.json()
        dl_url = doc.get("url")
        r4 = requests.get(dl_url, timeout=60)
        r4.raise_for_status()

        content = r4.content
        if doc.get("compressionAlgorithm") == "GZIP":
            content = gzip.decompress(content)

        # Parse TSV
        lines = content.decode("utf-8", errors="replace").strip().split("\n")
        if len(lines) < 2:
            return []

        header = lines[0].split("\t")
        daily_agg = {}
        for line in lines[1:]:
            cols = line.split("\t")
            row = dict(zip(header, cols))
            date_str = (row.get("purchase-date") or row.get("order-date", ""))[:10]
            if not date_str:
                continue
            channel = "Target+" if "target" in row.get("sales-channel", "").lower() else "Amazon"
            key = (date_str, channel)
            if key not in daily_agg:
                daily_agg[key] = {
                    "date": date_str,
                    "seller_id": seller["seller_id"],
                    "brand": seller["brand"],
                    "channel": channel,
                    "gross_sales": 0, "net_sales": 0, "orders": 0,
                    "units": 0, "fees": 0, "refunds": 0,
                }
            try:
                amt = float(row.get("item-price", 0) or 0)
                qty = int(row.get("quantity", 1) or 1)
            except (ValueError, TypeError):
                amt, qty = 0, 1
            daily_agg[key]["gross_sales"] += amt
            daily_agg[key]["orders"] += 1
            daily_agg[key]["units"] += qty
            fee_rate = 0.08 if channel == "Target+" else 0.15
            daily_agg[key]["fees"] += amt * fee_rate
            daily_agg[key]["net_sales"] += amt * (1 - fee_rate)

        return list(daily_agg.values())

    except Exception as e:
        print(f"    [ERROR] SP report {start}~{end}: {e}")
        return []


def collect_meta_ads(date_from: str, date_to: str) -> list[dict]:
    """Collect Meta Ads ad-level daily insights."""
    print("[Meta Ads] Collecting...")
    if not META_ACCESS_TOKEN:
        print("  [SKIP] No META_ACCESS_TOKEN")
        return []

    acct = META_AD_ACCOUNT_ID if META_AD_ACCOUNT_ID.startswith("act_") else f"act_{META_AD_ACCOUNT_ID}"
    base = f"https://graph.facebook.com/v18.0/{acct}"

    # 1. Campaign objectives
    objectives = {}
    url = f"{base}/campaigns?fields=id,name,objective,status&limit=500&access_token={META_ACCESS_TOKEN}"
    while url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        for c in data.get("data", []):
            objectives[c["id"]] = {
                "name": c.get("name", ""),
                "objective": c.get("objective", ""),
                "status": c.get("status", ""),
            }
        url = data.get("paging", {}).get("next")
    print(f"  Campaigns: {len(objectives)}")

    # 2. Ad landing URLs
    landing_urls = {}
    url = f"{base}/ads?fields=id,creative{{effective_object_story_spec{{link_data{{link}}}}}}&limit=500&access_token={META_ACCESS_TOKEN}"
    while url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            for ad in data.get("data", []):
                try:
                    link = ad["creative"]["effective_object_story_spec"]["link_data"]["link"]
                    landing_urls[ad["id"]] = link
                except (KeyError, TypeError):
                    pass
            url = data.get("paging", {}).get("next")
        except Exception:
            break
    print(f"  Ads with URLs: {len(landing_urls)}")

    # 3. Daily insights (15-day chunks)
    all_rows = []
    d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    cur = d_from

    while cur <= d_to:
        chunk_end = min(cur + timedelta(days=14), d_to)
        url = (f"{base}/insights?level=ad&time_increment=1"
               f"&time_range={{\"since\":\"{cur.isoformat()}\",\"until\":\"{chunk_end.isoformat()}\"}}"
               f"&fields=ad_id,ad_name,campaign_id,campaign_name,adset_id,adset_name,"
               f"impressions,clicks,spend,reach,frequency,actions,action_values"
               f"&limit=500&access_token={META_ACCESS_TOKEN}")
        page_count = 0
        while url:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            data = r.json()
            for row in data.get("data", []):
                cid = row.get("campaign_id", "")
                camp_info = objectives.get(cid, {})
                obj = camp_info.get("objective", "")
                ctype = "traffic" if obj in (
                    "LINK_CLICKS", "POST_ENGAGEMENT", "REACH",
                    "BRAND_AWARENESS", "VIDEO_VIEWS"
                ) else "cvr"

                # Extract purchases from actions
                purchases = 0
                purchase_value = 0
                for a in (row.get("actions") or []):
                    if a.get("action_type") == "purchase":
                        purchases = int(a.get("value", 0))
                for av in (row.get("action_values") or []):
                    if av.get("action_type") == "purchase":
                        purchase_value = float(av.get("value", 0))

                # Brand detection from campaign name or landing URL
                cname = row.get("campaign_name", "")
                landing = landing_urls.get(row.get("ad_id", ""), "")
                brand = _detect_meta_brand(cname, landing)

                all_rows.append({
                    "date": row.get("date_start", ""),
                    "ad_id": row.get("ad_id", ""),
                    "ad_name": row.get("ad_name", ""),
                    "campaign_id": cid,
                    "campaign_name": cname,
                    "adset_id": row.get("adset_id", ""),
                    "adset_name": row.get("adset_name", ""),
                    "brand": brand,
                    "campaign_type": ctype,
                    "objective": obj,
                    "impressions": int(row.get("impressions", 0)),
                    "clicks": int(row.get("clicks", 0)),
                    "spend": float(row.get("spend", 0)),
                    "reach": int(row.get("reach", 0)),
                    "frequency": float(row.get("frequency", 0)),
                    "purchases": purchases,
                    "purchase_value": purchase_value,
                    "landing_url": landing,
                })
            url = data.get("paging", {}).get("next")
            page_count += 1
        print(f"  {cur} ~ {chunk_end}: {page_count} pages")
        cur = chunk_end + timedelta(days=1)

    print(f"  Total: {len(all_rows)} rows")
    return all_rows


def _detect_meta_brand(campaign_name: str, landing_url: str) -> str:
    """Detect brand from campaign name or landing URL."""
    cn = campaign_name.lower()
    lu = landing_url.lower()
    if any(k in cn or k in lu for k in ["grosmimi", "grosm"]):
        return "Grosmimi"
    if any(k in cn or k in lu for k in ["cha&mom", "chaandmom", "chamom", "cha_mom", "orbitool"]):
        return "CHA&MOM"
    if any(k in cn or k in lu for k in ["naeiae", "fleeters"]):
        return "Naeiae"
    if any(k in cn or k in lu for k in ["onzenna", "zezebaebae"]):
        return "Onzenna"
    if any(k in cn or k in lu for k in ["alpremio"]):
        return "Alpremio"
    return "Unknown"


def collect_google_ads(date_from: str, date_to: str) -> list[dict]:
    """Collect Google Ads campaign daily metrics."""
    print("[Google Ads] Collecting...")
    if not GOOGLE_ADS_DEV_TOKEN:
        print("  [SKIP] No GOOGLE_ADS_DEVELOPER_TOKEN")
        return []

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("  [SKIP] google-ads package not installed")
        return []

    config = {
        "developer_token": GOOGLE_ADS_DEV_TOKEN,
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)
    ga_service = client.get_service("GoogleAdsService")

    # Discover sub-accounts
    query_accounts = """
        SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager
        FROM customer_client
        WHERE customer_client.manager = false AND customer_client.status = 'ENABLED'
    """
    all_rows = []

    try:
        stream = ga_service.search_stream(
            customer_id=GOOGLE_ADS_LOGIN_CUSTOMER_ID,
            query=query_accounts,
        )
        sub_accounts = []
        for batch in stream:
            for row in batch.results:
                sub_accounts.append({
                    "id": str(row.customer_client.id),
                    "name": row.customer_client.descriptive_name,
                })
        print(f"  Sub-accounts: {len(sub_accounts)}")
    except Exception as e:
        print(f"  [ERROR] Account discovery: {e}")
        return []

    for acct in sub_accounts:
        query = f"""
            SELECT campaign.id, campaign.name, campaign.advertising_channel_type,
                   segments.date,
                   metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND campaign.status != 'REMOVED'
            ORDER BY segments.date
        """
        try:
            stream = ga_service.search_stream(customer_id=acct["id"], query=query)
            for batch in stream:
                for row in batch.results:
                    all_rows.append({
                        "date": row.segments.date,
                        "customer_id": acct["id"],
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                        "brand": _detect_google_brand(row.campaign.name),
                        "campaign_type": str(row.campaign.advertising_channel_type).replace("AdvertisingChannelType.", ""),
                        "impressions": row.metrics.impressions,
                        "clicks": row.metrics.clicks,
                        "spend": row.metrics.cost_micros / 1_000_000,
                        "conversions": float(row.metrics.conversions),
                        "conversion_value": float(row.metrics.conversions_value),
                    })
        except Exception as e:
            print(f"  [WARN] {acct['name']}: {e}")

    print(f"  Total: {len(all_rows)} rows")
    return all_rows


def _detect_google_brand(campaign_name: str) -> str:
    cn = campaign_name.lower()
    if "grosmimi" in cn:
        return "Grosmimi"
    if any(k in cn for k in ["cha&mom", "chamom", "cha_mom", "orbitool"]):
        return "CHA&MOM"
    if "naeiae" in cn or "fleeters" in cn:
        return "Naeiae"
    if "onzenna" in cn:
        return "Onzenna"
    if "alpremio" in cn:
        return "Alpremio"
    return "Unknown"


def collect_ga4(date_from: str, date_to: str) -> list[dict]:
    """Collect GA4 daily sessions and purchases."""
    print("[GA4] Collecting...")
    if not GA4_PROPERTY_ID:
        print("  [SKIP] No GA4_PROPERTY_ID")
        return []

    # Get access token
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "refresh_token",
            "client_id": GA4_CLIENT_ID,
            "client_secret": GA4_CLIENT_SECRET,
            "refresh_token": GA4_REFRESH_TOKEN,
        }, timeout=30)
        r.raise_for_status()
        ga4_token = r.json()["access_token"]
    except Exception as e:
        print(f"  [ERROR] GA4 token: {e}")
        return []

    body = {
        "dateRanges": [{"startDate": date_from, "endDate": date_to}],
        "dimensions": [
            {"name": "date"},
            {"name": "sessionDefaultChannelGrouping"},
        ],
        "metrics": [
            {"name": "sessions"},
            {"name": "ecommercePurchases"},
        ],
    }
    try:
        r = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:runReport",
            headers={"Authorization": f"Bearer {ga4_token}"},
            json=body, timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        rows = []
        for row in data.get("rows", []):
            dims = row.get("dimensionValues", [])
            mets = row.get("metricValues", [])
            date_raw = dims[0]["value"] if dims else ""
            date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(date_raw) == 8 else date_raw
            rows.append({
                "date": date_str,
                "channel_grouping": dims[1]["value"] if len(dims) > 1 else "(all)",
                "sessions": int(mets[0]["value"]) if mets else 0,
                "purchases": int(mets[1]["value"]) if len(mets) > 1 else 0,
            })
        print(f"  Total: {len(rows)} rows")
        return rows
    except Exception as e:
        print(f"  [ERROR] GA4 report: {e}")
        return []


def collect_gsc(date_from: str, date_to: str) -> list[dict]:
    """Collect Google Search Console search analytics (clicks, impressions, CTR, position)."""
    print("[GSC] Collecting...")
    if not os.path.exists(GSC_SERVICE_ACCOUNT_PATH):
        print(f"  [SKIP] No service account at {GSC_SERVICE_ACCOUNT_PATH}")
        return []

    try:
        import google.oauth2.service_account as sa_module
        import google.auth.transport.requests as tr_module
        creds = sa_module.Credentials.from_service_account_file(
            GSC_SERVICE_ACCOUNT_PATH,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        creds.refresh(tr_module.Request())
        token = creds.token
    except Exception as e:
        print(f"  [ERROR] GSC auth: {e}")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    all_rows = []

    for site_url in GSC_SITES:
        encoded = requests.utils.quote(site_url, safe="")
        body = {
            "startDate": date_from,
            "endDate": date_to,
            "dimensions": ["date", "query"],
            "rowLimit": 5000,
            "dataState": "final",
        }
        try:
            r = requests.post(
                f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query",
                headers=headers, json=body, timeout=60,
            )
            if r.status_code == 403:
                print(f"  [SKIP] {site_url} — no access (403)")
                continue
            r.raise_for_status()
            for row in r.json().get("rows", []):
                keys = row.get("keys", [])
                all_rows.append({
                    "date": keys[0] if keys else date_to,
                    "site_url": site_url,
                    "query": keys[1] if len(keys) > 1 else "(unknown)",
                    "clicks": int(row.get("clicks", 0)),
                    "impressions": int(row.get("impressions", 0)),
                    "ctr": round(float(row.get("ctr", 0)), 4),
                    "position": round(float(row.get("position", 0)), 1),
                })
            print(f"  {site_url}: {len(r.json().get('rows', []))} rows")
        except Exception as e:
            print(f"  [ERROR] {site_url}: {e}")

    print(f"  Total GSC rows: {len(all_rows)}")
    return all_rows


def collect_dataforseo(date_from: str, date_to: str) -> list[dict]:
    """Collect keyword search volumes via Google Ads Keyword Planner API.

    Replaces DataForSEO (2026-03-09) — same data, zero cost, direct source.
    Uses GenerateKeywordHistoricalMetrics for exact volume per keyword.
    """
    print("[Keywords] Collecting via Google Ads Keyword Planner...")
    if not GOOGLE_ADS_DEV_TOKEN:
        print("  [SKIP] No GOOGLE_ADS_DEVELOPER_TOKEN")
        return []

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("  [SKIP] google-ads package not installed")
        return []

    config = {
        "developer_token": GOOGLE_ADS_DEV_TOKEN,
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)

    # Find first active sub-account for keyword planner access
    ga_service = client.get_service("GoogleAdsService")
    kp_service = client.get_service("KeywordPlanIdeaService")

    try:
        stream = ga_service.search_stream(
            customer_id=GOOGLE_ADS_LOGIN_CUSTOMER_ID,
            query="""SELECT customer_client.id, customer_client.descriptive_name
                     FROM customer_client
                     WHERE customer_client.manager = false AND customer_client.status = 'ENABLED'""",
        )
        customer_id = None
        for batch in stream:
            for row in batch.results:
                customer_id = str(row.customer_client.id)
                break
            if customer_id:
                break
        if not customer_id:
            print("  [SKIP] No active sub-account found")
            return []
        print(f"  Using account: {customer_id}")
    except Exception as e:
        print(f"  [ERROR] Account discovery: {e}")
        return []

    # Build keyword -> brand mapping
    all_keywords = []
    kw_brand_map = {}
    for brand, kws in DATAFORSEO_KEYWORDS.items():
        for kw in kws:
            all_keywords.append(kw)
            kw_brand_map[kw.lower()] = brand

    # Call GenerateKeywordHistoricalMetrics
    results = []
    try:
        request = client.get_type("GenerateKeywordHistoricalMetricsRequest")
        request.customer_id = customer_id
        request.keywords.extend(all_keywords)
        # US location
        request.geo_target_constants.append(
            client.get_service("GeoTargetConstantService").geo_target_constant_path(2840)
        )
        # English
        request.language = client.get_service("GoogleAdsService").language_constant_path(1000)

        response = kp_service.generate_keyword_historical_metrics(request=request)

        for result in response.results:
            kw = result.text
            metrics = result.keyword_metrics
            # Monthly search volumes
            monthly = []
            for m in metrics.monthly_search_volumes:
                monthly.append({
                    "year": m.year,
                    "month": m.month.value if hasattr(m.month, 'value') else int(m.month),
                    "monthly_searches": m.monthly_searches,
                })

            # Competition enum to string
            comp_enum = str(metrics.competition).split(".")[-1] if metrics.competition else ""

            results.append({
                "date": date_to,
                "keyword": kw,
                "brand": kw_brand_map.get(kw.lower(), "Unknown"),
                "search_volume": metrics.avg_monthly_searches or 0,
                "cpc": round((metrics.high_top_of_page_bid_micros or 0) / 1_000_000, 2),
                "competition_index": metrics.competition_index or 0,
                "competition": comp_enum,
                "monthly_searches": json.dumps(monthly),
            })

    except Exception as e:
        print(f"  [ERROR] Keyword Planner: {e}")

    print(f"  Total keyword rows: {len(results)}")
    return results


def collect_klaviyo(date_from: str, date_to: str) -> list[dict]:
    """Collect Klaviyo campaign/flow daily metrics."""
    print("[Klaviyo] Collecting...")
    if not KLAVIYO_API_KEY:
        print("  [SKIP] No KLAVIYO_API_KEY")
        return []

    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "accept": "application/json",
        "revision": "2024-10-15",
    }

    all_rows = []

    # Campaigns list
    url = "https://a.klaviyo.com/api/campaigns/?filter=equals(messages.channel,'email')"
    campaigns = []
    while url:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            for c in data.get("data", []):
                attrs = c.get("attributes", {})
                campaigns.append({
                    "id": c["id"],
                    "name": attrs.get("name", ""),
                    "send_time": (attrs.get("send_time") or "")[:10],
                })
            url = data.get("links", {}).get("next")
        except Exception as e:
            print(f"  [WARN] Campaigns list: {e}")
            break

    # Filter to date range
    for camp in campaigns:
        if camp["send_time"] and date_from <= camp["send_time"] <= date_to:
            all_rows.append({
                "date": camp["send_time"],
                "source_type": "campaign",
                "source_name": camp["name"],
                "source_id": camp["id"],
                "sends": 0, "opens": 0, "clicks": 0,
                "conversions": 0, "revenue": 0,
            })

    print(f"  Campaigns in range: {len(all_rows)}")
    return all_rows


def _fetch_variant_prices(base: str, headers: dict) -> tuple:
    """Fetch all product variant prices from Shopify.

    Returns two dicts:
      d2c_prices   {vid: compare_at_price ?? price}  — D2C/ONZ reference (MSRP)
      amazon_prices {vid: price}                      — Amazon reference (Shopify base price)

    D2C discount = (compare_at_price ?? price) - actual_paid  (captures Shopify sale events)
    Amazon discount = (shopify_price - amazon_selling_price)   (captures channel pricing gap)
    """
    d2c_prices = {}
    amazon_prices = {}
    url = f"{base}/products.json?limit=250&fields=id,variants"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        for product in r.json().get("products", []):
            for v in product.get("variants", []):
                vid = v["id"]
                base_price    = float(v.get("price") or 0)
                compare_price = float(v.get("compare_at_price") or 0)
                d2c_prices[vid]    = compare_price if compare_price > 0 else base_price
                amazon_prices[vid] = base_price   # Shopify regular price (no compare_at)
        link = r.headers.get("Link", "")
        url = None
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]
    print(f"  Variant price map: {len(d2c_prices)} variants loaded")
    return d2c_prices, amazon_prices


def collect_shopify(date_from: str, date_to: str) -> list[dict]:
    """Collect Shopify orders aggregated daily by brand/channel.

    ONZ/D2C channels: discount = (compare_at_price ?? price) - actual_paid
    Amazon channel:   discount = (shopify_base_price - amazon_selling_price) + coupon
    → Amazon uses Shopify 'price' as reference (NOT compare_at_price) to avoid inflation.
    """
    print("[Shopify] Collecting...")
    if not SHOPIFY_SHOP or not SHOPIFY_ACCESS_TOKEN:
        print("  [SKIP] No Shopify credentials")
        return []

    shop = SHOPIFY_SHOP.replace(".myshopify.com", "") if ".myshopify.com" in SHOPIFY_SHOP else SHOPIFY_SHOP
    base = f"https://{shop}.myshopify.com/admin/api/2024-01"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    # Load variant prices: d2c uses compare_at_price??price, amazon uses base price only
    d2c_prices, amazon_prices = _fetch_variant_prices(base, headers)

    all_orders = []
    url = (f"{base}/orders.json?status=any&limit=250"
           f"&created_at_min={date_from}T00:00:00-08:00"
           f"&created_at_max={date_to}T23:59:59-08:00"
           f"&fields=id,created_at,source_name,line_items,tags,financial_status,gateway")

    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        orders = r.json().get("orders", [])
        all_orders.extend(orders)
        link = r.headers.get("Link", "")
        url = None
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]

    print(f"  Orders fetched: {len(all_orders)}")

    # Aggregate daily by brand/channel using line-item level pricing
    daily = {}
    for order in all_orders:
        date_str = order["created_at"][:10]
        tags   = (order.get("tags")        or "").lower()
        source = (order.get("source_name") or "").lower()

        # Channel detection (order level)
        # NOTE: "amazon" in tags catches multiple cases — order matters:
        #  1. Faire B2B wholesale → B2B (Faire tag present)
        #  2. FBA MCF fulfilled ("Exported To Amazon by WebBee App") → D2C
        #  3. FBA MCF rejected ("Rejected by Amazon - WebBee app") → D2C
        #     Both 2 & 3 are Shopify DTC sales; Amazon is just fulfillment logistics
        #  4. True Amazon Marketplace orders don't come through Shopify (they're in amazon_sales_daily via SP-API)
        if "faire" in tags:
            channel = "B2B"
        elif "exported to amazon" in tags or "amazon status" in tags or "rejected by amazon" in tags:
            channel = "D2C"   # FBA MCF (fulfilled or rejected): sale is on Shopify, not Amazon Marketplace
        elif "amazon" in tags or "amazon" in source:
            channel = "Amazon"
        elif "tiktok" in tags or "tiktok" in source:
            channel = "TikTok"
        elif any(k in tags for k in ["b2b", "wholesale"]):
            channel = "B2B"
        elif any(k in tags for k in ["pr", "sample", "supporter"]):
            channel = "PR"
        else:
            channel = "D2C"

        # Brand detection (order level, from line items)
        brand = _detect_shopify_brand(order.get("line_items", []))

        # Compute gross/discount/net from line items
        # - ONZ/D2C channels: list_price = compare_at_price ?? price (Shopify MSRP ref)
        # - Amazon channel: sell_price IS the reference price; discount = promo only
        gross = net = discount = 0.0
        units = 0
        for li in order.get("line_items", []):
            vid        = li.get("variant_id")
            qty        = int(li.get("quantity", 1) or 1)
            sell_price = float(li.get("price", 0) or 0)        # unit price before coupon
            line_disc  = float(li.get("total_discount", 0) or 0)  # coupon/promo on this line

            if channel == "Amazon":
                # Amazon: ref = Shopify base price (price, NOT compare_at_price)
                # For Grosmimi orders before March 2025, use pre-price-increase prices.
                if brand == "Grosmimi" and date_str < GROSMIMI_PRICE_CUTOFF:
                    ref_price = GROSMIMI_OLD_PRICES.get(vid, amazon_prices.get(vid, sell_price))
                else:
                    ref_price = amazon_prices.get(vid, sell_price)
                # If Amazon listed above Shopify ref (premium pricing), treat as 0 discount
                ref_price = max(ref_price, sell_price)
                gross    += ref_price * qty
                net      += sell_price * qty - line_disc
                discount += (ref_price - sell_price) * qty + line_disc
            else:
                # D2C/ONZ: ref = compare_at_price ?? price (Shopify MSRP)
                list_price = d2c_prices.get(vid, sell_price)
                gross    += list_price * qty
                net      += sell_price * qty - line_disc
                discount += list_price * qty - (sell_price * qty - line_disc)
            units    += qty

        key = (date_str, brand, channel)
        if key not in daily:
            daily[key] = {
                "date": date_str, "brand": brand, "channel": channel,
                "gross_sales": 0.0, "discounts": 0.0, "net_sales": 0.0,
                "orders": 0, "units": 0, "refunds": 0,
            }
        daily[key]["gross_sales"] += gross
        daily[key]["discounts"]   += discount
        daily[key]["net_sales"]   += net
        daily[key]["orders"]      += 1
        daily[key]["units"]       += units

    rows = list(daily.values())
    print(f"  Daily aggregated: {len(rows)} rows")
    return rows


def _detect_shopify_brand(line_items):
    """Detect brand from Shopify line items."""
    for li in line_items:
        title = (li.get("title") or "").lower()
        vendor = (li.get("vendor") or "").lower()
        combined = f"{title} {vendor}"
        if "grosmimi" in combined:
            return "Grosmimi"
        if any(k in combined for k in ["cha&mom", "chamom", "orbitool"]):
            return "CHA&MOM"
        if "naeiae" in combined:
            return "Naeiae"
        if "onzenna" in combined:
            return "Onzenna"
        if "alpremio" in combined:
            return "Alpremio"
    return "Unknown"


# ── Campaign Metadata Collectors ─────────────────────────────────────────

def collect_amazon_campaigns(date_from: str, date_to: str) -> list[dict]:
    """Collect Amazon Ads campaign metadata (name, status, budget, bid strategy)."""
    print("[Amazon Campaigns] Collecting...")
    token = _get_amz_ads_token()
    headers = {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.spCampaign.v3+json",
        "Accept": "application/vnd.spCampaign.v3+json",
    }

    # Get profiles (needs standard content-type)
    profile_headers = {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=profile_headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]

    all_campaigns = []
    for p in profiles:
        pid = str(p["profileId"])
        pname = p.get("accountInfo", {}).get("name", pid)
        brand = PROFILE_BRAND_MAP.get(pname, pname)
        h = {**headers, "Amazon-Advertising-API-Scope": pid}

        try:
            r = requests.post(
                "https://advertising-api.amazon.com/sp/campaigns/list",
                headers=h, json={"maxResults": 5000}, timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            camps = data if isinstance(data, list) else data.get("campaigns", [])
            for c in camps:
                budget_obj = c.get("budget", {})
                all_campaigns.append({
                    "campaign_id": str(c.get("campaignId", "")),
                    "profile_id": pid,
                    "brand": brand,
                    "name": c.get("name", ""),
                    "status": c.get("state", c.get("status", "UNKNOWN")).upper(),
                    "budget": float(budget_obj.get("budget", 0)
                                    if isinstance(budget_obj, dict)
                                    else budget_obj or 0),
                    "bid_strategy": c.get("dynamicBidding", {}).get("strategy", "")
                                    if isinstance(c.get("dynamicBidding"), dict) else "",
                    "campaign_type": "SP",
                })
            print(f"  {pname} ({brand}): {len(camps)} campaigns")
        except Exception as e:
            print(f"  [WARN] {pname}: {e}")

    print(f"  Total: {len(all_campaigns)} campaigns")
    return all_campaigns


def collect_meta_campaigns(date_from: str, date_to: str) -> list[dict]:
    """Collect Meta Ads campaign metadata (name, objective, status)."""
    print("[Meta Campaigns] Collecting...")
    if not META_ACCESS_TOKEN:
        print("  [SKIP] No META_ACCESS_TOKEN")
        return []

    acct = META_AD_ACCOUNT_ID if META_AD_ACCOUNT_ID.startswith("act_") else f"act_{META_AD_ACCOUNT_ID}"
    url = (f"https://graph.facebook.com/v18.0/{acct}/campaigns"
           f"?fields=id,name,objective,status"
           f"&limit=500&access_token={META_ACCESS_TOKEN}")

    all_campaigns = []
    while url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        for c in data.get("data", []):
            cname = c.get("name", "")
            obj = c.get("objective", "")
            ctype = "traffic" if obj in (
                "LINK_CLICKS", "POST_ENGAGEMENT", "REACH",
                "BRAND_AWARENESS", "VIDEO_VIEWS"
            ) else "cvr"
            brand = _detect_meta_brand(cname, "")

            all_campaigns.append({
                "campaign_id": c.get("id", ""),
                "name": cname,
                "objective": obj,
                "status": c.get("status", "UNKNOWN"),
                "brand": brand,
                "campaign_type": ctype,
            })
        url = data.get("paging", {}).get("next")

    print(f"  Total: {len(all_campaigns)} campaigns")
    return all_campaigns


# ══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════

CHANNEL_COLLECTORS = {
    "amazon_ads": ("amazon_ads_daily", collect_amazon_ads),
    "amazon_sales": ("amazon_sales_daily", collect_amazon_sales),
    "amazon_campaigns": ("amazon_campaigns", collect_amazon_campaigns),
    "meta": ("meta_ads_daily", collect_meta_ads),
    "meta_campaigns": ("meta_campaigns", collect_meta_campaigns),
    "google": ("google_ads_daily", collect_google_ads),
    "ga4": ("ga4_daily", collect_ga4),
    "klaviyo": ("klaviyo_daily", collect_klaviyo),
    "shopify": ("shopify_orders_daily", collect_shopify),
    "gsc": ("gsc_daily", collect_gsc),
    "dataforseo": ("dataforseo_keywords", collect_dataforseo),
}


def _get_collection_summary():
    """Build collection summary dict for status display and email notification."""
    pst_today = _get_pst_today()
    yesterday = (pst_today - timedelta(days=1)).isoformat()

    # Local cache status
    cache_status = {}
    for channel, (table, _) in CHANNEL_COLLECTORS.items():
        cache_path = os.path.join(CACHE_DIR, f"{table}.json")
        if os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            with open(cache_path, "r", encoding="utf-8") as f:
                rows = json.load(f)
            dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
            cache_status[channel] = {
                "rows": len(rows), "min_date": dates[0] if dates else "?",
                "max_date": dates[-1] if dates else "?",
                "updated": mtime.strftime("%Y-%m-%d %H:%M"),
            }
        else:
            cache_status[channel] = None

    # PG status
    pg_status = {}
    try:
        r = requests.get(f"{ORBITOOLS_BASE}/status/",
                         auth=(ORBITOOLS_USER, ORBITOOLS_PASS), timeout=10)
        if r.status_code == 200:
            pg_status = r.json().get("status", {})
    except Exception:
        pass

    # Identify stale channels (latest_date < yesterday)
    stale = []
    for table, info in pg_status.items():
        latest = info.get("latest_date", "")
        if latest and latest < yesterday:
            days_behind = (pst_today - timedelta(days=1) - datetime.fromisoformat(latest).date() if isinstance(latest, str) else timedelta(0))
            try:
                days_behind = (datetime.fromisoformat(yesterday).date() - datetime.fromisoformat(latest).date()).days
            except Exception:
                days_behind = "?"
            stale.append({"table": table, "latest": latest, "days_behind": days_behind})

    return {"pst_today": pst_today.isoformat(), "yesterday": yesterday,
            "cache": cache_status, "pg": pg_status, "stale": stale}


def show_status():
    """Show Data Keeper collection status."""
    summary = _get_collection_summary()
    pst_now = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=-8))).strftime("%Y-%m-%d %H:%M PST")

    print(f"=== Data Keeper Status === ({pst_now})\n")
    for channel, info in summary["cache"].items():
        if info:
            print(f"  {channel:15s} | {info['rows']:>6,} rows | "
                  f"{info['min_date']} ~ {info['max_date']} | "
                  f"updated: {info['updated']}")
        else:
            print(f"  {channel:15s} | no cache")

    if summary["pg"]:
        print("\n=== PostgreSQL Status ===\n")
        for table, info in summary["pg"].items():
            print(f"  {table:30s} | {info.get('count', 0):>6,} rows | "
                  f"latest: {info.get('latest_date', '?')}")
    else:
        print("\n  [PG] Not reachable (orbitools API)")


def _send_collection_email(results=None, elapsed_total=0, recipient=None):
    """Send Data Keeper email notification.

    Args:
        results: Collection results dict (None for status-only email)
        elapsed_total: Total collection time in seconds
        recipient: Override recipient (default from env)
    """
    try:
        from send_gmail import send_email
    except ImportError:
        print("  [Notify] send_gmail not available, skipping email")
        return

    if not recipient:
        recipient = os.getenv("DATA_KEEPER_RECIPIENT", os.getenv("PPC_REPORT_RECIPIENT", "all@orbiters.co.kr"))

    summary = _get_collection_summary()
    pst_now = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=-8))).strftime("%Y-%m-%d %H:%M PST")
    kst_now = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")

    status_only = results is None

    # Health check
    if status_only:
        health = "ALL GREEN" if not summary["stale"] else "ISSUES DETECTED"
    else:
        fail = [ch for ch, r in results.items() if not r["ok"]]
        health = "ALL GREEN" if not fail and not summary["stale"] else "ISSUES DETECTED"
    health_color = "#0d6e2e" if health == "ALL GREEN" else "#c0392b"

    # Collection results section (only if results provided)
    collection_section = ""
    if results:
        ok = [ch for ch, r in results.items() if r["ok"]]
        fail = [ch for ch, r in results.items() if not r["ok"]]
        ch_rows = ""
        for ch, r in results.items():
            bg = "#f6fff8" if r["ok"] else "#fff5f5"
            status = f"{r['rows']:,} rows" if r["ok"] else f"FAIL: {r['error']}"
            icon = "OK" if r["ok"] else "FAIL"
            ch_rows += f"""<tr style="background:{bg}">
                <td style="padding:6px 10px;border-bottom:1px solid #eee"><b>{ch}</b></td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{icon}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{status}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee">{r['elapsed']:.0f}s</td>
            </tr>"""
        collection_section = f"""
        <h3 style="margin:16px 0 8px;color:#333">Collection Results ({len(ok)} ok / {len(fail)} fail)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
            <tr style="background:#f0f0f0"><th style="padding:6px 10px;text-align:left">Channel</th><th style="padding:6px 10px;text-align:left">Status</th><th style="padding:6px 10px;text-align:left">Detail</th><th style="padding:6px 10px;text-align:left">Time</th></tr>
            {ch_rows}
        </table>"""

    # PG status table
    pg_rows = ""
    for table, info in summary["pg"].items():
        latest = info.get("latest_date", "?")
        count = info.get("count", 0)
        is_stale = any(s["table"] == table for s in summary["stale"])
        bg = "#fff5f5" if is_stale else "#f8f9fc"
        stale_tag = f' <span style="color:#c0392b;font-weight:bold">({next(s["days_behind"] for s in summary["stale"] if s["table"] == table)}d behind)</span>' if is_stale else ""
        pg_rows += f"""<tr style="background:{bg}">
            <td style="padding:6px 10px;border-bottom:1px solid #eee">{table}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right">{count:,}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee">{latest}{stale_tag}</td>
        </tr>"""

    # Stale alert section
    stale_section = ""
    if summary["stale"]:
        stale_items = "".join(
            f"<li><b>{s['table']}</b> - latest: {s['latest']}, <span style='color:#c0392b'>{s['days_behind']}d behind</span></li>"
            for s in summary["stale"]
        )
        stale_section = f"""
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px 16px;margin:16px 0">
            <b style="color:#856404">Stale Data Alert</b>
            <ul style="margin:8px 0 0 0;padding-left:20px">{stale_items}</ul>
        </div>"""

    title = "Data Keeper Daily Status" if status_only else "Data Keeper Collection Report"
    subtitle = f"{kst_now} / {pst_now}"
    if not status_only:
        subtitle += f" | Total: {elapsed_total:.0f}s"

    html = f"""<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:white;padding:20px 24px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">{title}</h2>
        <p style="margin:4px 0 0;opacity:0.8;font-size:13px">{subtitle}</p>
    </div>
    <div style="padding:16px 24px;background:#fff;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px">
        <div style="display:inline-block;background:{health_color};color:white;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;margin-bottom:12px">{health}</div>
        {stale_section}
        {collection_section}
        <h3 style="margin:20px 0 8px;color:#333">PostgreSQL Status</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
            <tr style="background:#f0f0f0"><th style="padding:6px 10px;text-align:left">Table</th><th style="padding:6px 10px;text-align:right">Rows</th><th style="padding:6px 10px;text-align:left">Latest Date</th></tr>
            {pg_rows}
        </table>
        <p style="margin:16px 0 0;font-size:11px;color:#999">Auto-generated by Data Keeper | WAT Framework</p>
    </div>
</div>"""

    subject = f"[Data Keeper] {health} - {kst_now}"
    try:
        cc = os.getenv("DATA_KEEPER_CC", "grosmimi.usa@gmail.com")
        result = send_email(to=recipient, subject=subject, body_html=html, cc=cc)
        print(f"  [Notify] Email sent to {recipient} (cc: {cc}) (id: {result.get('id', '?')})")
    except Exception as e:
        print(f"  [Notify] Email failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Data Keeper - Unified data collector")
    parser.add_argument("--channel", type=str, default="all",
                        help="Channel to collect (amazon_ads, amazon_sales, meta, google, ga4, klaviyo, shopify, gsc, dataforseo, all)")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="Lookback days (default: 35)")
    parser.add_argument("--skip-pg", action="store_true",
                        help="Skip PostgreSQL push (local cache only)")
    parser.add_argument("--status", action="store_true",
                        help="Show collection status and exit")
    parser.add_argument("--notify", action="store_true",
                        help="Send email notification after collection")
    parser.add_argument("--notify-only", action="store_true",
                        help="Send status email only (no collection)")
    parser.add_argument("--notify-to", type=str, default=None,
                        help="Override email recipient")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.notify_only:
        print("[Notify] Sending status-only email...")
        _send_collection_email(results=None, elapsed_total=0, recipient=args.notify_to)
        return

    today = _get_pst_today()
    date_to = (today - timedelta(days=1)).isoformat()  # yesterday PST
    date_from = (today - timedelta(days=args.days)).isoformat()

    print(f"=== Data Keeper ===")
    print(f"  PST today: {today}")
    print(f"  Range: {date_from} ~ {date_to}")
    print(f"  Skip PG: {args.skip_pg}")
    print()

    channels = list(CHANNEL_COLLECTORS.keys()) if args.channel == "all" else [args.channel]

    total_start = time.time()
    results = {}

    for channel in channels:
        if channel not in CHANNEL_COLLECTORS:
            print(f"[SKIP] Unknown channel: {channel}")
            continue

        table, collector = CHANNEL_COLLECTORS[channel]
        start_t = time.time()

        try:
            rows = collector(date_from, date_to)
            _save_cache(table, rows)
            if not args.skip_pg and rows:
                _push_to_pg(table, rows)
            elapsed = time.time() - start_t
            results[channel] = {"ok": True, "rows": len(rows), "elapsed": elapsed, "error": None}
            print(f"  [{channel}] Done in {elapsed:.0f}s\n")
        except Exception as e:
            elapsed = time.time() - start_t
            results[channel] = {"ok": False, "rows": 0, "elapsed": elapsed, "error": str(e)[:120]}
            print(f"  [{channel}] FAILED in {elapsed:.0f}s: {e}\n")

    # Export to Shared folder for team access
    print("[Shared Export]")
    _export_to_shared()

    # Scan for new data signals from team
    signals = _scan_signals()
    if signals:
        print(f"\n[Signals] {len(signals)} pending request(s):")
        for sig in signals:
            print(f"  - {sig.get('channel', '?')} (by {sig.get('requested_by', '?')}) [{sig['file']}]")

    elapsed_total = time.time() - total_start
    print(f"\n=== Data Keeper Complete ({elapsed_total:.0f}s) ===")

    # Send email notification if requested
    if args.notify:
        print("\n[Notify] Sending collection report email...")
        _send_collection_email(results, elapsed_total, recipient=args.notify_to)


if __name__ == "__main__":
    main()
