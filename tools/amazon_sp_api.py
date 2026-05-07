"""
Amazon SP-API - Multi-region Order/Sales/SKU Health data fetcher

Supports:
  - Japan (FE): Amazon.co.jp  — weekly sales
  - US (NA): Amazon.com       — weekly sales + SKU health management

Auth: LWA OAuth2 (Login with Amazon)
Endpoints:
  FE: https://sellingpartnerapi-fe.amazon.com
  NA: https://sellingpartnerapi-na.amazon.com

Usage:
    python tools/amazon_sp_api.py                # test JP connection + last 7 days
    python tools/amazon_sp_api.py --us           # test US connection
    python tools/amazon_sp_api.py --sku-health   # sync US SKU health data
"""

import os, sys, io, time, json, csv, gzip
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import requests

def _setup_encoding():
    if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# ── Shared LWA Credentials ───────────────────────────────────────────────────

LWA_CLIENT_ID = os.getenv("AMAZON_LWA_CLIENT_ID")
LWA_CLIENT_SECRET = os.getenv("AMAZON_LWA_CLIENT_SECRET")
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# ── Region Configuration ─────────────────────────────────────────────────────

REGION_CONFIGS = {
    'FE': {
        'endpoint': 'https://sellingpartnerapi-fe.amazon.com',
        'marketplace_id': os.getenv('AMAZON_MARKETPLACE_ID', 'A1VC38T7YXB528'),
        'refresh_token': os.getenv('AMAZON_REFRESH_TOKEN'),
        'seller_id': os.getenv('AMAZON_SELLER_ID'),
        'label': 'Amazon.co.jp',
        'currency': '\u00a5',
    },
    'NA': {
        'endpoint': 'https://sellingpartnerapi-na.amazon.com',
        'marketplace_id': os.getenv('AMAZON_US_MARKETPLACE_ID', 'ATVPDKIKX0DER'),
        'refresh_token': os.getenv('AMAZON_US_REFRESH_TOKEN', os.getenv('AMAZON_REFRESH_TOKEN')),
        'seller_id': os.getenv('AMAZON_US_SELLER_ID', os.getenv('AMAZON_SELLER_ID')),
        'label': 'Amazon.com',
        'currency': '$',
    },
}

# Backward-compatible globals (used by existing weekly_sales)
MARKETPLACE_ID = REGION_CONFIGS['FE']['marketplace_id']
REFRESH_TOKEN = REGION_CONFIGS['FE']['refresh_token']
SP_API_BASE = REGION_CONFIGS['FE']['endpoint']

TMP_DIR = Path('.tmp/compliance')

# ── Auth ──────────────────────────────────────────────────────────────────────

_token_cache = {}  # {region: {'token': str, 'expiry': datetime}}


def _refresh_access_token(region='FE'):
    """Exchange refresh token for access token via LWA. Caches per region."""
    global _token_cache

    cached = _token_cache.get(region)
    if cached and cached.get('expiry') and datetime.now() < cached['expiry']:
        return cached['token']

    cfg = REGION_CONFIGS[region]
    if not cfg['refresh_token']:
        raise ValueError(f"No refresh token configured for region {region}. "
                         f"Set AMAZON_US_REFRESH_TOKEN in .env for US.")

    resp = requests.post(LWA_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": LWA_CLIENT_ID,
        "client_secret": LWA_CLIENT_SECRET,
        "refresh_token": cfg['refresh_token'],
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    _token_cache[region] = {
        'token': data["access_token"],
        'expiry': datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60),
    }
    return _token_cache[region]['token']


def _headers(token):
    return {"x-amz-access-token": token}


# ── API Helpers ───────────────────────────────────────────────────────────────

def _api_get(path, params, region='FE', timeout=30, _retries=0):
    """Authenticated GET to SP-API with automatic rate-limit retry."""
    cfg = REGION_CONFIGS[region]
    token = _refresh_access_token(region)

    resp = requests.get(
        f"{cfg['endpoint']}{path}",
        params=params,
        headers=_headers(token),
        timeout=timeout,
    )

    if resp.status_code == 429 and _retries < 3:
        wait = int(resp.headers.get('Retry-After', 5))
        print(f"  Rate limited, waiting {wait}s...")
        time.sleep(wait)
        return _api_get(path, params, region, timeout, _retries + 1)

    resp.raise_for_status()
    return resp.json()


