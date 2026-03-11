"""
Google Ads Tester -- 데이터 정확성 & 리포트 품질 검증
=======================================================
Google Ads 일간 분석 플로우의 각 단계를 자동 검증한다.

예상 payload 형식: .tmp/gads_payload_YYYYMMDD.json
예상 report 형식: .tmp/gads_report_YYYYMMDD.html

Usage:
    python tools/google_ads_tester.py --validate-only
    python tools/google_ads_tester.py --check-report
    python tools/google_ads_tester.py --results

Checks:
    [D] Payload Integrity   - JSON 구조, 필수 키, 날짜
    [M] Metric Sanity       - ROAS/CTR/CPC/PMAX ROAS 범위
    [B] Brand Coverage      - 브랜드별 데이터 완전성
    [T] Campaign Type       - Search / Shopping / PMax 구분 정상 여부
    [A] Anomaly Logic       - 위험 캠페인/Ad Group 리스트업
    [R] Report HTML         - 섹션 존재, NaN 미표시
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
TMP = ROOT / ".tmp"
RESULTS_FILE = TMP / "gads_test_results.json"

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


# ─── payload 탐색 ────────────────────────────────────────────────────────────

def find_latest_payload():
    files = sorted(TMP.glob("gads_payload_*.json"), reverse=True)
    return files[0] if files else None

def find_latest_report():
    files = sorted(TMP.glob("gads_report_*.html"), reverse=True)
    return files[0] if files else None


# ─── D: Payload 구조 검증 ─────────────────────────────────────────────────

# run_google_ads_daily.py 가 생성할 것으로 예상되는 payload 키
REQUIRED_KEYS = [
    "analysis_date", "yesterday", "summary",
    "brand_breakdown", "campaigns_30d", "campaigns_7d",
    "anomalies_detected",
]

SUMMARY_PERIODS = ["yesterday", "7d", "30d"]
SUMMARY_METRICS = ["spend", "conversions_value", "roas", "ctr", "cpc", "impressions", "clicks"]

def check_payload_integrity():
    path = find_latest_payload()
    if not path:
        fail("No gads_payload_*.json found in .tmp/ -- run_google_ads_daily.py 먼저 실행")
        return False, [{"check": "payload_integrity", "status": "FAIL", "detail": "no file"}]

    log(f"\n  Loading: {path.name}")
    d = json.loads(path.read_text(encoding="utf-8"))
    results = []
    passed = True

    analysis_date = d.get("analysis_date", "?")
    info(f"Analysis date: {analysis_date}")

    missing_keys = [k for k in REQUIRED_KEYS if k not in d]
    if missing_keys:
        fail(f"Missing required keys: {missing_keys}")
        passed = False
    else:
        ok("All required top-level keys present")

    summary = d.get("summary", {})
    for period in SUMMARY_PERIODS:
        if period not in summary:
            warn(f"summary missing period: {period}")
        else:
            p = summary[period]
            missing_m = [m for m in SUMMARY_METRICS if m not in p]
            if missing_m:
                warn(f"summary.{period} missing: {missing_m}")
            else:
                ok(f"summary.{period} complete")

    results.append({"check": "payload_integrity", "status": "PASS" if passed else "FAIL",
                    "analysis_date": analysis_date})
    return passed, results


# ─── M: 지표 Sanity 검사 ─────────────────────────────────────────────────

# Google Ads (Shopping + Search) 업계 기준
GADS_THRESHOLDS = {
    "roas":  (0, 200),   # 0~200 정상 (> 200이면 집계 오류 의심)
    "ctr":   (0, 30),    # 0%~30% (Search CTR 10%+ possible for branded)
    "cpc":   (0, 100),   # $0~$100
}

GADS_DANGER = {
    "roas": 2.0,   # < 2.0 위험 (Google CPC가 Meta보다 높아서 ROAS 목표도 높음)
    "ctr":  0.5,   # < 0.5% Search CTR 위험 (Shopping은 0.2%+면 OK)
}

def check_metrics_sanity():
    path = find_latest_payload()
    if not path:
        return None, [{"check": "metrics_sanity", "status": "SKIP"}]

    d = json.loads(path.read_text(encoding="utf-8"))
    summary = d.get("summary", {})
    passed = True
    results = []
    errors = []

    log("\n  Checking portfolio summary metrics:")

    for period in SUMMARY_PERIODS:
        p = summary.get(period, {})
        spend = p.get("spend", 0)
        if spend == 0:
            info(f"  {period}: no spend")
            continue

        roas  = p.get("roas", 0)
        ctr   = p.get("ctr", 0)
        cpc   = p.get("cpc", 0)
        rev   = p.get("conversions_value", 0)
        clicks = p.get("clicks", 0)
        impr   = p.get("impressions", 0)

        # ROAS cross-check: rev / spend
        if spend > 0:
            calc_roas = round(rev / spend, 2)
            if roas > 0 and abs(calc_roas - roas) / max(roas, 0.01) > 0.05:
                warn(f"  {period}: reported ROAS={roas:.2f} but calc={calc_roas:.2f} (5%+ diff)")
            else:
                ok(f"  {period}: ROAS cross-check OK ({roas:.2f})")

        # CTR cross-check: clicks / impressions * 100
        if impr > 0 and clicks > 0:
            calc_ctr = round(clicks / impr * 100, 2)
            if ctr > 0 and abs(calc_ctr - ctr) / max(ctr, 0.01) > 0.05:
                warn(f"  {period}: reported CTR={ctr:.2f}% but calc={calc_ctr:.2f}%")

        for metric, (lo, hi) in GADS_THRESHOLDS.items():
            val = p.get(metric, 0)
            if not (lo <= val <= hi):
                fail(f"  {period}: {metric}={val} out of valid range [{lo}, {hi}]")
                errors.append(f"{period}.{metric}={val}")
                passed = False

        danger_flag = ""
        if roas > 0 and roas < GADS_DANGER["roas"]:
            danger_flag = " [!DANGER ROAS]"
        info(f"  [{period}] spend=${spend:,.0f} | ROAS={roas:.2f} | CTR={ctr:.2f}%{danger_flag}")

    # Brand-level
    log("\n  Brand-level ROAS (30d):")
    for b in d.get("brand_breakdown", []):
        brand  = b.get("brand", "?")
        roas30 = b.get("roas_30d", 0)
        spend30 = b.get("spend_30d", 0)
        if spend30 < 50:
            continue
        symbol = "[GOOD]" if roas30 >= 3.0 else ("[WARN]" if roas30 >= 2.0 else "[DANGER]")
        log(f"    {symbol} {brand:20s} | ROAS={roas30:.2f} | spend=${spend30:,.0f}")

    if not errors:
        ok("All portfolio metrics within valid ranges")
    results.append({"check": "metrics_sanity", "status": "PASS" if passed else "FAIL",
                    "errors": errors})
    return passed, results


# ─── B: 브랜드 커버리지 ─────────────────────────────────────────────────────

EXPECTED_BRANDS = ["Grosmimi", "CHA&MOM", "Alpremio"]

def check_brand_coverage():
    path = find_latest_payload()
    if not path:
        return None, [{"check": "brand_coverage", "status": "SKIP"}]

    d = json.loads(path.read_text(encoding="utf-8"))
    bb = d.get("brand_breakdown", [])

    if isinstance(bb, list):
        brands_found = [b.get("brand", "") for b in bb if b.get("spend_30d", 0) > 50]
    elif isinstance(bb, dict):
        brands_found = [k for k, v in bb.items() if (v.get("spend_30d", 0) if isinstance(v, dict) else 0) > 50]
    else:
        brands_found = []

    log(f"\n  Active brands (30d spend > $50): {brands_found}")

    missing = [b for b in EXPECTED_BRANDS if b not in brands_found]
    if missing:
        warn(f"Expected brands not in report: {missing}")
        return True, [{"check": "brand_coverage", "status": "WARN", "missing": missing}]
    else:
        ok("All expected brands covered")
        return True, [{"check": "brand_coverage", "status": "PASS"}]


# ─── T: 캠페인 타입 구분 ─────────────────────────────────────────────────────

# Google Ads는 캠페인 타입이 중요: Search / Shopping / PMax
CAMPAIGN_TYPE_KEYWORDS = {
    "Search":   ["search", "dsa", "branded", "keyword"],
    "Shopping": ["shopping", "pla"],
    "PMax":     ["pmax", "performance max", "p-max"],
}

def check_campaign_types():
    path = find_latest_payload()
    if not path:
        return None, [{"check": "campaign_types", "status": "SKIP"}]

    d = json.loads(path.read_text(encoding="utf-8"))
    c30 = d.get("campaigns_30d", {})
    all_campaigns = []

    if isinstance(c30, dict):
        for section in ("top5", "bottom5", "zero_sales"):
            all_campaigns.extend(c30.get(section, []))
    elif isinstance(c30, list):
        all_campaigns = c30

    if not all_campaigns:
        warn("No campaigns found to classify")
        return True, [{"check": "campaign_types", "status": "SKIP"}]

    type_counts = {"Search": 0, "Shopping": 0, "PMax": 0, "Other": 0}
    for c in all_campaigns:
        name = (c.get("campaign_name") or c.get("campaign", "")).lower()
        typed = False
        for t, kws in CAMPAIGN_TYPE_KEYWORDS.items():
            if any(k in name for k in kws):
                type_counts[t] += 1
                typed = True
                break
        if not typed:
            type_counts["Other"] += 1

    log("\n  Campaign type distribution:")
    for t, cnt in type_counts.items():
        if cnt > 0:
            log(f"    {t:10s}: {cnt}")

    if type_counts["Other"] > len(all_campaigns) * 0.5:
        warn(f"50%+ campaigns untyped -- consider adding campaign_type field to payload")
        return True, [{"check": "campaign_types", "status": "WARN", "type_counts": type_counts}]
    else:
        ok("Campaign types classifiable")
        return True, [{"check": "campaign_types", "status": "PASS", "type_counts": type_counts}]


# ─── A: 이상 감지 로직 ──────────────────────────────────────────────────────

def check_anomaly_logic():
    path = find_latest_payload()
    if not path:
        return None, [{"check": "anomaly_logic", "status": "SKIP"}]

    d = json.loads(path.read_text(encoding="utf-8"))
    anomalies = d.get("anomalies_detected", [])
    c30 = d.get("campaigns_30d", {})

    log(f"\n  Anomalies: {len(anomalies)}")
    for a in anomalies[:5]:
        warn(f"  {str(a)[:100]}")

    # Zero-sales 캠페인 (spend > 0)
    zero_sales = c30.get("zero_sales", []) if isinstance(c30, dict) else []
    real_zero = [c for c in zero_sales if (c.get("cost", 0) > 0) or (c.get("spend", 0) > 0)]
    if real_zero:
        warn(f"  {len(real_zero)} campaigns with spend but 0 conversions")
        for c in real_zero[:3]:
            spend = c.get("cost", 0) or c.get("spend", 0)
            warn(f"    ${spend:.0f} spent | {(c.get('campaign_name') or c.get('campaign','?'))[:55]}")

    # 7d vs 30d 방향성
    s7  = d.get("summary", {}).get("7d", {})
    s30 = d.get("summary", {}).get("30d", {})
    r7, r30 = s7.get("roas", 0), s30.get("roas", 0)
    if r7 > 0 and r30 > 0:
        delta = (r7 - r30) / r30 * 100
        if delta < -20:
            warn(f"7d ROAS ({r7:.2f}) vs 30d ({r30:.2f}) -- trend deteriorating ({delta:+.1f}%)")
        elif delta > 20:
            ok(f"7d ROAS ({r7:.2f}) vs 30d ({r30:.2f}) -- trend improving ({delta:+.1f}%)")
        else:
            ok(f"ROAS trend stable (7d={r7:.2f}, 30d={r30:.2f})")

    ok("Anomaly check complete")
    return True, [{"check": "anomaly_logic", "status": "PASS",
                   "anomaly_count": len(anomalies),
                   "zero_sales_count": len(real_zero)}]


# ─── R: HTML 리포트 구조 ─────────────────────────────────────────────────────

GADS_REQUIRED_SECTIONS = [
    ("브랜드별",    r"브랜드별|brand.*성과|brand performance"),
    ("캠페인",      r"캠페인|campaign"),
    ("이상 감지",   r"이상|anomal|alert|위험|급락"),
    ("액션",        r"액션|action|해야 할|개선"),
]

def check_report_html(report_file=None):
    if not report_file:
        report_file = find_latest_report()
    if not report_file:
        warn("No gads_report_*.html found -- run_google_ads_daily.py 먼저 실행")
        return None, [{"check": "report_html", "status": "SKIP"}]

    report_file = Path(report_file)
    html = report_file.read_text(encoding="utf-8", errors="replace")
    log(f"\n  Checking: {report_file.name} ({len(html):,} bytes)")

    passed = True
    section_results = {}
    for label, pattern in GADS_REQUIRED_SECTIONS:
        if re.search(pattern, html, re.IGNORECASE):
            ok(f"Section found: {label}")
            section_results[label] = "PASS"
        else:
            fail(f"Section MISSING: {label}")
            section_results[label] = "FAIL"
            passed = False

    for p in [r"\bNaN\b", r"\bundefined\b", r"None</td>"]:
        if re.search(p, html):
            warn(f"Possible bad value: {p}")

    table_count = html.count("<table")
    info(f"Tables in HTML: {table_count}")

    return passed, [{"check": "report_html",
                     "status": "PASS" if passed else "FAIL",
                     "sections": section_results,
                     "tables": table_count}]


# ─── 전체 실행 ───────────────────────────────────────────────────────────────

def run_all_checks(report_file=None):
    all_results = {"ran_at": datetime.now().isoformat(), "checks": []}
    overall_pass = True

    checks = [
        ("D: Payload Integrity", check_payload_integrity),
        ("M: Metric Sanity",     check_metrics_sanity),
        ("B: Brand Coverage",    check_brand_coverage),
        ("T: Campaign Types",    check_campaign_types),
        ("A: Anomaly Logic",     check_anomaly_logic),
        ("R: Report HTML",       lambda: check_report_html(report_file)),
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
    RESULTS_FILE.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Results saved: {RESULTS_FILE}")
    return overall_pass


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Ads Tester")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate-only", action="store_true")
    group.add_argument("--check-report",  action="store_true")
    group.add_argument("--results",       action="store_true")
    parser.add_argument("--report-file",  type=str)
    args = parser.parse_args()

    if args.validate_only:
        run_all_checks(args.report_file)
    elif args.check_report:
        passed, _ = check_report_html(args.report_file)
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
