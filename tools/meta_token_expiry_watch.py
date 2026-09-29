# -*- coding: utf-8 -*-
"""Meta 토큰 만료 사전 경보 — data_access_expires_at 이 임계일(기본 D-7) 이내면 세은에게 미리 알림.

배경: META_JP_ACCESS_TOKEN(LIVE·dev모드 우회)은 토큰 자체는 무기한이나 data_access 가
90일 주기로 만료된다. 만료되면 Graph 400 으로 wl/ih 자동집행이 전부 죽는다(2026-09-29 사고).
"만료된 후에 알았어" 를 막기 위해 매일 만료일을 체크해 1주일 전 미리 통보(세은 2026-09-29 지시).

판정: debug_token(app access token) → data_access_expires_at.
  - 남은 일수 <= threshold(기본 7) 이고 > 0 → 경보.
  - 이미 만료(<= 0) → 긴급 경보.
  - 무기한(0=만료없음) 또는 threshold 초과 → 조용(알림 없음).

사용: python tools/meta_token_expiry_watch.py [--dry-run] [--threshold-days N]
  --dry-run = 알림 미발송, 판정만 출력.
"""
import argparse, os, sys, urllib.parse, urllib.request, json
from datetime import datetime, timezone
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
import wl_d3_watchdog as w   # envget, notify

GV = "v21.0"

# 감시 대상 토큰: (라벨, 토큰 env키, app_id env키, app_secret env키)
# JP LIVE 토큰이 자동집행(wl/ih)의 단일 실패점. app 은 JP 전용(FB_APP_ID/SECRET).
WATCH = [
    ("META_JP_ACCESS_TOKEN (JP LIVE — wl/ih 자동집행)", "META_JP_ACCESS_TOKEN", "FB_APP_ID", "FB_APP_SECRET"),
]


def check_one(tok, appid, appsec):
    if not tok:
        return {"error": "토큰 env 부재"}
    if not (appid and appsec):
        return {"error": "app id/secret env 부재 — debug_token 불가"}
    apptok = f"{appid}|{appsec}"
    u = (f"https://graph.facebook.com/{GV}/debug_token"
         f"?input_token={urllib.parse.quote(tok)}&access_token={urllib.parse.quote(apptok)}")
    try:
        d = json.load(urllib.request.urlopen(u, timeout=30)).get("data", {})
    except Exception as e:
        return {"error": f"debug_token 실패: {str(e)[:150]}"}
    now = datetime.now(timezone.utc).timestamp()
    da = d.get("data_access_expires_at", 0) or 0
    ex = d.get("expires_at", 0) or 0
    # data_access 를 우선 기준(더 이른 실효 만료). 둘 다 0 이면 무기한.
    eff = min([t for t in (da, ex) if t > 0], default=0)
    return {
        "is_valid": d.get("is_valid"),
        "expires_at": ex,
        "data_access_expires_at": da,
        "eff_expiry": eff,
        "days_left": (eff - now) / 86400 if eff else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Meta 토큰 만료 사전 경보")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--threshold-days", type=int, default=7)
    args = ap.parse_args()

    alerts, lines = [], []
    for label, tk, ak, sk in WATCH:
        r = check_one(w.envget(tk), w.envget(ak), w.envget(sk))
        if r.get("error"):
            msg = f"⚠️ [{label}] 만료일 확인 실패 — {r['error']}"
            lines.append(msg)
            alerts.append(msg)   # 확인 실패도 경보(무음 진행 금지)
            continue
        dl = r["days_left"]
        if dl is None:
            lines.append(f"✅ [{label}] 무기한(만료없음)")
            continue
        exp_iso = datetime.fromtimestamp(r["eff_expiry"], tz=timezone.utc).date().isoformat()
        stat = f"[{label}] data_access 만료 {exp_iso} (D{dl:+.1f}일)"
        if dl <= 0:
            msg = f"🚨 만료됨 — {stat} · 즉시 재발급+GitHub Secret 갱신 필요"
            lines.append(msg); alerts.append(msg)
        elif dl <= args.threshold_days:
            msg = f"⏰ 만료 임박 — {stat} · {args.threshold_days}일 내 재발급 준비"
            lines.append(msg); alerts.append(msg)
        else:
            lines.append(f"✅ {stat} — 여유")

    report = "Meta 토큰 만료 점검\n\n" + "\n".join(lines)
    print(report)

    if alerts and not args.dry_run:
        subject = f"⏰ [Meta토큰] 만료 임박/실패 {len(alerts)}건 — 재발급 준비"
        print("\n알림:", w.notify(report, subject=subject))
    elif alerts:
        print(f"\n(dry-run) 경보 {len(alerts)}건 — 발송 생략")
    else:
        print("\n경보 없음 — 전 토큰 여유.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