def _api_post(path, body, region='FE', timeout=30, _retries=0):
    """Authenticated POST to SP-API with automatic rate-limit retry."""
    cfg = REGION_CONFIGS[region]
    token = _refresh_access_token(region)

    resp = requests.post(
        f"{cfg['endpoint']}{path}",
        json=body,
        headers={**_headers(token), "Content-Type": "application/json"},
        timeout=timeout,
    )

    if resp.status_code == 429 and _retries < 3:
        time.sleep(5)
        return _api_post(path, body, region, timeout, _retries + 1)

    resp.raise_for_status()
    return resp.json()


# ── Existing: Weekly Sales (backward compatible) ─────────────────────────────

def weekly_sales(date_from_str, date_to_str, region='FE'):
    """Get total sales for a date range.

    Args:
        date_from_str: "YYYY-MM-DD"
        date_to_str:   "YYYY-MM-DD"
        region: 'FE' (Japan) or 'NA' (US)

    Returns: dict with total_sales, order_count
    """
    cfg = REGION_CONFIGS[region]
    print(f"\nSearching {cfg['label']} orders: {date_from_str} ~ {date_to_str}")

    all_orders = []
    next_token = None

    while True:
        if next_token:
            params = {"NextToken": next_token, "MarketplaceIds": cfg['marketplace_id']}
        else:
            params = {
                "MarketplaceIds": cfg['marketplace_id'],
                "CreatedAfter": f"{date_from_str}T00:00:00Z",
            }
            from datetime import date as date_cls
            to_date = date_cls.fromisoformat(date_to_str)
            if to_date < datetime.now().date():
                params["CreatedBefore"] = f"{date_to_str}T23:59:59Z"

        data = _api_get('/orders/v0/orders', params, region=region, timeout=30)

        orders = data.get("payload", {}).get("Orders", [])
        all_orders.extend(orders)

        next_token = data.get("payload", {}).get("NextToken")
        if not next_token:
            break
        time.sleep(1)

    total = 0
    for o in all_orders:
        amt = o.get("OrderTotal", {})
        if amt and amt.get("Amount"):
            total += float(amt["Amount"])

    total = int(total)
    print(f"  Found {len(all_orders)} orders, total sales: {cfg['currency']}{total:,}")

    return {"total_sales": total, "order_count": len(all_orders)}


# ── Reports API ───────────────────────────────────────────────────────────────

def _create_report(report_type, region='NA'):
    """Request a report. Returns reportId."""
    cfg = REGION_CONFIGS[region]
    data = _api_post('/reports/2021-06-30/reports', {
        'reportType': report_type,
        'marketplaceIds': [cfg['marketplace_id']],
    }, region=region)
    report_id = data.get('reportId')
    print(f"  Report requested: {report_id} ({report_type})")
    return report_id


def _wait_for_report(report_id, region='NA', max_wait=300):
    """Poll until report is DONE. Returns reportDocumentId."""
    start = time.time()
    while time.time() - start < max_wait:
        data = _api_get(f'/reports/2021-06-30/reports/{report_id}', {}, region=region)
        status = data.get('processingStatus')
        print(f"  Report status: {status}")

        if status == 'DONE':
            return data.get('reportDocumentId')
        elif status in ('CANCELLED', 'FATAL'):
            raise RuntimeError(f"Report failed with status: {status}")

        time.sleep(10)

    raise TimeoutError(f"Report not ready after {max_wait}s")


def _download_report_document(doc_id, region='NA'):
    """Download and parse a report document. Returns list of dicts (TSV rows)."""
    data = _api_get(f'/reports/2021-06-30/documents/{doc_id}', {}, region=region)
    url = data.get('url')
    compression = data.get('compressionAlgorithm')

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    content = resp.content
    if compression == 'GZIP':
        content = gzip.decompress(content)

    text = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    return list(reader)


