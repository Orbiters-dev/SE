"""Rakuten 주문 파이프라인 로컬 실행기.

세은 PC에서 전체 파이프라인을 순서대로 실행하고,
완료 후 결과를 n8n webhook으로 보내 Teams 알림을 자동 전송한다.

실행 순서:
  1. rakuten_order_confirm.py  — RMS 주문확인+발송메일 (100→500, 한 세션)
     ↓ 10분 대기 (KSE 반영 대기, --no-wait로 생략 가능)
  2. kse_rakuten_order.py      — KSE 주문수집+옵션코드+배송접수
  3. fill_kseoms_option_code.py — KSE 옵션코드 보정
  4. rakuten_tracking_input.py — RMS 송장번호 입력

Usage:
    python tools/run_rakuten_pipeline.py --headed
    python tools/run_rakuten_pipeline.py --headed --dry-run   # 조회만
    python tools/run_rakuten_pipeline.py --headed --skip-confirm  # Step 1 건너뛰기
"""
import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DIR = Path(__file__).parent
PROJECT_ROOT = DIR.parent
sys.path.insert(0, str(DIR))
from env_loader import load_env

load_env()

PYTHON = sys.executable
TEAMS_WEBHOOK_SEEUN = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")


def run_step(script: str, name: str, args: list[str] = None) -> dict:
    """스크립트 실행 후 결과 반환."""
    cmd = [PYTHON, str(DIR / script)] + (args or [])
    print(f"\n{'─' * 50}")
    print(f"  ▶ {name}")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"{'─' * 50}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,  # 5분 타임아웃
            cwd=str(PROJECT_ROOT),
        )

        # stdout 출력
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-15:]:
                print(f"  {line}")

        if result.returncode == 0:
            print(f"  ✓ {name} 완료")
        else:
            print(f"  ✗ {name} 실패 (exit={result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    print(f"  [ERR] {line}")

        # 마지막 줄에서 주요 숫자 추출
        last_lines = result.stdout.strip().split("\n")[-5:] if result.stdout else []
        detail = " / ".join(l.strip() for l in last_lines if l.strip() and ("건" in l or "완료" in l or "발송" in l or "입력" in l))

        return {
            "name": name,
            "success": result.returncode == 0,
            "detail": detail or ("성공" if result.returncode == 0 else "실패"),
        }

    except subprocess.TimeoutExpired:
        print(f"  ✗ {name} 타임아웃 (5분 초과)")
        return {"name": name, "success": False, "detail": "타임아웃 (5분 초과)"}
    except Exception as e:
        print(f"  ✗ {name} 오류: {e}")
        return {"name": name, "success": False, "detail": str(e)}


def send_to_teams(steps: list, total_orders: int = 0):
    """Teams 웹훅으로 파이프라인 결과 직접 전송 (심플 텍스트)."""
    if not TEAMS_WEBHOOK_SEEUN:
        print("  [WARN] TEAMS_WEBHOOK_URL_SEEUN 미설정")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    all_success = all(s["success"] for s in steps)
    success_count = sum(1 for s in steps if s["success"])

    lines = []
    if all_success:
        lines.append(f"**{date_str} Rakuten 주문 파이프라인 완료**")
    else:
        lines.append(f"**{date_str} Rakuten 파이프라인 ({success_count}/{len(steps)} 성공)**")

    lines.append("")
    for s in steps:
        icon = "v" if s["success"] else "x"
        lines.append(f"{icon} {s['name']}")
        if s.get("detail"):
            lines.append(f"   {s['detail']}")

    if total_orders > 0:
        lines.append("")
        lines.append(f"총 {total_orders}건 처리 완료.")
    lines.append("")
    lines.append("주문 들어온 것 공유드립니다.")

    text = "\n".join(lines)

    print(f"\n{'=' * 50}")
    print(f"  Teams 직접 전송 중...")

    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(TEAMS_WEBHOOK_SEEUN, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status in (200, 202):
                print(f"  [OK] Teams 직접 전송 완료")
            else:
                print(f"  [WARN] Teams 응답: {r.status}")

    except Exception as e:
        print(f"  [WARN] Teams 전송 실패: {e}")
        print(f"  (파이프라인 자체는 정상 완료됨)")


def main():
    parser = argparse.ArgumentParser(description="Rakuten 주문 파이프라인 로컬 실행")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--dry-run", action="store_true", help="조회만 (실제 처리 안 함)")
    parser.add_argument("--skip-confirm", action="store_true", help="Step 1 주문확인+발송메일 건너뛰기")
    parser.add_argument("--skip-kse", action="store_true", help="Step 2~3 KSE 건너뛰기")
    parser.add_argument("--skip-tracking", action="store_true", help="Step 4 송장번호 건너뛰기")
    parser.add_argument("--no-wait", action="store_true", help="RMS→KSE 10분 대기 생략")
    parser.add_argument("--no-notify", action="store_true", help="Teams 알림 안 보냄")
    args = parser.parse_args()

    mode_args = []
    if args.headed:
        mode_args.append("--headed")
    if args.dry_run:
        mode_args.append("--dry-run")

    print(f"\n{'=' * 60}")
    print(f"  Rakuten 주문 파이프라인")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print(f"  [DRY-RUN] 조회만 합니다")
    print(f"{'=' * 60}")

    steps = []

    # Step 1: RMS 주문확인 + 발송메일 (한 세션에서 처리)
    if not args.skip_confirm:
        result = run_step("rakuten_order_confirm.py", "Step 1: RMS 주문확인+발송메일 (100→500)", mode_args)
        steps.append(result)

        # RMS → KSE 10분 대기 (KSE에 주문 반영 대기)
        if result["success"] and not args.skip_kse and not args.dry_run and not args.no_wait:
            wait_min = 10
            print(f"\n  ⏳ KSE 주문 반영 대기 ({wait_min}분)...")
            import time as _t
            _t.sleep(wait_min * 60)
            print(f"  ✓ 대기 완료")

    # Step 2: KSE 주문수집 + 옵션코드 + 배송접수
    if not args.skip_kse:
        result = run_step("kse_rakuten_order.py", "Step 2: KSE 주문수집+옵션코드+배송접수", mode_args)
        steps.append(result)

    # Step 3: 옵션코드 보정
    if not args.skip_kse:
        result = run_step("fill_kseoms_option_code.py", "Step 3: KSE 옵션코드 보정", mode_args)
        steps.append(result)

    # Step 4: 송장번호 입력
    if not args.skip_tracking:
        result = run_step("rakuten_tracking_input.py", "Step 4: RMS 송장번호 입력", mode_args)
        steps.append(result)

    # ── 결과 요약 ──
    print(f"\n{'=' * 60}")
    print(f"  파이프라인 완료")
    print(f"{'=' * 60}")
    for s in steps:
        icon = "✅" if s["success"] else "❌"
        print(f"  {icon} {s['name']}: {s['detail']}")

    success_count = sum(1 for s in steps if s["success"])
    print(f"\n  결과: {success_count}/{len(steps)} 성공")

    # ── Teams 직접 알림 ──
    if not args.no_notify and not args.dry_run:
        send_to_teams(steps)
    elif args.dry_run:
        print(f"\n  [DRY-RUN] Teams 알림 생략")


if __name__ == "__main__":
    main()
