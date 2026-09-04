# -*- coding: utf-8 -*-
"""JP 수집 자가복구 + 축별 신선도 경보 (JPDash_Catchup, 3시간 간격)

문제(세은 발견): 09:20 로컬 수집 작업이 실행 도중 킬(0xC000013A)되면
rpp_daily / rakuten_sales_daily 축이 조용히 얼어붙는다. 기존 GH 감시자는 앱의
BUILD_AT 마커(=야간 빌드가 돌았나)만 봐서, 빌드는 매일 돌지만 한 축이 stale인
경우를 못 잡았다 → 세은이 매번 눈으로 발견해야 했다.

이 스크립트는 두 가지를 한다:
  1) 자가복구 — 각 축 JSON 의 최신일이 어제 미만이면 해당 collector 를 --update-app 로
     재실행해 스스로 메꾼다. PC 가 깨어 있는 한 대부분의 킬은 세은 모르게 치유된다.
  2) 축별 경보 — 재수집 후에도 여전히 stale 이면(예: 라쿠텐 로그인 파손) 그때만
     Teams + Gmail 2채널로 경보. 정상 복구는 조용히(경보 X).

정상(모든 축 fresh)이면 아무 것도 안 하고 조용히 종료 → 3시간마다 돌아도 소음 0.

사용:
  python tools/catchup_jp_collectors.py            # 점검 + 필요 시 자가복구/경보
  python tools/catchup_jp_collectors.py --dry-run  # 상태만 출력, 수집·경보 안 함
  python tools/catchup_jp_collectors.py --force-alert  # 경보 경로 테스트(1발 강제 발송)
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
PY = sys.executable

# .env 선로드 — TEAMS_WEBHOOK_URL_SEEUN 을 alert() 에서 읽으려면 이 시점에 로드돼야
# 한다(send_gmail import 시점의 load_env 는 너무 늦어 Teams 채널이 조용히 스킵됨).
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass

# 자가복구 축: (라벨, JSON 스토어, collector 스크립트, 재수집 타임아웃초)
AXES = [
    ("일별매출", ROOT / "data" / "rakuten_sales_daily.json",
     "tools/collect_rakuten_sales_daily.py", 300),
    ("RPP", ROOT / "data" / "rpp_daily.json",
     "tools/collect_rpp_daily.py", 360),
]

# 감시 전용 축: (라벨, 시드 경로, 허용 지연일, 조치 힌트)
# 자가복구 불가(체인/로그인 필요) — 신선도만 보고 stale이면 경보. 앱이 실제 읽는 시드 기준.
MONITOR = [
    ("라쿠텐 트래픽분해", ROOT / "meta-app" / "lib" / "traffic-daily-seed.json", 2,
     "build_jp_dash 미실행(JPDash 체인 실패/행). PC에서 체인 확인 필요."),
    ("아마존 트래픽분해", ROOT / "meta-app" / "lib" / "amz-traffic-seed.json", 3,
     "아마존 세션 로그인 필요 — br_traffic_login_collect.py 실행(로그인 1회)."),
]

LOG = ROOT / ".tmp" / "ceo_ads_report" / "logs" / f"catchup_{date.today():%Y%m%d}.log"
# 경보 dedup 상태 — 같은 정체 상태를 오늘 이미 알렸으면 3시간 사이클마다 재발송 안 함.
ALERT_STATE = ROOT / ".tmp" / "ceo_ads_report" / "catchup_alert_state.json"


def already_alerted_today(sig: str) -> bool:
    """오늘 같은 정체 시그니처로 이미 경보했으면 True (반복 발송 차단)."""
    try:
        st = json.loads(ALERT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return st.get("date") == date.today().isoformat() and st.get("sig") == sig


def mark_alerted_today(sig: str) -> None:
    try:
        ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE.write_text(
            json.dumps({"date": date.today().isoformat(), "sig": sig}), encoding="utf-8")
    except OSError:
        pass


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def max_day(store: Path) -> str | None:
    """스토어 내 가장 최근 날짜(YYYY-MM-DD) 또는 None."""
    if not store.exists():
        return None
    try:
        days = json.loads(store.read_text(encoding="utf-8")).get("days", {})
    except (json.JSONDecodeError, OSError):
        return None
    return max(days) if days else None


def run_collector(script: str, timeout: int) -> tuple[bool, str]:
    """collector --update-app 재실행. (성공여부, 마지막출력꼬리)."""
    try:
        r = subprocess.run(
            [PY, script, "--update-app"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        tail = (r.stdout or "")[-400:] + (("\n[stderr] " + r.stderr[-300:]) if r.stderr.strip() else "")
        return r.returncode == 0, tail.strip()
    except subprocess.TimeoutExpired:
        return False, f"타임아웃 {timeout}s 초과 — 수집 도중 지연/중단"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def alert(kind: str, text: str) -> None:
    """Teams 웹훅 + Gmail 2채널 동시 발송. 한쪽만 성공해도 발송 성공으로 본다.
    (웹훅 202 후 증발 전례 8/26·8/28~30 → 단독 신뢰 불가.)
    kind = 제목 구분(자동복구 실패 / 수집 정체(수동조치) 등) — 복구 불가축 정체를
    "자동복구 실패"로 오인하지 않도록 상황별 제목을 붙인다."""
    import os
    sent = []
    hook = os.getenv("TEAMS_WEBHOOK_URL_SEEUN")
    if hook:
        try:
            import urllib.request
            body = json.dumps({"text": text}).encode()
            req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15)
            sent.append("teams")
        except Exception as e:  # noqa: BLE001
            log(f"  [ALERT] teams 실패: {type(e).__name__}: {e}")
    try:
        os.environ.setdefault("GMAIL_OAUTH_CREDENTIALS_PATH", str(ROOT / "credentials" / "gmail_oauth_credentials.json"))
        os.environ.setdefault("GMAIL_TOKEN_PATH", str(ROOT / "credentials" / "gmail_token.json"))
        from send_gmail import send_email
        send_email(
            to="se.heo@orbiters.co.kr",
            subject="[JPDash 자가복구] 수집 축 정체 — 자동복구 실패",
            body_html=f"<p>{text}</p><p style='color:#888'>catchup_jp_collectors.py "
                      f"(로컬 JPDash_Catchup, 3h) — 재수집 시도 후에도 stale 이라 경보합니다.</p>",
        )
        sent.append("email")
    except Exception as e:  # noqa: BLE001
        log(f"  [ALERT] gmail 실패: {type(e).__name__}: {e}")
    log(f"  [ALERT] 발송 채널: {','.join(sent) if sent else '없음(둘 다 실패)'}")


def rebuild_and_deploy() -> tuple[bool, str]:
    """복구된 시드를 화면에 반영 — build_jp_dash(html 재생성) → deploy(vercel).
    catchup이 시드만 고치고 배포를 안 해 화면이 다음 정기체인까지 stale이던 구멍을 메운다.
    (build_jp_dash가 rpp/sales 시드를 읽어 html을 다시 만들어야만 화면에 반영됨.)"""
    import os
    build = ROOT / ".tmp" / "ceo_ads_report" / "build_jp_dash.py"
    deploy = ROOT / ".tmp" / "ceo_ads_report" / "deploy_to_meta_app.ps1"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        rb = subprocess.run([PY, str(build)], cwd=str(ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=900, env=env)
        if rb.returncode != 0:
            return False, "build_jp_dash 실패: " + ((rb.stderr or rb.stdout) or "")[-200:].strip()
        dp = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(deploy)], cwd=str(ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
        if dp.returncode != 0:
            return False, "deploy 실패: " + ((dp.stderr or dp.stdout) or "")[-200:].strip()
        return True, "build+deploy 완료 — 화면 반영됨"
    except subprocess.TimeoutExpired as e:
        return False, f"타임아웃: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="상태만 출력, 수집·경보 안 함")
    ap.add_argument("--force-alert", action="store_true", help="경보 경로 테스트(강제 1발)")
    args = ap.parse_args()

    if args.force_alert:
        alert("경보 경로 테스트",
              "[테스트] 경보 경로 점검 — 이 메시지가 Teams·Gmail 두 곳 모두에 보이면 정상. "
              "한쪽만 보이면 안 보인 채널이 죽은 것.")
        return 0

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    log(f"=== catchup 점검 (기대 최신일 >= {yesterday}) ===")

    # 자가복구축: 재수집 시도 후에도 stale이면 '진짜 이상(자동복구 실패)'.
    heal_failed = []
    did_heal = False  # 재수집으로 복구된 축이 하나라도 있으면 True → build+deploy로 화면 반영
    for label, store, script, timeout in AXES:
        cur = max_day(store)
        fresh = cur is not None and cur >= yesterday
        log(f"[{label}] 최신일={cur or 'NONE'} → {'fresh' if fresh else 'STALE'}")
        if fresh or args.dry_run:
            continue
        # 자가복구
        log(f"[{label}] 재수집 실행 ({script} --update-app)…")
        ok, tail = run_collector(script, timeout)
        new = max_day(store)
        healed = new is not None and new >= yesterday
        log(f"[{label}] 재수집 {'성공' if ok else '실패'} · 최신일={new or 'NONE'} → {'복구' if healed else '여전히 STALE'}")
        if healed:
            did_heal = True
        else:
            heal_failed.append(f"{label}(최신 {new or 'NONE'}, 기대 {yesterday}) — {tail[:180]}")

    # 감시 전용 축 — 자가복구 불가(체인/로그인 필요). stale이면 '수동조치 필요'로 분류.
    monitor_stale = []
    for label, seed, tol, hint in MONITOR:
        cur = max_day(seed)
        limit = (date.today() - timedelta(days=tol)).isoformat()
        fresh = cur is not None and cur >= limit
        log(f"[{label}] 최신일={cur or 'NONE'} (허용 {tol}일 지연) → {'fresh' if fresh else 'STALE'}")
        if not fresh:
            monitor_stale.append(f"{label}(최신 {cur or 'NONE'}) — {hint}")

    if args.dry_run:
        log("dry-run: 경보 안 함")
        return 0

    # 복구가 실제 일어났으면 화면에 반영 — 시드만 고치고 배포 안 해 화면이 다음
    # 정기체인까지 stale이던 구멍을 메운다. build_jp_dash(html 재생성) → deploy(vercel).
    if did_heal:
        ok, msg = rebuild_and_deploy()
        log(f"[배포] {msg}")

    if not heal_failed and not monitor_stale:
        log("OK: 모든 축 fresh (또는 자가복구 성공)")
        return 0

    # 제목·본문 분리 — 복구 불가축 정체를 '자동복구 실패'로 오인하지 않도록.
    parts = []
    if heal_failed:
        parts.append("자동복구 실패: " + " / ".join(heal_failed))
    if monitor_stale:
        parts.append("수동조치 필요(자가복구 불가축): " + " / ".join(monitor_stale))
    kind = "자동복구 실패" if heal_failed else "수집 정체(수동조치)"

    # dedup — 같은 정체 상태를 오늘 이미 알렸으면 3시간 사이클마다 반복 발송하지 않음.
    signature = "|".join(sorted(heal_failed + monitor_stale))
    if already_alerted_today(signature):
        log(f"경보 스킵(오늘 동일 상태 이미 발송): {kind}")
        return 1
    alert(kind, "  ·  ".join(parts))
    mark_alerted_today(signature)
    return 1


if __name__ == "__main__":
    sys.exit(main())
