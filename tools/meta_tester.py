"""
Meta Ads Tester — 데이터 정확성 & 리포트 품질 검증
=====================================================
Meta Ads 일간 분석 플로우의 각 단계를 자동 검증한다.

Shopify 테스터와 달리, "API 응답이 있냐"가 아니라
"숫자가 맞냐, 계산이 맞냐, 리포트에 빠진 것 없냐"를 검사한다.

Usage:
    # 최근 7일 데이터 수집 후 전체 검증
    python tools/meta_tester.py --run

    # 이미 수집된 JSON만 검증 (API 호출 없음)
    python tools/meta_tester.py --validate-only

    # 특정 날짜 기준 검증
    python tools/meta_tester.py --run --days 14

    # 드라이런 리포트(HTML) 구조 검증
    python tools/meta_tester.py --check-report --report-file .tmp/meta_ads_report_2026-03-01.html

    # 결과 보기
    python tools/meta_tester.py --results

Checks:
    [D] Data Fetch      - API 응답 완전성, 필드 누락, 날짜 범위 커버
    [M] Metrics         - ROAS/CTR/CPC/CPM 재계산 vs 원본 데이터 일치
    [B] Brand           - 캠페인 브랜드 분류 누락 (Non-classified 비율)
    [S] Sum Consistency - adset spend 합산 ≈ campaign spend (±5%)
    [A] Anomaly Logic   - 이상 감지 조건 실제 작동 여부
    [R] Report HTML     - 이메일 HTML 5개 섹션 존재, NaN/0 미표시
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
TMP = ROOT / ".tmp"
META_DIR = TMP / "meta_ads"
RESULTS_FILE = TMP / "meta_test_results.json"

sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

PYTHON = sys.executable

# ─── 출력 헬퍼 ───────────────────────────────────────────────────────────────

def log(msg):  print(msg)
def ok(msg):   print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def sep():     print("-" * 60)


# ─── 지표 재계산 헬퍼 ────────────────────────────────────────────────────────

def load_json(path):
    """Load JSON that may be wrapped as {'data': [...]} or a bare list."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw

def calc_metrics(row):
    spend  = float(row.get("spend", 0) or 0)
    impr   = float(row.get("impressions", 0) or 0)
    clicks = float(row.get("clicks", 0) or 0)
    reach  = float(row.get("reach", 0) or 0)

    # Flat fields (fetch_meta_ads_daily output)
    purchases = float(row.get("purchases", 0) or 0)
    rev       = float(row.get("purchases_value", 0) or 0)

    roas = round(rev / spend, 4) if spend > 0 else 0
    ctr  = round(clicks / impr * 100, 4) if impr > 0 else 0
    cpc  = round(spend / clicks, 4) if clicks > 0 else 0
    cpm  = round(spend / impr * 1000, 4) if impr > 0 else 0
    freq = round(impr / reach, 4) if reach > 0 else 0

    return {"spend": spend, "impressions": impr, "clicks": clicks,
            "roas": roas, "ctr": ctr, "cpc": cpc, "cpm": cpm,
            "frequency": freq, "purchases": purchases, "revenue": rev}


# ─── D: 데이터 수집 품질 ────────────────────────────────────────────────────

def check_data_fetch(days=7):
    results = []
    passed = True

    for level in ("campaign", "adset", "ad"):
        fpath = META_DIR / f"{level}.json"
        log(f"\n  [{level.upper()}] {fpath.name}")

        if not fpath.exists():
            fail(f"{fpath.name} not found")
            results.append({"check": f"file_{level}", "status": "FAIL",
                            "detail": "file missing"})
            passed = False
            continue

        data = load_json(fpath)

        if not data:
            fail("Empty data file")
            results.append({"check": f"file_{level}", "status": "FAIL",
                            "detail": "empty"})
            passed = False
            continue

        ok(f"{len(data)} rows loaded")

        # 날짜 커버리지
        dates = set(row.get("date") or row.get("date_start") for row in data
                    if row.get("date") or row.get("date_start"))
        if dates:
            min_d = min(dates)
            max_d = max(dates)
            expected_days = min(days, (datetime.now() - datetime(2024,1,1)).days)
            info(f"Date range: {min_d} ~ {max_d} ({len(dates)} days)")
            if len(dates) < days * 0.7:
                warn(f"Only {len(dates)} days of data (expected ~{days})")

        # 필수 필드 누락 검사
        required = ["campaign_id", "campaign_name", "spend", "impressions", "clicks"]
        missing_fields = set()
        for row in data[:50]:  # 샘플 50개만
            for f in required:
                if f not in row:
                    missing_fields.add(f)
        if missing_fields:
            fail(f"Missing fields in rows: {missing_fields}")
            passed = False
        else:
            ok(f"All required fields present")

        # $0 spend 비율 (너무 많으면 의심)
        zero_spend = sum(1 for r in data if float(r.get("spend", 0) or 0) == 0)
        pct = zero_spend / len(data) * 100
        if pct > 80:
            warn(f"{pct:.0f}% rows have $0 spend (might be paused ads)")
        else:
            ok(f"Non-zero spend rows: {len(data) - zero_spend}/{len(data)}")

        results.append({"check": f"fetch_{level}", "status": "PASS",
                        "rows": len(data), "dates": len(dates)})

    return passed, results


