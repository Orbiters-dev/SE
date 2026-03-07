# -*- coding: utf-8 -*-
"""
weekly_performance_notion.py - Weekly Performance Report Notion Page Creator

Collects campaign-level data from Meta, Google, Amazon APIs and Shopify,
then creates a Notion page following the standard weekly report template.

Template: WK8-9 format (excl. Promo Performance Comparison)
Reference: https://www.notion.so/WK8-9-Performance-Team-Weekly-Report-1-31a86c6dc04680eb95ecd495eca2aa26

Usage:
    python tools/weekly_performance_notion.py --week WK11
    python tools/weekly_performance_notion.py --week WK11 --archive-page <page_id>
    python tools/weekly_performance_notion.py --start 2026-03-06 --end 2026-03-12 --label WK11
    python tools/weekly_performance_notion.py --week WK10 --dry-run
"""
import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
TMP  = ROOT / ".tmp"

# ── Credentials ────────────────────────────────────────────────────────────
META_TOKEN   = os.environ.get('META_ACCESS_TOKEN', '')
META_ACCOUNT = os.environ.get('META_AD_ACCOUNT_ID', '')
NOTION_TOKEN = os.environ.get('NOTION_API_TOKEN', '')
NOTION_DB    = '2fb86c6dc04680988f1fe3a5803eb4f0'

# ── Brand classification (shared with run_meta_ads_daily.py) ──────────────
BRAND_RULES = [
    ("Grosmimi",    ["grosmimi", "grosm", "ppsu", "stainless steel", "sls cup",
                     "stainless straw", "| gm |", " gm |", "| gm_", "_gm_", "gm_tumbler",
                     "dentalmom", "dental mom", "dental_mom", "livfuselli", "tumbler",
                     "laurence"]),
    ("CHA&MOM",     ["cha&mom", "cha_mom", "chamom", "| cm |", " cm |", "| cm_", "_cm_",
                     "skincare", "lotion", "hair wash", "love&care", "love_care", "love care"]),
    ("Alpremio",    ["alpremio"]),
    ("Easy Shower", ["easy shower", "easy_shower", "easyshower", "shower stand"]),
    ("Hattung",     ["hattung"]),
    ("Beemymagic",  ["beemymagic", "beemy"]),
    ("Comme Moi",   ["commemoi", "comme moi", "commemo"]),
    ("Naeiae",      ["naeiae", "rice snack", "pop rice", "clearance"]),
    ("RIDE & GO",   ["ride & go", "ridego", "ride_go"]),
    ("Promo",       ["newyear", "new year", "asc campaign (legacy)", "promo campaign"]),
]

BRAND_URL_RULES = [
    ("Grosmimi",    ["grosmimi"]),
    ("CHA&MOM",     ["cha-mom", "chamom", "cha_mom"]),
    ("Alpremio",    ["alpremio"]),
    ("Easy Shower", ["easy-shower", "easyshower"]),
    ("Naeiae",      ["naeiae"]),
    ("Hattung",     ["hattung"]),
]

def classify_brand(name):
    n = name.lower()
    for brand, kws in BRAND_RULES:
        if any(k in n for k in kws):
            return brand
    return "General"

def classify_brand_by_url(url):
    """Fallback brand classification using landing page URL."""
    if not url:
        return None
    u = url.lower()
    for brand, kws in BRAND_URL_RULES:
        if any(k in u for k in kws):
            return brand
    return None

def classify_type(name):
    """Classify campaign type. PMax campaigns treated as CVR."""
    n = name.lower()
    if 'cvr' in n or 'conversion' in n:
        return 'cvr'
    if 'pmax' in n or 'performance max' in n:
        return 'cvr'
    if 'traffic' in n or 'awareness' in n:
        return 'traffic'
    return 'other'


# ══════════════════════════════════════════════════════════════════════════
# Week Date Utilities
# ══════════════════════════════════════════════════════════════════════════

def week_dates(week_label):
    """Convert WKnn label to (start_date, end_date) strings.

    Week basis: Fri-Thu PST. WK number = ISO week of the ending Thursday.
    WK10 = 2026-02-27 (Fri) ~ 2026-03-05 (Thu)
    """
    wk_num = int(week_label.upper().replace('WK', ''))
    # Find the Thursday of the given ISO week in the current year
    year = date.today().year
    # ISO week 1 day 4 (Thursday) of the year
    jan4 = date(year, 1, 4)  # Jan 4 is always in ISO week 1
    # Monday of ISO week 1
    iso_w1_mon = jan4 - timedelta(days=jan4.isoweekday() - 1)
    # Thursday of the target week
    thu = iso_w1_mon + timedelta(weeks=wk_num - 1, days=3)
    # Friday of the same week (6 days before Thursday)
    fri = thu - timedelta(days=6)
    return fri.isoformat(), thu.isoformat()

def prev_week_label(week_label):
    """Return previous week label: WK10 -> WK9, WK1 -> WK52 (prior year)."""
    num = int(week_label.upper().replace('WK', ''))
    if num <= 1:
        return 'WK52'
    return f'WK{num - 1}'


# ══════════════════════════════════════════════════════════════════════════
# Data Fetchers
# ══════════════════════════════════════════════════════════════════════════

