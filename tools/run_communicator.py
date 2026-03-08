"""
run_communicator.py - ORBI Communicator

12시간 단위 통합 상태 이메일 (PST 0:00 / PST 12:00)

핵심 기능:
  - Data Keeper 9개 채널 freshness 모니터링
  - GitHub Actions 워크플로우 실행 이력 추적
  - 연속 실패/지연 카운트 → 에스컬레이션 알림 ("쪼기")
  - 복구 감지 ("복구됨!")
  - 상태 파일로 회차간 기억 유지 (.tmp/communicator_state.json)

Usage:
    python tools/run_communicator.py               # 발송
    python tools/run_communicator.py --dry-run     # 발송 없이 확인
    python tools/run_communicator.py --preview     # .tmp/communicator_preview.html 저장
    python tools/run_communicator.py --reset-state # 상태 초기화 후 발송
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
GH_REPO  = os.getenv("GITHUB_REPOSITORY", "")  # e.g. "Orbiters-dev/WJ-Test1"

RECIPIENT = os.getenv("COMMUNICATOR_RECIPIENT") or os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER    = os.getenv("GMAIL_SENDER", "hello@zezebaebae.com")

STATE_PATH = Path(__file__).resolve().parent.parent / ".tmp" / "communicator_state.json"

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

# ── 워크플로우 스케줄 (PST) ────────────────────────────────────────────
WORKFLOW_SCHEDULE = [
    {"file": "data_keeper.yml",     "label": "Data Keeper",  "times": ["00:00", "12:00"], "days": "매일"},
    {"file": "amazon_ppc_daily.yml","label": "Amazon PPC",   "times": ["10:00"],          "days": "매일"},
    {"file": "meta_ads_daily.yml",  "label": "Meta Ads",     "times": ["10:00"],          "days": "매일"},
    {"file": "polar_weekly.yml",    "label": "Polar Weekly", "times": ["10:00"],          "days": "월요일"},
    {"file": "communicator.yml",    "label": "Communicator", "times": ["00:00", "12:00"], "days": "매일"},
]

# 연속 실패 N회 이상이면 에스컬레이션
ESCALATE_THRESHOLD = 2


# ── 상태 파일 (회차간 기억) ────────────────────────────────────────────

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


def tick_failure(state_section: dict, key: str, now_iso: str):
    """연속 실패 카운터 +1."""
    if key not in state_section:
        state_section[key] = {"consecutive": 0, "first_failed": now_iso, "status": "fail"}
    prev = state_section[key]
    if prev.get("status") != "fail":
        # 새로 실패 시작
        state_section[key] = {"consecutive": 1, "first_failed": now_iso, "status": "fail"}
    else:
        state_section[key]["consecutive"] = prev.get("consecutive", 0) + 1


def tick_recovery(state_section: dict, key: str) -> bool:
    """직전 실패였으면 True(복구) 반환 후 상태 초기화."""
    was_failing = state_section.get(key, {}).get("status") == "fail"
    if key in state_section:
        state_section[key] = {"consecutive": 0, "status": "ok"}
    return was_failing


# ── 데이터 수집 ───────────────────────────────────────────────────────

def get_datakeeper_status() -> dict:
    """orbitools API → {table: {rows, updated, date_range}}."""
    try:
        r = requests.get(
            f"{ORBITOOLS_BASE}/status/",
            auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json()
        data = raw.get("status", raw)
        result = {}
        for key, info in data.items():
            result[key] = {
                "rows":       info.get("count", 0),
                "updated":    info.get("latest_collected", ""),
                "date_range": info.get("latest_date", "—"),
            }
        return result
    except Exception as e:
        print(f"[WARN] DataKeeper status 조회 실패: {e}")
        return {}


def get_gh_runs(hours: int = 24) -> list[dict]:
    """GitHub Actions 최근 실행 이력."""
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
    """(emoji, age_str) — 🟢 fresh / 🟡 stale / 🔴 missing"""
    info = status.get(table_key, {})
    if not info or not info.get("updated"):
        return "🔴", "데이터 없음"
    try:
        updated = datetime.fromisoformat(info["updated"].replace("Z", "+00:00"))
        age_h   = (NOW_UTC - updated).total_seconds() / 3600
        max_age = CHANNEL_META.get(table_key, {}).get("max_age_h", 14)
        age_str = f"{age_h:.1f}h 전"
        if age_h <= max_age * 0.8:
            return "🟢", age_str
        elif age_h <= max_age:
            return "🟡", age_str
        else:
            return "🔴", age_str
    except Exception:
        return "🔴", "파싱 오류"


def summarize_runs(runs: list[dict]) -> list[dict]:
    """워크플로우 파일별 최신 1건씩 추출."""
    seen = {}
    for r in sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True):
        wf_file = r.get("path", "").split("/")[-1]
        if wf_file not in seen:
            seen[wf_file] = r
    return list(seen.values())


def get_next_schedules() -> list[dict]:
    """향후 12시간 이내 예정 목록."""
    upcoming, cutoff = [], NOW_PST + timedelta(hours=12)
    for wf in WORKFLOW_SCHEDULE:
        for t in wf["times"]:
            h, m = map(int, t.split(":"))
            candidate = NOW_PST.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= NOW_PST:
                candidate += timedelta(days=1)
            if candidate <= cutoff:
                upcoming.append({
                    "label": wf["label"],
                    "time_pst": candidate.strftime("%m/%d %H:%M PST"),
                    "days": wf["days"],
                })
    return sorted(upcoming, key=lambda x: x["time_pst"])


# ── HTML 헬퍼 ─────────────────────────────────────────────────────────

def _badge(conclusion, status):
    if status == "in_progress":
        return '<span style="background:#1a73e8;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">🔄 실행중</span>'
    m = {
        "success":   '<span style="background:#0d6e2e;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">✅ 성공</span>',
        "failure":   '<span style="background:#c0392b;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">❌ 실패</span>',
        "cancelled": '<span style="background:#7f8c8d;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">⚪ 취소</span>',
        "skipped":   '<span style="background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">⏭ 스킵</span>',
    }
    return m.get(conclusion or "", '<span style="background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">— 알수없음</span>')


def _ago(iso_str):
    try:
        dt   = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        mins = int((NOW_UTC - dt).total_seconds() / 60)
        return f"{mins}분 전" if mins < 60 else f"{mins // 60}시간 {mins % 60}분 전"
    except Exception:
        return iso_str


def _streak_badge(n: int) -> str:
    """연속 실패 횟수 배지."""
    if n <= 1:
        return ""
    color = "#c0392b" if n >= ESCALATE_THRESHOLD else "#e67e22"
    return f' <span style="background:{color};color:white;padding:1px 6px;border-radius:8px;font-size:11px;font-weight:700">{n}회 연속</span>'


# ── HTML 이메일 빌드 ──────────────────────────────────────────────────

def build_html(dk_status: dict, gh_runs: list[dict], state: dict) -> tuple[str, list[str]]:
    """Returns (html, critical_issues_list)."""
    ts_str = NOW_PST.strftime("%Y-%m-%d %H:%M PST")
    period = "자정" if NOW_PST.hour < 12 else "정오"
    now_iso = NOW_UTC.isoformat()

    ch_state = state.setdefault("channels", {})
    wf_state = state.setdefault("workflows", {})

    # ── 1. 데이터 상태 테이블 ─────────────────────────────────────────
    data_rows_html = ""
    alert_items    = []
    recovery_items = []
    fresh_count = stale_count = missing_count = 0

    for key, meta in CHANNEL_META.items():
        emoji, age_str = classify_freshness(key, dk_status)
        info      = dk_status.get(key, {})
        rows_raw  = info.get("rows", None)
        rows      = f"{rows_raw:,}" if isinstance(rows_raw, int) else "—"
        dr        = info.get("date_range", "—")

        if emoji == "🟢":
            fresh_count += 1
            row_bg = "#f6fff8"
            recovered = tick_recovery(ch_state, key)
            if recovered:
                recovery_items.append(f"🟢 {meta['label']}: 복구됨!")
        elif emoji == "🟡":
            stale_count += 1
            row_bg = "#fffbf0"
            tick_failure(ch_state, key, now_iso)
            n = ch_state[key]["consecutive"]
            streak = _streak_badge(n)
            alert_items.append(f"⚠️ {meta['label']}: 데이터 지연 ({age_str}){streak.replace('<span', ' <b').replace('</span>', '</b>').replace(' style=\"background:#c0392b;color:white;padding:1px 6px;border-radius:8px;font-size:11px;font-weight:700\"', '').replace(' style=\"background:#e67e22;color:white;padding:1px 6px;border-radius:8px;font-size:11px;font-weight:700\"', '')}")
        else:
            missing_count += 1
            row_bg = "#fff5f5"
            tick_failure(ch_state, key, now_iso)
            n = ch_state[key]["consecutive"]
            streak = _streak_badge(n)
            msg = f"🔴 {meta['label']}: 데이터 없음"
            if n >= ESCALATE_THRESHOLD:
                msg += f" ({n}회 연속 미수집 — 확인 필요!)"
            alert_items.append(msg)

        # 연속 실패 배지 (테이블용)
        n_streak = ch_state.get(key, {}).get("consecutive", 0)
        streak_html = _streak_badge(n_streak) if emoji != "🟢" else ""

        data_rows_html += f"""
        <tr style="background:{row_bg}">
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{emoji} {meta['label']}{streak_html}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{age_str}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">{rows} rows</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{dr}</td>
        </tr>"""

    # ── 2. 워크플로우 이력 테이블 ─────────────────────────────────────
    run_rows_html  = ""
    fail_workflows = []

    if gh_runs:
        recent = summarize_runs(gh_runs)
        for run in recent:
            wf_file    = run.get("path", "").split("/")[-1]
            label      = next((w["label"] for w in WORKFLOW_SCHEDULE if w["file"] == wf_file), run.get("name", "—"))
            conclusion = run.get("conclusion")
            status_val = run.get("status")
            badge      = _badge(conclusion, status_val)
            ago        = _ago(run.get("run_started_at", run.get("created_at", "")))
            run_url    = run.get("html_url", "#")

            dur_str = "—"
            if run.get("run_started_at") and run.get("updated_at") and conclusion:
                try:
                    s   = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                    e   = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                    sec = int((e - s).total_seconds())
                    dur_str = f"{sec // 60}분 {sec % 60}초"
                except Exception:
                    pass

            if conclusion == "failure":
                tick_failure(wf_state, wf_file, now_iso)
                n = wf_state[wf_file]["consecutive"]
                streak_html = _streak_badge(n)
                msg = f"❌ {label}: 워크플로우 실패"
                if n >= ESCALATE_THRESHOLD:
                    msg += f" ({n}회 연속 — 즉시 확인 필요!)"
                fail_workflows.append(f'{msg} → <a href="{run_url}" style="color:#c0392b">로그</a>')
                streak_in_table = streak_html
            else:
                recovered = tick_recovery(wf_state, wf_file)
                if recovered:
                    recovery_items.append(f"🟢 {label} 워크플로우: 복구됨!")
                streak_in_table = ""

            run_rows_html += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eee">{label}{streak_in_table}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{badge}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{ago}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{dur_str}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:11px">
                <a href="{run_url}" style="color:#1a73e8">로그</a>
              </td>
            </tr>"""
    else:
        run_rows_html = '<tr><td colspan="5" style="padding:16px;text-align:center;color:#999">워크플로우 이력 없음 (GH_PAT 미설정 또는 24시간 내 실행 없음)</td></tr>'

    # ── 3. 다음 예정 작업 ─────────────────────────────────────────────
    upcoming_html = ""
    for item in get_next_schedules():
        upcoming_html += f"""
        <tr>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">⏰ {item['label']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;font-weight:bold">{item['time_pst']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;color:#666">{item['days']}</td>
        </tr>"""
    if not upcoming_html:
        upcoming_html = '<tr><td colspan="3" style="padding:16px;text-align:center;color:#999">향후 12시간 이내 예정 없음</td></tr>'

    # ── 4. 알림 & 복구 섹션 ───────────────────────────────────────────
    critical   = [a for a in alert_items + fail_workflows if "연속" in a or "즉시" in a or "4회" in a or "확인 필요" in a]
    all_alerts = alert_items + fail_workflows
    alert_html = ""

    if recovery_items:
        rec_html = "".join(f'<li style="margin:4px 0">{r}</li>' for r in recovery_items)
        alert_html += f"""
        <div style="background:#e8f5e9;border:1px solid #4caf50;border-radius:6px;padding:12px 18px;margin:0 0 12px">
            <b style="color:#1b5e20">🎉 복구됨 ({len(recovery_items)}건)</b>
            <ul style="margin:6px 0 0;padding-left:20px;font-size:13px;color:#2e7d32">{rec_html}</ul>
        </div>"""

    if all_alerts:
        # 에스컬레이션 여부 판단
        has_critical = bool(critical)
        bg_color  = "#fce4ec" if has_critical else "#fff3cd"
        bd_color  = "#e91e63" if has_critical else "#ffc107"
        txt_color = "#880e4f" if has_critical else "#856404"
        icon      = "🚨" if has_critical else "⚠️"
        title     = f"{icon} {'긴급 알림' if has_critical else '주의 필요'} ({len(all_alerts)}건)"

        items_html = "".join(f'<li style="margin:4px 0">{a}</li>' for a in all_alerts)
        alert_html += f"""
        <div style="background:{bg_color};border:1px solid {bd_color};border-radius:6px;padding:14px 18px;margin:0 0 24px">
            <b style="color:{txt_color}">{title}</b>
            <ul style="margin:8px 0 0;padding-left:20px;font-size:13px;color:{txt_color}">{items_html}</ul>
        </div>"""

    # ── 5. 헬스 배지 ──────────────────────────────────────────────────
    if critical:
        h_color, h_label, h_dot = "#880e4f", "긴급", "🚨"
    elif missing_count > 0 or fail_workflows:
        h_color, h_label, h_dot = "#c0392b", "주의 필요", "🔴"
    elif stale_count > 0:
        h_color, h_label, h_dot = "#e67e22", "지연 있음", "🟡"
    else:
        h_color, h_label, h_dot = "#0d6e2e", "정상", "🟢"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f4f6f9;font-family:'Apple SD Gothic Neo',Arial,sans-serif">