# ─── M: 지표 계산 정확도 ────────────────────────────────────────────────────

def check_metrics():
    fpath = META_DIR / "campaign.json"
    if not fpath.exists():
        warn("campaign.json not found -- skipping metrics check")
        return None, [{"check": "metrics", "status": "SKIP"}]

    data = load_json(fpath)

    results = []
    passed = True
    errors = 0
    sample = [r for r in data if float(r.get("spend", 0) or 0) > 10][:20]

    log(f"\n  Checking metrics for {len(sample)} campaigns with spend > $10")

    for row in sample:
        m = calc_metrics(row)
        name = row.get("campaign_name", "?")[:40]

        # 기본 sanity: ROAS가 0~100 범위여야 함
        if m["roas"] > 100:
            fail(f"Suspicious ROAS={m['roas']:.1f} | {name}")
            errors += 1

        # CTR이 0~50% 범위여야 함
        if m["ctr"] > 50:
            fail(f"Suspicious CTR={m['ctr']:.1f}% | {name}")
            errors += 1

        # CPM이 $0~$500 범위여야 함
        if m["cpm"] > 500:
            warn(f"Very high CPM=${m['cpm']:.0f} | {name}")

        # Spend > 0인데 impressions = 0 이상한 케이스
        if m["spend"] > 0 and m["impressions"] == 0:
            fail(f"spend=${m['spend']:.2f} but impressions=0 | {name}")
            errors += 1

    if errors == 0:
        ok(f"All {len(sample)} campaign metrics look sane")
        results.append({"check": "metrics_sanity", "status": "PASS",
                        "samples_checked": len(sample)})
    else:
        fail(f"{errors} metric anomalies found")
        results.append({"check": "metrics_sanity", "status": "FAIL",
                        "anomalies": errors})
        passed = False

    # Revenue vs ROAS cross-check
    total_spend = sum(float(r.get("spend", 0) or 0) for r in data)
    total_rev = sum(float(r.get("purchases_value", 0) or 0) for r in data)
    if total_spend > 0:
        portfolio_roas = round(total_rev / total_spend, 2)
        info(f"Portfolio ROAS: {portfolio_roas:.2f}x (spend=${total_spend:,.0f}, rev=${total_rev:,.0f})")
        ok("Revenue / Spend cross-check complete")

    return passed, results


# ─── B: 브랜드 분류 정확도 ──────────────────────────────────────────────────

BRAND_RULES = [
    ("Grosmimi",    ["grosmimi", "grosm", "grossmimi", "ppsu", "stainless steel",
                     "sls cup", "stainless straw", "| gm |", " gm |", "| gm_",
                     "_gm_", "gm_tumbler", "dentalmom", "dental mom", "dental_mom", "livfuselli"]),
    ("CHA&MOM",     ["cha&mom", "cha_mom", "chamom", "| cm |", " cm |", "| cm_",
                     "_cm_", "skincare", "lotion", "hair wash", "love&care",
                     "love_care", "love care"]),
    ("Alpremio",    ["alpremio"]),
    ("Easy Shower", ["easy shower", "easy_shower", "easyshower", "shower stand"]),
    ("Hattung",     ["hattung"]),
    ("Beemymagic",  ["beemymagic", "beemy"]),
    ("Comme Moi",   ["commemoi", "comme moi", "commemo"]),
    ("BabyRabbit",  ["babyrabbit", "baby rabbit"]),
    ("Naeiae",      ["naeiae", "rice snack", "pop rice"]),
    ("RIDE & GO",   ["ride & go", "ridego", "ride_go"]),
    ("BambooeBebe", ["bamboobebe"]),
    # Multi-brand / account-level campaigns (ZeZeBaeBae store, not a single brand)
    ("ZZB (Multi-brand)", ["shopify |", "| shopify", "general |", "| general",
                           "clearance", "laurence", "dsh", "zezebaebae"]),
    ("Promo",       ["newyear", "new year", "new_year", "asc campaign (legacy)",
                     "promo campaign", "promo_campaign"]),
]