def _fetch_meta_campaign_urls():
    """Fetch ad landing URLs grouped by campaign_id for brand fallback."""
    url = f"https://graph.facebook.com/v18.0/{META_ACCOUNT}/ads"
    params = {
        'access_token': META_TOKEN,
        'fields': 'campaign_id,creative{effective_object_story_spec}',
        'limit': 500,
        'filtering': json.dumps([
            {'field': 'effective_status', 'operator': 'IN',
             'value': ['ACTIVE', 'PAUSED']}
        ]),
    }
    camp_urls = {}  # campaign_id -> first URL found
    req_url = url + '?' + urllib.parse.urlencode(params)
    try:
        while req_url:
            resp = requests.get(req_url, timeout=60)
            data = resp.json()
            if 'error' in data:
                break
            for ad in data.get('data', []):
                cid = ad.get('campaign_id', '')
                creative = ad.get('creative', {})
                spec = creative.get('effective_object_story_spec', {})
                link_data = spec.get('link_data', {})
                link_url = link_data.get('link', '')
                if link_url and cid and cid not in camp_urls:
                    camp_urls[cid] = link_url
            req_url = data.get('paging', {}).get('next')
    except Exception as e:
        print(f"  [META] URL fetch error (non-fatal): {e}")
    return camp_urls


def fetch_meta_campaigns(start, end):
    """Fetch campaign-level insights from Meta Graph API.

    Uses landing URL for brand classification when campaign name is insufficient.
    """
    # Step 1: Get campaign ad URLs for brand fallback
    camp_urls = _fetch_meta_campaign_urls()

    # Step 2: Get campaign-level insights
    url = f"https://graph.facebook.com/v18.0/{META_ACCOUNT}/insights"
    params = {
        'access_token': META_TOKEN,
        'level': 'campaign',
        'fields': 'campaign_id,campaign_name,spend,impressions,clicks,actions,action_values',
        'time_range': json.dumps({'since': start, 'until': end}),
        'time_increment': 'all_days',
        'limit': 500,
    }
    campaigns = []
    req_url = url + '?' + urllib.parse.urlencode(params)
    while req_url:
        resp = requests.get(req_url, timeout=60)
        data = resp.json()
        if 'error' in data:
            print(f"  [META ERROR] {data['error'].get('message', '')}")
            break
        campaigns.extend(data.get('data', []))
        req_url = data.get('paging', {}).get('next')

    results = []
    for c in campaigns:
        spend = float(c.get('spend', 0))
        if spend == 0:
            continue
        conv_value = 0
        for av in (c.get('action_values') or []):
            if av['action_type'] in ('omni_purchase', 'purchase'):
                conv_value += float(av.get('value', 0))
        purchases = 0
        for a in (c.get('actions') or []):
            if a['action_type'] in ('omni_purchase', 'purchase'):
                purchases += int(float(a.get('value', 0)))

        name = c.get('campaign_name', '')
        cid = c.get('campaign_id', '')

        # Brand: try name first, then URL fallback
        brand = classify_brand(name)
        if brand == 'General' and cid in camp_urls:
            url_brand = classify_brand_by_url(camp_urls[cid])
            if url_brand:
                brand = url_brand

        roas = conv_value / spend if spend > 0 else 0
        results.append({
            'channel': 'Meta',
            'sales_channel': 'Onzenna',
            'campaign': name,
            'brand': brand,
            'type': classify_type(name),
            'spend': spend,
            'sales': conv_value,
            'roas': roas,
            'purchases': purchases,
            'impressions': int(c.get('impressions', 0)),
            'clicks': int(c.get('clicks', 0)),
        })
    return results


