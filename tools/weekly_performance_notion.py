"""
weekly_performance_notion.py

Reads weekly Polar data from .tmp/weekly_polar_data/,
calculates KPMs and OKR metrics, and creates a Notion page
replicating the Performance Team Weekly Report template.

Week period: Friday 00:00 ~ Thursday 23:59 PST
  (Business cutoff: Thursday 11:00 PM PST; daily data uses full calendar days)

Auto-fills:
  - OKR Table: ROAS (CVR), CAC, Email Open Rate, Campaigns Launched rows
  - Key Performance Metrics bullets with CVR/Traffic split and channel breakdown
  - Top/Bottom 5 ROAS campaigns (traffic excluded)
  - Promo comparison tables (if promo_comparison_data.json exists)

Scope: All ads EXCEPT Grosmimi Amazon PPC.

Usage:
    python tools/weekly_performance_notion.py --week 2026-W08 --dry-run
    python tools/weekly_performance_notion.py --week 2026-W08
    python tools/weekly_performance_notion.py --discover

Prerequisites:
    - .env: NOTION_API_TOKEN
    - .tmp/weekly_polar_data/ JSON files (from Polar MCP queries, daily granularity)
"""

import os
import sys
import re
import json
import argparse
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
if not NOTION_TOKEN:
    raise ValueError("NOTION_API_TOKEN not found in .env")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

WEEKLY_REPORT_DB_ID = os.getenv(
    "WEEKLY_REPORT_NOTION_DB_ID",
    "2fb86c6dc04680988f1fe3a5803eb4f0",
)

# Irene (Jiseon) user ID in Notion workspace
IRENE_USER_ID = "22dd872b-594c-81f8-8d59-0002cc35027b"

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, ".tmp", "weekly_polar_data")

# OKR Targets — update each quarter
OKR_TARGETS = {
    "roas": 3.0,
    "cac": 25.00,
    "email_open_rate": 50.0,  # percentage
}

# Data file mapping
DATA_FILES = {
    "meta": "wk_meta_ads_weekly.json",
    "google": "wk_google_ads_weekly.json",
    "tiktok": "wk_tiktok_ads_weekly.json",
    "amazon": "wk_amazon_ads_weekly.json",
    "shopify": "wk_shopify_weekly.json",
    "ga4": "wk_ga4_weekly.json",
    "klaviyo": "wk_klaviyo_weekly.json",
}

PROMO_FILE = "promo_comparison_data.json"

# Meta objective classification
META_CVR_OBJECTIVES = {"OUTCOME_SALES"}
META_TRAFFIC_OBJECTIVES = {"LINK_CLICKS", "APP_INSTALLS", "OUTCOME_ENGAGEMENT"}

# Minimum spend ($) to include in top/bottom ROAS ranking
MIN_SPEND_FOR_RANKING = 20

# ---------------------------------------------------------------------------
# Campaign classification constants (from polar_financial_model.py)
# ---------------------------------------------------------------------------

AMZ_BR = [
    ("cha&mom", "CHA&MOM"),
    ("naeiae", "Naeiae"),
    ("alpremio", "Alpremio"),
    ("comme", "Comme Moi"),
]

FB_BR = [
    ("alpremio", "Alpremio"), ("naeiae", "Naeiae"),
    ("cha&mom", "CHA&MOM"), ("love&care", "CHA&MOM"),
    ("| cm |", "CHA&MOM"), ("_cm_", "CHA&MOM"),
    ("| gm |", "Grosmimi"), ("_gm_", "Grosmimi"),
    ("grosmimi", "Grosmimi"), ("dental mom", "Grosmimi"), ("dentalmom", "Grosmimi"),
    ("livfuselli", "Grosmimi"), ("tumbler", "Grosmimi"), ("stainless", "Grosmimi"),
    ("sls", "Grosmimi"), ("laurence", "Grosmimi"), ("lauren", "Grosmimi"),
    ("asc campaign", "Grosmimi"),
]

# Meta campaign landing patterns
FB_LAND_AMZ = [
    "amz_traffic", "amz | traffic", "amz| traffic",
    "asc | amz | traffic", "asc i amz i traffic", "tof | amz |",
]
FB_LAND_TARGET = ["target | traffic", "target |traffic"]

AD_PROD = [
    ("ppsu", "PPSU Straw Cup"), ("flip top", "Flip Top Cup"), ("fliptop", "Flip Top Cup"),
    ("knotted", "Flip Top Cup"), ("stainless", "Stainless Cup"),
    ("tumbler", "Tumbler"), ("stage1", "Replacement Parts"), ("stage2", "PPSU Straw Cup"),
    ("replacements", "Replacement Parts"), ("wash", "Skincare"), ("lotion", "Skincare"),
    ("cream", "Skincare"), ("naeiae", "Food & Snacks"), ("alpremio", "Baby Carrier"),
]


# ---------------------------------------------------------------------------
# Campaign classification functions
# ---------------------------------------------------------------------------


def ad_brand_amazon(campaign_name):
    """Classify Amazon campaign to brand. Default = Grosmimi."""
    c = campaign_name.lower()
    for keyword, brand in AMZ_BR:
        if keyword in c:
            return brand
    return "Grosmimi"


def ad_brand(camp, plat):
    """Classify campaign brand by platform."""
    c = camp.lower()
    if plat == "Amazon":
        for k, b in AMZ_BR:
            if k in c:
                return b
        return "Grosmimi"
    if plat == "Meta":
        for k, b in FB_BR:
            if k in c:
                return b
        return "Other"
    if plat == "Google":
        return "Grosmimi"
    return "Other"


def ad_prod(camp):
    """Classify campaign product category."""
    c = camp.lower()
    for k, cat in AD_PROD:
        if k in c:
            return cat
    return "General"


def ad_landing(camp, plat):
    """Determine which sales channel (landing page) an ad targets.

    Returns: "Onzenna", "Amazon", or "TargetPlus"
    """
    c = camp.lower()
    if plat == "Amazon":
        return "Amazon"
    if plat == "Google":
        return "Onzenna"
    if plat == "Meta":
        for pat in FB_LAND_AMZ:
            if pat in c:
                return "Amazon"
        for pat in FB_LAND_TARGET:
            if pat in c:
                return "TargetPlus"
        return "Onzenna"
    if plat == "TikTok":
        if ("amz" in c or "amazon" in c) and "traffic" in c:
            return "Amazon"
        return "Onzenna"
    return "Onzenna"


def is_meta_traffic_campaign(campaign_name, objective):
    """Check if a Meta campaign is a traffic/non-CVR campaign.

    Traffic = LINK_CLICKS/APP_INSTALLS/OUTCOME_ENGAGEMENT objectives
    OR Meta->AMZ / Meta->Target landing regardless of objective.
    """
    landing = ad_landing(campaign_name, "Meta")
    if landing in ("Amazon", "TargetPlus"):
        return True
    if objective in META_TRAFFIC_OBJECTIVES:
        return True
    return False


def classify_meta_row(row):
    """Classify a Meta row into: 'cvr', 'meta_amz', 'meta_target', or 'meta_other_traffic'.

    - cvr: OUTCOME_SALES + Onzenna landing -> included in ROAS/CAC
    - meta_amz: Any Meta campaign landing on Amazon -> Traffic bucket
    - meta_target: Any Meta campaign landing on TargetPlus -> Traffic bucket
    - meta_other_traffic: LINK_CLICKS/APP_INSTALLS/OUTCOME_ENGAGEMENT + Onzenna landing -> Traffic
    """
    camp = row.get("campaign", "")
    obj = row.get("objective", "")
    landing = ad_landing(camp, "Meta")

    if landing == "Amazon":
        return "meta_amz"
    if landing == "TargetPlus":
        return "meta_target"
    if obj in META_CVR_OBJECTIVES:
        return "cvr"
    return "meta_other_traffic"


