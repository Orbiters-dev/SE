"""
run_communicator.py - ORBI Communicator

12시간 단위 통합 상태 이메일 (PST 0:00 / PST 12:00)

이메일 구성:
  1. 데이터 수집 상태  - Data Keeper 9개 채널 freshness
  2. 워크플로우 이력   - 최근 24시간 GitHub Actions 실행 결과
  3. 다음 예정 작업   - 향후 12시간 스케줄
  4. 알림             - 실패/지연 항목

Usage:
    python tools/run_communicator.py
    python tools/run_communicator.py --dry-run   # 이메일 전송 없이 HTML만 출력
    python tools/run_communicator.py --preview   # .tmp/communicator_preview.html 저장
"""

import argparse
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

ORBITOOLS_BASE = os.getenv("ORBITOOLS_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

GH_TOKEN   = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN", "")
GH_REPO    = os.getenv("GITHUB_REPOSITORY", "")  # e.g. "orbiters/orbiters-claude"

RECIPIENT  = os.getenv("COMMUNICATOR_RECIPIENT") or os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER     = os.getenv("GMAIL_SENDER", "hello@zezebaebae.com")

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

# ── 워크플로우 스케줄 (PST 기준) ──────────────────────────────────────
WORKFLOW_SCHEDULE = [
    {"file": "data_keeper.yml",    "label": "Data Keeper",   "times": ["00:00", "12:00"], "days": "매일"},
    {"file": "amazon_ppc_daily.yml","label": "Amazon PPC",   "times": ["10:00"],          "days": "매일"},
    {"file": "meta_ads_daily.yml", "label": "Meta Ads",      "times": ["10:00"],          "days": "매일"},
    {"file": "polar_weekly.yml",   "label": "Polar Weekly",  "times": ["10:00"],          "days": "월요일"},
    {"file": "communicator.yml",   "label": "Communicator",  "times": ["00:00", "12:00"], "days": "매일"},
]


# ── 데이터 수집 ───────────────────────────────────────────────────────

def get_datakeeper_status() -> dict:
    """orbitools API에서 Data Keeper 채널 상태 조회."""
    try:
        r = requests.get(
            f"{ORBITOOLS_BASE}/status/",
            auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[WARN] DataKeeper status 조회 실패: {e}")
        return {}


def get_gh_runs(hours: int = 24) -> list[dict]:
    """GitHub Actions 최근 실행 이력 조회."""
    if not GH_TOKEN or not GH_REPO:
        print("[WARN] GH_PAT / GITHUB_REPOSITORY 미설정 → 워크플로우 이력 스킵")
        return []
    try:
        since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(
            f"https://api.github.com/repos/{GH_REPO}/actions/runs",
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            params={"per_page": 50, "created": f">={since}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("workflow_runs", [])
    except Exception as e:
        print(f"[WARN] GitHub Actions 조회 실패: {e}")
        return []


# ── 분석 헬퍼 ────────────────────────────────────────────────────────

def classify_freshness(table_key: str, status: dict) -> tuple[str, str]:
    """
    Returns (emoji, age_str)
    🟢 fresh  🟡 stale  🔴 missing
    """
    info = status.get(table_key, {})
    if not info or not info.get("updated"):
        return "🔴", "데이터 없음"

    try:
        updated = datetime.fromisoformat(info["updated"].replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
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
    """워크플로우 파일별로 최신 실행 1건씩 추출."""
    seen = {}
    for r in sorted(runs, key=lambda x: x.get("created_at", ""), reverse=True):
        wf_file = r.get("path", "").split("/")[-1]  # .github/workflows/xxx.yml → xxx.yml
        if wf_file not in seen:
            seen[wf_file] = r
    return list(seen.values())


def get_next_schedules() -> list[dict]:
    """향후 12시간 이내 예정된 실행 목록."""
    upcoming = []
    now_pst = NOW_PST
    cutoff = now_pst + timedelta(hours=12)

    for wf in WORKFLOW_SCHEDULE:
        for t in wf["times"]:
            h, m = map(int, t.split(":"))
            # 오늘
            candidate = now_pst.replace(hour=h, minute=m, second=0, microsecond=0)
            # 이미 지났으면 내일
            if candidate <= now_pst:
                candidate += timedelta(days=1)
            if candidate <= cutoff:
                upcoming.append({
                    "label": wf["label"],
                    "time_pst": candidate.strftime("%m/%d %H:%M PST"),
                    "days": wf["days"],
                })

    upcoming.sort(key=lambda x: x["time_pst"])
    return upcoming


# ── HTML 이메일 생성 ──────────────────────────────────────────────────

def _status_badge(conclusion: str | None, status: str | None) -> str:
    if status == "in_progress":
        return '<span style="background:#1a73e8;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">🔄 실행 중</span>'
    mapping = {
        "success":   ('<span style="background:#0d6e2e;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">✅ 성공</span>', True),
        "failure":   ('<span style="background:#c0392b;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">❌ 실패</span>', False),
        "cancelled": ('<span style="background:#7f8c8d;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">⚪ 취소</span>', None),
        "skipped":   ('<span style="background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">⏭ 스킵</span>', None),
    }
    badge, _ = mapping.get(conclusion or "", ('<span style="background:#95a5a6;color:white;padding:2px 8px;border-radius:10px;font-size:11px;">— 알 수 없음</span>', None))
    return badge


def _time_ago(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 60:
            return f"{mins}분 전"
        return f"{mins // 60}시간 {mins % 60}분 전"
    except Exception:
        return iso_str


def build_html(dk_status: dict, gh_runs: list[dict]) -> str:
    period = "자정" if NOW_PST.hour < 12 else "정오"
    title  = f"ORBI Communicator — {NOW_PST.strftime('%Y-%m-%d')} {period} 리포트"
    ts_str = NOW_PST.strftime("%Y-%m-%d %H:%M PST")

    # ── 1. 데이터 상태 테이블 ────────────────────────────────────────
    data_rows_html = ""
    alert_items   = []
    fresh_count   = stale_count = missing_count = 0

    for key, meta in CHANNEL_META.items():
        emoji, age_str = classify_freshness(key, dk_status)
        info    = dk_status.get(key, {})
        rows    = info.get("rows", "—")
        dr      = info.get("date_range", "—")

        if emoji == "🟢":
            fresh_count += 1
            row_bg = "#f6fff8"
        elif emoji == "🟡":
            stale_count += 1
            row_bg = "#fffbf0"
            alert_items.append(f"⚠️ {meta['label']}: 데이터 지연 ({age_str})")
        else:
            missing_count += 1
            row_bg = "#fff5f5"
            alert_items.append(f"🔴 {meta['label']}: 데이터 없음")

        data_rows_html += f"""
        <tr style="background:{row_bg}">
            <td style="padding:8px 12px;border-bottom:1px solid #eee">{emoji} {meta['label']}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{age_str}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-variant-numeric:tabular-nums">{rows:,} rows</td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{dr}</td>
        </tr>"""

    # ── 2. 워크플로우 이력 테이블 ────────────────────────────────────
    run_rows_html  = ""
    fail_workflows = []

    if gh_runs:
        recent = summarize_runs(gh_runs)
        for run in recent:
            wf_name    = run.get("name", "—")
            wf_file    = run.get("path", "").split("/")[-1]
            label      = next((w["label"] for w in WORKFLOW_SCHEDULE if w["file"] == wf_file), wf_name)
            conclusion = run.get("conclusion")
            status     = run.get("status")
            badge      = _status_badge(conclusion, status)
            started_at = run.get("run_started_at", run.get("created_at", ""))
            ago        = _time_ago(started_at)
            run_url    = run.get("html_url", "#")

            # 소요 시간 계산
            duration_str = "—"
            if run.get("run_started_at") and run.get("updated_at") and conclusion:
                try:
                    s = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                    e = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                    sec = int((e - s).total_seconds())
                    duration_str = f"{sec // 60}분 {sec % 60}초"
                except Exception:
                    pass

            if conclusion == "failure":
                fail_workflows.append(f"❌ {label}: 최근 실행 실패 → <a href='{run_url}'>로그 확인</a>")

            run_rows_html += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #eee">{label}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{badge}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{ago}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:12px">{duration_str}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;font-size:11px">
                    <a href="{run_url}" style="color:#1a73e8">로그</a>
                </td>
            </tr>"""
    else:
        run_rows_html = '<tr><td colspan="5" style="padding:16px;text-align:center;color:#999">워크플로우 이력 없음 (GH_PAT 미설정 또는 최근 24시간 실행 없음)</td></tr>'

    # ── 3. 다음 예정 작업 ────────────────────────────────────────────
    upcoming     = get_next_schedules()
    upcoming_html = ""
    for item in upcoming:
        upcoming_html += f"""
        <tr>
            <td style="padding:7px 12px;border-bottom:1px solid #eee">⏰ {item['label']}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #eee;font-weight:bold">{item['time_pst']}</td>
            <td style="padding:7px 12px;border-bottom:1px solid #eee;color:#666">{item['days']}</td>
        </tr>"""
    if not upcoming_html:
        upcoming_html = '<tr><td colspan="3" style="padding:16px;text-align:center;color:#999">향후 12시간 이내 예정 작업 없음</td></tr>'

    # ── 4. 알림 섹션 ────────────────────────────────────────────────
    all_alerts = alert_items + fail_workflows
    alert_html = ""
    if all_alerts:
        alert_items_html = "".join(
            f'<li style="margin:4px 0">{a}</li>' for a in all_alerts
        )
        alert_html = f"""
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:14px 18px;margin:0 0 24px">
            <b style="color:#856404">⚠️ 주의 필요 ({len(all_alerts)}건)</b>
            <ul style="margin:8px 0 0;padding-left:20px;font-size:13px;color:#6b5900">
                {alert_items_html}
            </ul>
        </div>"""

    # ── 전체 헬스 배지 ──────────────────────────────────────────────
    total = len(CHANNEL_META)
    if missing_count > 0 or fail_workflows:
        health_color = "#c0392b"
        health_label = "주의 필요"
        health_dot   = "🔴"
    elif stale_count > 0:
        health_color = "#e67e22"
        health_label = "지연 있음"
        health_dot   = "🟡"
    else:
        health_color = "#0d6e2e"
        health_label = "정상"
        health_dot   = "🟢"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f4f6f9;font-family:'Apple SD Gothic Neo',Arial,sans-serif">
<div style="max-width:640px;margin:0 auto">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#1a1f2e 0%,#2d3556 100%);color:white;padding:24px 28px;border-radius:10px 10px 0 0">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <h1 style="margin:0;font-size:20px;font-weight:700">📡 ORBI Communicator</h1>
        <p style="margin:6px 0 0;opacity:0.75;font-size:13px">{ts_str}</p>
      </div>
      <div style="text-align:right">
        <div style="background:{health_color};display:inline-block;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600">
          {health_dot} {health_label}
        </div>
        <p style="margin:6px 0 0;opacity:0.65;font-size:12px">데이터: {fresh_count}✅ {stale_count}⚠️ {missing_count}🔴</p>
      </div>
    </div>
  </div>

  <!-- 본문 -->
  <div style="background:white;padding:28px;border:1px solid #e5e5e5;border-top:none;border-radius:0 0 10px 10px">

    {alert_html}

    <!-- 데이터 수집 상태 -->
    <h2 style="margin:0 0 14px;font-size:16px;color:#1a1f2e;border-bottom:2px solid #e5e5e5;padding-bottom:8px">
      📊 데이터 수집 현황
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:28px">
      <tr style="background:#f8f9fc">
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">채널</th>
        <th style="padding:9px 12px;text-align:center;font-weight:600;color:#555">최종 수집</th>
        <th style="padding:9px 12px;text-align:right;font-weight:600;color:#555">Row 수</th>
        <th style="padding:9px 12px;text-align:left;font-weight:600;color:#555">기간</th>
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

    <!-- 다음 예정 작업 -->
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


# ── 실행 ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ORBI Communicator - 통합 상태 이메일 발송")
    parser.add_argument("--dry-run",  action="store_true", help="이메일 미발송, HTML 콘솔 출력")
    parser.add_argument("--preview",  action="store_true", help=".tmp/communicator_preview.html 저장")
    parser.add_argument("--to",       default=RECIPIENT,   help="수신자 이메일")
    args = parser.parse_args()

    print(f"\n[Communicator] 시작 — {NOW_PST.strftime('%Y-%m-%d %H:%M PST')}")

    # 데이터 수집
    print("[1/2] Data Keeper 상태 조회 중...")
    dk_status = get_datakeeper_status()
    print(f"      {len(dk_status)}개 채널 조회됨")

    print("[2/2] GitHub Actions 이력 조회 중...")
    gh_runs = get_gh_runs(hours=24)
    print(f"      {len(gh_runs)}개 실행 이력 조회됨")

    # HTML 생성
    html = build_html(dk_status, gh_runs)

    # 프리뷰 저장
    if args.preview:
        preview_path = Path(__file__).resolve().parent.parent / ".tmp" / "communicator_preview.html"
        preview_path.parent.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        print(f"[Preview] 저장됨: {preview_path}")

    period  = "자정" if NOW_PST.hour < 12 else "정오"
    subject = f"[ORBI] {NOW_PST.strftime('%m/%d')} {period} 상태 리포트"

    if args.dry_run:
        print(f"\n[Dry Run] Subject: {subject}")
        print(html[:500] + "...")
        return

    # 이메일 발송
    print(f"\n[EMAIL] → {args.to}")
    from send_gmail import send_email
    result = send_email(to=args.to, subject=subject, body_html=html, sender=SENDER)
    print(f"[완료] 이메일 발송 완료 (ID: {result.get('id', '?')})")


if __name__ == "__main__":
    main()
