#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JP/US 키워드 트렌드 발굴 — Google Ads Keyword Planner

1) GenerateKeywordIdeas: 씨앗 → 카테고리 연관 키워드 수백 개 + 월별 검색량 (발굴)
2) GenerateKeywordHistoricalMetrics: 브랜드 지명 고정 세트 볼륨 (비교 잣대)

Usage:
    python tools/kw_trend_jp.py                     # JP + US 수집 → .tmp/kw_insight/
    python tools/kw_trend_jp.py --markets JP        # JP만
    python tools/kw_trend_jp.py --max-ideas 500     # 발굴 상한 조정
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    print("[WARN] python-dotenv 미설치 — 셸 환경변수만 사용")

REQUIRED_ENV = ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"]

OUT_DIR = ROOT / ".tmp" / "kw_insight"

# Google Ads 상수: geo=2392(일본)/2840(미국), lang=1005(일본어)/1000(영어)
GEO = {"JP": 2392, "US": 2840}
LANG = {"JP": 1005, "US": 1000}

SEEDS = {
    "JP": ["ストローマグ", "ベビーマグ", "ppsu", "ステンレス ストローマグ", "グロミミ"],
    "US": ["sippy cup", "straw cup", "toddler cup", "stainless steel sippy cup", "grosmimi"],
}
BRAND_SET = {
    "JP": ["グロミミ", "grosmimi", "ピジョン マグマグ", "マグマグ", "サーモス ベビーストローマグ",
           "ビーボックス", "b.box", "リッチェル ストローマグ", "コンビ ラクマグ", "ラクマグ",
           "マンチキン ミラクルカップ", "munchkin"],
    "US": ["grosmimi", "b.box sippy cup", "bbox", "munchkin 360 cup", "thermos baby",
           "richell", "pigeon magmag", "nuk sippy cup", "zojirushi kids"],
}

API_RETRIES = 3
RETRY_WAIT_S = 10


def check_env() -> list[str]:
    """필수 env 검증 — 누락 키 목록 반환."""
    return [k for k in REQUIRED_ENV if not os.getenv(k)]


def get_client_and_customer(customer_id_override: str | None = None):
    """GoogleAdsClient + 키워드플래너용 계정 ID.

    계정 선택: --customer-id 인자 > GOOGLE_ADS_CUSTOMER_ID env > 활성 서브계정 목록의 첫 번째
    (여러 개면 전체 목록을 출력해 어떤 계정이 선택됐는지 투명하게 보여줌).
    data_keeper.collect_dataforseo와 동일 패턴.
    """
    from google.ads.googleads.client import GoogleAdsClient
    config = {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
        "login_customer_id": os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "8625697405"),
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(config)

    explicit = customer_id_override or os.getenv("GOOGLE_ADS_CUSTOMER_ID")
    if explicit:
        print("account (explicit):", explicit)
        return client, str(explicit)

    ga = client.get_service("GoogleAdsService")
    stream = ga.search_stream(
        customer_id=config["login_customer_id"],
        query="""SELECT customer_client.id, customer_client.descriptive_name
                 FROM customer_client
                 WHERE customer_client.manager = false AND customer_client.status = 'ENABLED'""",
    )
    candidates = []
    for batch in stream:
        for row in batch.results:
            candidates.append((str(row.customer_client.id), row.customer_client.descriptive_name))
    if not candidates:
        raise RuntimeError("활성 Google Ads 서브계정 없음 — GOOGLE_ADS_CUSTOMER_ID로 직접 지정 가능")
    if len(candidates) > 1:
        print("sub-accounts found:", candidates, "→ 첫 번째 사용 (--customer-id로 변경 가능)")
    customer_id = candidates[0][0]
    print("account:", customer_id)
    return client, customer_id


def _is_transient(e: Exception) -> bool:
    """재시도 대상 = API/네트워크 일시 오류만 (프로그래밍 오류는 즉시 전파)."""
    if isinstance(e, (TypeError, AttributeError, KeyError, ValueError)):
        return False
    name = type(e).__name__
    if name == "GoogleAdsException":
        msg = str(e).lower()
        return any(t in msg for t in ("quota", "rate", "resource_exhausted", "deadline",
                                      "unavailable", "internal"))
    return True  # 네트워크 계열 등 나머지는 재시도


def _with_retry(fn, label: str):
    """일시 오류(쿼터/네트워크)만 재시도하는 래퍼."""
    last = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if not _is_transient(e):
                raise
            last = e
            print(f"  [{label}] attempt {attempt}/{API_RETRIES} failed: {e}")
            if attempt < API_RETRIES:
                time.sleep(RETRY_WAIT_S * attempt)
    print(f"  [{label}] 최종 실패 ({API_RETRIES}회 재시도 소진): {last}")
    raise last


def monthly_list(metrics) -> list[dict]:
    """monthly_search_volumes proto → [{year, month, searches}] (없으면 빈 리스트)."""
    out = []
    for m in getattr(metrics, "monthly_search_volumes", []) or []:
        out.append({"year": m.year,
                    "month": m.month.value if hasattr(m.month, "value") else int(m.month),
                    "searches": m.monthly_searches or 0})
    return out