def extract_campaign_date(campaign_name):
    """Try to extract a start date from campaign name.

    Looks for patterns like YYYYMMDD or YYYY_MM_DD or YYYY-MM-DD in campaign name.
    Returns "YYYY-MM-DD" string or empty string.
    """
    # Try YYYYMMDD (8 digits not part of longer number)
    m = re.search(r'(?<!\d)(20[2-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)', campaign_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Try YYYY-MM-DD or YYYY_MM_DD
    m = re.search(r'(20[2-3]\d)[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])', campaign_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Try YYYYMM (just year-month, no day)
    m = re.search(r'(?<!\d)(20[2-3]\d)(0[1-9]|1[0-2])(?!\d)', campaign_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


# ---------------------------------------------------------------------------
# Notion API helpers (from sync_influencer_notion.py)
# ---------------------------------------------------------------------------


def notion_api(method, endpoint, json_body=None, max_retries=3):
    """Make a Notion API call with retry logic."""
    url = f"https://api.notion.com/v1/{endpoint}"
    for attempt in range(max_retries):
        try:
            if method == "GET":
                resp = requests.get(url, headers=NOTION_HEADERS, timeout=30)
            elif method == "POST":
                resp = requests.post(url, headers=NOTION_HEADERS, json=json_body, timeout=30)
            elif method == "PATCH":
                resp = requests.patch(url, headers=NOTION_HEADERS, json=json_body, timeout=30)
            elif method == "DELETE":
                resp = requests.delete(url, headers=NOTION_HEADERS, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1))
                print(f"    Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            if resp.status_code == 409:
                print(f"    Conflict (409). Retrying in 1s...")
                time.sleep(1)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    API error (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    return None


def get_all_child_blocks(block_id):
    """Get all child blocks of a page/block with pagination."""
    all_blocks = []
    cursor = None
    while True:
        url = f"blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        data = notion_api("GET", url)
        if not data:
            break
        all_blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return all_blocks


def get_block_text(block):
    """Extract plain text from a Notion block."""
    btype = block.get("type", "")
    if btype in ("heading_1", "heading_2", "heading_3", "paragraph",
                 "bulleted_list_item", "numbered_list_item", "to_do"):
        rt = block.get(btype, {}).get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in rt)
    return ""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_json(name):
    """Load a JSON data file from the weekly data directory."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        print(f"  WARNING: {name} not found")
        return {"tableData": [], "totalData": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Week date helpers (Fri-Thu, PST 11:00 PM cutoff)
# ---------------------------------------------------------------------------


def parse_week(week_str):
    """Parse '2026-W08' -> (year, week_number)."""
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError(f"Invalid week format: {week_str}. Expected YYYY-Wnn")
    return int(parts[0]), int(parts[1])


def get_week_dates(year, week):
    """Get Fri-Thu date range for a given ISO week number.

    Maps ISO week N to:
      Friday  = ISO Monday - 3 days
      Thursday = ISO Monday + 3 days

    Business cutoff: PST Thursday 11:00 PM.
    Data uses full calendar days (Fri 00:00 ~ Thu 23:59 PST).
    """
    iso_monday = date.fromisocalendar(year, week, 1)
    friday = iso_monday - timedelta(days=3)
    thursday = iso_monday + timedelta(days=3)
    return friday, thursday


# ---------------------------------------------------------------------------
# Metric extraction (range-based, for daily-granularity data)
# ---------------------------------------------------------------------------


def sum_ads_for_range(data, start_date, end_date, spend_key, revenue_key,
                      clicks_key, impressions_key, exclude_fn=None,
                      include_fn=None):
    """Sum ads metrics for a date range with optional row filtering.

    exclude_fn: if returns True, skip this row (e.g. Grosmimi Amazon)
    include_fn: if provided, row must pass this check to be included

    Returns dict with spend, revenue, clicks, impressions, and campaign set.
    """
    spend = 0.0
    revenue = 0.0
    clicks = 0
    impressions = 0
    campaigns = set()
    for row in data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        if exclude_fn and exclude_fn(row):
            continue
        if include_fn and not include_fn(row):
            continue
        spend += row.get(spend_key, 0) or 0
        revenue += row.get(revenue_key, 0) or 0
        clicks += row.get(clicks_key, 0) or 0
        impressions += row.get(impressions_key, 0) or 0
        camp = row.get("campaign", "")
        if camp:
            campaigns.add(camp)
    return {"spend": spend, "revenue": revenue, "clicks": clicks,
            "impressions": impressions, "campaigns": campaigns}


def sum_meta_by_bucket(data, start_date, end_date):
    """Classify all Meta rows into CVR / Meta->AMZ / Meta->Target / Meta Other Traffic.

    Returns dict of bucket -> {spend, revenue, clicks, impressions, campaigns}.
    """
    sp_key = "facebookads_ad_platform_and_device.raw.spend"
    rev_key = "facebookads_ad_platform_and_device.raw.purchases_conversion_value"
    clk_key = "facebookads_ad_platform_and_device.raw.clicks"
    imp_key = "facebookads_ad_platform_and_device.raw.impressions"

    buckets = {}
    for bucket_name in ("cvr", "meta_amz", "meta_target", "meta_other_traffic"):
        buckets[bucket_name] = {"spend": 0.0, "revenue": 0.0, "clicks": 0,
                                "impressions": 0, "campaigns": set()}

    for row in data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        bucket = classify_meta_row(row)
        b = buckets[bucket]
        b["spend"] += row.get(sp_key, 0) or 0
        b["revenue"] += row.get(rev_key, 0) or 0
        b["clicks"] += row.get(clk_key, 0) or 0
        b["impressions"] += row.get(imp_key, 0) or 0
        camp = row.get("campaign", "")
        if camp:
            b["campaigns"].add(camp)

    return buckets


def get_shopify_for_range(data, start_date, end_date):
    """Aggregate Shopify metrics for a date range."""
    gross_sales = total_sales = total_orders = discounts = 0.0
    for row in data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        gross_sales += row.get("shopify_sales_main.raw.gross_sales", 0) or 0
        total_sales += row.get("shopify_sales_main.computed.total_sales", 0) or 0
        total_orders += row.get("shopify_sales_main.raw.total_orders", 0) or 0
        discounts += row.get("shopify_sales_main.raw.discounts", 0) or 0
    return {"gross_sales": gross_sales, "total_sales": total_sales,
            "total_orders": int(total_orders), "discounts": discounts}


def get_ga4_for_range(data, start_date, end_date):
    """Aggregate GA4 metrics for a date range."""
    sessions = purchases = 0
    for row in data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        sessions += row.get("ga_main.raw.sessions", 0) or 0
        purchases += row.get("ga_main.raw.ecommerce_purchases", 0) or 0
    return {"sessions": int(sessions), "purchases": int(purchases)}


def get_klaviyo_for_range(data, start_date, end_date):
    """Aggregate Klaviyo metrics for a date range (weighted avg rates)."""
    total_sends = total_revenue = 0.0
    weighted_open = weighted_click = 0.0
    for row in data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        sends = row.get("klaviyo_sales_main.raw.campaign_send", 0) or 0
        revenue = row.get("klaviyo_sales_main.raw.campaign_revenue", 0) or 0
        or_val = row.get("klaviyo_sales_main.computed.campaign_unique_open_rate", 0) or 0
        cr_val = row.get("klaviyo_sales_main.computed.campaign_unique_click_rate_excl_bot", 0) or 0
        total_sends += sends
        total_revenue += revenue
        weighted_open += or_val * sends
        weighted_click += cr_val * sends
    open_rate = (weighted_open / total_sends * 100) if total_sends > 0 else 0
    click_rate = (weighted_click / total_sends * 100) if total_sends > 0 else 0
    return {"sends": int(total_sends), "revenue": total_revenue,
            "open_rate": open_rate, "click_rate": click_rate}


def is_grosmimi_amazon(row):
    """Check if an Amazon Ads row belongs to Grosmimi."""
    campaign = row.get("campaign", "")
    return ad_brand_amazon(campaign) == "Grosmimi"


def _safe_roas(revenue, spend):
    return revenue / spend if spend > 0 else 0


def _safe_cpc(spend, clicks):
    return spend / clicks if clicks > 0 else 0


def get_campaign_roas_list(meta_data, google_data, tiktok_data, amazon_data,
                           start_date, end_date):
    """Get per-campaign ROAS list from CVR platforms only (excludes traffic).

    CVR campaigns:
    - Meta: OUTCOME_SALES + Onzenna landing only
    - Google: all
    - TikTok: all
    - Amazon: non-Grosmimi

    Returns list of dicts with: campaign, ad_channel, sales_channel, brand,
    product, spend, revenue, sales (=revenue), roas, start_date
    """
    campaign_agg = {}  # key = (ad_channel, campaign) -> {spend, revenue}

    # Meta CVR only (exclude traffic campaigns)
    sp_key = "facebookads_ad_platform_and_device.raw.spend"
    rev_key = "facebookads_ad_platform_and_device.raw.purchases_conversion_value"
    for row in meta_data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        camp = row.get("campaign", "")
        if not camp:
            continue
        bucket = classify_meta_row(row)
        if bucket != "cvr":
            continue  # exclude all traffic campaigns
        key = ("Meta", camp)
        if key not in campaign_agg:
            campaign_agg[key] = {"spend": 0.0, "revenue": 0.0}
        campaign_agg[key]["spend"] += row.get(sp_key, 0) or 0
        campaign_agg[key]["revenue"] += row.get(rev_key, 0) or 0

    # Google all
    g_sp = "googleads_campaign_and_device.raw.cost"
    g_rv = "googleads_campaign_and_device.raw.conversion_value"
    for row in google_data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        camp = row.get("campaign", "")
        if not camp:
            continue
        key = ("Google", camp)
        if key not in campaign_agg:
            campaign_agg[key] = {"spend": 0.0, "revenue": 0.0}
        campaign_agg[key]["spend"] += row.get(g_sp, 0) or 0
        campaign_agg[key]["revenue"] += row.get(g_rv, 0) or 0

    # TikTok all
    t_sp = "tiktokads_campaign_and_platform.raw.spend"
    t_rv = "tiktokads_campaign_and_platform.raw.purchases_conversion_value"
    for row in tiktok_data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        camp = row.get("campaign", "")
        if not camp:
            continue
        key = ("TikTok", camp)
        if key not in campaign_agg:
            campaign_agg[key] = {"spend": 0.0, "revenue": 0.0}
        campaign_agg[key]["spend"] += row.get(t_sp, 0) or 0
        campaign_agg[key]["revenue"] += row.get(t_rv, 0) or 0

    # Amazon non-Grosmimi
    a_sp = "amazonads_campaign.raw.cost"
    a_rv = "amazonads_campaign.raw.attributed_sales"
    for row in amazon_data.get("tableData", []):
        rd = row.get("date", "")
        if rd < start_date or rd > end_date:
            continue
        camp = row.get("campaign", "")
        if not camp:
            continue
        if is_grosmimi_amazon(row):
            continue
        key = ("Amazon", camp)
        if key not in campaign_agg:
            campaign_agg[key] = {"spend": 0.0, "revenue": 0.0}
        campaign_agg[key]["spend"] += row.get(a_sp, 0) or 0
        campaign_agg[key]["revenue"] += row.get(a_rv, 0) or 0

    result = []
    for (plat_name, camp), d in campaign_agg.items():
        if d["spend"] <= 0:
            continue
        result.append({
            "campaign": camp,
            "ad_channel": plat_name,
            "sales_channel": ad_landing(camp, plat_name),
            "brand": ad_brand(camp, plat_name),
            "product": ad_prod(camp),
            "spend": d["spend"],
            "revenue": d["revenue"],
            "roas": d["revenue"] / d["spend"],
            "start_date": extract_campaign_date(camp),
        })
    return result


def calculate_metrics(week_str):
    """Calculate all performance metrics for this week, last week, and 2 weeks ago.

    Week period: Friday-Thursday (PST 11 PM cutoff, full calendar days).
    Splits ads into CVR campaigns (ROAS) and Traffic campaigns (avg CPC).

    CVR bucket: Meta(OUTCOME_SALES + Onzenna landing) + Google + TikTok + Amazon(non-Grosmimi)
    Traffic bucket: Meta->AMZ + Meta->Target + Meta other traffic objectives
    CAC = CVR spend / Shopify orders (same base as ROAS)
    """
    year, week_num = parse_week(week_str)

    # 3 periods: this week, last week, 2 weeks ago (for campaigns launched comparison)
    periods_info = {}
    for label, offset in [("this", 0), ("last", 7), ("prev2", 14)]:
        fri, thu = get_week_dates(year, week_num)
        fri = fri - timedelta(days=offset)
        thu = thu - timedelta(days=offset)
        periods_info[label] = (fri.isoformat(), thu.isoformat())

    # Load all data files
    meta = load_json(DATA_FILES["meta"])
    google = load_json(DATA_FILES["google"])
    tiktok = load_json(DATA_FILES["tiktok"])
    amazon = load_json(DATA_FILES["amazon"])
    shopify = load_json(DATA_FILES["shopify"])
    ga4 = load_json(DATA_FILES["ga4"])
    klaviyo = load_json(DATA_FILES["klaviyo"])

    results = {}
    for period in ("this", "last", "prev2"):
        start, end = periods_info[period]

        # --- Meta: classify into 4 buckets ---
        meta_buckets = sum_meta_by_bucket(meta, start, end)
        meta_cvr = meta_buckets["cvr"]
        meta_amz = meta_buckets["meta_amz"]
        meta_target = meta_buckets["meta_target"]
        meta_other_traffic = meta_buckets["meta_other_traffic"]

        # --- Google (all CVR) ---
        google_all = sum_ads_for_range(
            google, start, end,
            "googleads_campaign_and_device.raw.cost",
            "googleads_campaign_and_device.raw.conversion_value",
            "googleads_campaign_and_device.raw.clicks",
            "googleads_campaign_and_device.raw.impressions")

        # --- TikTok (all CVR) ---
        tiktok_all = sum_ads_for_range(
            tiktok, start, end,
            "tiktokads_campaign_and_platform.raw.spend",
            "tiktokads_campaign_and_platform.raw.purchases_conversion_value",
            "tiktokads_campaign_and_platform.raw.clicks",
            "tiktokads_campaign_and_platform.raw.impressions")

        # --- Amazon (non-Grosmimi -> CVR bucket) ---
        amazon_filtered = sum_ads_for_range(
            amazon, start, end,
            "amazonads_campaign.raw.cost",
            "amazonads_campaign.raw.attributed_sales",
            "amazonads_campaign.raw.clicks",
            "amazonads_campaign.raw.impressions",
            exclude_fn=is_grosmimi_amazon)

        # Aggregate: CVR bucket
        cvr_spend = (meta_cvr["spend"] + google_all["spend"]
                      + tiktok_all["spend"] + amazon_filtered["spend"])
        cvr_revenue = (meta_cvr["revenue"] + google_all["revenue"]
                        + tiktok_all["revenue"] + amazon_filtered["revenue"])

        # Aggregate: Traffic bucket
        traffic_meta_amz_spend = meta_amz["spend"]
        traffic_meta_amz_clicks = meta_amz["clicks"]
        traffic_meta_target_spend = meta_target["spend"]
        traffic_meta_target_clicks = meta_target["clicks"]
        traffic_meta_other_spend = meta_other_traffic["spend"]
        traffic_meta_other_clicks = meta_other_traffic["clicks"]
        traffic_total_spend = (traffic_meta_amz_spend + traffic_meta_target_spend
                               + traffic_meta_other_spend)
        traffic_total_clicks = (traffic_meta_amz_clicks + traffic_meta_target_clicks
                                + traffic_meta_other_clicks)

        total_spend = cvr_spend + traffic_total_spend

        s = get_shopify_for_range(shopify, start, end)
        ga = get_ga4_for_range(ga4, start, end)
        kl = get_klaviyo_for_range(klaviyo, start, end)

        cvr_roas = _safe_roas(cvr_revenue, cvr_spend)
        traffic_avg_cpc = _safe_cpc(traffic_total_spend, traffic_total_clicks)
        # CAC = CVR spend only / Shopify orders (same base as ROAS)
        cac = cvr_spend / s["total_orders"] if s["total_orders"] > 0 else 0
        cvr_pct = (ga["purchases"] / ga["sessions"] * 100) if ga["sessions"] > 0 else 0

        # Campaign sets for "launched" detection (Meta + Google only, CVR+traffic)
        all_meta_campaigns = set()
        for b in meta_buckets.values():
            all_meta_campaigns |= b["campaigns"]
        mg_campaigns = all_meta_campaigns | google_all["campaigns"]

        results[period] = {
            "total_spend": total_spend,
            # CVR totals
            "cvr_spend": cvr_spend,
            "cvr_revenue": cvr_revenue,
            "cvr_roas": cvr_roas,
            # Per-channel CVR ROAS
            "meta_cvr_spend": meta_cvr["spend"],
            "meta_cvr_revenue": meta_cvr["revenue"],
            "meta_cvr_roas": _safe_roas(meta_cvr["revenue"], meta_cvr["spend"]),
            "google_spend": google_all["spend"],
            "google_revenue": google_all["revenue"],
            "google_roas": _safe_roas(google_all["revenue"], google_all["spend"]),
            "tiktok_spend": tiktok_all["spend"],
            "tiktok_revenue": tiktok_all["revenue"],
            "tiktok_roas": _safe_roas(tiktok_all["revenue"], tiktok_all["spend"]),
            "amazon_cvr_spend": amazon_filtered["spend"],
            "amazon_cvr_revenue": amazon_filtered["revenue"],
            "amazon_cvr_roas": _safe_roas(amazon_filtered["revenue"], amazon_filtered["spend"]),
            # Traffic totals
            "traffic_total_spend": traffic_total_spend,
            "traffic_total_clicks": traffic_total_clicks,
            "traffic_avg_cpc": traffic_avg_cpc,
            # Traffic per-source
            "traffic_meta_amz_spend": traffic_meta_amz_spend,
            "traffic_meta_amz_clicks": traffic_meta_amz_clicks,
            "traffic_meta_amz_cpc": _safe_cpc(traffic_meta_amz_spend, traffic_meta_amz_clicks),
            "traffic_meta_target_spend": traffic_meta_target_spend,
            "traffic_meta_target_clicks": traffic_meta_target_clicks,
            "traffic_meta_target_cpc": _safe_cpc(traffic_meta_target_spend, traffic_meta_target_clicks),
            "traffic_meta_other_spend": traffic_meta_other_spend,
            "traffic_meta_other_clicks": traffic_meta_other_clicks,
            "traffic_meta_other_cpc": _safe_cpc(traffic_meta_other_spend, traffic_meta_other_clicks),
            # Shopify / GA4 / Klaviyo
            "shopify_revenue": s["total_sales"],
            "shopify_orders": s["total_orders"],
            "cac": cac,
            "cvr": cvr_pct,
            "email_open_rate": kl["open_rate"],
            "email_ctr": kl["click_rate"],
            "ga_sessions": ga["sessions"],
            "ga_purchases": ga["purchases"],
            # Campaign sets (temporary)
            "_campaigns": mg_campaigns,
        }

    # Campaigns launched = new this week vs last week (Meta + Google)
    this_camps = results["this"].pop("_campaigns")
    last_camps = results["last"].pop("_campaigns")
    prev2_camps = results["prev2"].pop("_campaigns")

    this_launched = this_camps - last_camps
    last_launched = last_camps - prev2_camps

    # Per-campaign ROAS ranking (this week, CVR campaigns only — no traffic)
    all_camp_roas = get_campaign_roas_list(
        meta, google, tiktok, amazon,
        periods_info["this"][0], periods_info["this"][1])
    meaningful = [c for c in all_camp_roas if c["spend"] >= MIN_SPEND_FOR_RANKING]
    by_roas_desc = sorted(meaningful, key=lambda x: x["roas"], reverse=True)
    by_roas_asc = sorted(meaningful, key=lambda x: x["roas"])

    top5 = by_roas_desc[:5]
    top5_keys = {(c["ad_channel"], c["campaign"]) for c in top5}
    bottom5 = [c for c in by_roas_asc if (c["ad_channel"], c["campaign"]) not in top5_keys][:5]

    this_fri = date.fromisoformat(periods_info["this"][0])
    this_thu = date.fromisoformat(periods_info["this"][1])

    return {
        "week": week_str,
        "week_num": week_num,
        "this_friday": this_fri.isoformat(),
        "this_thursday": this_thu.isoformat(),
        "this": results["this"],
        "last": results["last"],
        "prev2": results["prev2"],
        "campaigns_launched": len(this_launched),
        "campaigns_launched_last": len(last_launched),
        "launched_list": sorted(this_launched),
        "launched_list_last": sorted(last_launched),
        "top5_roas": top5,
        "bottom5_roas": bottom5,
    }


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def print_summary(metrics):
    """Print formatted summary of calculated metrics."""
    print("\n" + "=" * 60)
    print(f"WEEKLY PERFORMANCE METRICS \u2014 {metrics['week']}")
    print(f"({metrics['this_friday']} ~ {metrics['this_thursday']}  Fri-Thu PST)")
    print("=" * 60)

    for label, key in [("This Week", "this"), ("Last Week", "last")]:
        d = metrics[key]
        print(f"\n  {label}:")
        print(f"    Total Ad Spend:           ${d['total_spend']:>10,.2f}")
        print(f"    --- CVR Campaigns (ROAS) ---")
        print(f"      Total CVR Spend:        ${d['cvr_spend']:>10,.2f}")
        print(f"      Total CVR ROAS:         {d['cvr_roas']:>10.2f}")
        print(f"        Meta (CVR):           ${d['meta_cvr_spend']:>10,.2f}  ROAS {d['meta_cvr_roas']:.2f}")
        print(f"        Google:               ${d['google_spend']:>10,.2f}  ROAS {d['google_roas']:.2f}")
        print(f"        TikTok:               ${d['tiktok_spend']:>10,.2f}  ROAS {d['tiktok_roas']:.2f}")
        print(f"        Amazon Ads (non-GM):  ${d['amazon_cvr_spend']:>10,.2f}  ROAS {d['amazon_cvr_roas']:.2f}")
        print(f"    --- Traffic Campaigns ---")
        print(f"      Total Traffic Spend:    ${d['traffic_total_spend']:>10,.2f}")
        print(f"      Avg CPC:                ${d['traffic_avg_cpc']:>10.2f}")
        print(f"        Meta -> AMZ:          ${d['traffic_meta_amz_spend']:>10,.2f}  CPC ${d['traffic_meta_amz_cpc']:.2f}")
        print(f"        Meta -> Target:       ${d['traffic_meta_target_spend']:>10,.2f}  CPC ${d['traffic_meta_target_cpc']:.2f}")
        print(f"        Meta Other Traffic:   ${d['traffic_meta_other_spend']:>10,.2f}  CPC ${d['traffic_meta_other_cpc']:.2f}")
        print(f"    Shopify Revenue:          ${d['shopify_revenue']:>10,.2f}")
        print(f"    Shopify Orders:           {d['shopify_orders']:>10}")
        print(f"    CAC (CVR spend/orders):   ${d['cac']:>10.2f}")
        print(f"    Conversion Rate:          {d['cvr']:>10.1f}%")
        print(f"    Email Open Rate:          {d['email_open_rate']:>10.1f}%")
        print(f"    Email CTR:                {d['email_ctr']:>10.2f}%")

    # Campaigns launched
    print(f"\n  Campaigns Launched (Google & Meta):")
    print(f"    This Week: {metrics['campaigns_launched']}")
    print(f"    Last Week: {metrics['campaigns_launched_last']}")
    if metrics["launched_list"]:
        print(f"    New This Week:")
        for camp in metrics["launched_list"][:20]:
            print(f"      - {camp}")
        if len(metrics["launched_list"]) > 20:
            print(f"      ... and {len(metrics['launched_list']) - 20} more")

    # Top/Bottom 5 ROAS (traffic excluded)
    if metrics["top5_roas"]:
        print(f"\n  Top 5 ROAS Campaigns (CVR only, min spend >= ${MIN_SPEND_FOR_RANKING}):")
        for i, c in enumerate(metrics["top5_roas"], 1):
            print(f"    {i}. [{c['ad_channel']}] -> {c['sales_channel']} | {c['brand']} / {c['product']}")
            print(f"       {c['campaign'][:60]}")
            print(f"       Spend: ${c['spend']:,.2f}  Revenue: ${c['revenue']:,.2f}  ROAS: {c['roas']:.2f}  Start: {c['start_date'] or 'N/A'}")
    if metrics["bottom5_roas"]:
        print(f"\n  Bottom 5 ROAS Campaigns (CVR only):")
        for i, c in enumerate(metrics["bottom5_roas"], 1):
            print(f"    {i}. [{c['ad_channel']}] -> {c['sales_channel']} | {c['brand']} / {c['product']}")
            print(f"       {c['campaign'][:60]}")
            print(f"       Spend: ${c['spend']:,.2f}  Revenue: ${c['revenue']:,.2f}  ROAS: {c['roas']:.2f}  Start: {c['start_date'] or 'N/A'}")

    # OKR status
    print(f"\n  OKR Progress:")
    tw = metrics["this"]
    for name, val, target, lower_better in [
        ("ROAS (CVR)", tw["cvr_roas"], OKR_TARGETS["roas"], False),
        ("CAC", tw["cac"], OKR_TARGETS["cac"], True),
        ("Email Open Rate", tw["email_open_rate"], OKR_TARGETS["email_open_rate"], False),
    ]:
        if lower_better:
            pct = (target / val * 100) if val > 0 else 0
        else:
            pct = (val / target * 100) if target > 0 else 0
        status = "On Track" if pct >= 100 else ("At Risk" if pct >= 80 else "Behind")
        print(f"    {name}: {val:.2f} vs target {target:.2f} -> {pct:.0f}% [{status}]")


# ---------------------------------------------------------------------------
# Notion block builders
# ---------------------------------------------------------------------------


def _text(content, bold=False):
    """Build a rich_text text object."""
    obj = {"type": "text", "text": {"content": content}}
    if bold:
        obj["annotations"] = {"bold": True}
    return obj


def heading_2(text):
    return {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [_text(text)]}
    }


def heading_3(text):
    return {
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [_text(text)]}
    }


def paragraph(text, bold=False):
    return {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [_text(text, bold=bold)] if text else []}
    }


def bullet(text, children=None):
    """Bulleted list item, optionally with nested children blocks."""
    block = {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_text(text)]}
    }
    if children:
        block["bulleted_list_item"]["children"] = children
    return block


def numbered(text):
    return {
        "object": "block", "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": [_text(text)]}
    }


def todo(text, checked=False):
    return {
        "object": "block", "type": "to_do",
        "to_do": {"rich_text": [_text(text)], "checked": checked}
    }


def divider():
    return {"object": "block", "type": "divider", "divider": {}}


def table_block(column_count, rows):
    """Build a Notion table block with rows."""
    table_rows = []
    for row in rows:
        cells = []
        for cell_text in row:
            cells.append([{"type": "text", "text": {"content": str(cell_text)}}])
        table_rows.append({
            "object": "block", "type": "table_row",
            "table_row": {"cells": cells}
        })
    return {
        "object": "block", "type": "table",
        "table": {
            "table_width": column_count,
            "has_column_header": True,
            "has_row_header": True,
            "children": table_rows,
        }
    }


# ---------------------------------------------------------------------------
# Promo comparison
# ---------------------------------------------------------------------------


def load_promo_data():
    """Load promo comparison data from JSON file."""
    path = os.path.join(DATA_DIR, PROMO_FILE)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt_money(val):
    """Format as $X,XXX."""
    return f"${val:,.0f}"


def fmt_pct(val):
    """Format as X.X%."""
    return f"{val:.1f}%"


def build_promo_summary_table(promos):
    """Build the promo summary comparison table for Notion."""
    names = [p["name"] for p in promos]
    header = ["Metric"] + names

    rows = [header]
    rows.append(["Period"] + [f"{p['start']} ~ {p['end']}" for p in promos])
    rows.append(["Days"] + [str(p["days"]) for p in promos])

    s = [p["summary"] for p in promos]
    rows.append(["Total Sales"] + [fmt_money(x["total_sales"]) for x in s])
    rows.append(["Total Orders"] + [str(x["total_orders"]) for x in s])
    rows.append(["AOV"] + [f"${x['aov']:.2f}" for x in s])
    rows.append(["Discounts"] + [fmt_money(x["total_discounts"]) for x in s])
    rows.append(["CVR"] + [fmt_pct(x["cvr"]) for x in s])
    rows.append(["Meta Spend (Shopify Landing)"] + [fmt_money(x["meta_spend"]) for x in s])
    rows.append(["Meta ROAS (Shopify Landing)"] + [f"{x['meta_roas']:.2f}" for x in s])
    rows.append(["Google Spend"] + [fmt_money(x["google_spend"]) for x in s])
    rows.append(["Google ROAS"] + [f"{x['google_roas']:.2f}" for x in s])
    rows.append(["Total Ad Spend (excl. Traffic)"] + [fmt_money(x["total_ad_spend"]) for x in s])

    return table_block(len(header), rows)


def build_promo_traffic_table(promos):
    """Build traffic mix comparison table."""
    names = [p["name"] for p in promos]
    header = ["Channel"] + names
    rows = [header]

    for channel in ["email", "organic", "paid", "direct", "other"]:
        label = channel.capitalize()
        row = [label]
        for p in promos:
            t = p["summary"]["traffic"]
            sessions = t.get(channel, 0)
            total = sum(t.values())
            pct = (sessions / total * 100) if total > 0 else 0
            row.append(f"{sessions:,} ({pct:.0f}%)")
        rows.append(row)

    rows.append(["Total Sessions"] + [
        f"{sum(p['summary']['traffic'].values()):,}" for p in promos
    ])

    return table_block(len(header), rows)


def build_promo_blocks():
    """Build all promo comparison Notion blocks."""
    data = load_promo_data()
    if not data:
        return []

    promos = data.get("promos", [])
    if not promos:
        return []

    blocks = []
    blocks.append(heading_3("Promo Performance Comparison"))
    blocks.append(paragraph("Valentine's vs recent promos (Meta: Shopify landing only, excl. AMZ/Target traffic)"))
    blocks.append(build_promo_summary_table(promos))
    blocks.append(paragraph(""))
    blocks.append(heading_3("Traffic Mix by Channel"))
    blocks.append(build_promo_traffic_table(promos))

    return blocks


# ---------------------------------------------------------------------------
# Build the full page content
# ---------------------------------------------------------------------------


def okr_status(val, target, lower_is_better=False):
    """Return status emoji string."""
    if target is None or target == 0:
        return "N/A"
    if lower_is_better:
        pct = (target / val * 100) if val > 0 else 0
    else:
        pct = (val / target * 100) if target > 0 else 0
    if pct >= 100:
        return "\U0001f7e2"  # green circle
    elif pct >= 80:
        return "\U0001f7e1"  # yellow circle
    else:
        return "\U0001f534"  # red circle


def okr_progress(val, target, lower_is_better=False):
    """Return progress percentage string."""
    if target is None or target == 0:
        return "N/A"
    if lower_is_better:
        pct = (target / val * 100) if val > 0 else 0
    else:
        pct = (val / target * 100) if target > 0 else 0
    return f"{pct:.0f}%"


def _vs(this_val, last_val, fmt_fn):
    """Format 'value (vs. last)' string."""
    return f"{fmt_fn(this_val)} (vs. {fmt_fn(last_val)})"


def _fmt_dollar(val):
    return f"${val:,.2f}"


def _fmt_roas(val):
    return f"{val:.2f}"


def _fmt_pct(val):
    return f"{val:.1f}%"


def _fmt_pct2(val):
    return f"{val:.2f}%"


def build_section2_content(metrics):
    """Build Section 2 auto-fill blocks (OKR table, KPM, Top/Bottom 5, Promo).

    These blocks are inserted after the "Performance Team OKR Progress" heading.
    Used by both create and update modes.
    """
    tw = metrics["this"]
    lw = metrics["last"]
    blocks = []

    blocks.append(paragraph("Scale efficient customer acquisition through optimized performance marketing"))

    # OKR Table
    blocks.append(table_block(6, [
        ["Key Result", "Target", "Last Week", "This Week", "Progress", "Status"],
        ["E-mail Campaign Automations", "50", "[#]", "[#]", "[%]", "\U0001f7e1"],
        ["Ad Creatives Developed & Tested", "30", "[#]", "[#]", "[%]", "\U0001f7e1"],
        [
            "Ad Campaigns Launched (Google & Meta)",
            "100",
            str(metrics["campaigns_launched_last"]),
            str(metrics["campaigns_launched"]),
            "[%]",
            "\U0001f7e1",
        ],
        [
            "ROAS (CVR Campaigns)",
            f"{OKR_TARGETS['roas']:.1f}",
            f"{lw['cvr_roas']:.2f}",
            f"{tw['cvr_roas']:.2f}",
            okr_progress(tw["cvr_roas"], OKR_TARGETS["roas"]),
            okr_status(tw["cvr_roas"], OKR_TARGETS["roas"]),
        ],
        [
            "CAC (CVR Campaigns)",
            f"${OKR_TARGETS['cac']:.0f}",
            f"${lw['cac']:.2f}",
            f"${tw['cac']:.2f}",
            okr_progress(tw["cac"], OKR_TARGETS["cac"], lower_is_better=True),
            okr_status(tw["cac"], OKR_TARGETS["cac"], lower_is_better=True),
        ],
        [
            "Email Open Rate",
            f"{OKR_TARGETS['email_open_rate']:.0f}%",
            f"{lw['email_open_rate']:.1f}%",
            f"{tw['email_open_rate']:.1f}%",
            okr_progress(tw["email_open_rate"], OKR_TARGETS["email_open_rate"]),
            okr_status(tw["email_open_rate"], OKR_TARGETS["email_open_rate"]),
        ],
    ]))

    # ---- Key Performance Metrics ---- AUTO-FILLED with nested bullets
    blocks.append(heading_3("Key Performance Metrics"))

    # Total Ad Spend with CVR/Traffic breakdown
    blocks.append(bullet(
        f"Total Ad Spend: {_vs(tw['total_spend'], lw['total_spend'], _fmt_dollar)}",
        children=[
            bullet(f"CVR Campaigns: ${tw['cvr_spend']:,.2f}"),
            bullet(f"Traffic Campaigns: ${tw['traffic_total_spend']:,.2f}"),
        ]
    ))

    # Revenue
    blocks.append(bullet(
        f"Revenue Generated (Shopify): {_vs(tw['shopify_revenue'], lw['shopify_revenue'], _fmt_dollar)}"
    ))

    # CVR Campaign ROAS with per-channel breakdown
    blocks.append(bullet(
        f"CVR Campaign ROAS: {_vs(tw['cvr_roas'], lw['cvr_roas'], _fmt_roas)}",
        children=[
            bullet(f"Meta (CVR): {tw['meta_cvr_roas']:.2f} (${tw['meta_cvr_spend']:,.0f} spend)"),
            bullet(f"Google Ads: {tw['google_roas']:.2f} (${tw['google_spend']:,.0f} spend)"),
            bullet(f"TikTok Ads: {tw['tiktok_roas']:.2f} (${tw['tiktok_spend']:,.0f} spend)"),
            bullet(f"Amazon Ads (non-Grosmimi): {tw['amazon_cvr_roas']:.2f} (${tw['amazon_cvr_spend']:,.0f} spend)"),
        ]
    ))

    # Traffic Campaign CPC with per-source breakdown
    blocks.append(bullet(
        f"Traffic Campaign Avg CPC: {_vs(tw['traffic_avg_cpc'], lw['traffic_avg_cpc'], _fmt_dollar)}",
        children=[
            bullet(f"Meta -> AMZ: CPC ${tw['traffic_meta_amz_cpc']:.2f} (${tw['traffic_meta_amz_spend']:,.0f} spend)"),
            bullet(f"Meta -> Target: CPC ${tw['traffic_meta_target_cpc']:.2f} (${tw['traffic_meta_target_spend']:,.0f} spend)"),
            bullet(f"Meta Other Traffic: CPC ${tw['traffic_meta_other_cpc']:.2f} (${tw['traffic_meta_other_spend']:,.0f} spend)"),
        ]
    ))

    # CAC
    blocks.append(bullet(
        f"CAC (CVR Campaigns): {_vs(tw['cac'], lw['cac'], _fmt_dollar)}",
        children=[
            bullet(f"= CVR Spend / Shopify Orders ({tw['shopify_orders']} orders)"),
        ]
    ))

    # Conversion Rate
    blocks.append(bullet(
        f"Conversion Rate: {_vs(tw['cvr'], lw['cvr'], _fmt_pct)}",
        children=[
            bullet(f"GA4: {tw['ga_purchases']} purchases / {tw['ga_sessions']} sessions"),
        ]
    ))

    # Email CTR
    blocks.append(bullet(
        f"Email Click-through Rate: {_vs(tw['email_ctr'], lw['email_ctr'], _fmt_pct2)}"
    ))

    # Campaigns Launched
    blocks.append(bullet(
        f"Campaigns Launched (Google & Meta): {metrics['campaigns_launched']} this week / {metrics['campaigns_launched_last']} last week"
    ))

    # Top 5 / Bottom 5 ROAS campaigns (traffic excluded)
    if metrics["top5_roas"]:
        blocks.append(heading_3("Top 5 ROAS Campaigns (CVR Only)"))
        top_rows = [["#", "Ad Channel", "Sales Channel", "Brand / Product",
                     "Campaign", "Spend", "Sales", "ROAS", "Start Date"]]
        for i, c in enumerate(metrics["top5_roas"], 1):
            camp_short = c["campaign"][:40] + ("..." if len(c["campaign"]) > 40 else "")
            top_rows.append([
                str(i), c["ad_channel"], c["sales_channel"],
                f"{c['brand']} / {c['product']}",
                camp_short, f"${c['spend']:,.0f}", f"${c['revenue']:,.0f}",
                f"{c['roas']:.2f}", c["start_date"] or "-",
            ])
        blocks.append(table_block(9, top_rows))

    if metrics["bottom5_roas"]:
        blocks.append(heading_3("Bottom 5 ROAS Campaigns (CVR Only)"))
        bot_rows = [["#", "Ad Channel", "Sales Channel", "Brand / Product",
                     "Campaign", "Spend", "Sales", "ROAS", "Start Date"]]
        for i, c in enumerate(metrics["bottom5_roas"], 1):
            camp_short = c["campaign"][:40] + ("..." if len(c["campaign"]) > 40 else "")
            bot_rows.append([
                str(i), c["ad_channel"], c["sales_channel"],
                f"{c['brand']} / {c['product']}",
                camp_short, f"${c['spend']:,.0f}", f"${c['revenue']:,.0f}",
                f"{c['roas']:.2f}", c["start_date"] or "-",
            ])
        blocks.append(table_block(9, bot_rows))

    blocks.append(heading_3("Wins & Achievements"))
    blocks.append(bullet("[Specific win or achievement]"))
    blocks.append(bullet("[Specific win or achievement]"))

    # Promo Comparison
    promo_blocks = build_promo_blocks()
    if promo_blocks:
        blocks.append(paragraph(""))
        blocks.extend(promo_blocks)

    # Empty paragraph before next section divider
    blocks.append(paragraph(""))

    return blocks


def build_page_blocks(metrics):
    """Build all Notion blocks for the weekly report page (create mode)."""
    tw = metrics["this"]
    lw = metrics["last"]
    wn = metrics["week_num"]

    blocks = []

    # -- Header --
    blocks.append(paragraph("Team: Performance Team (Paid Marketing)", bold=True))
    blocks.append(paragraph(f"Week of: [{metrics['this_friday']} ~ {metrics['this_thursday']}] (Fri-Thu PST)"))
    blocks.append(paragraph("Team Member: Jisun Hyun"))
    blocks.append(divider())
    blocks.append(paragraph(""))

    # -- Section 1: Focus Areas --
    blocks.append(heading_2("1\ufe0f\u20e3 What did I focus on last week?"))
    blocks.append(heading_3("Primary Focus Areas"))
    blocks.append(bullet("[Focus area 1]"))
    blocks.append(bullet("[Focus area 2]"))
    blocks.append(bullet("[Focus area 3]"))
    blocks.append(heading_3("Campaigns & Initiatives"))
    blocks.append(bullet("Campaign Name: [Description of what you worked on]"))
    blocks.append(bullet("Campaign Name: [Description of what you worked on]"))
    blocks.append(heading_3("Time Allocation"))
    blocks.append(bullet("Email Campaigns: [Hours or %]"))
    blocks.append(bullet("Ad Creative Development: [Hours or %]"))
    blocks.append(bullet("Campaign Setup & Management: [Hours or %]"))
    blocks.append(bullet("Testing & Optimization: [Hours or %]"))
    blocks.append(heading_3("Analysis & Reporting"))
    blocks.append(bullet("[Description]"))

    # -- Section 2: Results (OKRs) -- AUTO-FILLED --
    blocks.append(heading_2("2\ufe0f\u20e3 What were the results? (OKRs)"))
    blocks.append(heading_3("Performance Team OKR Progress"))
    blocks.extend(build_section2_content(metrics))

    # -- Section 3: Issues --
    blocks.append(heading_2("3\ufe0f\u20e3 What were issues I faced?"))
    blocks.append(heading_3("Challenges & Obstacles"))
    blocks.append(bullet("[Challenge description]"))
    blocks.append(bullet("[Challenge description]"))
    blocks.append(heading_3("Blockers"))
    blocks.append(todo("[Blocker description]"))
    blocks.append(todo("[Blocker description]"))
    blocks.append(heading_3("Resource Needs"))
    blocks.append(bullet("[Resource or support needed]"))

    # -- Section 4: Problem Solving --
    blocks.append(heading_2("4\ufe0f\u20e3 What problems did I solve / what did I learn?"))
    blocks.append(heading_3("Problem Solving"))
    blocks.append(bullet("[Problem description]"))
    blocks.append(bullet("[Problem description]"))
    blocks.append(heading_3("Key Learnings & Insights"))
    blocks.append(bullet("[Learning/insight]"))
    blocks.append(bullet("[Learning/insight]"))
    blocks.append(heading_3("Best Practices Identified"))
    blocks.append(bullet("[Best practice to share with team]"))
    blocks.append(bullet("[Best practice to share with team]"))

    # -- Section 5: Next Week --
    blocks.append(heading_2("5\ufe0f\u20e3 What will I do next week?"))
    blocks.append(heading_3("Planned Tasks"))
    blocks.append(numbered("[Priority task] - Expected impact: [Impact]"))
    blocks.append(numbered("[Priority task] - Expected impact: [Impact]"))
    blocks.append(numbered("[Priority task] - Expected impact: [Impact]"))
    blocks.append(heading_3("Key Result Focus"))
    blocks.append(paragraph("[Which key result you'll focus on]"))
    blocks.append(paragraph("[What you aim to achieve]"))
    blocks.append(heading_3("Support Needed"))
    blocks.append(bullet("[What you need from other teams or leadership]"))
    blocks.append(heading_3("Next Week Breakdown"))
    blocks.append(bullet("Ad Creative Development: [%]"))
    blocks.append(bullet("Campaign Management: [%]"))
    blocks.append(bullet("Testing & Optimization: [%]"))

    # -- Footer --
    blocks.append(paragraph(""))
    blocks.append(divider())
    blocks.append(paragraph(""))
    blocks.append(paragraph(f"Report submitted: [{metrics['this_friday']}]"))

    return blocks


# ---------------------------------------------------------------------------
# Notion page creation
# ---------------------------------------------------------------------------


def create_notion_page(metrics):
    """Create a new weekly report page in Notion."""
    wn = metrics["week_num"]
    blocks = build_page_blocks(metrics)

    # Notion API limits children to 100 blocks per call
    first_batch = blocks[:100]
    remaining = blocks[100:]

    body = {
        "parent": {"database_id": WEEKLY_REPORT_DB_ID},
        "icon": {"type": "emoji", "emoji": "\U0001f4ca"},
        "properties": {
            "Report File": {
                "title": [{"text": {"content": f"[WK{wn}] - Performance Team Weekly Report"}}]
            },
            "Report Date": {
                "date": {"start": metrics["this_friday"]}
            },
            "Team": {
                "select": {"name": "Performance Team"}
            },
            "Member": {
                "people": [{"id": IRENE_USER_ID}]
            },
        },
        "children": first_batch,
    }

    print("\n  Creating Notion page...")
    result = notion_api("POST", "pages", body)
    if not result:
        print("  ERROR: Failed to create page")
        return None

    page_id = result["id"]
    page_url = result.get("url", "")
    print(f"  Page created: {page_id}")
    if page_url:
        print(f"  URL: {page_url}")

    # Append remaining blocks if any
    if remaining:
        print(f"  Appending {len(remaining)} additional blocks...")
        time.sleep(0.35)
        append_body = {"children": remaining}
        notion_api("PATCH", f"blocks/{page_id}/children", append_body)

    return page_id


def update_notion_page(metrics, page_id):
    """Update Section 2 auto-fill data on an existing weekly report page.

    Strategy:
    1. Get all child blocks of the page
    2. Find "Performance Team OKR Progress" heading (anchor)
    3. Delete everything between anchor and the next divider
    4. Insert new auto-fill blocks after the anchor
    5. Update header/footer text blocks
    """
    print("\n  Reading existing page blocks...")
    all_blocks = get_all_child_blocks(page_id)
    if not all_blocks:
        print("  ERROR: Could not read page blocks")
        return None

    # Find anchor heading and blocks to delete
    anchor_id = None
    delete_ids = []
    found_anchor = False

    for b in all_blocks:
        btype = b.get("type", "")
        text = get_block_text(b)

        if btype == "heading_3" and "OKR Progress" in text:
            found_anchor = True
            anchor_id = b["id"]
            continue

        if found_anchor:
            if btype == "divider":
                break  # Stop before Section 3 divider
            delete_ids.append(b["id"])

    if not anchor_id:
        print("  ERROR: Could not find 'Performance Team OKR Progress' heading")
        return None

    # Update header text blocks
    for b in all_blocks:
        text = get_block_text(b)
        btype = b.get("type", "")
        if btype == "paragraph" and text.startswith("Week of:"):
            new_text = f"Week of: [{metrics['this_friday']} ~ {metrics['this_thursday']}] (Fri-Thu PST)"
            notion_api("PATCH", f"blocks/{b['id']}", {
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": new_text}}]}
            })
            print(f"    Updated 'Week of' header")
            time.sleep(0.1)
        if btype == "paragraph" and text.startswith("Report submitted:"):
            new_text = f"Report submitted: [{metrics['this_friday']}]"
            notion_api("PATCH", f"blocks/{b['id']}", {
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": new_text}}]}
            })
            print(f"    Updated 'Report submitted' footer")
            time.sleep(0.1)

    # Delete old Section 2 content blocks
    print(f"  Deleting {len(delete_ids)} old Section 2 blocks...")
    for bid in delete_ids:
        notion_api("DELETE", f"blocks/{bid}")
        time.sleep(0.12)  # Rate limit safety

    # Build new Section 2 content
    section2_blocks = build_section2_content(metrics)
    print(f"  Inserting {len(section2_blocks)} new blocks...")

    # Insert in batches of 100 after the anchor
    current_after = anchor_id
    for i in range(0, len(section2_blocks), 100):
        batch = section2_blocks[i:i + 100]
        body = {"children": batch, "after": current_after}
        result = notion_api("PATCH", f"blocks/{page_id}/children", body)
        if result and result.get("results"):
            current_after = result["results"][-1]["id"]
        time.sleep(0.35)

    print(f"  Page updated successfully: {page_id}")
    return page_id


# ---------------------------------------------------------------------------
# Discover mode
# ---------------------------------------------------------------------------


def discover():
    """Print data file status and Notion DB info."""
    print("=" * 60)
    print("WEEKLY PERFORMANCE REPORT \u2014 DISCOVER")
    print("=" * 60)

    print("\n--- Data Files ---")
    for key, fname in DATA_FILES.items():
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            size = os.path.getsize(path)
            data = load_json(fname)
            rows = len(data.get("tableData", []))
            dates = sorted(set(r.get("date", "") for r in data.get("tableData", [])))
            print(f"  {key:10s}: {fname} ({size:,} bytes, {rows} rows)")
            if dates:
                print(f"             Dates: {', '.join(dates)}")
        else:
            print(f"  {key:10s}: {fname} \u2014 MISSING")

    print("\n--- Notion Database ---")
    try:
        db = notion_api("GET", f"databases/{WEEKLY_REPORT_DB_ID}")
        if db:
            title = "".join(t.get("plain_text", "") for t in db.get("title", []))
            print(f"  Title: {title}")
            print(f"  Properties:")
            for name, config in db.get("properties", {}).items():
                print(f"    {name}: {config.get('type', '?')}")
    except Exception as e:
        print(f"  ERROR: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Weekly Performance Report: Polar data -> Notion page"
    )
    parser.add_argument("--week", type=str,
                        help="Target week in ISO format (e.g., 2026-W08)")
    parser.add_argument("--page-id", type=str,
                        help="Update an existing Notion page instead of creating new")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calculate metrics without creating/updating Notion page")
    parser.add_argument("--discover", action="store_true",
                        help="Show data files and Notion DB status")
    args = parser.parse_args()

    if not any([args.week, args.discover]):
        parser.print_help()
        return

    if args.discover:
        discover()
        return

    if not args.week:
        print("ERROR: --week is required (e.g., --week 2026-W08)")
        return

    mode = "UPDATE" if args.page_id else "CREATE"

    # Calculate metrics
    print("=" * 60)
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}WEEKLY PERFORMANCE REPORT ({mode})")
    print("=" * 60)

    print(f"\nStep 1: Loading data for {args.week}...")
    metrics = calculate_metrics(args.week)

    print(f"\nStep 2: Calculating metrics...")
    print_summary(metrics)

    if args.dry_run:
        print(f"\n[DRY RUN] Skipping Notion {mode.lower()}.")
        return

    if args.page_id:
        # Update existing page
        print(f"\nStep 3: Updating existing Notion page {args.page_id}...")
        page_id = update_notion_page(metrics, args.page_id)
    else:
        # Create new page
        print(f"\nStep 3: Creating Notion page...")
        page_id = create_notion_page(metrics)

    if page_id:
        print("\n" + "=" * 60)
        print("SUCCESS")
        print("=" * 60)
        print(f"  Mode: {mode}")
        print(f"  Week: {metrics['week']}")
        print(f"  Period: {metrics['this_friday']} ~ {metrics['this_thursday']} (Fri-Thu PST)")
        print(f"  Page ID: {page_id}")
        print(f"  Open in Notion to verify the report.")
    else:
        print(f"\nFAILED: Could not {mode.lower()} Notion page.")


if __name__ == "__main__":
    main()