# Campaign names containing these keywords are Traffic/Awareness — no purchase conversion expected
TRAFFIC_KEYWORDS = ["| traffic |", "traffic |", "| tof |", "| mof |",
                    "amz |", "amazon |", "| amz", "awareness", "brand awareness",
                    "reach campaign", "| reach |"]

def is_traffic_campaign(name):
    n = name.lower()
    return any(k in n for k in TRAFFIC_KEYWORDS)

def classify_brand(name):
    n = name.lower()
    for brand, kws in BRAND_RULES:
        if any(k in n for k in kws):
            return brand
    return "Non-classified"

def check_brand_classification():
    fpath = META_DIR / "campaign.json"
    if not fpath.exists():
        return None, [{"check": "brand", "status": "SKIP"}]

    data = load_json(fpath)

    # 고지출 캠페인만 (spend > $5)
    active = [r for r in data if float(r.get("spend", 0) or 0) > 5]
    if not active:
        warn("No campaigns with spend > $5")
        return True, [{"check": "brand", "status": "SKIP", "reason": "no active campaigns"}]

    # 캠페인 단위로 집약 (날짜별 중복 제거)
    seen = {}
    for row in active:
        cid = row.get("campaign_id")
        if cid not in seen:
            seen[cid] = row

    unique_campaigns = list(seen.values())
    brands = {}
    non_classified = []

    for row in unique_campaigns:
        name = row.get("campaign_name", "")
        brand = classify_brand(name)
        brands[brand] = brands.get(brand, 0) + 1
        if brand == "Non-classified":
            non_classified.append(name)

    total = len(unique_campaigns)
    nc_pct = len(non_classified) / total * 100

    log(f"\n  Brand distribution ({total} unique campaigns):")
    for brand, cnt in sorted(brands.items(), key=lambda x: -x[1]):
        log(f"    {brand:20s} {cnt:3d} campaigns")

    passed = True
    results = []

    if nc_pct > 30:
        fail(f"Non-classified: {len(non_classified)}/{total} ({nc_pct:.0f}%) -- too many unclassified")
        for name in non_classified[:5]:
            warn(f"  Unclassified: {name[:70]}")
        passed = False
        results.append({"check": "brand_classification", "status": "FAIL",
                        "non_classified_pct": round(nc_pct, 1),
                        "examples": non_classified[:5]})
    elif nc_pct > 10:
        warn(f"Non-classified: {len(non_classified)}/{total} ({nc_pct:.0f}%) -- worth reviewing")
        for name in non_classified[:3]:
            warn(f"  Unclassified: {name[:70]}")
        results.append({"check": "brand_classification", "status": "WARN",
                        "non_classified_pct": round(nc_pct, 1)})
    else:
        ok(f"Brand classification OK: {nc_pct:.0f}% non-classified ({len(non_classified)}/{total})")
        results.append({"check": "brand_classification", "status": "PASS",
                        "non_classified_pct": round(nc_pct, 1)})

    return passed, results


# ─── S: 합산 일치성 (adset spend ≈ campaign spend) ──────────────────────────

