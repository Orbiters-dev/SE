"""Generate CPV (Cost Per View) data for Content Intelligence dashboard.

Reads Grosmimi collab sheet for costs, scrapes IG post metrics via Apify,
calculates CPV and grades, outputs cpv_data.js for the dashboard.

Usage:
    python tools/generate_cpv_data.py

Output:
    docs/content-dashboard/cpv_data.js
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import os
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

# ── Config ──
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
DOCS_DIR = os.path.join(ROOT, "docs", "content-dashboard")

COLLAB_SHEET_ID = "1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU"
COLLAB_TAB = "Grosmimi"
SA_PATH = os.path.join(ROOT, "..", "seeun", "credentials", "google_service_account.json")
if not os.path.exists(SA_PATH):
    SA_PATH = os.path.join(ROOT, "credentials", "google_service_account.json")

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
if not APIFY_TOKEN:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "")

# Product COGS in KRW (actual cost, not retail)
PRODUCT_COGS_KRW = {
    "stain": 32000,
    "stainless": 32000,
    "fliptop": 25000,
    "onetouch": 25000,
    "ppsu": 20000,
}
KRW_TO_JPY = 1 / 9.5

# CPV grade thresholds — v2 (2026-04-14, percentile 기반 ABCD)
# Organic CPV 기준, 동적 계산. 수정 시 nego_calculator.py도 같이 변경할 것.
# A: 상위 20% / B: 20~50% / C: 50~90% / D: 하위 10%
GRADE_PCT = {"A": 20, "B": 52, "C": 90}  # 누적 percentile cutoff

# Ad spend from META sheet (whitelisting) — 캠페인명 → spend (¥)
# Source: Japan_Marketing Plan_Monthly_V1_251119 (1).xlsx > META tab
# Rakuten 캠페인, 자체 콘텐츠(Instagram 게시물:) 제외
AD_SPEND_MAP = {
    # key = (username, campaign hint) for matching
    "PPSU_coni_WL_20260126": {"username": "coni.ikuji", "spend": 80600, "product_hint": "ppsu"},
    "AD G | Stainless 300ml | coni": {"username": "coni.ikuji", "spend": 55248, "product_hint": "stain"},
    "AD D | PPSU 300ml | ichikuru_fufu": {"username": "ichikuru_fufu", "spend": 35855},
    "AD B | PPSU 300ml | monyuru 1": {"username": "mon_yuru.ikuji", "spend": 381},
    "AD B | PPSU 300ml | monyuru 2": {"username": "mon_yuru.ikuji", "spend": 9948},
    "AD C | Daino | emachi": {"username": "emachi_mom", "spend": 3339},
    "AD D | Stainless 300ml | Erimama": {"username": "eri_mama_ikuji", "spend": 2321},
    "AD B | Stainless | tepi": {"username": "tepi_ikuji", "spend": 1095},
    "AD H | Stainless 300ml | mayuka": {"username": "mayuka_mom", "spend": 237},
    "AD I | Stainless 200ml | shiroi": {"username": "shiro_ikuji", "spend": 69},
    "AD C | PPSU 200ml | memeko": {"username": "memeko_babyikuji", "spend": 10},
}


def get_product_cost(product_str):
    p = product_str.lower()
    if "stain" in p:
        return round(32000 * KRW_TO_JPY)
    if "fliptop" in p or "onetouch" in p:
        return round(25000 * KRW_TO_JPY)
    return round(20000 * KRW_TO_JPY)  # ppsu default


def load_collab_data():
    """Load collab data from Google Sheets — per-post (not per-creator)."""
    creds = Credentials.from_service_account_file(
        SA_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(COLLAB_SHEET_ID)
    ws = sh.worksheet(COLLAB_TAB)
    rows = ws.get_all_values()

    posts = []
    for row in rows[3:]:  # skip 2 header rows + 1 sub-header
        cid = row[3].strip()
        raw_url = row[16].strip()
        if not cid or not raw_url:
            continue

        deal_type = row[23].strip()
        fee_str = row[24].strip().replace(",", "").replace("-", "").strip()
        fee = float(fee_str) if fee_str else 0
        product = row[6].strip()
        product_cost = get_product_cost(product)
        total_cost = product_cost + fee
        is_paid = deal_type.lower() == "paid"

        # Extract URLs — each URL = 1 post record
        urls = []
        for u in raw_url.replace("\n", " ").split():
            u = u.strip()
            if u.startswith("http") and "instagram.com" in u:
                if "?" in u:
                    u = u.split("?")[0]
                urls.append(u)

        for url in urls:
            posts.append({
                "username": cid,
                "url": url,
                "fee": fee / len(urls) if len(urls) > 1 else fee,
                "product_cost": product_cost / len(urls) if len(urls) > 1 else product_cost,
                "total_cost": total_cost / len(urls) if len(urls) > 1 else total_cost,
                "is_paid": is_paid,
                "product": product,
            })

    # Manual fixes: split multi-post entries where sheet has only 1 URL
    SPLIT_FIXES = {
        "emachi_mom": {
            "urls": [
                "https://www.instagram.com/reel/DUHVuzgE4_P/",
                "https://www.instagram.com/reel/DVLiB1Jkxs0/",
            ],
        },
    }
    new_posts = []
    for p in posts:
        fix = SPLIT_FIXES.get(p["username"])
        if fix and len(fix["urls"]) > 1:
            n = len(fix["urls"])
            for u in fix["urls"]:
                new_posts.append({
                    **p,
                    "url": u,
                    "fee": p["fee"] / n,
                    "product_cost": p["product_cost"] / n,
                    "total_cost": p["total_cost"] / n,
                })
        else:
            new_posts.append(p)
    posts = new_posts

    print(f"Loaded {len(posts)} posts from sheet")
    return posts


def scrape_metrics(urls):
    """Scrape Instagram post metrics via Apify — per-URL (not aggregated)."""
    if not APIFY_TOKEN:
        print("WARNING: No APIFY_API_TOKEN, skipping scrape")
        return {}

    unique_urls = list(set(urls))
    print(f"Scraping {len(unique_urls)} URLs via Apify...")

    payload = {
        "directUrls": unique_urls,
        "resultsType": "posts",
        "resultsLimit": len(unique_urls) + 10,
    }

    resp = requests.post(
        f"https://api.apify.com/v2/acts/apify~instagram-scraper/runs"
        f"?token={APIFY_TOKEN}&waitForFinish=300",
        json=payload,
        timeout=320,
    )

    data = resp.json().get("data", {})
    dataset_id = data.get("defaultDatasetId", "")
    status = data.get("status", "")
    print(f"Apify run status: {status}, dataset: {dataset_id}")

    if not dataset_id:
        print("ERROR: No dataset returned")
        return {}

    results = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}",
        timeout=60,
    ).json()

    print(f"Scraped {len(results)} posts")

    # Index by URL (per-post, not aggregated)
    metrics = {}
    for item in results:
        shortcode = item.get("shortCode", "")
        url = item.get("url", "") or f"https://www.instagram.com/reel/{shortcode}/"
        views = item.get("videoPlayCount", 0) or 0
        likes = item.get("likesCount", 0) or 0
        comments = item.get("commentsCount", 0) or 0
        owner = item.get("ownerUsername", "")

        # Normalize URL for matching
        norm = url.rstrip("/").split("?")[0]
        metrics[norm] = {
            "views": views,
            "likes": max(likes, 0),
            "comments": max(comments, 0),
            "shortcode": shortcode,
            "owner": owner,
        }
        # Also index by shortcode URL patterns
        if shortcode:
            for pattern in [
                f"https://www.instagram.com/reel/{shortcode}",
                f"https://www.instagram.com/p/{shortcode}",
            ]:
                metrics[pattern] = metrics[norm]

    return metrics


def match_ad_spend(username, product):
    """Match a post to ad spend from META sheet."""
    total = 0
    p = product.lower()
    for _key, entry in AD_SPEND_MAP.items():
        if entry["username"] != username:
            continue
        # If product_hint exists, match by product type
        hint = entry.get("product_hint", "")
        if hint:
            if hint == "ppsu" and "stain" not in p and "fliptop" not in p and "onetouch" not in p:
                total += entry["spend"]
            elif hint == "stain" and "stain" in p:
                total += entry["spend"]
            elif not hint:
                total += entry["spend"]
        else:
            total += entry["spend"]
    return total


def calculate_cpv(posts, metrics):
    """Calculate CPV per post — organic + total (with ad spend). ABCD by natural gaps."""
    results = []

    for post in posts:
        url_norm = post["url"].rstrip("/").split("?")[0]
        m = metrics.get(url_norm)

        if not m:
            parts = url_norm.rstrip("/").split("/")
            shortcode = parts[-1] if parts else ""
            for pattern in [
                f"https://www.instagram.com/reel/{shortcode}",
                f"https://www.instagram.com/p/{shortcode}",
            ]:
                m = metrics.get(pattern)
                if m:
                    break

        if not m:
            continue

        views = m.get("views", 0)
        if views <= 0:
            continue

        ad_spend = match_ad_spend(post["username"], post.get("product", ""))
        organic_cost = post["total_cost"]
        total_cost = organic_cost + ad_spend
        organic_cpv = organic_cost / views
        total_cpv = total_cost / views

        results.append({
            "username": post["username"],
            "url": post["url"],
            "shortcode": m.get("shortcode", ""),
            "deal_type": "paid" if post["is_paid"] else "free",
            "fee": round(post["fee"]),
            "product_cost": round(post["product_cost"]),
            "ad_spend": ad_spend,
            "organic_cost": round(organic_cost),
            "total_cost": round(total_cost),
            "product": post["product"],
            "views": views,
            "likes": m.get("likes", 0),
            "comments": m.get("comments", 0),
            "organic_cpv": round(organic_cpv, 2),
            "total_cpv": round(total_cpv, 2),
            "cpv": round(organic_cpv, 2),  # backward compat for chart
            "grade": "",  # assigned below by percentile
        })

    results.sort(key=lambda x: x["organic_cpv"])
    n = len(results)
    if n > 0:
        i_a = max(0, int(n * GRADE_PCT["A"] / 100) - 1)
        i_b = max(0, int(n * GRADE_PCT["B"] / 100) - 1)
        i_c = max(0, int(n * GRADE_PCT["C"] / 100) - 1)
        cut_a = results[i_a]["organic_cpv"]
        cut_b = results[i_b]["organic_cpv"]
        cut_c = results[i_c]["organic_cpv"]
        for r in results:
            cpv = r["organic_cpv"]
            if cpv <= cut_a:
                r["grade"] = "A"
            elif cpv <= cut_b:
                r["grade"] = "B"
            elif cpv <= cut_c:
                r["grade"] = "C"
            else:
                r["grade"] = "D"

    a = len([r for r in results if r["grade"] == "A"])
    b = len([r for r in results if r["grade"] == "B"])
    c = len([r for r in results if r["grade"] == "C"])
    d = len([r for r in results if r["grade"] == "D"])
    print(f"Grades: A({a}) ≤¥{cut_a} | B({b}) ≤¥{cut_b} | C({c}) ≤¥{cut_c} | D({d}) >¥{cut_c}")
    return results


def generate_js(results):
    """Output cpv_data.js for the dashboard."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    output_path = os.path.join(DOCS_DIR, "cpv_data.js")

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")

    js = f"// Auto-generated by generate_cpv_data.py — {ts}\n"
    js += f"var CPV_DATA = {json.dumps(results, ensure_ascii=False, indent=2)};\n"
    js += f'var CPV_UPDATED = "{ts}";\n'

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js)

    print(f"Written {output_path} ({len(results)} creators)")
    return output_path


def main():
    print("=== CPV Data Generator (per-post) ===")
    posts = load_collab_data()

    all_urls = [p["url"] for p in posts]
    metrics = scrape_metrics(all_urls)
    results = calculate_cpv(posts, metrics)

    path = generate_js(results)

    # Summary
    a = len([r for r in results if r["grade"] == "A"])
    b = len([r for r in results if r["grade"] == "B"])
    c = len([r for r in results if r["grade"] == "C"])
    d = len([r for r in results if r["grade"] == "D"])
    paid = len([r for r in results if r["deal_type"] == "paid"])
    free = len([r for r in results if r["deal_type"] == "free"])
    print(f"\nSummary: {len(results)} posts")
    print(f"  A: {a} | B: {b} | C: {c} | D: {d}")
    print(f"  Paid: {paid} | Free: {free}")
    print(f"  Output: {path}")


if __name__ == "__main__":
    main()