<div style="max-width:640px;margin:0 auto">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#1a1f2e 0%,#2d3556 100%);color:white;padding:24px 28px;border-radius:10px 10px 0 0">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <h1 style="margin:0;font-size:20px;font-weight:700">📡 ORBI Communicator</h1>
        <p style="margin:6px 0 0;opacity:0.75;font-size:13px">{ts_str} ({period} 리포트)</p>
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

    <!-- 데이터 수집 현황 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📊 데이터 수집 현황
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">채널</th>
        <th style="padding:9px 12px;text-align:center;font-weight:600;color:#555">최종 수집</th>
        <th style="padding:9px 12px;text-align:right;font-weight:600;color:#555">Row 수</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">최신 날짜</th>
      </tr>
      {data_rows_html}
    </table>

    <!-- 워크플로우 이력 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      🔄 워크플로우 이력 (최근 24시간)
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">워크플로우</th>
        <th style="padding:9px 12px;text-align:center;font-weight:600;color:#555">결과</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">시작</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">소요</th>
        <th style="padding:9px 12px;text-align:center;font-weight:600;color:#555">로그</th>
      </tr>
      {run_rows_html}
    </table>

    <!-- 향후 12시간 예정 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📅 향후 12시간 예정 작업
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">작업</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">예정 시간</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">주기</th>
      </tr>
      {upcoming_html}
    </table>

  </div>

  <!-- 푸터 -->
  <div style="text-align:center;padding:14px;font-size:11px;color:#999">
    ORBI Communicator — WAT Framework 자동 발송 | {ts_str}
  </div>