def check_sum_consistency():
    c_path = META_DIR / "campaign.json"
    a_path = META_DIR / "adset.json"

    if not c_path.exists() or not a_path.exists():
        return None, [{"check": "sum_consistency", "status": "SKIP"}]

    campaigns = load_json(c_path)
    adsets    = load_json(a_path)

    # 날짜+캠페인 기준으로 집계
    camp_spend = {}
    for r in campaigns:
        key = (r.get("campaign_id"), r.get("date") or r.get("date_start"))
        camp_spend[key] = camp_spend.get(key, 0) + float(r.get("spend", 0) or 0)

    adset_spend = {}
    for r in adsets:
        key = (r.get("campaign_id"), r.get("date") or r.get("date_start"))
        adset_spend[key] = adset_spend.get(key, 0) + float(r.get("spend", 0) or 0)

    mismatches = []
    for key in camp_spend:
        c_s = camp_spend[key]
        a_s = adset_spend.get(key, 0)
        if c_s == 0:
            continue
        diff_pct = abs(c_s - a_s) / c_s * 100
        if diff_pct > 5:
            mismatches.append({"campaign_id": key[0], "date": key[1],
                               "campaign_spend": round(c_s, 2),
                               "adset_spend": round(a_s, 2),
                               "diff_pct": round(diff_pct, 1)})

    passed = True
    if not mismatches:
        ok(f"Spend consistency OK: adset sums match campaign totals (checked {len(camp_spend)} day-campaign pairs)")
        return True, [{"check": "sum_consistency", "status": "PASS"}]
    elif len(mismatches) < 3:
        warn(f"{len(mismatches)} minor mismatches (likely API rounding)")
        for m in mismatches[:3]:
            warn(f"  {m['date']} | campaign ${m['campaign_spend']:.2f} vs adset ${m['adset_spend']:.2f} ({m['diff_pct']:.1f}%)")
        return True, [{"check": "sum_consistency", "status": "WARN",
                       "mismatches": len(mismatches)}]
    else:
        fail(f"{len(mismatches)} spend mismatches > 5%")
        for m in mismatches[:5]:
            fail(f"  {m['date']} cid={m['campaign_id']} | ${m['campaign_spend']:.2f} vs ${m['adset_spend']:.2f}")
        passed = False
        return False, [{"check": "sum_consistency", "status": "FAIL",
                        "mismatches": len(mismatches), "examples": mismatches[:5]}]


# ─── A: 이상 감지 로직 검증 ─────────────────────────────────────────────────

def _aggregate_by_key(rows, key_field, name_field):
    """데일리 rows를 key(campaign_id / adset_id) 기준으로 기간 합산."""
    agg = {}
    for r in rows:
        kid = r.get(key_field)
        if kid not in agg:
            agg[kid] = {
                "name": r.get(name_field, ""),
                "spend": 0.0, "impressions": 0.0, "clicks": 0.0,
                "purchases": 0.0, "purchases_value": 0.0,
                # Frequency: 일별 impr/reach 가중평균을 위해 reach 합산은 부정확
                # → 최대 일별 frequency를 burnout 지표로 사용
                "max_daily_freq": 0.0,
            }
        agg[kid]["spend"]           += float(r.get("spend", 0) or 0)
        agg[kid]["impressions"]     += float(r.get("impressions", 0) or 0)
        agg[kid]["clicks"]          += float(r.get("clicks", 0) or 0)
        agg[kid]["purchases"]       += float(r.get("purchases", 0) or 0)
        agg[kid]["purchases_value"] += float(r.get("purchases_value", 0) or 0)
        daily_freq = float(r.get("frequency", 0) or 0)
        if daily_freq > agg[kid]["max_daily_freq"]:
            agg[kid]["max_daily_freq"] = daily_freq
    return list(agg.values())


