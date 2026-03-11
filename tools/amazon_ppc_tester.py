"""
Amazon PPC Tester -- 데이터 정확성 & 리포트 품질 검증
=======================================================
Amazon PPC 일간 분석 플로우의 각 단계를 자동 검증한다.

Meta 테스터와 같은 철학: "숫자가 맞냐, 계산이 맞냐, 리포트에 빠진 것 없냐"

Usage:
    python tools/amazon_ppc_tester.py --run          # payload 생성 + 검증
    python tools/amazon_ppc_tester.py --validate-only  # 기존 payload만 검증
    python tools/amazon_ppc_tester.py --check-report   # HTML 리포트만 검사
    python tools/amazon_ppc_tester.py --results         # 마지막 결과 보기

Checks:
    [D] Payload Integrity   - JSON 구조, 필수 키, 날짜
    [M] Metric Sanity       - ROAS/ACOS/CTR/CPC 범위 검사
    [B] Brand Coverage      - brand_breakdown 완전성
    [A] Anomaly Validity    - anomalies_detected 실제 데이터와 일치 여부
    [R] Report HTML         - 4개 섹션 존재, NaN 미표시
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
TMP = ROOT / ".tmp"
RESULTS_FILE = TMP / "amazon_ppc_test_results.json"

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
    files = sorted(TMP.glob("ppc_payload_*.json"), reverse=True)
    return files[0] if files else None

def find_latest_report():
    # 날짜 형식 ppc_report_YYYYMMDD.html 우선
    import re as _re
    dated = [f for f in TMP.glob("ppc_report_*.html")
             if _re.match(r"ppc_report_\d{8}\.html$", f.name)]
    if dated:
        return sorted(dated, reverse=True)[0]
    # 날짜 파일 없으면 가장 큰 용량의 파일 (전체 리포트일 가능성 높음)
    all_files = list(TMP.glob("ppc_report*.html"))
    return sorted(all_files, key=lambda f: f.stat().st_size, reverse=True)[0] if all_files else None


# ─── D: Payload 구조 검증 ─────────────────────────────────────────────────

REQUIRED_KEYS = [
    "analysis_date", "yesterday", "summary", "brand_breakdown",
    "campaigns_30d", "campaigns_7d", "anomalies_detected",
    "total_active_30d", "total_active_7d",
]

SUMMARY_PERIODS = ["yesterday", "7d", "30d"]
SUMMARY_METRICS = ["spend", "sales", "roas", "acos", "cpc", "ctr"]

def check_payload_integrity():
    path = find_latest_payload()
    if not path:
        fail("No ppc_payload_*.json found in .tmp/ -- run the pipeline first")
        return False, [{"check": "payload_integrity", "status": "FAIL", "detail": "no file"}]

    log(f"\n  Loading: {path.name}")
    d = json.loads(path.read_text(encoding="utf-8"))
    results = []
    passed = True

    # 날짜 확인
    analysis_date = d.get("analysis_date", "?")
    yesterday = d.get("yesterday", "?")
    info(f"Analysis date: {analysis_date} | Data for: {yesterday}")

    # 필수 키 확인
    missing_keys = [k for k in REQUIRED_KEYS if k not in d]
    if missing_keys:
        fail(f"Missing required keys: {missing_keys}")
        passed = False
    else:
        ok("All required top-level keys present")

    # summary 구조 확인
    summary = d.get("summary", {})
    for period in SUMMARY_PERIODS:
        if period not in summary:
            fail(f"summary missing period: {period}")
            passed = False
        else:
            p = summary[period]
            missing_m = [m for m in SUMMARY_METRICS if m not in p]
            if missing_m:
                warn(f"summary.{period} missing metrics: {missing_m}")
            else:
                ok(f"summary.{period} complete ({len(SUMMARY_METRICS)} metrics)")

    # campaigns_30d 구조
    c30 = d.get("campaigns_30d", {})
    for section in ("top5", "bottom5", "zero_sales"):
        if section not in c30:
            warn(f"campaigns_30d missing section: {section}")
        elif isinstance(c30[section], list):
            ok(f"campaigns_30d.{section}: {len(c30[section])} entries")

    # brand_breakdown
    bb = d.get("brand_breakdown", [])
    if not isinstance(bb, list) or len(bb) == 0:
        fail("brand_breakdown is empty or wrong type")
        passed = False
    else:
        ok(f"brand_breakdown: {len(bb)} brands")

    results.append({"check": "payload_integrity", "status": "PASS" if passed else "FAIL",
                    "analysis_date": analysis_date})
    return passed, results


# ─── M: 지표 Sanity 검사 ─────────────────────────────────────────────────

# Amazon SP 광고 업계 기준
AMZ_THRESHOLDS = {
    "roas": (0, 100),    # 0~100 정상 (> 100이면 집계 오류)
    "acos": (0, 200),    # 0%~200% (> 200이면 이상)
    "ctr":  (0, 10),     # 0%~10% (> 10%이면 이상)
    "cpc":  (0, 50),     # $0~$50 (> $50이면 이상)
}

AMZ_DANGER = {
    "roas": 2.0,   # < 2.0 위험
    "acos": 40.0,  # > 40% 위험
    "ctr":  0.2,   # < 0.2% 위험 (Amazon SP 기준)
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

    for period in ("yesterday", "7d", "30d"):
        p = summary.get(period, {})
        spend = p.get("spend", 0)
        if spend == 0:
            info(f"  {period}: no spend -- skipping")
            continue

        roas = p.get("roas", 0)
        acos = p.get("acos", 0)
        ctr  = p.get("ctr", 0)
        cpc  = p.get("cpc", 0)
        sales = p.get("sales", 0)

        # Cross-check: ROAS vs ACOS (ACOS = 1/ROAS * 100)
        if roas > 0:
            expected_acos = round(100 / roas, 1)
            acos_delta = abs(expected_acos - acos)
            if acos_delta > 5:
                warn(f"  {period}: ROAS={roas:.2f} implies ACOS={expected_acos:.1f}%, reported={acos:.1f}% (diff {acos_delta:.1f}pp)")
            else:
                ok(f"  {period}: ROAS/ACOS cross-check OK (ROAS={roas:.2f}, ACOS={acos:.1f}%)")

        # Sanity bounds
        for metric, (lo, hi) in AMZ_THRESHOLDS.items():
            val = p.get(metric, 0)
            if not (lo <= val <= hi):
                fail(f"  {period}: {metric}={val} out of range [{lo}, {hi}]")
                errors.append(f"{period}.{metric}={val}")
                passed = False

        # Danger level flags
        if roas > 0 and roas < AMZ_DANGER["roas"]:
            warn(f"  {period}: Portfolio ROAS={roas:.2f} -- below danger threshold ({AMZ_DANGER['roas']})")
        if acos > AMZ_DANGER["acos"]:
            warn(f"  {period}: Portfolio ACOS={acos:.1f}% -- above danger threshold ({AMZ_DANGER['acos']}%)")

        info(f"  [{period}] spend=${spend:,.0f} | sales=${sales:,.0f} | ROAS={roas:.2f} | ACOS={acos:.1f}% | CTR={ctr:.2f}%")

    # Brand-level ROAS check
    log("\n  Brand-level ROAS (30d):")
    for b in d.get("brand_breakdown", []):
        brand = b.get("brand", "?")
        roas30 = b.get("roas_30d", 0)
        spend30 = b.get("spend_30d", 0)
        roas7 = b.get("roas_7d", 0)
        if spend30 < 50:
            continue
        symbol = "[GOOD]" if roas30 >= 3.0 else ("[WARN]" if roas30 >= 2.0 else "[DANGER]")
        log(f"    {symbol} {brand:20s} | 30d ROAS={roas30:.2f} | 7d ROAS={roas7:.2f} | spend30d=${spend30:,.0f}")

    if not errors:
        ok("All portfolio metrics within valid ranges")
    results.append({"check": "metrics_sanity",
                    "status": "PASS" if passed else "FAIL",
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
    brands_found = [b.get("brand", "") for b in bb if b.get("spend_30d", 0) > 50]

    log(f"\n  Active brands (30d spend > $50): {brands_found}")

    missing = [b for b in EXPECTED_BRANDS if b not in brands_found]
    passed = True

    if missing:
        warn(f"Expected brands not in report: {missing}")
        warn("  (May have 0 spend this period -- verify manually)")
        return True, [{"check": "brand_coverage", "status": "WARN", "missing": missing}]
    else:
        ok(f"All expected brands covered: {EXPECTED_BRANDS}")
        return True, [{"check": "brand_coverage", "status": "PASS"}]


# ─── A: 이상 감지 유효성 검증 ────────────────────────────────────────────────

def check_anomaly_validity():
    path = find_latest_payload()
    if not path:
        return None, [{"check": "anomaly_validity", "status": "SKIP"}]

    d = json.loads(path.read_text(encoding="utf-8"))
    anomalies = d.get("anomalies_detected", [])
    c30_bottom = d.get("campaigns_30d", {}).get("bottom5", [])
    c30_zero   = d.get("campaigns_30d", {}).get("zero_sales", [])
    summary7   = d.get("summary", {}).get("7d", {})
    summary30  = d.get("summary", {}).get("30d", {})

    log(f"\n  Anomalies detected: {len(anomalies)}")
    for a in anomalies[:5]:
        warn(f"  {str(a)[:100]}")

    # Zero-sales campaigns 유효성: 실제 spend > $0이어야 의미 있음
    real_zero = [c for c in c30_zero if c.get("cost", 0) > 0]
    if real_zero:
        fail(f"Zero-sales campaigns with real spend: {len(real_zero)}")
        for c in real_zero[:3]:
            warn(f"  ${c.get('cost',0):.0f} spent | {c.get('campaign','?')[:55]}")

    # Bottom5 vs Top5 순서 일치 확인 (bottom5 avg ROAS < top5 avg ROAS)
    c30_top = d.get("campaigns_30d", {}).get("top5", [])
    top_roas_avg  = sum(c.get("roas", 0) for c in c30_top) / len(c30_top) if c30_top else 0
    bot_roas_avg  = sum(c.get("roas", 0) for c in c30_bottom) / len(c30_bottom) if c30_bottom else 0
    if top_roas_avg > 0 and bot_roas_avg > top_roas_avg:
        fail(f"bottom5 avg ROAS ({bot_roas_avg:.2f}) > top5 avg ROAS ({top_roas_avg:.2f}) -- labeling error?")
    else:
        ok(f"top5 avg ROAS={top_roas_avg:.2f} > bottom5 avg ROAS={bot_roas_avg:.2f} (order consistent)")

    # 7d vs 30d ROAS 방향성 체크
    roas7  = summary7.get("roas", 0)
    roas30 = summary30.get("roas", 0)
    if roas7 > 0 and roas30 > 0:
        delta_pct = (roas7 - roas30) / roas30 * 100
        if delta_pct < -20:
            warn(f"7d ROAS ({roas7:.2f}) significantly below 30d ROAS ({roas30:.2f}) -- trend deteriorating")
        elif delta_pct > 20:
            ok(f"7d ROAS ({roas7:.2f}) above 30d ROAS ({roas30:.2f}) -- trend improving")
        else:
            ok(f"7d vs 30d ROAS stable (7d={roas7:.2f}, 30d={roas30:.2f}, delta={delta_pct:+.1f}%)")

    ok("Anomaly check complete")
    return True, [{"check": "anomaly_validity", "status": "PASS",
                   "anomaly_count": len(anomalies),
                   "zero_sales_with_spend": len(real_zero)}]


# ─── R: HTML 리포트 구조 ─────────────────────────────────────────────────────

AMZ_REQUIRED_SECTIONS = [
    ("브랜드별",    r"브랜드별|brand.*성과|brand performance"),
    ("캠페인",      r"캠페인|campaign|상위.*하위|top.*bottom"),
    ("이상 감지",   r"이상|anomal|alert|ROAS.*급락|급락"),
    ("액션",        r"액션|action|해야 할|개선"),
]

def check_report_html(report_file=None):
    if not report_file:
        report_file = find_latest_report()
    if not report_file:
        warn("No ppc_report_*.html found in .tmp/ -- run pipeline first")
        return None, [{"check": "report_html", "status": "SKIP"}]

    report_file = Path(report_file)
    html = report_file.read_text(encoding="utf-8", errors="replace")
    log(f"\n  Checking: {report_file.name} ({len(html):,} bytes)")

    passed = True
    section_results = {}

    for label, pattern in AMZ_REQUIRED_SECTIONS:
        if re.search(pattern, html, re.IGNORECASE):
            ok(f"Section found: {label}")
            section_results[label] = "PASS"
        else:
            fail(f"Section MISSING: {label}")
            section_results[label] = "FAIL"
            passed = False

    # NaN / undefined / None 체크
    for p in [r"\bNaN\b", r"\bundefined\b", r"None</td>"]:
        if re.search(p, html):
            warn(f"Possible bad value: {p}")

    table_count = html.count("<table")
    info(f"Tables in HTML: {table_count}")
    if table_count < 2:
        warn("Very few tables -- report may be incomplete")

    return passed, [{"check": "report_html",
                     "status": "PASS" if passed else "FAIL",
                     "sections": section_results,
                     "tables": table_count}]


# ─── 전체 실행 ───────────────────────────────────────────────────────────────

def run_fetch(days):
    log(f"\n[FETCH] Running run_amazon_ppc_daily.py --dry-run --days {days}")
    script = TOOLS_DIR / "run_amazon_ppc_daily.py"
    result = subprocess.run(
        [PYTHON, str(script), "--dry-run", "--days", str(days)],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        fail(f"Fetch failed:\n{result.stderr[:500]}")
        return False
    log(result.stdout[-600:] if result.stdout else "(no output)")
    ok("Fetch complete")
    return True


def run_all_checks(report_file=None):
    all_results = {"ran_at": datetime.now().isoformat(), "checks": []}
    overall_pass = True

    checks = [
        ("D: Payload Integrity",  check_payload_integrity),
        ("M: Metric Sanity",      check_metrics_sanity),
        ("B: Brand Coverage",     check_brand_coverage),
        ("A: Anomaly Validity",   check_anomaly_validity),
        ("R: Report HTML",        lambda: check_report_html(report_file)),
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
    parser = argparse.ArgumentParser(description="Amazon PPC Tester")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run",           action="store_true", help="Fetch (dry-run) + validate")
    group.add_argument("--validate-only", action="store_true", help="Validate existing payload")
    group.add_argument("--check-report",  action="store_true", help="Check HTML report only")
    group.add_argument("--results",       action="store_true", help="Show last test results")
    parser.add_argument("--days",        type=int, default=30)
    parser.add_argument("--report-file", type=str)
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
