#!/usr/bin/env python3
"""
Preview Outreach Batch — Config-driven eligible creator counter.

Reads Config from EC2 API (PipelineConfig), counts eligible creators
from Airtable by Initial Discovery Date, estimates brand split from
Content keywords, and writes eligible counts back to EC2 API.

Usage:
    python tools/preview_outreach_batch.py              # Count + update Config
    python tools/preview_outreach_batch.py --dry-run    # Count only, no Config update
    python tools/preview_outreach_batch.py --full-scan  # Check ALL content for brand (slow)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import os
import ssl
import urllib.request
import urllib.parse
import argparse
from collections import Counter, defaultdict
from datetime import datetime

# ── Secrets ──────────────────────────────────────────────────────────────
def load_secrets():
    p = os.path.expanduser('~/.wat_secrets')
    if os.path.exists(p):
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    k = k.replace('export ', '').strip()
                    v = v.strip().strip('"').strip("'")
                    os.environ[k] = v

load_secrets()
AT_KEY = os.environ.get('AIRTABLE_API_KEY', '')

# ── EC2 API ──────────────────────────────────────────────────────────────
EC2_API_BASE = 'https://orbitools.orbiters.co.kr/api/onzenna'
EC2_USER = os.environ.get('ORBITOOLS_USER', 'admin')
EC2_PASS = os.environ.get('ORBITOOLS_PASS', 'admin')

def ec2_request(path, method='GET', data=None):
    """Make EC2 API request with basic auth."""
    import base64
    url = EC2_API_BASE + path
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{EC2_USER}:{EC2_PASS}".encode()).decode(),
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())

# ── Airtable IDs ─────────────────────────────────────────────────────────
BASE_ID = 'app3Vnmh7hLAVsevE'
TBL_CREATORS = 'tblv2Jw3ZAtAMhiYY'
TBL_CONTENT = 'tble4cuyVnXP4OvZR'

# ── Brand keywords (same as n8n Draft Gen) ───────────────────────────────
BRAND_KEYWORDS = {
    'Grosmimi': ['grosmimi', 'ppsu', 'straw cup', 'baby bottle', 'bpa-free', 'bpa free',
                 'sippy cup', 'training cup', 'anti-colic', 'anti colic'],
    'CHA&MOM': ['cha&mom', 'chamom', 'ps cream', 'skincare', 'lotion', 'moisturizer',
                'baby cream', 'eczema', 'sensitive skin', 'diaper cream'],
    'Naeiae': ['naeiae', 'rice puff', 'baby snack', 'organic snack', 'puff snack',
               'teething wafer', 'baby food', 'rice cracker'],
}


def at_request(url, method='GET', data=None):
    """Make Airtable API request."""
    headers = {"Authorization": f"Bearer {AT_KEY}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def at_paginate(table, formula=None, fields=None, sort=None):
    """Paginate through all records in an Airtable table."""
    params = []
    if formula:
        params.append(f"filterByFormula={urllib.parse.quote(formula)}")
    if fields:
        for f in fields:
            params.append(f"fields%5B%5D={urllib.parse.quote(f)}")
    if sort:
        for i, (field, direction) in enumerate(sort):
            params.append(f"sort%5B{i}%5D%5Bfield%5D={urllib.parse.quote(field)}")
            params.append(f"sort%5B{i}%5D%5Bdirection%5D={direction}")
    params.append("pageSize=100")

    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}?{'&'.join(params)}"
    records = []
    offset = None
    while True:
        fetch_url = url + (f"&offset={offset}" if offset else "")
        data = at_request(fetch_url)
        records.extend(data.get('records', []))
        offset = data.get('offset')
        if not offset:
            break
    return records


def detect_brand(text):
    """Detect brand from content text using keyword matching."""
    if not text:
        return 'Unknown'
    text_lower = text.lower()
    scores = {}
    for brand, keywords in BRAND_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[brand] = score
    if not scores:
        return 'Unknown'
    return max(scores, key=scores.get)


def get_today_config():
    """Get today's Config from EC2 API."""
    try:
        return ec2_request('/pipeline/config/today/')
    except Exception as e:
        print(f"  WARNING: EC2 API error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Preview outreach batch eligibility')
    parser.add_argument('--dry-run', action='store_true', help='Count only, do not update Config')
    parser.add_argument('--full-scan', action='store_true', help='Check ALL content for brand split (slow)')
    parser.add_argument('--sample', type=int, default=100, help='Sample size for brand estimation (default: 100)')
    args = parser.parse_args()

    print("=" * 60)
    print("  OUTREACH BATCH PREVIEW")
    print("=" * 60)

    # ── 1. Read Config from EC2 ──────────────────────────────────────
    print("\n[1/4] Reading Config from EC2 API...")
    config = get_today_config()
    if not config:
        print("  WARNING: No Config available. Using defaults.")
        update_date = None
        batch_size = 10
        start_from_beginning = False
        config_date = datetime.now().strftime('%Y-%m-%d')
    else:
        update_date = config.get('update_date')
        batch_size = config.get('creators_contacted', 10)
        start_from_beginning = config.get('start_from_beginning', False)
        config_date = config.get('date', datetime.now().strftime('%Y-%m-%d'))
        print(f"  Update Date: {update_date or '(not set)'}")
        print(f"  Batch Size (Creators Contacted): {batch_size}")
        print(f"  Start From Beginning: {start_from_beginning}")

    effective_date = None if start_from_beginning else update_date

    # ── 2. Count eligible creators (Airtable) ────────────────────────
    print("\n[2/4] Counting eligible creators...")
    base_formula = "AND({Email}!=BLANK(),{Outreach Status}='Not Started',{Partnership Status}='New')"
    if effective_date:
        base_formula = f"AND({base_formula},{{Initial Discovery Date}}>='{effective_date}')"

    eligible = at_paginate(
        TBL_CREATORS,
        formula=base_formula,
        fields=['Username', 'Email', 'Platform', 'Initial Discovery Date', 'Content'],
        sort=[('Initial Discovery Date', 'asc')]
    )

    total_eligible = len(eligible)
    print(f"  Total eligible: {total_eligible}")

    # Group by Initial Discovery Date
    by_date = defaultdict(list)
    for r in eligible:
        d = r['fields'].get('Initial Discovery Date', '(none)')
        by_date[d].append(r)

    print(f"\n  By Initial Discovery Date:")
    for d in sorted(by_date.keys()):
        creators = by_date[d]
        print(f"    {d}: {len(creators)}")

    # Next batch preview
    next_batch = eligible[:batch_size] if eligible else []
    if next_batch:
        first_date = next_batch[0]['fields'].get('Initial Discovery Date', '?')
        last_date = next_batch[-1]['fields'].get('Initial Discovery Date', '?')
        print(f"\n  Next batch ({len(next_batch)} creators):")
        print(f"    Discovery dates: {first_date} ~ {last_date}")
        platforms = Counter(r['fields'].get('Platform', '?') for r in next_batch)
        print(f"    Platforms: {dict(platforms)}")

    # ── 3. Brand estimation ──────────────────────────────────────────
    print("\n[3/4] Estimating brand split...")
    sample_size = len(eligible) if args.full_scan else min(args.sample, len(eligible))

    if sample_size == 0:
        print("  No eligible creators to analyze.")
        brand_counts = Counter()
    else:
        # Collect Content record IDs from sample
        sample = eligible[:sample_size]
        content_ids = set()
        creator_content_map = {}  # content_id -> creator_id
        for r in sample:
            for cid in r['fields'].get('Content', []):
                content_ids.add(cid)
                creator_content_map[cid] = r['id']

        print(f"  Fetching {len(content_ids)} content records (from {sample_size} creators)...")

        # Fetch content records in batches using OR formula
        content_texts = {}  # creator_id -> combined text
        content_list = list(content_ids)
        batch_sz = 50
        for i in range(0, len(content_list), batch_sz):
            batch = content_list[i:i + batch_sz]
            or_parts = ','.join([f"RECORD_ID()='{cid}'" for cid in batch])
            formula = f"OR({or_parts})"
            records = at_paginate(TBL_CONTENT, formula=formula,
                                 fields=['Caption', 'Summary', 'Text'])
            for r in records:
                f = r['fields']
                text = ' '.join(filter(None, [
                    f.get('Caption', ''),
                    f.get('Summary', ''),
                    f.get('Text', ''),
                ]))
                cid = r['id']
                creator_id = creator_content_map.get(cid, cid)
                if creator_id not in content_texts:
                    content_texts[creator_id] = text
                else:
                    content_texts[creator_id] += ' ' + text

        # Detect brands
        brand_counts = Counter()
        creator_brands = {}
        for r in sample:
            text = content_texts.get(r['id'], '')
            brand = detect_brand(text)
            brand_counts[brand] += 1
            creator_brands[r['id']] = brand

        print(f"\n  Brand split ({'full scan' if args.full_scan else f'sample of {sample_size}'}):")
        for brand, count in brand_counts.most_common():
            pct = count / sample_size * 100
            print(f"    {brand}: {count} ({pct:.1f}%)")

        if not args.full_scan and sample_size < total_eligible:
            print(f"\n  Estimated totals (extrapolated to {total_eligible}):")
            for brand, count in brand_counts.most_common():
                est = int(count / sample_size * total_eligible)
                print(f"    {brand}: ~{est}")

    # ── 4. Update Config via EC2 API ─────────────────────────────────
    if args.dry_run:
        print("\n[4/4] DRY RUN -- skipping Config update.")
    elif config:
        print("\n[4/4] Updating Config via EC2 API...")
        update_data = {
            'eligible_total': total_eligible,
            'updated_by': 'preview_tool',
        }
        # Add brand counts
        for brand, field in [('Grosmimi', 'eligible_grosmimi'),
                             ('CHA&MOM', 'eligible_chaenmom'),
                             ('Naeiae', 'eligible_naeiae')]:
            if args.full_scan:
                update_data[field] = brand_counts.get(brand, 0)
            else:
                sample_count = brand_counts.get(brand, 0)
                est = int(sample_count / max(sample_size, 1) * total_eligible) if sample_size > 0 else 0
                update_data[field] = est

        update_data['eligible_unknown'] = (
            total_eligible
            - update_data.get('eligible_grosmimi', 0)
            - update_data.get('eligible_chaenmom', 0)
            - update_data.get('eligible_naeiae', 0)
        )

        try:
            ec2_request(f'/pipeline/config/{config_date}/', method='POST', data=update_data)
            print(f"  Updated EC2 Config with: {json.dumps(update_data, indent=2)}")
        except Exception as e:
            print(f"  Error updating Config: {e}")
    else:
        print("\n[4/4] No Config to update.")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Date filter: {'All (Start From Beginning)' if not effective_date else f'>= {effective_date}'}")
    print(f"  Total eligible: {total_eligible}")
    print(f"  Batch size: {batch_size}")
    if total_eligible > 0:
        batches_needed = (total_eligible + batch_size - 1) // batch_size
        print(f"  Batches needed: {batches_needed}")
        dates_list = sorted(by_date.keys())
        print(f"  Discovery date range: {dates_list[0]} ~ {dates_list[-1]}")
    print(f"  Brand split: {dict(brand_counts)}")
    print("=" * 60)


if __name__ == '__main__':
    main()
