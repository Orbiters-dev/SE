# -*- coding: utf-8 -*-
"""메타 JP 졸업/OFF 자동 실행기 (2026-09-15 세은 위임).
- 졸업: 기존 Testing 크리에이티브(media+ig_user) 재사용 → 제품별 Proven 캠페인에 재생성(ACTIVE) + Testing PAUSE
- OFF:  Testing off / Proven CPLPV>150 / delivery 실패 → status=PAUSED
- 판정 = meta_jp_daily 빌더 재사용, on/off = Graph 실시간 status(절대룰6)
- 실행 전 스냅샷(롤백맵), 실행 후 보고. 무음 실패 금지.
사용: python tools/meta_jp_grad_off_executor.py [--dry-run] [--notify]
"""
import argparse, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
import meta_jp_daily as M
import wl_auto_upload as W
import wl_d3_watchdog as w

LIVE = w.envget("META_JP_ACCESS_TOKEN")
SYS = w.envget("META_JP_SYSUSER_TOKEN")
ACT = W.ACT
# Proven = 제품별 ABO ad set 1개에 asset(광고) 전부 투입 (세은 2026-09-15 교정 — adset 신설 금지).
# 졸업 = 아래 기존 Proven adset 에 ad(creative)만 추가.
PPSU_PROVEN_ADSET = "120248266438170223"       # Rakuten_Grosmimi_WL_PPSU_Proven_2026 (ABO ₩40K) — fliptop 공용
STAINLESS_PROVEN_ADSET = "120238769892260223"  # Rakuten_Grosmimi_WL_Stainless_Proven_2026 (ABO ₩160K)
SNAP_DIR = os.path.join(BASE, ".tmp", "grad_snapshots")


import re
_ASIN_RE = re.compile(r"_(B0[A-Z0-9]{8})(?:_|$)")
# 알려진 ASIN → 제품 (명시 매핑 — 신규 제품은 여기 추가해야 라우팅됨)
_ASIN_PRODUCT = {
    "B0G6CCJ24K": "stainless",
    "B0DJNXD66N": "fliptop",
    "B08TZY1TFY": "ppsu", "B0B9GLVWYN": "ppsu",
}
_PROVEN_ADSET = {"stainless": STAINLESS_PROVEN_ADSET, "ppsu": PPSU_PROVEN_ADSET, "fliptop": PPSU_PROVEN_ADSET}
# 공용 Proven adset (여러 광고 공유) — adset OFF 시 풀 전체 중단되므로 동반 OFF 절대 금지.
_SHARED_PROVEN_ADSETS = {PPSU_PROVEN_ADSET, STAINLESS_PROVEN_ADSET}


def pause_testing_adset(ad_id, dry):
    """Testing 광고 OFF 시 소속 ad set 도 동반 PAUSE (세은 2026-09-17 — '헷갈리니까').
    'testing 캠페인에 있는 애들만' 3중 가드:
      ① 호출측이 reason=='Testing off' 일 때만 진입
      ② Graph 실시간 campaign stage == testing 재확인 (절대룰6)
      ③ 공용 Proven adset 은 절대 제외 (풀 전체 중단 방지)
    조회 실패/비Testing/공용이면 skip + 사유 리턴 (무음 실패 금지).
    반환: (paused_bool, detail_str, adset_id_or_None)."""
    if not ad_id:
        return (False, "adset 동반 X: ad_id 없음", None)
    info = W.get(ad_id, LIVE, fields="adset{id},campaign{name}")
    if "err" in (info or {}) or not (info or {}).get("adset"):
        return (False, f"adset 동반 X: 조회 실패 {W.err_of(info or {}).get('message', '')[:50]}", None)
    adset_id = (info.get("adset") or {}).get("id")
    camp = (info.get("campaign") or {}).get("name", "")
    if M.adset_stage("", camp) != "testing":
        return (False, f"adset 동반 X: 비Testing 캠페인({camp[:28]})", adset_id)
    if adset_id in _SHARED_PROVEN_ADSETS:
        return (False, f"adset 동반 X: 공용 Proven adset {adset_id}", adset_id)
    if dry:
        return (True, f"adset {adset_id} 동반 OFF (예정)", adset_id)
    az = W.post(adset_id, LIVE, {"status": "PAUSED"})
    aok = az.get("success") or az.get("id")
    return (bool(aok), f"adset {adset_id} PAUSED={'OK' if aok else az}", adset_id)


