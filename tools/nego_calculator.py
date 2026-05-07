"""Influencer negotiation calculator based on CPV grade system.

Calculates max budget, recommends accept/counter/reject,
and generates counter-offer amounts.

Usage:
    # Manual input
    python tools/nego_calculator.py --followers 2408 --avg-views 1500 --product ppsu
    python tools/nego_calculator.py --followers 2408 --avg-views 1500 --product ppsu --requested 10000

    # Auto-fetch by handle (PG first, Apify fallback)
    python tools/nego_calculator.py --handle @username --product ppsu --requested 10000
"""
import argparse
import json
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)

# ── CPV Grade Thresholds — v1 provisional (2026-04-14, percentile 기반) ──
# A: 상위30% (≤¥0.3) | B: 30~75% (¥0.3~3.5) | C: 하위25% (>¥3.5)
# 차주 채널별 분석 후 확정 예정. 수정 시 generate_cpv_data.py도 같이 변경할 것.
GRADE_A_MAX = 0.3
GRADE_B_MAX = 3.5

# ── Product COGS in KRW ──
PRODUCT_COGS_KRW = {
    "ppsu": 20000, "onetouch": 25000, "fliptop": 25000, "stainless": 32000,
}
KRW_TO_JPY = 1 / 9.5
POTENTIAL_MULTIPLIER = 1.5


def cogs_jpy(product: str) -> int:
    krw = PRODUCT_COGS_KRW.get(product.lower(), PRODUCT_COGS_KRW["ppsu"])
    return round(krw * KRW_TO_JPY)


def fetch_creator_stats(handle: str) -> dict:
    """Fetch creator stats: try PG first, then Apify fallback.

    Returns: {followers: int, avg_views: int, source: str}
    """
    handle = handle.lstrip("@")

    # ── Step 1: PG via DataKeeper ──
    stats = _fetch_from_pg(handle)
    if stats:
        return stats

    # ── Step 2: Apify fallback ──
    stats = _fetch_from_apify(handle)
    if stats:
        return stats

    return {"followers": 0, "avg_views": 0, "source": "none"}


def _fetch_from_pg(handle: str) -> dict | None:
    """Query content_posts from PG for this creator."""
    try:
        from data_keeper_client import DataKeeper
        dk = DataKeeper()
        rows = dk.get("content_posts", days=90, limit=500)
        creator_posts = [r for r in rows
                         if r.get("username", "").lower() == handle.lower()]
        if not creator_posts:
            return None

        views = [r.get("views", 0) or 0 for r in creator_posts if r.get("views")]
        if not views:
            return None

        followers = max(r.get("followers", 0) or 0 for r in creator_posts)
        avg_views = round(sum(views) / len(views))
        print(f"  [PG] {handle}: {len(views)} posts, avg views={avg_views}, followers={followers}")
        return {"followers": followers, "avg_views": avg_views, "source": "pg"}
    except Exception as e:
        print(f"  [PG] query failed: {e}")
        return None