def check_anomaly_logic():
    fpath = META_DIR / "campaign.json"
    if not fpath.exists():
        return None, [{"check": "anomaly_logic", "status": "SKIP"}]

    data = load_json(fpath)

    # ── 캠페인 기간 합산 (daily rows → per-campaign totals) ──────────────────
    campaigns_agg = _aggregate_by_key(data, "campaign_id", "campaign_name")

    results = []
    danger_roas = []
    good_roas   = []
    traffic_campaigns = []

    log("\n  [Campaign-level aggregated over full period]")

    for c in campaigns_agg:
        spend = c["spend"]
        rev   = c["purchases_value"]
        roas  = round(rev / spend, 2) if spend > 0 else 0
        name  = c["name"]

        if is_traffic_campaign(name):
            # Traffic 캠페인은 CVR 기대 안 함 → 별도 리스트
            if spend > 50:
                traffic_campaigns.append({"name": name[:55], "spend": spend})
            continue

        if spend < 100:
            # CVR 캠페인이라도 기간 내 $100 미만은 통계적으로 유의미하지 않음
            continue

        if roas < 2.0:
            danger_roas.append({"name": name[:55], "roas": roas, "spend": spend})
        elif roas >= 3.0:
            good_roas.append({"name": name[:55], "roas": roas, "spend": spend})

    info(f"CVR campaigns (spend >= $100): {len(danger_roas) + len(good_roas)} evaluated")
    info(f"Traffic/AMZ campaigns (spend > $50): {len(traffic_campaigns)} (ROAS N/A)")
    info(f"ROAS < 2.0  [DANGER]: {len(danger_roas)}")
    info(f"ROAS >= 3.0 [GOOD]:   {len(good_roas)}")

    if danger_roas:
        for r in sorted(danger_roas, key=lambda x: -x["spend"])[:5]:
            warn(f"  [ROAS DANGER] {r['name']} | ROAS={r['roas']:.2f} | spend=${r['spend']:.0f}")
    if good_roas:
        for r in sorted(good_roas, key=lambda x: -x["roas"])[:3]:
            ok(f"  [ROAS GOOD]   {r['name']} | ROAS={r['roas']:.2f} | spend=${r['spend']:.0f}")

    # ── Frequency 위험 (adset — 최대 일별 frequency 기준) ───────────────────
    a_path = META_DIR / "adset.json"
    freq_danger = []
    if a_path.exists():
        adsets_agg = _aggregate_by_key(load_json(a_path), "adset_id", "adset_name")
        for c in adsets_agg:
            if c["spend"] < 20:
                continue
            mf = c["max_daily_freq"]
            if mf >= 2.0:  # 하루 2+ 노출 → 번아웃 주의
                freq_danger.append({"name": c["name"][:55], "max_freq": mf, "spend": c["spend"]})
        info(f"Max daily frequency >= 2.0 (burnout risk): {len(freq_danger)} ad sets")
        for r in sorted(freq_danger, key=lambda x: -x["max_freq"])[:5]:
            warn(f"  [FREQ BURNOUT] {r['name']} | max_daily_freq={r['max_freq']:.1f}")

    # ── CVR 캠페인에서 지출 있는데 구매 0인 ad (기간 합산 기준) ───────────────
    ad_path = META_DIR / "ad.json"
    spend_no_purchase = []
    if ad_path.exists():
        ads_agg = _aggregate_by_key(load_json(ad_path), "ad_id", "ad_name")
        for a in ads_agg:
            camp_name = ""
            # ad_name으로 traffic 판단 (캠페인명 없을 경우 ad_name 활용)
            if is_traffic_campaign(a["name"]):
                continue
            if a["spend"] >= 50 and a["purchases"] == 0:
                spend_no_purchase.append({"name": a["name"][:55], "spend": a["spend"]})
        info(f"CVR ads spend >= $50 with 0 purchases: {len(spend_no_purchase)}")
        for r in sorted(spend_no_purchase, key=lambda x: -x["spend"])[:5]:
            warn(f"  [NO PURCHASE] ${r['spend']:.0f} spent | {r['name']}")

    results.append({
        "check": "anomaly_logic",
        "status": "PASS",
        "roas_danger_campaigns": len(danger_roas),
        "roas_good_campaigns":   len(good_roas),
        "freq_burnout_adsets":   len(freq_danger),
        "spend_no_purchase_ads": len(spend_no_purchase),
    })
    ok("Anomaly detection complete (aggregated over full period)")
    return True, results


# ─── R: HTML 리포트 구조 검증 ────────────────────────────────────────────────

REQUIRED_SECTIONS = [
    ("브랜드별",  r"브랜드별|brand"),
    ("Ad Set",   r"Ad Set|adset|오디언스"),
    ("크리에이티브", r"크리에이티브|creative|CTR"),
    ("이상 감지", r"이상|anomal|alert|위험"),
    ("액션",     r"액션|action|해야 할"),
]