def product_route(name):
    """광고명에서 ASIN 정확 추출(정규식) → (제품, 기존 Proven ad set id).
    ASIN 0개·복수·미매핑이면 (None,None) → 호출측이 skip+보고(오라우팅 방지)."""
    asins = set(_ASIN_RE.findall(name or ""))
    if len(asins) != 1:
        return (None, None)
    prod = _ASIN_PRODUCT.get(next(iter(asins)))
    if not prod:
        return (None, None)
    return (prod, _PROVEN_ADSET[prod])


def today_candidates():
    """meta_jp_daily 빌더 재사용 — 졸업 / OFF 3종 후보 (yday 기준)."""
    yday = (datetime.now(timezone.utc) + timedelta(hours=9)).date() - timedelta(days=1)
    ws = yday - timedelta(days=6)
    rows_7d = M.fetch("ad", time_range={"since": ws.isoformat(), "until": yday.isoformat()})
    bw_7d = M.best_worst_from_rows(rows_7d, min_impr=200, ref_date=yday)
    off_ids, off_rows = set(), []
    for pk, pool in bw_7d.get("pools", {}).items():
        if "testing" not in pk:
            continue
        for a in pool.get("members", []):
            dl = a.get("days_live")
            if dl is None or dl < M.OFF_MIN_DAYS:
                continue
            if M.off_rule_check(a, yday).get("off_recommend") and a.get("ad_id"):
                off_ids.add(a["ad_id"]); off_rows.append(a)
    grads = M.graduation_candidates(rows_7d, yday, off_ad_ids=off_ids)
    fs = yday - timedelta(days=13)
    r14 = M.fetch("ad", time_range={"since": fs.isoformat(), "until": yday.isoformat()})
    r14d = M.fetch("ad", time_range={"since": fs.isoformat(), "until": yday.isoformat()}, with_daily=True)
    dfail = M.delivery_failure_candidates(r14, r14d, yday)
    ms = yday - timedelta(days=29)
    g14 = M.graph_ad_rows_for_gate(fs, yday); g30 = M.graph_ad_rows_for_gate(ms, yday)
    r30 = None if g30 is not None else M.fetch("ad", time_range={"since": ms.isoformat(), "until": yday.isoformat()})
    proven = M.proven_cplpv_candidates(g14 if g14 is not None else r14, g30 if g30 is not None else r30, yday)
    dfl = dfail if isinstance(dfail, list) else dfail.get("candidates", [])
    pcl = proven.get("candidates", []) if isinstance(proven, dict) else proven

    # graduation_candidates/일부 OFF 후보는 ad_id 를 반환 dict 에 안 담음(ad_name 만) →
    # fetch 한 row 로 ad_name→ad_id 매핑 주입 (공유 meta_jp_daily 미변경).
    name2id = {}
    for row in (rows_7d or []) + (r14 or []):
        an, ai = row.get("ad_name"), row.get("ad_id")
        if an and ai:
            name2id.setdefault(an, ai)
    for c in grads + off_rows + dfl + pcl:
        if isinstance(c, dict) and not c.get("ad_id"):
            c["ad_id"] = name2id.get(c.get("ad_name"))
    return yday, grads, off_rows, dfl, pcl


def graduate(ad_id, name, dry):
    """Testing 광고의 기존 creative_id 를 재사용 → 제품별 Proven 캠페인에 adset+ad(ACTIVE) 신설 + Testing PAUSE.
    (소재 재빌드 X — 이미 유효한 branded content 크리에이티브를 그대로 재참조.) 반환 (status, detail, created)."""
    if not ad_id:
        return ("fail_no_ad_id", f"{(name or '')[:40]} — ad_id 없음(후보 결측)", None)
    info = W.get(ad_id, LIVE, fields="name,effective_status,creative{id}")
    if "err" in (info or {}):
        return ("fail_lookup", f"{name[:40]} — 광고 조회 오류(일시): {W.err_of(info).get('message', '')[:80]}", None)
    orig_status = (info or {}).get("effective_status")
    creative_id = ((info or {}).get("creative") or {}).get("id")
    prod, adset_id = product_route(name)
    if not adset_id:
        return ("fail_route", f"{name[:40]} — ASIN 미매핑/모호로 Proven 라우팅 불가", None)
    if not creative_id:
        return ("fail_no_creative", f"{name[:40]} — creative_id 조회 실패", None)
    if dry:
        return ("would_graduate", f"{name[:46]} → {prod} Proven adset {adset_id} 에 광고 추가 creative={creative_id} (Testing status={orig_status})", None)
    # 기존 제품별 Proven ABO ad set 에 광고(asset)만 추가 (adset 신설 X — 세은 2026-09-15 교정)
    ad = W.post(f"{ACT}/ads", LIVE, {"name": name, "adset_id": adset_id,
                                     "creative": json.dumps({"creative_id": creative_id}), "status": "ACTIVE"})
    if "id" not in ad:
        return ("fail_ad", f"{name[:40]} — ad 추가 실패: {W.err_of(ad).get('message')}", None)
    # Testing PAUSE — ad + 소속 Testing adset 동반 OFF.
    # 졸업도 Testing 쪽은 adset까지 끈다(세은 2026-09-17 'Testing off=ad+adset' 룰이 졸업 경로엔
    # 누락돼, 졸업건이 'adset ACTIVE + ad PAUSED' 엇박으로 남던 버그. 2026-10-06 재지시로 보강).
    # pause_testing_adset = ②Testing 캠페인 재확인 + ③공용 Proven adset 제외 가드 내장이라 안전.
    pz = W.post(ad_id, LIVE, {"status": "PAUSED"})
    _as_ok, adset_off_detail, _asid = pause_testing_adset(ad_id, False)
    # created: proven_ad 는 롤백 시 삭제 대상 / shared_adset 은 공용이라 삭제 금지
    created = {"proven_ad": ad["id"], "shared_adset": adset_id, "reused_creative": creative_id,
              "testing_ad": ad_id, "testing_orig_status": orig_status, "product": prod}
    return ("graduated", f"{name[:40]} → Proven adset {adset_id} 광고 {ad['id']} (Testing {ad_id} PAUSED={pz.get('success') or pz} | {adset_off_detail})", created)