def _fetch_from_apify(handle: str) -> dict | None:
    """Scrape creator profile + recent posts via Apify."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass

    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("  [Apify] No APIFY_API_TOKEN")
        return None

    import requests
    print(f"  [Apify] Scraping @{handle}...")

    payload = {
        "usernames": [handle],
        "resultsLimit": 12,
    }
    try:
        resp = requests.post(
            f"https://api.apify.com/v2/acts/apify~instagram-scraper/runs"
            f"?token={token}&waitForFinish=120",
            json=payload, timeout=130,
        )
        data = resp.json().get("data", {})
        dataset_id = data.get("defaultDatasetId", "")
        if not dataset_id:
            print("  [Apify] No dataset returned")
            return None

        items = requests.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}",
            timeout=30,
        ).json()

        followers = 0
        views = []
        for item in items:
            if item.get("followersCount"):
                followers = max(followers, item["followersCount"])
            v = item.get("videoPlayCount", 0) or 0
            if v > 0:
                views.append(v)

        if not views:
            print(f"  [Apify] @{handle}: no video posts found")
            return {"followers": followers, "avg_views": 0, "source": "apify"}

        avg_views = round(sum(views) / len(views))
        print(f"  [Apify] @{handle}: {len(views)} videos, avg views={avg_views}, followers={followers}")
        return {"followers": followers, "avg_views": avg_views, "source": "apify"}
    except Exception as e:
        print(f"  [Apify] scrape failed: {e}")
        return None


def calculate(followers: int, avg_views: int, product: str,
              requested_fee: int = 0, has_potential: bool = False) -> dict:
    product_cost = cogs_jpy(product)
    a_cap_total = avg_views * GRADE_A_MAX
    b_cap_total = avg_views * GRADE_B_MAX
    a_max_fee = max(0, a_cap_total - product_cost)
    b_max_fee = max(0, b_cap_total - product_cost)
    potential_cap_fee = a_max_fee * POTENTIAL_MULTIPLIER
    gifting_cpv = product_cost / avg_views if avg_views > 0 else 999
    gifting_grade = _grade(gifting_cpv)

    result = {
        "product": product, "product_cost_jpy": product_cost,
        "followers": followers, "avg_views": avg_views,
        "gifting_cpv": round(gifting_cpv, 2), "gifting_grade": gifting_grade,
        "a_max_fee": round(a_max_fee), "b_max_fee": round(b_max_fee),
        "potential_cap_fee": round(potential_cap_fee), "requested_fee": requested_fee,
    }

    if requested_fee == 0:
        result["recommendation"] = "gifting"
        result["reasoning"] = f"무상 기프팅 시 CPV ¥{gifting_cpv:.2f} → {gifting_grade}등급"
        result["suggested_fee"] = 0
        return result

    if requested_fee <= a_max_fee:
        total = product_cost + requested_fee
        cpv = total / avg_views if avg_views > 0 else 999
        result.update({"recommendation": "accept", "projected_cpv": round(cpv, 2),
                       "projected_grade": _grade(cpv), "suggested_fee": requested_fee,
                       "reasoning": f"요구액 ¥{requested_fee:,} ≤ A상한 ¥{round(a_max_fee):,}. 예상 CPV ¥{cpv:.2f} → {_grade(cpv)}등급. 수용 추천."})
        return result

    if has_potential and requested_fee <= potential_cap_fee:
        total = product_cost + requested_fee
        cpv = total / avg_views if avg_views > 0 else 999
        result.update({"recommendation": "accept_with_potential", "projected_cpv": round(cpv, 2),
                       "projected_grade": _grade(cpv), "suggested_fee": requested_fee,
                       "reasoning": f"요구액 ¥{requested_fee:,} > A상한 but ≤ potential cap ¥{round(potential_cap_fee):,}. 수용 가능. 세은 최종 확인."})
        return result

    if requested_fee <= b_max_fee:
        counter = round(a_max_fee / 1000) * 1000
        if counter < 1000:
            counter = 0
        total = product_cost + counter
        cpv = total / avg_views if avg_views > 0 else 999
        result.update({"recommendation": "counter", "projected_cpv": round(cpv, 2),
                       "projected_grade": _grade(cpv), "counter_offer": counter, "suggested_fee": counter,
                       "reasoning": f"요구액 ¥{requested_fee:,} > A상한 ¥{round(a_max_fee):,}. ¥{counter:,} + 상품제공으로 카운터. 예상 CPV ¥{cpv:.2f} → {_grade(cpv)}등급."})
        return result

    result.update({"recommendation": "gifting_only", "suggested_fee": 0,
                   "reasoning": f"요구액 ¥{requested_fee:,} > B상한 ¥{round(b_max_fee):,}. 유상 비효율. 무상 기프팅 전환. CPV ¥{gifting_cpv:.2f} → {gifting_grade}등급."})
    return result


def _grade(cpv: float) -> str:
    if cpv <= GRADE_A_MAX:
        return "A"
    if cpv <= GRADE_B_MAX:
        return "B"
    return "C"


def print_report(result: dict):
    print("=" * 50)
    print("  NEGO CALCULATOR REPORT")
    print("=" * 50)
    print(f"  제품: {result['product']} (원가 ¥{result['product_cost_jpy']:,})")
    print(f"  팔로워: {result['followers']:,}")
    print(f"  평균 릴스 조회수: {result['avg_views']:,}")
    print(f"  무상 기프팅 CPV: ¥{result['gifting_cpv']} → {result['gifting_grade']}등급")
    print("-" * 50)
    print(f"  A등급 최대 보수: ¥{result['a_max_fee']:,}")
    print(f"  B등급 최대 보수: ¥{result['b_max_fee']:,}")
    if result["requested_fee"] > 0:
        print(f"  요구 금액: ¥{result['requested_fee']:,}")
    print(f"  ▶ 추천: {result['recommendation'].upper()}")
    if result.get("suggested_fee", 0) > 0:
        print(f"  ▶ 제안 금액: ¥{result['suggested_fee']:,}")
    if result.get("counter_offer"):
        print(f"  ▶ 카운터: ¥{result['counter_offer']:,} + 상품제공")
    if result.get("projected_cpv"):
        print(f"  ▶ 예상 CPV: ¥{result['projected_cpv']} → {result['projected_grade']}등급")
    print(f"  근거: {result['reasoning']}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Influencer negotiation calculator")
    parser.add_argument("--handle", type=str, help="IG handle (auto-fetch stats)")
    parser.add_argument("--followers", type=int, default=0)
    parser.add_argument("--avg-views", type=int, default=0)
    parser.add_argument("--product", type=str, default="ppsu",
                        choices=["ppsu", "onetouch", "fliptop", "stainless"])
    parser.add_argument("--requested", type=int, default=0)
    parser.add_argument("--potential", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    followers = args.followers
    avg_views = args.avg_views

    if args.handle:
        stats = fetch_creator_stats(args.handle)
        if stats["avg_views"] == 0:
            print(f"  WARNING: 조회수 데이터 없음 (source: {stats['source']})")
        followers = followers or stats["followers"]
        avg_views = avg_views or stats["avg_views"]

    if avg_views == 0:
        print("ERROR: avg_views 필수. --avg-views 또는 --handle로 지정하세요.")
        sys.exit(1)

    result = calculate(followers=followers, avg_views=avg_views, product=args.product,
                       requested_fee=args.requested, has_potential=args.potential)
    if args.handle:
        result["handle"] = args.handle
        result["data_source"] = stats.get("source", "manual")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