# ── SKU Health Functions ──────────────────────────────────────────────────────

def get_all_listings(region='NA', use_cache=True):
    """Get all seller listings via Reports API.

    Uses GET_MERCHANT_LISTINGS_ALL_DATA report.
    Caches for 4 hours.

    Returns: dict with fetched_at, region, total_skus, listings
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = TMP_DIR / f'listings_{region}.json'

    if use_cache and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding='utf-8'))
            cache_time = datetime.fromisoformat(cached.get('fetched_at', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(hours=4):
                print(f"  Using cached listings ({cached.get('total_skus', 0)} SKUs, "
                      f"cached {cache_time.strftime('%H:%M')})")
                return cached
        except (json.JSONDecodeError, ValueError):
            pass

    print("  Creating listings report (this may take 1-3 minutes)...")
    report_id = _create_report('GET_MERCHANT_LISTINGS_ALL_DATA', region)
    doc_id = _wait_for_report(report_id, region)
    listings = _download_report_document(doc_id, region)

    result = {
        'fetched_at': datetime.now().isoformat(),
        'region': region,
        'total_skus': len(listings),
        'listings': listings,
    }

    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  Downloaded {len(listings)} listings")
    return result


def get_fba_inventory(region='NA'):
    """Get FBA inventory summaries. Returns list of inventory items."""
    cfg = REGION_CONFIGS[region]
    all_items = []
    next_token = None

    while True:
        params = {
            'granularityType': 'Marketplace',
            'granularityId': cfg['marketplace_id'],
            'marketplaceIds': cfg['marketplace_id'],
        }
        if next_token:
            params['nextToken'] = next_token

        data = _api_get('/fba/inventory/v1/summaries', params, region=region)

        items = data.get('payload', {}).get('inventorySummaries', [])
        all_items.extend(items)

        pagination = data.get('pagination', {})
        next_token = pagination.get('nextToken')
        if not next_token:
            break
        time.sleep(1)

    print(f"  FBA inventory: {len(all_items)} items")
    return all_items


def get_listing_issues(sku, region='NA'):
    """Get issues/status for a specific SKU via Listings Items API.

    Returns dict with status, issues, summaries.
    """
    cfg = REGION_CONFIGS[region]
    seller_id = cfg['seller_id']
    if not seller_id:
        raise ValueError(f"No seller_id configured for region {region}. "
                         f"Set AMAZON_US_SELLER_ID in .env.")

    data = _api_get(
        f'/listings/2021-08-01/items/{seller_id}/{sku}',
        {
            'marketplaceIds': cfg['marketplace_id'],
            'includedData': 'issues,summaries',
        },
        region=region,
    )
    return data


def get_sku_health(region='NA', use_cache=True, progress_callback=None):
    """Comprehensive SKU health assessment.

    Combines:
    1. All listings (Reports API)
    2. FBA inventory levels
    3. Per-SKU health scoring

    Args:
        region: 'NA' (US) or 'FE' (JP)
        use_cache: Use 4-hour cache if available
        progress_callback: Optional fn(message) for UI updates

    Returns: dict with counts, skus, action_items
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = TMP_DIR / f'sku_health_{region}.json'

    if use_cache and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding='utf-8'))
            cache_time = datetime.fromisoformat(cached.get('fetched_at', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(hours=4):
                return cached
        except (json.JSONDecodeError, ValueError):
            pass

    def _update(msg):
        print(f"  {msg}")
        if progress_callback:
            progress_callback(msg)

    # Step 1: Get all listings
    _update("[1/3] Fetching all listings via Reports API...")
    listings_data = get_all_listings(region, use_cache=False)
    listings = listings_data.get('listings', [])

    # Step 2: Get FBA inventory
    _update("[2/3] Fetching FBA inventory...")
    fba_map = {}
    try:
        fba_items = get_fba_inventory(region)
        fba_map = {item.get('sellerSku', ''): item for item in fba_items}
    except Exception as e:
        _update(f"FBA inventory skipped: {e}")

    # Step 3: Assess health per SKU
    _update("[3/3] Assessing SKU health...")

    skus = []
    action_items = []
    counts = {
        'total': 0, 'active': 0, 'inactive': 0,
        'suppressed': 0, 'out_of_stock': 0, 'low_stock': 0,
    }

    for listing in listings:
        sku = listing.get('seller-sku', listing.get('sku', ''))
        asin = listing.get('asin1', listing.get('asin', ''))
        title = listing.get('item-name', listing.get('title', ''))
        status = listing.get('status', 'Active')
        price = listing.get('price', '')
        quantity = listing.get('quantity', '0')
        fulfillment = listing.get('fulfillment-channel', '')
        open_date = listing.get('open-date', '')

        counts['total'] += 1

        try:
            qty = int(quantity) if quantity else 0
        except (ValueError, TypeError):
            qty = 0

        # FBA inventory enrichment
        fba = fba_map.get(sku, {})
        inv_details = fba.get('inventoryDetails', {}) if fba else {}
        fba_fulfillable = inv_details.get('fulfillableQuantity', 0)
        fba_inbound = inv_details.get('inboundWorkingQuantity', 0)

        reserved = inv_details.get('reservedQuantity', {})
        fba_reserved = reserved.get('totalReservedQuantity', 0) if isinstance(reserved, dict) else 0

        # Determine health status
        health = 'GREEN'
        issues = []

        status_lower = (status or '').lower()
        if 'inactive' in status_lower or 'closed' in status_lower:
            health = 'RED'
            counts['inactive'] += 1
            issues.append('Listing inactive')
            action_items.append({
                'sku': sku, 'asin': asin, 'severity': 'HIGH',
                'action': 'Reactivate listing',
                'detail': f'{title[:60]} — Status: {status}',
            })
        elif 'suppressed' in status_lower or 'blocked' in status_lower:
            health = 'RED'
            counts['suppressed'] += 1
            issues.append('Listing suppressed')
            action_items.append({
                'sku': sku, 'asin': asin, 'severity': 'CRITICAL',
                'action': 'Fix suppressed listing',
                'detail': f'{title[:60]} — May need compliance docs',
            })
        else:
            counts['active'] += 1

        # Stock assessment
        effective_qty = fba_fulfillable if fulfillment == 'AMAZON_NA' else qty
        if effective_qty == 0:
            if health != 'RED':
                health = 'RED'
            counts['out_of_stock'] += 1
            issues.append('Out of stock')
            action_items.append({
                'sku': sku, 'asin': asin, 'severity': 'HIGH',
                'action': 'Replenish inventory',
                'detail': f'{title[:60]} — 0 units available',
            })
        elif effective_qty <= 10:
            if health == 'GREEN':
                health = 'YELLOW'
            counts['low_stock'] += 1
            issues.append(f'Low stock ({effective_qty} units)')
            action_items.append({
                'sku': sku, 'asin': asin, 'severity': 'MEDIUM',
                'action': 'Reorder soon',
                'detail': f'{title[:60]} — {effective_qty} units left',
            })

        skus.append({
            'sku': sku,
            'asin': asin,
            'title': (title or '')[:80],
            'status': status,
            'health': health,
            'price': price,
            'quantity': qty,
            'fba_fulfillable': fba_fulfillable,
            'fba_inbound': fba_inbound,
            'fba_reserved': fba_reserved,
            'fulfillment': 'FBA' if fulfillment == 'AMAZON_NA' else 'FBM',
            'issues': issues,
            'open_date': open_date,
        })

    # Sort: RED first, then YELLOW, then GREEN
    health_order = {'RED': 0, 'YELLOW': 1, 'GREEN': 2}
    skus.sort(key=lambda x: health_order.get(x['health'], 3))

    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    action_items.sort(key=lambda x: severity_order.get(x['severity'], 4))

    result = {
        'fetched_at': datetime.now().isoformat(),
        'region': region,
        'marketplace': REGION_CONFIGS[region]['label'],
        'total_skus': len(skus),
        'counts': counts,
        'skus': skus,
        'action_items': action_items,
    }

    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    _update(f"Done: {counts['active']} active, {counts['inactive']} inactive, "
            f"{counts['suppressed']} suppressed, {counts['out_of_stock']} OOS, "
            f"{counts['low_stock']} low stock")

    return result


# ── Connection Tests ──────────────────────────────────────────────────────────

def test_connection(region='FE'):
    """Test SP-API connection for a given region.

    Returns: dict with status, marketplaces, recent_sales
    """
    cfg = REGION_CONFIGS[region]
    print("=" * 50)
    print(f"Amazon SP-API Connection Test — {cfg['label']}")
    print("=" * 50)

    if not LWA_CLIENT_ID:
        print("  ERROR: AMAZON_LWA_CLIENT_ID not set in .env")
        return {'status': 'error', 'message': 'Missing LWA credentials'}

    if not cfg['refresh_token']:
        print(f"  ERROR: No refresh token for {region}")
        return {'status': 'error', 'message': f'Missing refresh token for {region}'}

    print(f"  Client ID: {LWA_CLIENT_ID[:20]}...")

    try:
        token = _refresh_access_token(region)
        print("  LWA token refreshed OK")
    except Exception as e:
        print(f"  Token refresh FAILED: {e}")
        return {'status': 'error', 'message': f'Token refresh failed: {e}'}

    # Check marketplace participations
    marketplaces = []
    try:
        resp_data = _api_get('/sellers/v1/marketplaceParticipations', {}, region=region)
        for mp in resp_data.get("payload", []):
            m = mp.get("marketplace", {})
            part = mp.get("participation", {})
            active = part.get("isParticipating", False)
            info = {
                'name': m.get('name', '?'),
                'country': m.get('countryCode', '?'),
                'id': m.get('id', '?'),
                'active': active,
            }
            marketplaces.append(info)
            print(f"  Marketplace: {info['name']} ({info['country']}) "
                  f"{'[ACTIVE]' if active else '[INACTIVE]'}")
    except Exception as e:
        print(f"  Marketplace check failed: {e}")

    # Recent sales
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    try:
        sales = weekly_sales(week_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), region=region)
        print(f"\n--- Last 7 days ---")
        print(f"  Orders: {sales['order_count']}")
        print(f"  Sales: {cfg['currency']}{sales['total_sales']:,}")
    except Exception as e:
        print(f"  Sales check failed: {e}")
        sales = {'total_sales': 0, 'order_count': 0}

    return {
        'status': 'ok',
        'region': region,
        'marketplace': cfg['label'],
        'marketplaces': marketplaces,
        'recent_sales': sales,
    }


def check_us_credentials():
    """Quick check if US SP-API credentials are configured.

    Returns dict with is_configured, missing_vars, details.
    """
    cfg = REGION_CONFIGS['NA']
    missing = []

    if not LWA_CLIENT_ID:
        missing.append('AMAZON_LWA_CLIENT_ID')
    if not LWA_CLIENT_SECRET:
        missing.append('AMAZON_LWA_CLIENT_SECRET')
    if not cfg['refresh_token']:
        missing.append('AMAZON_US_REFRESH_TOKEN (or AMAZON_REFRESH_TOKEN)')
    if not cfg['seller_id']:
        missing.append('AMAZON_US_SELLER_ID (or AMAZON_SELLER_ID)')

    return {
        'is_configured': len(missing) == 0,
        'missing_vars': missing,
        'marketplace_id': cfg['marketplace_id'],
        'seller_id': cfg['seller_id'],
        'endpoint': cfg['endpoint'],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _setup_encoding()

    if '--us' in sys.argv:
        test_connection('NA')
    elif '--sku-health' in sys.argv:
        region = 'NA'
        if '--jp' in sys.argv:
            region = 'FE'
        print(f"\nSyncing SKU health for {REGION_CONFIGS[region]['label']}...")
        result = get_sku_health(region, use_cache=False)
        print(f"\nTotal SKUs: {result['total_skus']}")
        print(f"Action items: {len(result['action_items'])}")
    else:
        test_connection('FE')