def turn_off(ad_id, name, reason, dry):
    # Testing 캠페인 OFF = ad + 소속 ad set 동반 PAUSE (세은 2026-09-17 — 혼동 방지).
    # delivery 실패·Proven CPLPV 는 Proven 공용 adset 이라 ad 만 OFF (pause_testing_adset 가 재차 가드).
    testing = (reason == "Testing off")
    if dry:
        base = f"{name[:46]} [{ad_id}] — {reason}"
        asid = None
        if testing:
            _ok, adset_detail, asid = pause_testing_adset(ad_id, True)
            base += f" | {adset_detail}"
        return ("would_off", base, asid)
    pz = W.post(ad_id, LIVE, {"status": "PAUSED"})
    ok = pz.get("success") or pz.get("id")
    msg = f"{name[:40]} [{ad_id}] {reason} → PAUSED={pz}"
    asid = None
    if ok and testing:
        _ok2, adset_detail, asid = pause_testing_adset(ad_id, False)
        msg += f" | {adset_detail}"
    return ("off" if ok else "fail_off", msg, asid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()
    if not LIVE or not SYS:
        print("FATAL: 토큰 미설정"); sys.exit(1)

    yday, grads, off_rows, dfail, pcl = today_candidates()
    os.makedirs(SNAP_DIR, exist_ok=True)
    snap = {"yday": str(yday), "dry": args.dry_run, "grads": [], "offs": [], "created": []}

    lines = [f"[졸업/OFF 자동실행] 기준일 {yday} {'(DRY-RUN)' if args.dry_run else ''}"]
    # 졸업
    lines.append(f"■ 졸업 {len(grads)}건")
    for g in grads:
        aid, nm = g.get("ad_id"), g.get("ad_name", "")
        snap["grads"].append({"ad_id": aid, "name": nm})
        st, detail, created = graduate(aid, nm, args.dry_run)
        if created:
            snap["created"].append(created)
        lines.append(f"  [{st}] {detail}")
    # OFF (Testing off + delivery 실패 + Proven CPLPV)
    offs = ([("Testing off", a) for a in off_rows]
            + [("delivery 실패", a) for a in dfail]
            + [("Proven CPLPV>150", a) for a in pcl])
    lines.append(f"■ OFF {len(offs)}건")
    for reason, a in offs:
        aid, nm = a.get("ad_id"), a.get("ad_name", "")
        st, detail, adset_paused = turn_off(aid, nm, reason, args.dry_run)
        snap["offs"].append({"ad_id": aid, "name": nm, "reason": reason, "adset_paused": adset_paused})
        lines.append(f"  [{st}] {detail}")

    report = "\n".join(lines)
    print(report)
    snap_path = os.path.join(SNAP_DIR, f"grad_off_{yday}{'_dry' if args.dry_run else ''}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f"\n스냅샷: {snap_path}")
    if args.notify and not args.dry_run:
        try:
            print("알림:", w.notify(report, subject=f"[졸업/OFF] {yday} 졸업{len(grads)}·OFF{len(offs)}"))
        except Exception as e:
            print(f"WARN 알림 예외: {str(e)[:100]}")


if __name__ == "__main__":
    main()
