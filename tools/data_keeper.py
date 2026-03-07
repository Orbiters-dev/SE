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

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

PST = timezone(timedelta(hours=-8))
DEFAULT_LOOKBACK_DAYS = 35  # cover 30d + buffer

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
        "client_id": os.getenv("AMZ_SP_GROSMIMI_CLIENT_ID", AMZ_SP_CLIENT_ID),
        "client_secret": os.getenv("AMZ_SP_GROSMIMI_CLIENT_SECRET", AMZ_SP_CLIENT_SECRET),
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
    _amz_ads_token_cache["expires"] = now + 3000
    return token


# ══════════════════════════════════════════════════════════════════════════
# CHANNEL COLLECTORS
# ══════════════════════════════════════════════════════════════════════════

def collect_amazon_ads(date_from: str, date_to: str) -> list[dict]:
    """Collect Amazon Ads campaign daily metrics (all profiles)."""
    print("[Amazon Ads] Collecting...")
    token = _get_amz_ads_token()
    headers = {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

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
            h = {**headers, "Amazon-Advertising-API-Scope": pid}
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

        # Poll
        for _ in range(40):  # 40 * 15s = 10min max
            time.sleep(15)
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


def collect_shopify(date_from: str, date_to: str) -> list[dict]:
    """Collect Shopify orders aggregated daily by brand/channel."""
    print("[Shopify] Collecting...")
    if not SHOPIFY_SHOP or not SHOPIFY_ACCESS_TOKEN:
        print("  [SKIP] No Shopify credentials")
        return []

    shop = SHOPIFY_SHOP.replace(".myshopify.com", "") if ".myshopify.com" in SHOPIFY_SHOP else SHOPIFY_SHOP
    base = f"https://{shop}.myshopify.com/admin/api/2024-01"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    all_orders = []
    url = (f"{base}/orders.json?status=any&limit=250"
           f"&created_at_min={date_from}T00:00:00-08:00"
           f"&created_at_max={date_to}T23:59:59-08:00"
           f"&fields=id,created_at,total_price,total_discounts,source_name,"
           f"line_items,tags,financial_status,gateway")

    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        orders = r.json().get("orders", [])
        all_orders.extend(orders)
        # Pagination via Link header
        link = r.headers.get("Link", "")
        url = None
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]

    print(f"  Orders fetched: {len(all_orders)}")

    # Aggregate daily by brand/channel
    daily = {}
    for order in all_orders:
        date_str = order["created_at"][:10]
        tags = (order.get("tags") or "").lower()
        source = (order.get("source_name") or "").lower()
        total = float(order.get("total_price", 0))
        discount = float(order.get("total_discounts", 0))
        units = sum(li.get("quantity", 1) for li in order.get("line_items", []))

        # Channel detection
        if "amazon" in tags or "amazon" in source:
            channel = "Amazon"
        elif "tiktok" in tags or "tiktok" in source:
            channel = "TikTok"
        elif any(k in tags for k in ["b2b", "wholesale"]):
            channel = "B2B"
        elif any(k in tags for k in ["pr", "sample", "supporter"]):
            channel = "PR"
        else:
            channel = "D2C"

        # Brand from line items
        brand = _detect_shopify_brand(order.get("line_items", []))

        key = (date_str, brand, channel)
        if key not in daily:
            daily[key] = {
                "date": date_str, "brand": brand, "channel": channel,
                "gross_sales": 0, "discounts": 0, "net_sales": 0,
                "orders": 0, "units": 0, "refunds": 0,
            }
        daily[key]["gross_sales"] += total
        daily[key]["discounts"] += discount
        daily[key]["net_sales"] += total - discount
        daily[key]["orders"] += 1
        daily[key]["units"] += units

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


# ══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════

CHANNEL_COLLECTORS = {
    "amazon_ads": ("amazon_ads_daily", collect_amazon_ads),
    "amazon_sales": ("amazon_sales_daily", collect_amazon_sales),
    "meta": ("meta_ads_daily", collect_meta_ads),
    "google": ("google_ads_daily", collect_google_ads),
    "ga4": ("ga4_daily", collect_ga4),
    "klaviyo": ("klaviyo_daily", collect_klaviyo),
    "shopify": ("shopify_orders_daily", collect_shopify),
}


def show_status():
    """Show Data Keeper collection status."""
    print("=== Data Keeper Status ===\n")
    for channel, (table, _) in CHANNEL_COLLECTORS.items():
        cache_path = os.path.join(CACHE_DIR, f"{table}.json")
        if os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            with open(cache_path, "r") as f:
                rows = json.load(f)
            dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
            print(f"  {channel:15s} | {len(rows):>6,} rows | "
                  f"{dates[0] if dates else '?'} ~ {dates[-1] if dates else '?'} | "
                  f"updated: {mtime:%Y-%m-%d %H:%M}")
        else:
            print(f"  {channel:15s} | no cache")

    # Check PG status
    try:
        r = requests.get(f"{ORBITOOLS_BASE}/status/",
                         auth=(ORBITOOLS_USER, ORBITOOLS_PASS), timeout=10)
        if r.status_code == 200:
            print("\n=== PostgreSQL Status ===\n")
            for table, info in r.json().get("status", {}).items():
                print(f"  {table:30s} | {info.get('count', 0):>6,} rows | "
                      f"latest: {info.get('latest_date', '?')}")
    except Exception:
        print("\n  [PG] Not reachable (orbitools API)")


def main():
    parser = argparse.ArgumentParser(description="Data Keeper - Unified data collector")
    parser.add_argument("--channel", type=str, default="all",
                        help="Channel to collect (amazon_ads, amazon_sales, meta, google, ga4, klaviyo, shopify, all)")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="Lookback days (default: 35)")
    parser.add_argument("--skip-pg", action="store_true",
                        help="Skip PostgreSQL push (local cache only)")
    parser.add_argument("--status", action="store_true",
                        help="Show collection status and exit")
    args = parser.parse_args()

    if args.status:
        show_status()
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
            print(f"  [{channel}] Done in {elapsed:.0f}s\n")
        except Exception as e:
            elapsed = time.time() - start_t
            print(f"  [{channel}] FAILED in {elapsed:.0f}s: {e}\n")

    print("=== Data Keeper Complete ===")


if __name__ == "__main__":
    main()