def fetch_google_campaigns(start, end):
    """Fetch campaign-level data from Google Ads API."""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("  [GOOGLE] google-ads library not available, skipping")
        return []

    dev_token    = os.environ.get('GOOGLE_ADS_DEVELOPER_TOKEN', '')
    client_id    = os.environ.get('GOOGLE_ADS_CLIENT_ID', '')
    client_secret = os.environ.get('GOOGLE_ADS_CLIENT_SECRET', '')
    refresh_token = os.environ.get('GOOGLE_ADS_REFRESH_TOKEN', '')
    login_cid    = os.environ.get('GOOGLE_ADS_LOGIN_CUSTOMER_ID', '8625697405')

    if not all([dev_token, client_id, client_secret, refresh_token]):
        print("  [GOOGLE] Missing credentials, skipping")
        return []

    config = {
        'developer_token': dev_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'login_customer_id': login_cid,
        'use_proto_plus': True,
    }
    client = GoogleAdsClient.load_from_dict(config)
    ga_service = client.get_service("GoogleAdsService")

    # Discover sub-accounts
    query_clients = """
        SELECT customer_client.id, customer_client.descriptive_name,
               customer_client.manager
        FROM customer_client
        WHERE customer_client.manager = FALSE
    """
    customer_ids = []
    try:
        response = ga_service.search(customer_id=login_cid, query=query_clients)
        for row in response:
            customer_ids.append(str(row.customer_client.id))
    except Exception as e:
        print(f"  [GOOGLE] MCC query error: {e}")
        customer_ids = [login_cid]

    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
          AND metrics.impressions > 0
    """
    results = []
    for cid in customer_ids:
        try:
            response = ga_service.search(customer_id=cid, query=query)
            for row in response:
                name = row.campaign.name
                spend = row.metrics.cost_micros / 1_000_000
                conv_value = row.metrics.conversions_value
                roas = conv_value / spend if spend > 0 else 0
                results.append({
                    'channel': 'Google',
                    'sales_channel': 'Onzenna',
                    'campaign': name,
                    'brand': classify_brand(name),
                    'type': classify_type(name),
                    'spend': round(spend, 2),
                    'sales': round(conv_value, 2),
                    'roas': round(roas, 2),
                    'purchases': int(row.metrics.conversions),
                    'impressions': row.metrics.impressions,
                    'clicks': row.metrics.clicks,
                })
        except Exception as e:
            print(f"  [GOOGLE] CID {cid} error: {e}")
    return results


def fetch_amazon_campaigns(start, end):
    """Fetch Amazon Ads campaign data (excl Grosmimi)."""
    amz_client_id     = os.environ.get('AMZ_ADS_CLIENT_ID', '')
    amz_client_secret = os.environ.get('AMZ_ADS_CLIENT_SECRET', '')
    amz_refresh       = os.environ.get('AMZ_ADS_REFRESH_TOKEN', '')

    if not all([amz_client_id, amz_client_secret, amz_refresh]):
        print("  [AMAZON] Missing credentials, skipping")
        return []

    # Get access token
    token_data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'client_id': amz_client_id,
        'client_secret': amz_client_secret,
        'refresh_token': amz_refresh,
    }).encode()
    req = urllib.request.Request('https://api.amazon.com/auth/o2/token',
                                data=token_data,
                                headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_resp = json.loads(resp.read())
        access_token = token_resp['access_token']
    except Exception as e:
        print(f"  [AMAZON] Token error: {e}")
        return []

    headers = {
        'Amazon-Advertising-API-ClientId': amz_client_id,
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    try:
        req = urllib.request.Request('https://advertising-api.amazon.com/v2/profiles',
                                    headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            profiles = json.loads(resp.read())
    except Exception as e:
        print(f"  [AMAZON] Profiles error: {e}")
        return []

    GROSMIMI_NAMES = ['grosmimi', 'grosmimi usa']
    PROFILE_BRAND_MAP = {'fleeters': 'Naeiae', 'orbitool': 'CHA&MOM'}

    us_profiles = []
    for p in profiles:
        if p.get('countryCode') == 'US':
            name = (p.get('accountInfo', {}).get('name', '') or '').lower()
            if not any(g in name for g in GROSMIMI_NAMES):
                us_profiles.append(p)

    results = []
    for profile in us_profiles:
        pid = str(profile['profileId'])
        pname = profile.get('accountInfo', {}).get('name', '') or ''
        brand = 'Non-classified'
        for key, b in PROFILE_BRAND_MAP.items():
            if key in pname.lower():
                brand = b
                break

        headers_p = {**headers, 'Amazon-Advertising-API-Scope': pid}

        # Amazon Reporting API v3: use YYYY-MM-DD format, DAILY timeUnit
        # (SUMMARY timeUnit is not supported for spCampaigns)
        report_body = json.dumps({
            'name': f'weekly_{start}_{pid}',
            'startDate': start,
            'endDate': end,
            'configuration': {
                'adProduct': 'SPONSORED_PRODUCTS',
                'groupBy': ['campaign'],
                'columns': ['date', 'impressions', 'clicks', 'cost', 'sales14d',
                            'purchases14d', 'campaignName', 'campaignId'],
                'reportTypeId': 'spCampaigns',
                'timeUnit': 'DAILY',
                'format': 'GZIP_JSON',
            }
        }).encode()

        try:
            req = urllib.request.Request('https://advertising-api.amazon.com/reporting/reports',
                                        data=report_body, headers=headers_p, method='POST')
            with urllib.request.urlopen(req, timeout=60) as resp:
                report_resp = json.loads(resp.read())
            report_id = report_resp.get('reportId', '')
        except Exception as e:
            print(f"  [AMAZON] Report create error ({pname}): {e}")
            continue

        # Poll (max 300s — Grosmimi USA has many campaigns, needs longer)
        report_url = None
        for _ in range(60):
            time.sleep(5)
            try:
                req = urllib.request.Request(
                    f'https://advertising-api.amazon.com/reporting/reports/{report_id}',
                    headers=headers_p)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status = json.loads(resp.read())
                if status.get('status') == 'COMPLETED':
                    report_url = status.get('url', '')
                    break
                elif status.get('status') == 'FAILURE':
                    print(f"  [AMAZON] Report failed ({pname}): {status.get('failureReason','')}")
                    break
            except Exception as e:
                print(f"  [AMAZON] Poll error: {e}")

        if not report_url:
            print(f"  [AMAZON] Report timeout ({pname})")
            continue

        try:
            req = urllib.request.Request(report_url)
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = gzip.decompress(resp.read())
            rows = json.loads(raw)
        except Exception as e:
            print(f"  [AMAZON] Download error ({pname}): {e}")
            continue

        # Aggregate daily rows to campaign level
        camp_agg = {}
        for row in rows:
            cname = row.get('campaignName', '')
            if cname not in camp_agg:
                camp_agg[cname] = {'spend': 0, 'sales': 0, 'purchases': 0,
                                   'impressions': 0, 'clicks': 0}
            camp_agg[cname]['spend'] += float(row.get('cost', 0))
            camp_agg[cname]['sales'] += float(row.get('sales14d', 0))
            camp_agg[cname]['purchases'] += int(row.get('purchases14d', 0))
            camp_agg[cname]['impressions'] += int(row.get('impressions', 0))
            camp_agg[cname]['clicks'] += int(row.get('clicks', 0))

        for cname, agg in camp_agg.items():
            if agg['spend'] == 0:
                continue
            results.append({
                'channel': 'Amazon',
                'sales_channel': 'Amazon',
                'campaign': cname,
                'brand': brand if brand != 'Non-classified' else classify_brand(cname),
                'type': 'cvr',
                'spend': round(agg['spend'], 2),
                'sales': round(agg['sales'], 2),
                'roas': round(agg['sales'] / agg['spend'], 2) if agg['spend'] > 0 else 0,
                'purchases': agg['purchases'],
                'impressions': agg['impressions'],
                'clicks': agg['clicks'],
            })

    return results


def fetch_shopify(start, end):
    """Fetch Shopify order totals for a date range (PST)."""
    shop  = os.environ.get('SHOPIFY_SHOP', '')
    token = os.environ.get('SHOPIFY_ACCESS_TOKEN', '')
    if not shop or not token:
        print("  [SHOPIFY] Missing credentials")
        return {'sales': 0, 'orders': 0}

    url = f"https://{shop}/admin/api/2024-01/orders.json"
    hdrs = {'X-Shopify-Access-Token': token}

    total_sales = 0
    total_orders = 0
    params = {
        'status': 'any',
        'created_at_min': f'{start}T00:00:00-08:00',
        'created_at_max': f'{end}T23:59:59-08:00',
        'limit': 250,
        'fields': 'id,total_price,financial_status',
    }

    page_url = url + '?' + urllib.parse.urlencode(params)
    while page_url:
        resp = requests.get(page_url, headers=hdrs, timeout=60)
        data = resp.json()
        for o in data.get('orders', []):
            if o.get('financial_status') not in ('refunded', 'voided'):
                total_sales += float(o.get('total_price', 0))
                total_orders += 1
        link = resp.headers.get('Link', '')
        if 'rel="next"' in link:
            for part in link.split(','):
                if 'rel="next"' in part:
                    page_url = part.split('<')[1].split('>')[0]
                    break
        else:
            page_url = None

    return {'sales': round(total_sales, 2), 'orders': total_orders}


# ══════════════════════════════════════════════════════════════════════════
# Notion Block Helpers
# ══════════════════════════════════════════════════════════════════════════

def txt(s):
    return [{'type': 'text', 'text': {'content': str(s)}}]

def bold_txt(label, value):
    return [
        {'type': 'text', 'text': {'content': str(label)}, 'annotations': {'bold': True}},
        {'type': 'text', 'text': {'content': str(value)}},
    ]

def h2(s):
    return {'object': 'block', 'type': 'heading_2', 'heading_2': {'rich_text': txt(s)}}

def h3(s):
    return {'object': 'block', 'type': 'heading_3', 'heading_3': {'rich_text': txt(s)}}

def bullet(s):
    return {'object': 'block', 'type': 'bulleted_list_item',
            'bulleted_list_item': {'rich_text': txt(s)}}

def para(s):
    return {'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': txt(s)}}

def para_bold(label, value):
    return {'object': 'block', 'type': 'paragraph',
            'paragraph': {'rich_text': bold_txt(label, value)}}

def todo_block(s, checked=False):
    return {'object': 'block', 'type': 'to_do',
            'to_do': {'rich_text': txt(s), 'checked': checked}}

def numbered(s):
    return {'object': 'block', 'type': 'numbered_list_item',
            'numbered_list_item': {'rich_text': txt(s)}}

DIVIDER = {'object': 'block', 'type': 'divider', 'divider': {}}

def table_row(cells):
    return {'type': 'table_row', 'table_row': {'cells': [txt(c) for c in cells]}}


# ══════════════════════════════════════════════════════════════════════════
# Page Builder
# ══════════════════════════════════════════════════════════════════════════

def build_page(wk_label, wk_start, wk_end, prev_label,
               this_data, prev_data, this_camps, prev_camps):
    """Build full Notion page children matching WK8-9 template."""

    def agg(d, camps):
        m = {}
        for ch in ('Meta', 'Google', 'Amazon'):
            m[f'{ch.lower()}_spend'] = sum(c['spend'] for c in camps if c['channel'] == ch)
            m[f'{ch.lower()}_conv']  = sum(c['sales'] for c in camps if c['channel'] == ch)
        m['ad_spend']  = m['meta_spend'] + m['google_spend'] + m['amazon_spend']
        m['conv_value'] = m['meta_conv'] + m['google_conv'] + m['amazon_conv']
        m['shopify_sales']  = d['shopify']['sales']
        m['shopify_orders'] = d['shopify']['orders']
        m['roas'] = m['conv_value'] / m['ad_spend'] if m['ad_spend'] > 0 else 0
        m['cac']  = m['ad_spend'] / m['shopify_orders'] if m['shopify_orders'] > 0 else 0
        m['aov']  = m['shopify_sales'] / m['shopify_orders'] if m['shopify_orders'] > 0 else 0
        return m

    cur = agg(this_data, this_camps)
    prev_m = agg(prev_data, prev_camps)

    # CVR-only
    cvr_cur  = [c for c in this_camps if c['type'] == 'cvr']
    cvr_prev = [c for c in prev_camps if c['type'] == 'cvr']
    cvr_spend_c = sum(c['spend'] for c in cvr_cur)
    cvr_conv_c  = sum(c['sales'] for c in cvr_cur)
    cvr_spend_p = sum(c['spend'] for c in cvr_prev)
    cvr_conv_p  = sum(c['sales'] for c in cvr_prev)
    cvr_roas_c  = cvr_conv_c / cvr_spend_c if cvr_spend_c > 0 else 0
    cvr_roas_p  = cvr_conv_p / cvr_spend_p if cvr_spend_p > 0 else 0
    cvr_cac_c   = cvr_spend_c / cur['shopify_orders'] if cur['shopify_orders'] > 0 else 0
    cvr_cac_p   = cvr_spend_p / prev_m['shopify_orders'] if prev_m['shopify_orders'] > 0 else 0

    roas_target = 3.0
    cac_target  = 25.0
    roas_pct = int(cvr_roas_c / roas_target * 100) if roas_target else 0
    cac_pct  = int(min(cac_target / cvr_cac_c, 1.0) * 100) if cvr_cac_c > 0 else 0
    roas_st = 'Green' if cvr_roas_c >= roas_target else ('Yellow' if cvr_roas_c >= roas_target * 0.8 else 'Red')
    cac_st  = 'Green' if cvr_cac_c <= cac_target else ('Yellow' if cvr_cac_c <= cac_target * 1.2 else 'Red')

    # Traffic CPC
    traf_c = [c for c in this_camps if c['type'] == 'traffic']
    traf_p = [c for c in prev_camps if c['type'] == 'traffic']
    traf_cpc_c = sum(c['spend'] for c in traf_c) / max(sum(c['clicks'] for c in traf_c), 1)
    traf_cpc_p = sum(c['spend'] for c in traf_p) / max(sum(c['clicks'] for c in traf_p), 1)

    n_camps_c = len(this_camps)
    n_camps_p = len(prev_camps)

    # Conversion campaigns: Top/Bottom 5 (spend >= $10)
    cvr_ranked = [c for c in cvr_cur if c['spend'] >= 10]
    cvr_top5 = sorted(cvr_ranked, key=lambda x: x['roas'], reverse=True)[:5]
    cvr_bot5 = sorted(cvr_ranked, key=lambda x: x['roas'])[:5]

    # Traffic campaigns: Top/Bottom 5 (spend >= $10, rank by CPC)
    traf_ranked = [c for c in traf_c if c['spend'] >= 10]
    traf_top5 = sorted(traf_ranked, key=lambda x: x['spend'] / max(x['clicks'], 1))[:5]  # lowest CPC = best
    traf_bot5 = sorted(traf_ranked, key=lambda x: x['spend'] / max(x['clicks'], 1), reverse=True)[:5]  # highest CPC

    # Newly added campaigns this week (not in prev_camps by name)
    prev_names = {c['campaign'].lower() for c in prev_camps}
    new_camps = [c for c in this_camps if c['campaign'].lower() not in prev_names and c['spend'] >= 5]

    # Channel breakdown
    def ch_spend(camps, ch):
        return sum(c['spend'] for c in camps if c['channel'] == ch)
    meta_roas = cur['meta_conv'] / cur['meta_spend'] if cur['meta_spend'] > 0 else 0
    goog_roas = cur['google_conv'] / cur['google_spend'] if cur['google_spend'] > 0 else 0
    amz_roas  = cur['amazon_conv'] / cur['amazon_spend'] if cur['amazon_spend'] > 0 else 0

    def fmoney(v, fallback='[TBD]'):
        return f'${v:,.0f}' if v > 0 else fallback
    def froas(v, fallback='[TBD]'):
        return f'{v:.2f}' if v > 0 else fallback

    # Helper: compute CPC/CTR for a campaign
    def camp_cpc(c):
        return c['spend'] / c['clicks'] if c['clicks'] > 0 else 0
    def camp_ctr(c):
        return (c['clicks'] / c['impressions'] * 100) if c['impressions'] > 0 else 0

    children = [
        para_bold('Team: ', 'Performance Team (Paid Marketing)'),
        para_bold('Week of: ', f'[{wk_start} ~ {wk_end}] (Fri-Thu PST)'),
        para_bold('Team Member: ', 'Jisun Hyun'),
        DIVIDER, para(''),

        # Section 1
        h2('1. What did I focus on last week?'),
        h3('Primary Focus Areas'),
        bullet('[Focus area 1]'), bullet('[Focus area 2]'),
        bullet('[Focus area 3]'), bullet('[Focus area 4]'),
        h3('Campaigns & Initiatives'),
        bullet('[Initiative 1: Description]'), bullet('[Initiative 2: Description]'),
        bullet('[Initiative 3: Description]'), bullet('[Initiative 4: Description]'),
        h3('Time Allocation'),
        bullet('Email Campaigns: [X Hours/effort]'),
        bullet('Ad Creative Development: [X Hours/effort]'),
        bullet('Campaign Setup & Management: [X Hours/effort]'),
        bullet('Testing & Optimization: [X Hours/effort]'),
        bullet('Analysis & Reporting: [X Hours/effort]'),
        para(''), DIVIDER, para(''),

        # Section 2
        h2('2. What were the results? (OKRs)'),
        h3('Performance Team OKR Progress'),
        para('Scale efficient customer acquisition through optimized performance marketing'),

        # OKR Table
        {'object': 'block', 'type': 'table', 'table': {
            'table_width': 6, 'has_column_header': True, 'has_row_header': False,
            'children': [
                table_row(['Key Result', 'Target', 'Last Week', 'This Week', 'Progress', 'Status']),
                table_row(['ROAS (Conversion Campaigns)', '3.0',
                           f'{cvr_roas_p:.2f}', f'{cvr_roas_c:.2f}', f'{roas_pct}%', roas_st]),
                table_row(['CAC (Conversion Campaigns)', '$25',
                           f'${cvr_cac_p:.2f}', f'${cvr_cac_c:.2f}', f'{cac_pct}%', cac_st]),
                table_row(['Email Open Rate', '50%', '[TBD]', '[TBD]', '[%]', 'Yellow']),
                table_row(['E-mail Campaign Automations', '50', '[#]', '[#]', '[%]', 'Yellow']),
                table_row(['Ad Creatives Developed & Tested', '30', '[#]', '[#]', '[%]', 'Yellow']),
                table_row(['Ad Campaigns Launched (Google & Meta)', '100',
                           str(n_camps_p), str(n_camps_c), '[%]', 'Yellow']),
            ]
        }},

        h3('Key Performance Metrics'),
        bullet(f'Total Ad Spend: ${cur["ad_spend"]:,.2f} (vs. ${prev_m["ad_spend"]:,.2f})'),
        bullet(f'Revenue Generated (Shopify): ${cur["shopify_sales"]:,.2f} (vs. ${prev_m["shopify_sales"]:,.2f})'),
        bullet(f'Conversion Campaign ROAS: {cvr_roas_c:.2f} (vs. {cvr_roas_p:.2f})'),
        bullet(f'Traffic Campaign Avg CPC: ${traf_cpc_c:.2f} (vs. ${traf_cpc_p:.2f})'),
        bullet(f'CAC (Conversion Campaigns): ${cvr_cac_c:.2f} (vs. ${cvr_cac_p:.2f})'),
        bullet('Conversion Rate: [TBD - needs GA4] (vs. [TBD])'),
        bullet('Email Click-through Rate: [TBD - needs Klaviyo] (vs. [TBD])'),
        bullet(f'Campaigns Launched (Google & Meta): {n_camps_c} this week / {n_camps_p} last week'),

        h3('Ad Spend Breakdown'),
        {'object': 'block', 'type': 'table', 'table': {
            'table_width': 5, 'has_column_header': True, 'has_row_header': False,
            'children': [
                table_row(['Channel', f'{prev_label} Spend', f'{wk_label} Spend',
                           f'{wk_label} Conv Value', f'{wk_label} ROAS']),
                table_row(['Meta Ads', fmoney(ch_spend(prev_camps, 'Meta')),
                           fmoney(cur['meta_spend']), fmoney(cur['meta_conv']),
                           froas(meta_roas)]),
                table_row(['Google Ads', fmoney(ch_spend(prev_camps, 'Google')),
                           fmoney(cur['google_spend']), fmoney(cur['google_conv']),
                           froas(goog_roas)]),
                table_row(['Amazon Ads (excl Grosmimi)',
                           fmoney(ch_spend(prev_camps, 'Amazon')),
                           fmoney(cur['amazon_spend']), fmoney(cur['amazon_conv']),
                           froas(amz_roas)]),
                table_row(['TOTAL', fmoney(prev_m['ad_spend']),
                           fmoney(cur['ad_spend']), fmoney(cur['conv_value']),
                           f'{cur["roas"]:.2f}']),
            ]
        }},
    ]

    # ── Campaign Tables with CPC, CTR, ROAS ──
    CAMP_HEADER = ['#', 'Channel', 'Brand / Product', 'Campaign', 'Spend', 'Sales', 'ROAS', 'CPC', 'CTR']

    def campaign_table(camps_list, title):
        children.append(h3(title))
        rows = [table_row(CAMP_HEADER)]
        for i, c in enumerate(camps_list):
            rows.append(table_row([
                str(i + 1), c['channel'],
                c['brand'], c['campaign'][:45],
                f'${c["spend"]:,.0f}', f'${c["sales"]:,.0f}',
                f'{c["roas"]:.2f}',
                f'${camp_cpc(c):.2f}',
                f'{camp_ctr(c):.1f}%',
            ]))
        if not camps_list:
            rows.append(table_row(['', '', '', '[No data yet]', '', '', '', '', '']))
        children.append({'object': 'block', 'type': 'table', 'table': {
            'table_width': len(CAMP_HEADER), 'has_column_header': True,
            'has_row_header': False, 'children': rows,
        }})

    # Conversion campaign tables
    campaign_table(cvr_top5, 'Top 5 Conversion Campaigns (by ROAS)')
    campaign_table(cvr_bot5, 'Bottom 5 Conversion Campaigns (by ROAS)')

    # Traffic campaign tables
    campaign_table(traf_top5, 'Top 5 Traffic Campaigns (by CPC, lowest = best)')
    campaign_table(traf_bot5, 'Bottom 5 Traffic Campaigns (by CPC, highest = worst)')

    # ── Newly Added Campaigns This Week ──
    children.append(h3('Newly Added Campaigns This Week'))
    if new_camps:
        NEW_HEADER = ['#', 'Type', 'Channel', 'Brand', 'Campaign', 'Spend', 'CPC', 'CTR', 'ROAS']
        new_rows = [table_row(NEW_HEADER)]
        for i, c in enumerate(sorted(new_camps, key=lambda x: x['spend'], reverse=True)):
            ctype = 'CVR' if c['type'] == 'cvr' else ('Traffic' if c['type'] == 'traffic' else 'Other')
            new_rows.append(table_row([
                str(i + 1), ctype, c['channel'],
                c['brand'], c['campaign'][:40],
                f'${c["spend"]:,.0f}',
                f'${camp_cpc(c):.2f}',
                f'{camp_ctr(c):.1f}%',
                f'{c["roas"]:.2f}',
            ]))
        children.append({'object': 'block', 'type': 'table', 'table': {
            'table_width': len(NEW_HEADER), 'has_column_header': True,
            'has_row_header': False, 'children': new_rows,
        }})
    else:
        children.append(bullet('No newly added campaigns this week'))

    children.extend([
        h3('Wins & Achievements'),
        bullet('[Specific win or achievement]'),
        bullet('[Specific win or achievement]'),
        para(''),

        h3('Traffic Mix by Channel'),
        {'object': 'block', 'type': 'table', 'table': {
            'table_width': 3, 'has_column_header': True, 'has_row_header': False,
            'children': [
                table_row(['Channel', prev_label, wk_label]),
                table_row(['Email', '[TBD]', '[TBD]']),
                table_row(['Organic', '[TBD]', '[TBD]']),
                table_row(['Paid', '[TBD]', '[TBD]']),
                table_row(['Direct', '[TBD]', '[TBD]']),
                table_row(['Other', '[TBD]', '[TBD]']),
                table_row(['Total Sessions', '[TBD]', '[TBD]']),
            ]
        }},
        para(''), DIVIDER, para(''),

        # Section 3
        h2('3. What were issues I faced?'),
        h3('Challenges & Obstacles'),
        para('Challenge 1: [Description]'),
        bullet('Impact: [Description]'), bullet('Status: [Resolution status]'),
        para('Challenge 2: [Description]'),
        bullet('Impact: [Description]'), bullet('Status: [Resolution status]'),
        h3('Blockers'),
        todo_block('[Blocker 1]'), todo_block('[Blocker 2]'),
        h3('Resource Needs'),
        bullet('[Resource or support needed]'),
        para(''), DIVIDER, para(''),

        # Section 4
        h2('4. What problems did I solve / what did I learn?'),
        h3('Problems Solved'),
        para('Problem: [Description]'),
        bullet('Solution: [Description]'), bullet('Impact: [Description]'),
        para('Problem: [Description]'),
        bullet('Solution: [Description]'), bullet('Impact: [Description]'),
        h3('Key Learnings & Insights'),
        bullet('Learning 1: [Description]'),
        h3('Best Practices Identified'),
        bullet('[Best practice to share with team]'),
        bullet('[Best practice to share with team]'),
        para(''), DIVIDER, para(''),

        # Section 5
        h2('5. What will I do next week?'),
        h3('Top Priorities'),
        numbered('[Priority 1]'), numbered('[Priority 2]'), numbered('[Priority 3]'),
        h3('Planned Activities'),
        para('Email Campaigns:'),
        todo_block('[Task 1]'), todo_block('[Task 2]'),
        para('Ad Creative Development:'),
        todo_block('[Task 1]'), todo_block('[Task 2]'),
        para('Campaign Management:'),
        todo_block('[Task 1]'), todo_block('[Task 2]'),
        para('Testing & Optimization:'),
        todo_block('[Task 1]'), todo_block('[Task 2]'),
        h3('OKR Focus'),
        bullet("Primary KR to move: [Which key result you'll focus on]"),
        bullet('Target progress: [What you aim to achieve]'),
        h3('Support Needed'),
        bullet('[What you need from other teams or leadership]'),
        para(''), DIVIDER, para(''),
        para(f'Report submitted: [{date.today().isoformat()}]'),
    ])

    return children, cur


# ══════════════════════════════════════════════════════════════════════════
# Notion API
# ══════════════════════════════════════════════════════════════════════════

def create_notion_page(title, children, archive_page_id=None):
    """Create Notion page in the weekly report database."""
    headers = {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }

    if archive_page_id:
        print(f"Archiving old page ({archive_page_id})...")
        r = requests.patch(f'https://api.notion.com/v1/pages/{archive_page_id}',
                           headers=headers, json={'archived': True}, timeout=30)
        if r.status_code == 200:
            print("  Archived")
        else:
            print(f"  Archive failed: {r.status_code}")

    page_data = {
        'parent': {'database_id': NOTION_DB},
        'properties': {'title': {'title': txt(title)}},
        'children': children[:100],
    }
    resp = requests.post('https://api.notion.com/v1/pages',
                         headers=headers, json=page_data, timeout=60)
    if resp.status_code != 200:
        print(f"FAILED: {resp.status_code}")
        print(resp.text[:500])
        return None

    page = resp.json()
    page_id = page['id']

    if len(children) > 100:
        remaining = children[100:]
        for i in range(0, len(remaining), 100):
            r = requests.patch(
                f'https://api.notion.com/v1/blocks/{page_id}/children',
                headers=headers, json={'children': remaining[i:i+100]}, timeout=60)
            if r.status_code != 200:
                print(f"  Append chunk failed: {r.status_code}")

    return page


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Weekly Performance Report Notion Page Creator')
    parser.add_argument('--week', help='Week label (e.g. WK11). Calculates Fri-Thu dates automatically.')
    parser.add_argument('--start', help='Explicit start date YYYY-MM-DD')
    parser.add_argument('--end', help='Explicit end date YYYY-MM-DD')
    parser.add_argument('--label', help='Week label override (e.g. WK11) when using --start/--end')
    parser.add_argument('--archive-page', help='Notion page ID to archive before creating new page')
    parser.add_argument('--dry-run', action='store_true', help='Collect data only, skip Notion page creation')
    parser.add_argument('--skip-amazon', action='store_true', help='Skip Amazon Ads data collection')
    args = parser.parse_args()

    if args.week:
        wk_label = args.week.upper()
        wk_start, wk_end = week_dates(wk_label)
        prev_label = prev_week_label(wk_label)
        prev_start, prev_end = week_dates(prev_label)
    elif args.start and args.end:
        wk_start, wk_end = args.start, args.end
        wk_label = args.label or 'WKxx'
        # Previous week = same duration, shifted back
        dur = (datetime.strptime(wk_end, '%Y-%m-%d') - datetime.strptime(wk_start, '%Y-%m-%d')).days
        prev_end_dt = datetime.strptime(wk_start, '%Y-%m-%d') - timedelta(days=1)
        prev_start_dt = prev_end_dt - timedelta(days=dur)
        prev_start, prev_end = prev_start_dt.strftime('%Y-%m-%d'), prev_end_dt.strftime('%Y-%m-%d')
        prev_label = f'Prev {wk_label}'
    else:
        parser.error('Provide --week or --start/--end')
        return

    print(f"=== Weekly Performance Report: {wk_label} ===")
    print(f"This week: {wk_start} ~ {wk_end}")
    print(f"Prev week: {prev_start} ~ {prev_end} ({prev_label})")

    # Collect data
    print("\n[1/7] Meta campaigns (this week)...")
    meta_c = fetch_meta_campaigns(wk_start, wk_end)
    print(f"  {len(meta_c)} campaigns")

    print("[2/7] Meta campaigns (prev week)...")
    meta_p = fetch_meta_campaigns(prev_start, prev_end)
    print(f"  {len(meta_p)} campaigns")

    print("[3/7] Google campaigns (this week)...")
    google_c = fetch_google_campaigns(wk_start, wk_end)
    print(f"  {len(google_c)} campaigns")

    print("[4/7] Google campaigns (prev week)...")
    google_p = fetch_google_campaigns(prev_start, prev_end)
    print(f"  {len(google_p)} campaigns")

    amz_c, amz_p = [], []
    if not args.skip_amazon:
        print("[5/7] Amazon campaigns (this week, excl Grosmimi)...")
        amz_c = fetch_amazon_campaigns(wk_start, wk_end)
        print(f"  {len(amz_c)} campaigns")
    else:
        print("[5/7] Amazon campaigns - SKIPPED")

    print("[6/7] Shopify (this week)...")
    shop_c = fetch_shopify(wk_start, wk_end)
    print(f"  ${shop_c['sales']:,.2f} sales, {shop_c['orders']} orders")

    print("[7/7] Shopify (prev week)...")
    shop_p = fetch_shopify(prev_start, prev_end)
    print(f"  ${shop_p['sales']:,.2f} sales, {shop_p['orders']} orders")

    this_camps = meta_c + google_c + amz_c
    prev_camps = meta_p + google_p + amz_p

    # Save raw data
    TMP.mkdir(parents=True, exist_ok=True)
    raw_path = TMP / f'{wk_label.lower()}_raw_data.json'
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump({
            'this_campaigns': this_camps, 'prev_campaigns': prev_camps,
            'this_shopify': shop_c, 'prev_shopify': shop_p,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nRaw data: {raw_path}")

    if args.dry_run:
        print("\n[Dry Run] Skipping Notion page creation.")
        return

    # Build and create page
    children, metrics = build_page(
        wk_label, wk_start, wk_end, prev_label,
        {'shopify': shop_c}, {'shopify': shop_p},
        this_camps, prev_camps
    )

    title = f'[{wk_label}] - Performance Team Weekly Report'
    page = create_notion_page(title, children, archive_page_id=args.archive_page)
    if page:
        print(f"\nSUCCESS: {page.get('url', '')}")
        print(f"Page ID: {page['id']}")
    else:
        print("\nFailed to create page")
        sys.exit(1)


if __name__ == '__main__':
    main()
