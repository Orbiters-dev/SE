"""
run_communicator.py - ORBI Communicator

12시간 단위 통합 상태 이메일 (PST 0:00 / PST 12:00)

이메일 구성:
  1. 태스크 업데이트  - 실행된 워크플로우별 섬머리 + 관련 링크
     └─ Syncly: 탭별 row 수 (US/JP D+60 Tracker, Posts Master, SNS 탭)
  2. 데이터 수집 현황 - 9채널 freshness (간단)
  3. 다음 예정 작업  - 향후 12시간 스케줄
  4. 알림            - 연속 실패 에스컬레이션 ("쪼기")

Usage:
    python tools/run_communicator.py
    python tools/run_communicator.py --dry-run
    python tools/run_communicator.py --preview
    python tools/run_communicator.py --cc someone@email.com
    python tools/run_communicator.py --reset-state
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

# ── 설정 ──────────────────────────────────────────────────────────────
PST = timezone(timedelta(hours=-8))
NOW_PST = datetime.now(PST)
NOW_UTC = datetime.now(timezone.utc)

ORBITOOLS_BASE = os.getenv("ORBITOOLS_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

GH_TOKEN = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN", "")
GH_REPO  = os.getenv("GITHUB_REPOSITORY", "")

RECIPIENT = os.getenv("COMMUNICATOR_RECIPIENT") or os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")
CC_DEFAULT = os.getenv("COMMUNICATOR_CC", "mj.lee@orbiters.co.kr")
SENDER    = os.getenv("GMAIL_SENDER", "hello@zezebaebae.com")

SA_PATH   = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH   = PROJECT_ROOT / ".tmp" / "communicator_state.json"

ESCALATE_THRESHOLD = 2

# ── 채널 메타데이터 ────────────────────────────────────────────────────
CHANNEL_META = {
    "shopify_orders_daily": {"label": "Shopify Orders",   "max_age_h": 14},
    "amazon_sales_daily":   {"label": "Amazon Sales",     "max_age_h": 14},
    "amazon_ads_daily":     {"label": "Amazon Ads",       "max_age_h": 14},
    "amazon_campaigns":     {"label": "Amazon Campaigns", "max_age_h": 25},
    "meta_ads_daily":       {"label": "Meta Ads",         "max_age_h": 14},
    "meta_campaigns":       {"label": "Meta Campaigns",   "max_age_h": 25},
    "google_ads_daily":     {"label": "Google Ads",       "max_age_h": 14},
    "ga4_daily":            {"label": "GA4",              "max_age_h": 14},
    "klaviyo_daily":        {"label": "Klaviyo",          "max_age_h": 14},
}

CHANNEL_LINKS = {
    "shopify_orders_daily": "https://admin.shopify.com/store/onzenna/orders",
    "amazon_sales_daily":   "https://sellercentral.amazon.com/",
    "amazon_ads_daily":     "https://advertising.amazon.com/",
    "meta_ads_daily":       "https://business.facebook.com/",
    "google_ads_daily":     "https://ads.google.com/",
    "ga4_daily":            "https://analytics.google.com/",
    "klaviyo_daily":        "https://www.klaviyo.com/",
}

# ── 워크플로우 스케줄 ─────────────────────────────────────────────────
WORKFLOW_SCHEDULE = [
    {"file": "data_keeper.yml",     "label": "Data Keeper",  "times": ["00:00", "12:00"], "days": "매일"},
    {"file": "amazon_ppc_daily.yml","label": "Amazon PPC",   "times": ["08:00", "20:00"], "days": "매일"},
    {"file": "meta_ads_daily.yml",  "label": "Meta Ads",     "times": ["00:00", "12:00"], "days": "매일"},
    {"file": "syncly_daily.yml",    "label": "Syncly Sync",  "times": ["08:00"],          "days": "매일"},
    {"file": "kpi_weekly.yml",      "label": "KPI Weekly",   "times": ["08:00"],          "days": "월요일"},
    {"file": "communicator.yml",    "label": "Communicator", "times": ["00:00", "12:00"], "days": "매일"},
]

# ── 워크플로우별 상세 메타 (링크 + 설명) ──────────────────────────────
_gh_base = f"https://github.com/{GH_REPO}/actions" if GH_REPO else "#"
WORKFLOW_DETAILS = {
    "data_keeper.yml": {
        "emoji": "📦",
        "desc": "전채널 광고/매출 데이터 수집 (Amazon Ads·Sales, Meta, Google, GA4, Klaviyo, Shopify)",
        "links": [{"label": "orbitools API", "url": "https://orbitools.orbiters.co.kr/api/datakeeper/status/"}],
    },
    "amazon_ppc_daily.yml": {
        "emoji": "🛒",
        "desc": "Amazon PPC 캠페인 분석 리포트 생성 (ROAS, ACOS, 입찰 추천)",
        "links": [{"label": "Actions Artifacts", "url": _gh_base}],
    },
    "meta_ads_daily.yml": {
        "emoji": "📢",
        "desc": "Meta Ads 일일 퍼포먼스 분석 (캠페인/광고세트/소재 레벨)",
        "links": [
            {"label": "Meta Business", "url": "https://business.facebook.com/"},
            {"label": "Actions Artifacts", "url": _gh_base},
        ],
    },
    "polar_weekly.yml": {
        "emoji": "📊",
        "desc": "ORBI 주간 재무 모델 업데이트 (Polar Financial Model)",
        "links": [{"label": "Actions Log", "url": _gh_base}],
    },
    "communicator.yml": {
        "emoji": "📡",
        "desc": "ORBI Communicator — 이 리포트 자동 발송",
        "links": [],
    },
}

# Syncly 관련 시트 ID
SYNCLY_SRC_ID     = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"  # D+60 소스
ONZENNA_SNS_ID    = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"  # ONZENNA SNS 타겟
CHAENMOM_SNS_ID   = "16XUPd-VMoh6LEjSvupsmhkd1vEQNOTcoEhRCnPqkA_I"  # CHA&MOM SNS 타겟

SYNCLY_TABS = [
    {"sheet_id": SYNCLY_SRC_ID,   "tab": "US Posts Master",  "header_rows": 1, "label": "US Posts Master"},
    {"sheet_id": SYNCLY_SRC_ID,   "tab": "US D+60 Tracker",  "header_rows": 2, "label": "US D+60 Tracker"},
    {"sheet_id": SYNCLY_SRC_ID,   "tab": "JP Posts Master",  "header_rows": 1, "label": "JP Posts Master"},
    {"sheet_id": SYNCLY_SRC_ID,   "tab": "JP D+60 Tracker",  "header_rows": 2, "label": "JP D+60 Tracker"},
    {"sheet_id": ONZENNA_SNS_ID,  "tab": "SNS",              "header_rows": 2, "label": "ONZENNA SNS 탭"},
    {"sheet_id": CHAENMOM_SNS_ID, "tab": "SNS",              "header_rows": 2, "label": "CHA&MOM SNS 탭"},
]

SHEET_URLS = {
    SYNCLY_SRC_ID:   f"https://docs.google.com/spreadsheets/d/{SYNCLY_SRC_ID}/edit",
    ONZENNA_SNS_ID:  f"https://docs.google.com/spreadsheets/d/{ONZENNA_SNS_ID}/edit",
    CHAENMOM_SNS_ID: f"https://docs.google.com/spreadsheets/d/{CHAENMOM_SNS_ID}/edit",
}


# ── Naeiae PPC 변경 추적 ──────────────────────────────────────────────
NAEIAE_BASELINE_PATH = PROJECT_ROOT / ".tmp" / "naeiae_execution_baseline.json"


def get_naeiae_ppc_tracking_html() -> str:
    """실행된 Naeiae PPC 변경사항 + 현재 DataKeeper 성과 비교."""
    if not NAEIAE_BASELINE_PATH.exists():
        return ""
    try:
        baseline = json.loads(NAEIAE_BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""

    before  = baseline.get("before", {})
    changes = baseline.get("changes_executed", {})
    exec_date = baseline.get("executed_date", "")

    # 현재 Naeiae 7d ROAS (DataKeeper)
    current_roas_7d = current_spend_7d = current_sales_7d = current_acos_7d = None
    days_since = 0
    try:
        from datetime import date as _date, timedelta, datetime as _dt
        today = _date.today()
        cutoff_7d = (today - timedelta(days=7)).isoformat()
        r = requests.get(f"{ORBITOOLS_BASE}/query/",
                         params={"table": "amazon_ads_daily", "limit": 5000},
                         auth=(ORBITOOLS_USER, ORBITOOLS_PASS), timeout=15)
        if r.ok:
            rows = [row for row in r.json().get("rows", [])
                    if row.get("brand") == "Naeiae" and row.get("date", "") >= cutoff_7d]
            if rows:
                spend = sum(float(row.get("spend", 0) or 0) for row in rows)
                sales = sum(float(row.get("sales", 0) or 0) for row in rows)
                current_spend_7d = spend
                current_sales_7d = sales
                current_roas_7d  = round(sales / spend, 2) if spend > 0 else 0
                current_acos_7d  = round(spend / sales * 100, 1) if sales > 0 else 0
        if exec_date:
            days_since = (today - _dt.strptime(exec_date, "%Y-%m-%d").date()).days
    except Exception:
        pass

    def _delta(bv, av, higher_better=True, fmt=".2f", suf=""):
        if av is None or bv is None:
            return '<span style="color:#999">—</span>'
        pct  = ((av - bv) / bv * 100) if bv else 0
        good = (av > bv) == higher_better
        c    = "#006100" if good else "#9C0006"
        arr  = "▲" if av > bv else "▼"
        return f'<span style="color:{c};font-weight:bold">{format(av, fmt)}{suf} ({arr}{abs(pct):.1f}%)</span>'

    negatives = changes.get("negatives_added", [])
    bids      = changes.get("bid_reductions", [])
    harvested = changes.get("keywords_harvested", [])
    wasted    = changes.get("wasted_spend_14d", 0)

    neg_rows = "".join(
        f'<tr><td style="padding:3px 6px;font-size:12px">❌ {n["term"]}</td>'
        f'<td style="padding:3px 6px;font-size:11px;color:#888">{n["reason"]}</td></tr>'
        for n in negatives)
    bid_rows = "".join(
        f'<tr><td style="padding:3px 6px;font-size:12px">↓ {b["target"][:30]}</td>'
        f'<td style="padding:3px 6px;font-size:12px;color:#9C0006;font-weight:bold">{b["change"]}</td></tr>'
        for b in bids)
    hvst_rows = "".join(
        f'<tr><td style="padding:3px 6px;font-size:12px">✅ {h["term"]}</td>'
        f'<td style="padding:3px 6px;font-size:12px;color:#006100;font-weight:bold">ROAS {h["roas_14d"]}x</td></tr>'
        for h in harvested)

    if current_roas_7d is not None:
        perf_html = f"""<table width="100%" cellpadding="6" cellspacing="0" border="0"
          style="border-collapse:collapse;margin-top:10px;font-size:13px">
          <tr bgcolor="#F2F2F2">
            <th style="padding:6px 10px;text-align:left;color:#555">지표</th>
            <th style="padding:6px 10px;text-align:right;color:#555">실행 전</th>
            <th style="padding:6px 10px;text-align:right;color:#555">현재 ({days_since}일 후)</th>
            <th style="padding:6px 10px;text-align:right;color:#555">변화</th>
          </tr>
          <tr><td style="padding:6px 10px">7d ROAS</td>
              <td style="padding:6px 10px;text-align:right">{before.get('roas_7d',0):.2f}x</td>
              <td style="padding:6px 10px;text-align:right"><b>{current_roas_7d:.2f}x</b></td>
              <td style="padding:6px 10px;text-align:right">{_delta(before.get('roas_7d'), current_roas_7d, True, ".2f", "x")}</td></tr>
          <tr bgcolor="#F9F9F9">
              <td style="padding:6px 10px">7d ACOS</td>
              <td style="padding:6px 10px;text-align:right">{before.get('acos_7d',0):.1f}%</td>
              <td style="padding:6px 10px;text-align:right"><b>{current_acos_7d:.1f}%</b></td>
              <td style="padding:6px 10px;text-align:right">{_delta(before.get('acos_7d'), current_acos_7d, False, ".1f", "%")}</td></tr>
          <tr><td style="padding:6px 10px">7d Spend</td>
              <td style="padding:6px 10px;text-align:right">${before.get('spend_7d',0):.0f}</td>
              <td style="padding:6px 10px;text-align:right"><b>${current_spend_7d:.0f}</b></td>
              <td style="padding:6px 10px;text-align:right">{_delta(before.get('spend_7d'), current_spend_7d, False, ".0f", "")}</td></tr>
          <tr bgcolor="#F9F9F9">
              <td style="padding:6px 10px">7d Sales</td>
              <td style="padding:6px 10px;text-align:right">${before.get('sales_7d',0):.0f}</td>
              <td style="padding:6px 10px;text-align:right"><b>${current_sales_7d:.0f}</b></td>
              <td style="padding:6px 10px;text-align:right">{_delta(before.get('sales_7d'), current_sales_7d, True, ".0f", "")}</td></tr>
        </table>
        <p style="font-size:11px;color:#888;margin:5px 0">※ 2-3일 attribution lag 감안. 변화는 2-3일 후 더 명확해짐.</p>"""
    else:
        perf_html = '<p style="color:#999;font-size:12px;margin:8px 0">DataKeeper 조회 실패 — 다음 수집 후 표시</p>'

    return f"""
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      🛒 Naeiae PPC 변경 추적 <span style="font-size:12px;color:#888;font-weight:normal">(실행일: {exec_date})</span>
    </h2>
    <table width="100%" cellpadding="0" cellspacing="12" border="0" style="border-collapse:collapse;margin-bottom:10px">
      <tr>
        <td width="33%" valign="top">
          <b style="font-size:12px;color:#9C0006">네거티브 추가 ({len(negatives)}개, ${wasted:.0f}/14d 회수)</b>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px">{neg_rows}</table>
        </td>
        <td width="33%" valign="top">
          <b style="font-size:12px;color:#9C5700">입찰 축소 ({len(bids)}건)</b>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px">{bid_rows}</table>
        </td>
        <td width="33%" valign="top">
          <b style="font-size:12px;color:#006100">키워드 하베스팅 ({len(harvested)}개)</b>
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px">{hvst_rows}</table>
        </td>
      </tr>
    </table>
    <b style="font-size:13px">성과 추이</b>
    {perf_html}"""


# ── 상태 파일 ─────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"channels": {}, "workflows": {}}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(exist_ok=True)
    state["last_run"] = NOW_UTC.isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def tick_failure(section: dict, key: str, now_iso: str):
    if key not in section or section[key].get("status") != "fail":
        section[key] = {"consecutive": 1, "first_failed": now_iso, "status": "fail"}
    else:
        section[key]["consecutive"] = section[key].get("consecutive", 0) + 1


def tick_recovery(section: dict, key: str) -> bool:
    was_failing = section.get(key, {}).get("status") == "fail"
    if key in section:
        section[key] = {"consecutive": 0, "status": "ok"}
    return was_failing


# ── 데이터 수집 ───────────────────────────────────────────────────────

def get_datakeeper_status() -> dict:
    try:
        r = requests.get(f"{ORBITOOLS_BASE}/status/",
                         auth=(ORBITOOLS_USER, ORBITOOLS_PASS), timeout=15)
        r.raise_for_status()
        raw  = r.json()
        data = raw.get("status", raw)
        return {k: {"rows": v.get("count", 0),
                    "updated": v.get("latest_collected", ""),
                    "date_range": v.get("latest_date", "—")}
                for k, v in data.items()}
    except Exception as e:
        print(f"[WARN] DataKeeper status 실패: {e}")
        return {}


def get_syncly_stats() -> list[dict]:
    """각 Syncly 탭의 현재 row 수 조회. 실패 시 빈 리스트."""
    sa_full = SA_PATH if os.path.isabs(SA_PATH) else str(PROJECT_ROOT / SA_PATH)
    if not os.path.exists(sa_full):
        print(f"[WARN] 서비스 계정 없음 ({sa_full}) -> Syncly 탭 통계 스킵")
        return []
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file(
            sa_full, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        gc = gspread.authorize(creds)
    except Exception as e:
        print(f"[WARN] gspread 초기화 실패: {e}")
        return []

    results = []
    for tab_def in SYNCLY_TABS:
        try:
            sh  = gc.open_by_key(tab_def["sheet_id"])
            ws  = sh.worksheet(tab_def["tab"])
            all_rows = ws.get_all_values()
            data_count = max(0, len(all_rows) - tab_def["header_rows"])
            results.append({
                "label":    tab_def["label"],
                "count":    data_count,
                "sheet_id": tab_def["sheet_id"],
                "tab":      tab_def["tab"],
            })
            print(f"  [{tab_def['label']}] {data_count} rows")
        except Exception as e:
            results.append({"label": tab_def["label"], "count": None, "error": str(e),
                             "sheet_id": tab_def["sheet_id"], "tab": tab_def["tab"]})
            print(f"  [{tab_def['label']}] 오류: {e}")
    return results


def get_gh_runs(hours: int = 24) -> list[dict]:
    if not GH_TOKEN or not GH_REPO:
        print("[WARN] GH_PAT / GITHUB_REPOSITORY 미설정 -> 워크플로우 이력 스킵")
        return []
    try:
        since = (NOW_UTC - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(
            f"https://api.github.com/repos/{GH_REPO}/actions/runs",
            headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"},
            params={"per_page": 50, "created": f">={since}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("workflow_runs", [])
    except Exception as e:
        print(f"[WARN] GitHub Actions 조회 실패: {e}")
        return []


# ── 분석 ─────────────────────────────────────────────────────────────

def classify_freshness(table_key: str, status: dict) -> tuple[str, str]:
    info = status.get(table_key, {})
    if not info or not info.get("updated"):
        return "🔴", "데이터 없음"
    try:
        updated = datetime.fromisoformat(info["updated"].replace("Z", "+00:00"))
        age_h   = (NOW_UTC - updated).total_seconds() / 3600
        max_age = CHANNEL_META.get(table_key, {}).get("max_age_h", 14)
        age_str = f"{age_h:.1f}h 전"
        if age_h <= max_age * 0.8:   return "🟢", age_str
        elif age_h <= max_age:        return "🟡", age_str
        else:                          return "🔴", age_str
    except Exception:
        return "🔴", "파싱 오류"


def summarize_runs(runs: list[dict]) -> dict[str, dict]:
    seen = {}
    for r in sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True):
        wf_file = r.get("path", "").split("/")[-1]
        if wf_file not in seen:
            seen[wf_file] = r
    return seen


def check_missing_runs(recent: dict[str, dict]) -> list[dict]:
    """스케줄 시간 기준으로 실행됐어야 하는데 기록이 없는 워크플로우 목록 반환."""
    overdue = []
    for wf in WORKFLOW_SCHEDULE:
        wf_file = wf["file"]
        if wf_file == "communicator.yml":
            continue  # 자기 자신은 체크 안 함

        for t in wf["times"]:
            h, m = map(int, t.split(":"))

            # 가장 최근에 실행됐어야 하는 시간 계산
            if wf.get("days") == "월요일":
                days_since = NOW_PST.weekday()  # 0=월
                if days_since == 0 and NOW_PST.hour * 60 + NOW_PST.minute < h * 60 + m:
                    continue  # 오늘 월요일인데 아직 시간이 안됨
                last_sched = (NOW_PST - timedelta(days=days_since)).replace(
                    hour=h, minute=m, second=0, microsecond=0)
            else:
                last_sched = NOW_PST.replace(hour=h, minute=m, second=0, microsecond=0)
                if last_sched > NOW_PST:
                    last_sched -= timedelta(days=1)

            # 30분 이상 지났을 때만 체크 (Actions 실행 지연 여유)
            overdue_mins = (NOW_PST - last_sched).total_seconds() / 60
            if overdue_mins < 30:
                continue

            # 최근 실행이 스케줄 이후인지 확인
            run = recent.get(wf_file)
            if not run:
                overdue.append({
                    "label": wf["label"],
                    "file": wf_file,
                    "scheduled": last_sched.strftime("%m/%d %H:%M PST"),
                    "overdue_mins": int(overdue_mins),
                    "run": None,
                })
                continue

            try:
                run_time_utc = datetime.fromisoformat(
                    run.get("run_started_at", run.get("created_at", "")).replace("Z", "+00:00"))
                run_time_pst = run_time_utc.astimezone(PST)
                if run_time_pst < last_sched:
                    overdue.append({
                        "label": wf["label"],
                        "file": wf_file,
                        "scheduled": last_sched.strftime("%m/%d %H:%M PST"),
                        "overdue_mins": int(overdue_mins),
                        "run": run,  # 이전 실행은 있지만 최신 스케줄 기준 없음
                    })
            except Exception:
                pass

    return overdue


def get_next_schedules() -> list[dict]:
    upcoming, cutoff = [], NOW_PST + timedelta(hours=12)
    for wf in WORKFLOW_SCHEDULE:
        for t in wf["times"]:
            h, m = map(int, t.split(":"))
            candidate = NOW_PST.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= NOW_PST:
                candidate += timedelta(days=1)
            if candidate <= cutoff:
                upcoming.append({"label": wf["label"],
                                  "time_pst": candidate.strftime("%m/%d %H:%M PST"),
                                  "days": wf["days"]})
    return sorted(upcoming, key=lambda x: x["time_pst"])


# ── HTML 헬퍼 ─────────────────────────────────────────────────────────

def _badge(conclusion, status_val):
    if status_val == "in_progress":
        return '<span style="background:#1a73e8;color:white;padding:2px 8px;border-radius:10px;font-size:11px">🔄 실행중</span>'
    m = {
        "success":   '<span style="background:#0d6e2e;color:white;padding:2px 8px;border-radius:10px;font-size:11px">✅ 성공</span>',
        "failure":   '<span style="background:#c0392b;color:white;padding:2px 8px;border-radius:10px;font-size:11px">❌ 실패</span>',
        "cancelled": '<span style="background:#7f8c8d;color:white;padding:2px 8px;border-radius:10px;font-size:11px">⚪ 취소</span>',
    }
    return m.get(conclusion or "", '<span style="background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:11px">— 기록없음</span>')


def _ago(iso_str):
    try:
        mins = int((NOW_UTC - datetime.fromisoformat(iso_str.replace("Z", "+00:00"))).total_seconds() / 60)
        return f"{mins}분 전" if mins < 60 else f"{mins // 60}h {mins % 60}m 전"
    except Exception:
        return iso_str


def _dur(run: dict) -> str:
    try:
        if not (run.get("run_started_at") and run.get("updated_at") and run.get("conclusion")):
            return "—"
        s   = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
        e   = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        sec = int((e - s).total_seconds())
        return f"{sec // 60}분 {sec % 60}초"
    except Exception:
        return "—"


def _streak_badge(n: int) -> str:
    if n <= 1: return ""
    color = "#c0392b" if n >= ESCALATE_THRESHOLD else "#e67e22"
    return f' <span style="background:{color};color:white;padding:1px 6px;border-radius:8px;font-size:11px;font-weight:700">{n}회 연속</span>'


def _link(label: str, url: str) -> str:
    return f'<a href="{url}" style="color:#1a73e8;text-decoration:none">{label}</a>'


def _links_row(links: list[dict], run_url: str = "") -> str:
    items = (([{"label": "실행 로그", "url": run_url}] if run_url else []) + links)
    if not items: return ""
    parts = " &nbsp;·&nbsp; ".join(_link(l["label"], l["url"]) for l in items)
    return f'<div style="margin-top:5px;font-size:12px;color:#555">{parts}</div>'


def _syncly_detail_html(syncly_stats: list[dict]) -> str:
    """Syncly 탭별 row 수 미니 테이블."""
    if not syncly_stats:
        return ""
    rows = ""
    for s in syncly_stats:
        count = s.get("count")
        count_str = f"{count:,}" if isinstance(count, int) else "오류"
        sheet_url = SHEET_URLS.get(s["sheet_id"], "#")
        rows += f"""<tr>
          <td style="padding:3px 8px;color:#555;font-size:12px">{_link(s['label'], sheet_url)}</td>
          <td style="padding:3px 8px;text-align:right;font-size:12px;font-weight:600">{count_str} rows</td>
        </tr>"""
    return f"""<table style="border-collapse:collapse;margin-top:6px;width:100%">{rows}</table>"""


# ── HTML 이메일 빌드 ──────────────────────────────────────────────────

def build_html(dk_status: dict, gh_runs: list[dict], state: dict,
               syncly_stats: list[dict]) -> tuple[str, list, int]:

    ts_str  = NOW_PST.strftime("%Y-%m-%d %H:%M PST")
    period  = "자정" if NOW_PST.hour < 12 else "정오"
    now_iso = NOW_UTC.isoformat()

    ch_state = state.setdefault("channels", {})
    wf_state = state.setdefault("workflows", {})
    recent   = summarize_runs(gh_runs)  # {wf_file: run_dict}

    # ─ 미실행 에이전트 감지 ──────────────────────────────────────────
    missing_runs = check_missing_runs(recent)

    # ─ 1. 태스크 업데이트 ────────────────────────────────────────────
    task_rows_html = ""
    fail_workflows = []
    recovery_items = []
    missing_agents = []   # 미실행 에이전트 목록

    # missing_runs를 파일명으로 빠르게 조회
    missing_files = {m["file"] for m in missing_runs}

    for wf in WORKFLOW_SCHEDULE:
        wf_file = wf["file"]
        detail  = WORKFLOW_DETAILS.get(wf_file, {})
        emoji   = detail.get("emoji", "⚙️")
        desc    = detail.get("desc", "")
        links   = detail.get("links", [])
        run     = recent.get(wf_file)

        # Syncly 워크플로우인 경우 탭별 상세 추가
        extra_html = ""
        if wf_file == "data_keeper.yml" and syncly_stats:
            extra_html = _syncly_detail_html(syncly_stats)

        if run:
            conclusion = run.get("conclusion")
            status_val = run.get("status")
            badge      = _badge(conclusion, status_val)
            ago        = _ago(run.get("run_started_at", run.get("created_at", "")))
            dur        = _dur(run)
            run_url    = run.get("html_url", "")

            if conclusion == "failure":
                tick_failure(wf_state, wf_file, now_iso)
                n      = wf_state[wf_file]["consecutive"]
                streak = _streak_badge(n)
                msg    = f"❌ {wf['label']}: 워크플로우 실패"
                if n >= ESCALATE_THRESHOLD:
                    msg += f" ({n}회 연속 — 즉시 확인!)"
                fail_workflows.append(f'{msg} → <a href="{run_url}" style="color:#c0392b">로그</a>')
                row_bg    = "#fff5f5"
                status_td = f"{badge}{streak}"
            else:
                recovered = tick_recovery(wf_state, wf_file)
                if recovered:
                    recovery_items.append(f"🟢 {wf['label']} 워크플로우: 복구됨!")
                if conclusion == "success":
                    # 마지막 성공 시간 기록
                    wf_state.setdefault(wf_file, {})["last_success"] = now_iso
                row_bg    = "#f6fff8" if conclusion == "success" else "#f8f9fc"
                status_td = badge

            # 미실행 배지 (이전 실행은 있지만 최신 스케줄 미충족)
            if wf_file in missing_files:
                miss_info = next(m for m in missing_runs if m["file"] == wf_file)
                status_td += f' <span style="background:#e67e22;color:white;padding:1px 6px;border-radius:8px;font-size:11px">⏰ +{miss_info["overdue_mins"]}분 지연</span>'
                missing_agents.append(miss_info)

            links_html = _links_row(links, run_url)
            time_html  = f'<span style="font-size:12px;color:#666">{ago}</span><br><span style="font-size:11px;color:#999">{dur}</span>'
        else:
            row_bg     = "#fff8e1"
            status_td  = '<span style="background:#e67e22;color:white;padding:2px 8px;border-radius:10px;font-size:11px">⚠️ 미실행</span>'
            links_html = _links_row(links)
            time_html  = '<span style="color:#ccc">—</span>'
            if wf_file in missing_files:
                miss_info = next(m for m in missing_runs if m["file"] == wf_file)
                missing_agents.append(miss_info)
                # 미실행도 연속 실패로 카운트
                tick_failure(wf_state, wf_file, now_iso)
                n = wf_state[wf_file]["consecutive"]
                msg = f"⚠️ {wf['label']}: 미실행 (예정 {miss_info['scheduled']}, +{miss_info['overdue_mins']}분)"
                if n >= ESCALATE_THRESHOLD:
                    msg += f" {n}회 연속!"
                fail_workflows.append(msg)

        task_rows_html += f"""
        <tr style="background:{row_bg}">
          <td style="padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top">
            <b style="font-size:13px">{emoji} {wf['label']}</b>
            <div style="color:#666;font-size:12px;margin-top:2px">{desc}</div>
            {links_html}
            {extra_html}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;text-align:center;vertical-align:top;white-space:nowrap">{status_td}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top;white-space:nowrap">{time_html}</td>
        </tr>"""

    # ─ Naeiae PPC 변경 추적 섹션 ────────────────────────────────────
    ppc_tracking_html = get_naeiae_ppc_tracking_html()

    # ─ 2. Syncly 탭 섹션 (별도 섹션) ─────────────────────────────────
    syncly_section_html = ""
    if syncly_stats:
        syncly_rows = ""
        for s in syncly_stats:
            count     = s.get("count")
            count_str = f"{count:,}" if isinstance(count, int) else "오류"
            err_html  = f'<span style="color:#c0392b;font-size:11px">{s.get("error","")}</span>' if s.get("error") else ""
            sheet_url = SHEET_URLS.get(s["sheet_id"], "#")
            color     = "#f6fff8" if isinstance(count, int) and count > 0 else "#fff5f5"
            syncly_rows += f"""
            <tr style="background:{color}">
              <td style="padding:7px 12px;border-bottom:1px solid #eee;font-size:13px">
                {_link(s['label'], sheet_url)}
              </td>
              <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600">{count_str} rows</td>
              <td style="padding:7px 12px;border-bottom:1px solid #eee;font-size:11px;color:#888">{err_html}</td>
            </tr>"""

        syncly_section_html = f"""
    <!-- Syncly 탭 현황 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📱 Syncly / SNS 트래커 탭 현황
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">탭</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#555">현재 Rows</th>
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">비고</th>
      </tr>
      {syncly_rows}
    </table>"""

    # ─ 3. 데이터 수집 현황 (간단) ────────────────────────────────────
    data_rows_html = ""
    alert_items    = []
    fresh_count = stale_count = missing_count = 0

    for key, meta in CHANNEL_META.items():
        emoji, age_str = classify_freshness(key, dk_status)
        info     = dk_status.get(key, {})
        rows_raw = info.get("rows", None)
        rows     = f"{rows_raw:,}" if isinstance(rows_raw, int) else "—"
        dr       = info.get("date_range", "—")
        ch_link  = CHANNEL_LINKS.get(key, "")
        label_h  = (_link(meta["label"], ch_link) if ch_link else meta["label"])

        if emoji == "🟢":
            fresh_count += 1
            row_bg = "#f6fff8"
            if tick_recovery(ch_state, key):
                recovery_items.append(f"🟢 {meta['label']}: 복구됨!")
        elif emoji == "🟡":
            stale_count += 1
            row_bg = "#fffbf0"
            tick_failure(ch_state, key, now_iso)
            n = ch_state[key]["consecutive"]
            alert_items.append(f"⚠️ {meta['label']}: 데이터 지연 ({age_str})" + (f" {n}회 연속" if n >= 2 else ""))
        else:
            missing_count += 1
            row_bg = "#fff5f5"
            tick_failure(ch_state, key, now_iso)
            n = ch_state[key]["consecutive"]
            msg = f"🔴 {meta['label']}: 데이터 없음"
            if n >= ESCALATE_THRESHOLD:
                msg += f" ({n}회 연속 — 확인 필요!)"
            alert_items.append(msg)

        n_st = ch_state.get(key, {}).get("consecutive", 0)
        streak_h = _streak_badge(n_st) if emoji != "🟢" else ""

        data_rows_html += f"""
        <tr style="background:{row_bg}">
          <td style="padding:7px 12px;border-bottom:1px solid #eee;font-size:13px">{emoji} {label_h}{streak_h}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center;font-size:12px;color:#555">{age_str}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:right;font-size:12px">{rows}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;font-size:11px;color:#888">{dr}</td>
        </tr>"""

    # ─ 4. 향후 12시간 ────────────────────────────────────────────────
    upcoming_html = ""
    for item in get_next_schedules():
        upcoming_html += f"""
        <tr>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">⏰ {item['label']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;font-weight:bold">{item['time_pst']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;color:#666">{item['days']}</td>
        </tr>"""
    if not upcoming_html:
        upcoming_html = '<tr><td colspan="3" style="padding:16px;text-align:center;color:#999">없음</td></tr>'

    # ─ 5. 알림 ───────────────────────────────────────────────────────
    alert_html = ""

    # 미실행 에이전트 전용 블록 (쪼기)
    unique_missing = {m["file"]: m for m in missing_agents}.values()
    if unique_missing:
        poke_rows = ""
        for m in unique_missing:
            prev_run = m.get("run")
            last_run_str = ""
            if prev_run:
                last_run_str = f" (이전 실행: {_ago(prev_run.get('run_started_at', prev_run.get('created_at', '')))})"
                log_url = prev_run.get("html_url", "")
                if log_url:
                    last_run_str += f' <a href="{log_url}" style="color:#c0392b">로그</a>'
            poke_rows += f'<li style="margin:5px 0"><b>{m["label"]}</b> — 예정 {m["scheduled"]} 기준 <b>+{m["overdue_mins"]}분</b> 미실행{last_run_str}</li>'
        alert_html += f"""
        <div style="background:#fff3e0;border:2px solid #ff9800;border-radius:6px;padding:14px 18px;margin:0 0 12px">
          <b style="color:#e65100">🔔 에이전트 쪼기 — 미실행 감지 ({len(list(unique_missing))}건)</b>
          <ul style="margin:8px 0 0;padding-left:20px;font-size:13px;color:#bf360c">{poke_rows}</ul>
        </div>"""

    if recovery_items:
        rec_html = "".join(f'<li style="margin:4px 0">{r}</li>' for r in recovery_items)
        alert_html += f"""
        <div style="background:#e8f5e9;border:1px solid #4caf50;border-radius:6px;padding:12px 18px;margin:0 0 12px">
          <b style="color:#1b5e20">🎉 복구됨 ({len(recovery_items)}건)</b>
          <ul style="margin:6px 0 0;padding-left:20px;font-size:13px;color:#2e7d32">{rec_html}</ul>
        </div>"""

    all_alerts = alert_items + fail_workflows
    critical   = [a for a in all_alerts if "연속" in a and ("즉시" in a or "확인 필요" in a)]

    if all_alerts:
        has_crit  = bool(critical)
        bg  = "#fce4ec" if has_crit else "#fff3cd"
        bd  = "#e91e63" if has_crit else "#ffc107"
        tc  = "#880e4f" if has_crit else "#856404"
        icon  = "🚨" if has_crit else "⚠️"
        title = f"{icon} {'긴급 알림' if has_crit else '주의 필요'} ({len(all_alerts)}건)"
        items = "".join(f'<li style="margin:4px 0">{a}</li>' for a in all_alerts)
        alert_html += f"""
        <div style="background:{bg};border:1px solid {bd};border-radius:6px;padding:14px 18px;margin:0 0 24px">
          <b style="color:{tc}">{title}</b>
          <ul style="margin:8px 0 0;padding-left:20px;font-size:13px;color:{tc}">{items}</ul>
        </div>"""

    # ─ 헬스 배지 ─────────────────────────────────────────────────────
    n_missing_agents = len(list(unique_missing))
    if critical:
        h_color, h_label, h_dot = "#880e4f", "긴급", "🚨"
    elif n_missing_agents > 0 or missing_count > 0 or fail_workflows:
        h_color, h_label, h_dot = "#c0392b", "주의 필요", "🔴"
    elif stale_count > 0:
        h_color, h_label, h_dot = "#e67e22", "지연 있음", "🟡"
    else:
        h_color, h_label, h_dot = "#0d6e2e", "정상", "🟢"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f4f6f9;font-family:'Apple SD Gothic Neo',Arial,sans-serif">
<div style="max-width:660px;margin:0 auto">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#1a1f2e 0%,#2d3556 100%);color:white;padding:24px 28px;border-radius:10px 10px 0 0">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <h1 style="margin:0;font-size:20px;font-weight:700">📡 ORBI Communicator</h1>
        <p style="margin:5px 0 0;opacity:0.75;font-size:13px">{ts_str} ({period} 리포트)</p>
      </div>
      <div style="text-align:right">
        <div style="background:{h_color};display:inline-block;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600">
          {h_dot} {h_label}
        </div>
        <p style="margin:6px 0 0;opacity:0.65;font-size:12px">데이터: {fresh_count}✅ {stale_count}⚠️ {missing_count}🔴</p>
      </div>
    </div>
  </div>

  <!-- 본문 -->
  <div style="background:white;padding:28px;border:1px solid #e5e5e5;border-top:none;border-radius:0 0 10px 10px">

    {alert_html}

    <!-- 태스크 업데이트 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      🔄 태스크 업데이트 (최근 24시간)
    </h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555;font-size:13px">작업 / 설명</th>
        <th style="padding:9px 12px;text-align:center;font-weight:600;color:#555;font-size:13px">결과</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555;font-size:13px">시간/소요</th>
      </tr>
      {task_rows_html}
    </table>

    {syncly_section_html}

    <!-- Naeiae PPC 변경 추적 -->
    {ppc_tracking_html}

    <!-- 데이터 수집 현황 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📊 데이터 수집 현황
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">채널</th>
        <th style="padding:8px 12px;text-align:center;font-weight:600;color:#555">최종 수집</th>
        <th style="padding:8px 12px;text-align:right;font-weight:600;color:#555">Rows</th>
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">최신 날짜</th>
      </tr>
      {data_rows_html}
    </table>

    <!-- 향후 12시간 예정 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📅 향후 12시간 예정 작업
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">
      <tr style="background:#f8f9fc">
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">작업</th>
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">예정 시간</th>
        <th style="padding:8px 12px;text-align:left;font-weight:600;color:#555">주기</th>
      </tr>
      {upcoming_html}
    </table>

  </div>

  <div style="text-align:center;padding:14px;font-size:11px;color:#999">
    ORBI Communicator — WAT Framework 자동 발송 | {ts_str}
  </div>

</div>
</body>
</html>"""

    return html, critical, n_missing_agents


# ── 실행 ─────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--preview",     action="store_true")
    parser.add_argument("--reset-state", action="store_true")
    parser.add_argument("--to",          default=RECIPIENT)
    parser.add_argument("--cc",          default=CC_DEFAULT, help="CC 이메일 (자이멜로 등)")
    parser.add_argument("--skip-syncly", action="store_true", help="Syncly 탭 통계 스킵")
    args = parser.parse_args()

    print(f"\n[Communicator] 시작 - {NOW_PST.strftime('%Y-%m-%d %H:%M PST')}")

    state = {"channels": {}, "workflows": {}} if args.reset_state else load_state()
    print(f"[State] last_run: {state.get('last_run', '없음')}")

    print("[1/3] Data Keeper 상태 조회 중...")
    dk_status = get_datakeeper_status()
    print(f"      {len(dk_status)}개 채널")

    print("[2/3] Syncly 탭 통계 조회 중...")
    syncly_stats = [] if args.skip_syncly else get_syncly_stats()

    print("[3/3] GitHub Actions 이력 조회 중...")
    gh_runs = get_gh_runs(hours=24)
    print(f"      {len(gh_runs)}개 실행 이력")

    html, critical, missing_cnt = build_html(dk_status, gh_runs, state, syncly_stats)
    save_state(state)

    if args.preview:
        preview_path = PROJECT_ROOT / ".tmp" / "communicator_preview.html"
        preview_path.parent.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        print(f"[Preview] {preview_path}")

    period  = "자정" if NOW_PST.hour < 12 else "정오"
    if critical:
        subject = f"[ORBI 🚨 긴급] {NOW_PST.strftime('%m/%d')} {period} — 연속 오류 감지"
    elif missing_cnt > 0:
        subject = f"[ORBI ⚠️ 쪼기] {NOW_PST.strftime('%m/%d')} {period} — 에이전트 {missing_cnt}개 미실행"
    else:
        subject = f"[ORBI] {NOW_PST.strftime('%m/%d')} {period} 상태 리포트"

    if args.dry_run:
        print(f"\n[Dry Run] Subject: {subject}")
        print(f"[Dry Run] To: {args.to}  CC: {args.cc or '없음'}")
        return

    print(f"\n[EMAIL] {subject}")
    print(f"[EMAIL] To: {args.to}" + (f"  CC: {args.cc}" if args.cc else ""))
    from send_gmail import send_email
    result = send_email(to=args.to, subject=subject, body_html=html,
                        sender=SENDER, cc=args.cc if args.cc else None)
    print(f"[완료] ID: {result.get('id', '?')}")


if __name__ == "__main__":
    main()