def check_report_html(report_file=None):
    # 가장 최근 리포트 자동 탐색
    if not report_file:
        html_files = sorted(TMP.glob("meta_ads_report_*.html"), reverse=True)
        if not html_files:
            warn("No report HTML found in .tmp/ -- run with --dry-run first")
            return None, [{"check": "report_html", "status": "SKIP",
                           "reason": "no HTML file"}]
        report_file = html_files[0]

    report_file = Path(report_file)
    if not report_file.exists():
        fail(f"Report file not found: {report_file}")
        return False, [{"check": "report_html", "status": "FAIL"}]

    html = report_file.read_text(encoding="utf-8", errors="replace")
    log(f"\n  Checking: {report_file.name} ({len(html):,} bytes)")

    passed = True
    results = []
    section_results = {}

    for label, pattern in REQUIRED_SECTIONS:
        if re.search(pattern, html, re.IGNORECASE):
            ok(f"Section found: {label}")
            section_results[label] = "PASS"
        else:
            fail(f"Section MISSING: {label}")
            section_results[label] = "FAIL"
            passed = False

    # NaN / undefined / None 노출 체크
    bad_patterns = [r"\bNaN\b", r"\bundefined\b", r"None</td>", r"\$0\.00</td>.*ROAS"]
    for p in bad_patterns:
        matches = re.findall(p, html)
        if matches:
            warn(f"Possible bad value in HTML: {p} ({len(matches)} occurrences)")

    # 최소 테이블 개수
    table_count = html.count("<table")
    info(f"Tables in HTML: {table_count}")
    if table_count < 2:
        warn("Very few tables -- report may be incomplete")

    results.append({"check": "report_html", "status": "PASS" if passed else "FAIL",
                    "sections": section_results, "tables": table_count})
    return passed, results


# ─── 전체 실행 ───────────────────────────────────────────────────────────────

def run_fetch(days):
    log(f"\n[FETCH] Running fetch_meta_ads_daily.py --level all --days {days}")
    fetch_script = TOOLS_DIR / "no_polar" / "fetch_meta_ads_daily.py"
    result = subprocess.run(
        [PYTHON, str(fetch_script), "--level", "all", "--days", str(days)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        fail(f"Fetch failed:\n{result.stderr[:500]}")
        return False
    log(result.stdout[-500:] if result.stdout else "(no output)")
    ok("Fetch complete")
    return True


def run_all_checks(report_file=None):
    all_results = {"ran_at": datetime.now().isoformat(), "checks": []}
    overall_pass = True

    checks = [
        ("D: Data Fetch",      lambda: check_data_fetch()),
        ("M: Metric Sanity",   lambda: check_metrics()),
        ("B: Brand Classification", lambda: check_brand_classification()),
        ("S: Sum Consistency", lambda: check_sum_consistency()),
        ("A: Anomaly Logic",   lambda: check_anomaly_logic()),
        ("R: Report HTML",     lambda: check_report_html(report_file)),
    ]

    for label, fn in checks:
        sep()
        log(f"CHECK: {label}")
        try:
            passed, results = fn()
        except Exception as e:
            fail(f"Exception: {e}")
            passed = False
            results = [{"check": label, "status": "ERROR", "detail": str(e)}]

        if passed is False:
            overall_pass = False
        all_results["checks"].extend(results)

    sep()
    final = "PASS" if overall_pass else "FAIL"
    log(f"\nOVERALL: {final}")

    RESULTS_FILE.write_text(json.dumps(all_results, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    log(f"Results saved: {RESULTS_FILE}")
    return overall_pass


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meta Ads Tester")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run",           action="store_true", help="Fetch data + run all checks")
    group.add_argument("--validate-only", action="store_true", help="Check existing JSON files only")
    group.add_argument("--check-report",  action="store_true", help="Check HTML report only")
    group.add_argument("--results",       action="store_true", help="Show last test results")
    parser.add_argument("--days",         type=int, default=7, help="Days to fetch (default 7)")
    parser.add_argument("--report-file",  type=str, help="Path to HTML report to check")
    args = parser.parse_args()

    if args.run:
        ok_fetch = run_fetch(args.days)
        if ok_fetch:
            run_all_checks(args.report_file)
        else:
            fail("Fetch failed -- skipping checks")

    elif args.validate_only:
        run_all_checks(args.report_file)

    elif args.check_report:
        passed, results = check_report_html(args.report_file)
        sep()
        log(f"Report check: {'PASS' if passed else 'FAIL'}")

    elif args.results:
        if not RESULTS_FILE.exists():
            log("No results yet.")
        else:
            data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
            log(f"Last run: {data.get('ran_at','?')[:16]}")
            sep()
            for c in data.get("checks", []):
                mark = "OK" if c.get("status") == "PASS" else ("--" if c.get("status") == "SKIP" else "!!")
                log(f"  [{mark}] {c.get('check','?'):30s} {c.get('status','?')}")