</div>
</body>
</html>"""

    return html, critical


# ── 실행 ─────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ORBI Communicator - 통합 상태 이메일 발송")
    parser.add_argument("--dry-run",     action="store_true", help="이메일 미발송")
    parser.add_argument("--preview",     action="store_true", help=".tmp/communicator_preview.html 저장")
    parser.add_argument("--reset-state", action="store_true", help="상태 파일 초기화")
    parser.add_argument("--to",          default=RECIPIENT,   help="수신자 이메일")
    args = parser.parse_args()

    print(f"\n[Communicator] 시작 - {NOW_PST.strftime('%Y-%m-%d %H:%M PST')}")

    # 상태 로드
    if args.reset_state:
        state = {"channels": {}, "workflows": {}}
        print("[State] 초기화됨")
    else:
        state = load_state()
        print(f"[State] 로드 완료 (last_run: {state.get('last_run', '없음')})")

    # 데이터 수집
    print("[1/2] Data Keeper 상태 조회 중...")
    dk_status = get_datakeeper_status()
    print(f"      {len(dk_status)}개 채널 조회됨")

    print("[2/2] GitHub Actions 이력 조회 중...")
    gh_runs = get_gh_runs(hours=24)
    print(f"      {len(gh_runs)}개 실행 이력 조회됨")

    # HTML 생성 + 상태 업데이트
    html, critical = build_html(dk_status, gh_runs, state)

    # 상태 저장 (dry-run도 저장 — 카운터 누적)
    save_state(state)
    print(f"[State] 저장됨: {STATE_PATH}")

    # 프리뷰 저장
    if args.preview:
        preview_path = Path(__file__).resolve().parent.parent / ".tmp" / "communicator_preview.html"
        preview_path.parent.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        print(f"[Preview] 저장됨: {preview_path}")

    # 제목 결정 (에스컬레이션 반영)
    period = "자정" if NOW_PST.hour < 12 else "정오"
    if critical:
        subject = f"[ORBI 🚨 긴급] {NOW_PST.strftime('%m/%d')} {period} — 연속 오류 감지"
    else:
        subject = f"[ORBI] {NOW_PST.strftime('%m/%d')} {period} 상태 리포트"

    if args.dry_run:
        print(f"\n[Dry Run] Subject: {subject}")
        print(f"[Dry Run] Critical: {critical}")
        return

    # 이메일 발송
    print(f"\n[EMAIL] Subject: {subject}")
    print(f"[EMAIL] -> {args.to}")
    from send_gmail import send_email
    result = send_email(to=args.to, subject=subject, body_html=html, sender=SENDER)
    print(f"[완료] 발송 완료 (ID: {result.get('id', '?')})")


if __name__ == "__main__":
    main()