def keyword_ideas(client, customer_id: str, market: str, max_ideas: int) -> list[dict]:
    """씨앗 → 연관 키워드 발굴 (avg_monthly_searches 내림차순)."""
    kp = client.get_service("KeywordPlanIdeaService")
    req = client.get_type("GenerateKeywordIdeasRequest")
    req.customer_id = customer_id
    req.geo_target_constants.append(
        client.get_service("GeoTargetConstantService").geo_target_constant_path(GEO[market]))
    req.language = client.get_service("GoogleAdsService").language_constant_path(LANG[market])
    req.include_adult_keywords = False
    req.keyword_seed.keywords.extend(SEEDS[market])

    def _call():
        ideas = []
        # 전량 수집 후 정렬 → 상위 max_ideas 절단 (절단 먼저 하면 top-N 왜곡)
        for idea in kp.generate_keyword_ideas(request=req):
            m = idea.keyword_idea_metrics
            comp = str(m.competition).split(".")[-1] if m.competition else "UNSPECIFIED"
            ideas.append({
                "keyword": idea.text,
                "avg_monthly_searches": int(m.avg_monthly_searches or 0),
                "competition": comp,
                "competition_index": int(m.competition_index or 0),
                "cpc_high": round((m.high_top_of_page_bid_micros or 0) / 1_000_000, 2),
                "monthly": monthly_list(m),
            })
        ideas.sort(key=lambda x: -x["avg_monthly_searches"])
        return ideas[:max_ideas]

    return _with_retry(_call, f"ideas:{market}")


def historical(client, customer_id: str, market: str, keywords: list[str]) -> list[dict]:
    """고정 키워드 세트의 월별 검색량 시계열."""
    kp = client.get_service("KeywordPlanIdeaService")
    req = client.get_type("GenerateKeywordHistoricalMetricsRequest")
    req.customer_id = customer_id
    req.keywords.extend(keywords)
    req.geo_target_constants.append(
        client.get_service("GeoTargetConstantService").geo_target_constant_path(GEO[market]))
    req.language = client.get_service("GoogleAdsService").language_constant_path(LANG[market])

    def _call():
        out = []
        for r in kp.generate_keyword_historical_metrics(request=req).results:
            m = r.keyword_metrics
            out.append({
                "keyword": r.text,
                "close_variants": [str(v) for v in (r.close_variants or [])],
                "avg_monthly_searches": int(m.avg_monthly_searches or 0),
                "monthly": monthly_list(m),
            })
        return out

    return _with_retry(_call, f"historical:{market}")


def main() -> int:
    ap = argparse.ArgumentParser(description="JP/US keyword trend discovery (Keyword Planner)")
    ap.add_argument("--markets", default="JP,US", help=f"쉼표 구분 — 지원: {','.join(GEO)}")
    ap.add_argument("--max-ideas", type=int, default=1500, help="시장당 발굴 키워드 상한")
    ap.add_argument("--customer-id", default=None, help="Google Ads 계정 ID 직접 지정 (기본: 첫 활성 서브계정)")
    args = ap.parse_args()

    missing = check_env()
    if missing:
        print("[ABORT] 필수 env 누락:", ", ".join(missing))
        return 1

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    if not markets:
        print("[ABORT] --markets가 비어 있음 — 지원:", list(GEO))
        return 1
    bad = [m for m in markets if m not in GEO or m not in SEEDS or m not in BRAND_SET]
    if bad:
        print("[ABORT] 지원하지 않는 마켓:", bad, "— 지원:", list(GEO))
        return 1

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print("[ABORT] 출력 디렉토리 생성 실패:", OUT_DIR, e)
        return 1
    try:
        client, customer_id = get_client_and_customer(args.customer_id)
    except Exception as e:
        print("[ABORT] Google Ads 클라이언트 초기화 실패:", e)
        return 1

    failures = 0
    for market in markets:
        try:
            print(f"=== {market} keyword ideas ===")
            ideas = keyword_ideas(client, customer_id, market, args.max_ideas)
            if not ideas:
                print(f"[WARN] {market} 발굴 결과 0건 — API/씨앗 확인 필요")
            print(market, "ideas:", len(ideas), "| top:",
                  [(i["keyword"], i["avg_monthly_searches"]) for i in ideas[:5]])

            print(f"=== {market} brand historical ===")
            hist = historical(client, customer_id, market, BRAND_SET[market])
            for h in hist:
                print(" ", h["keyword"], h["avg_monthly_searches"])
        except Exception as e:
            failures += 1
            print(f"[ERROR] {market} API 수집 실패: {e}")
            continue
        try:
            with open(OUT_DIR / f"ideas_{market}.json", "w", encoding="utf-8") as f:
                json.dump(ideas, f, ensure_ascii=False, indent=1)
            with open(OUT_DIR / f"brands_{market}.json", "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=1)
        except OSError as e:
            failures += 1
            print(f"[ERROR] {market} 파일 저장 실패: {e}")

    print("DONE ->", OUT_DIR, f"(markets={len(markets)}, failures={failures})")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
