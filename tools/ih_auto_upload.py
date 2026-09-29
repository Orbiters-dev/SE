# -*- coding: utf-8 -*-
"""IH(자사) D+3 자동 광고화 — @grosmimi_japan 릴스 중 게시 D+3 경과 & 미광고 & 제품확정 건을
IH Testing 캠페인에 IH 광고(ACTIVE)로 생성. 매일 JST 9시 (WL wl_auto_upload 와 동형).

파이프라인:
  1) GET /{GROS_IG}/media (자사 릴스) → D+3 경과 & 최근창(기본 21일) 필터
  2) 기존 IH 광고 source media set 대조 → 이미 광고화된 건 skip
  3) 제품 = 캡션 명시 키워드로 판별(ステンレス→stainless / PPSU·スマートマグ→PPSU). 애매=hold(추측 금지)
  4) 생성: advideos(SYS) → creative(LIVE·자사·DOF standard_enhancements 폴백) → adset(ACTIVE) → ad(ACTIVE)
  5) 결과(생성 N·보류 M·이른D+3 대기) → 세은 알림(wl_d3_watchdog.notify 재사용)

절대 규칙:
  - 제품 캡션 미확정이면 절대 추측 업로드 X → 보류 리스트만.
  - 생성 = ACTIVE (세은 2026-09-22 지시. WL 과 동일 auto-ON).
사용: python tools/ih_auto_upload.py [--dry-run] [--no-notify] [--window-days N]
레시피 출처: memory/reference_ih_video_source_drive_naming.md · .tmp/ih_create_0918.py
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
import wl_d3_watchdog as w   # envget, notify

VER = "v23.0"
ACT = "act_4117678028561958"
GROS_IG = "17841473805016400"
IH_CAMP = "120250841109750223"       # Rakuten_IH_PPSU&Stainless_Testing
DAILY_BUDGET = "8000"                 # ₩8,000/day (WL Testing 동일)
D3_DAYS = 3                           # 게시 후 광고화 게이트
PPSU_LP = "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_strawcup300/"
STAINLESS_LP = "https://item.rakuten.co.jp/littlefingerusa/stainless_steel_strawcup_300/"
# 세은 2026-09-22: 메타 PPSU 영상 목적지 LP = fliptop 통일(채널 비교 — 틱톡=strawcup / 메타=fliptop).
FLIPTOP_LP = "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_onetouch_srawcup/"

TARGETING = {"age_max": 65, "age_min": 18,
    "geo_locations": {"countries": ["JP"], "location_types": ["frequently_in", "home", "recent"]},
    "brand_safety_content_filter_levels": ["FACEBOOK_RELAXED", "AN_RELAXED"],
    "targeting_automation": {"advantage_audience": 1}}
DOF_FULL = {"creative_features_spec": {
    "standard_enhancements": {"enroll_status": "OPT_IN"}, "text_optimizations": {"enroll_status": "OPT_IN"},
    "video_auto_crop": {"enroll_status": "OPT_IN"}, "video_filtering": {"enroll_status": "OPT_IN"},
    "video_uncrop": {"enroll_status": "OPT_IN"}}}
DOF_NOSE = {"creative_features_spec": {k: v for k, v in DOF_FULL["creative_features_spec"].items() if k != "standard_enhancements"}}


def _req(url, data=None):
    for i in range(3):
        try:
            r = urllib.request.Request(url, data=data, method="POST" if data else "GET")
            with urllib.request.urlopen(r, timeout=90) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code in (429, 500, 503) and i < 2:
                continue
            return {"err": e.code, "body": body}
        except (urllib.error.URLError, OSError, ValueError) as e:
            if i < 2:
                continue
            return {"err": "network", "body": str(e)[:200]}
    return {"err": "network", "body": "retries exhausted"}

def post(path, tok, payload):
    payload["access_token"] = tok
    return _req(f"https://graph.facebook.com/{VER}/{path}", data=urllib.parse.urlencode(payload).encode())

def get(path, tok, **p):
    p["access_token"] = tok
    return _req(f"https://graph.facebook.com/{VER}/{path}?" + urllib.parse.urlencode(p))

def emsg(r):
    try:
        e = json.loads(r["body"])["error"]; return e.get("error_user_msg") or e.get("message"), e.get("error_subcode")
    except Exception:
        return str(r.get("body") or r.get("err"))[:200], None


def resolve_ih_product(caption):
    """캡션 명시 키워드로 제품 판별. 애매(둘 다/둘 다 아님)=None → hold(추측 금지)."""
    c = caption or ""
    has_st = any(k in c for k in ("ステンレス", "保温", "保冷"))
    has_ppsu = any(k in c for k in ("PPSU", "スマートマグ"))
    if has_st and not has_ppsu:
        return ("stainless", STAINLESS_LP)
    if has_ppsu and not has_st:
        return ("PPSU", FLIPTOP_LP)   # 세은 2026-09-22: PPSU 영상은 fliptop LP 로 통일(라벨 PPSU 유지, LP 만 fliptop)
    return (None, None)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️❤]")
def theme_from_caption(caption):
    """캡션 첫 줄에서 테마 토큰 추출(이모지·기호 제거, 16자). 광고명 가독용 — 부정확해도 사후 rename 가능."""
    first = (caption or "").strip().splitlines()[0] if (caption or "").strip() else ""
    t = _EMOJI.sub("", first)
    t = re.sub(r"[\s、。！？!?…♡◎✔️「」『』（）()【】/\\\"'*#]+", "", t)
    return (t[:16] or "IH").strip()


def ih_covered_media(sysk):
    """기존 IH 캠페인 광고의 source/effective media id set (재광고 방지)."""
    ads = get(f"{IH_CAMP}/ads", sysk,
              fields="creative{source_instagram_media_id,effective_instagram_media_id}", limit="200")
    used = set()
    for a in ads.get("data", []):
        cr = a.get("creative") or {}
        for k in ("source_instagram_media_id", "effective_instagram_media_id"):
            if cr.get(k):
                used.add(cr[k])
    return used


def candidates(sysk, window_days):
    """자사 릴스 → (대상, 보류, 이른) 분류."""
    jst_today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    used = ih_covered_media(sysk)
    media = get(f"{GROS_IG}/media", sysk, fields="id,permalink,media_type,timestamp,caption", limit="50").get("data", [])
    ready, hold, early = [], [], []
    for m in media:
        if m.get("media_type") != "VIDEO":
            continue
        ts = (m.get("timestamp") or "")[:10]
        if not ts:
            continue
        try:
            pdate = datetime.strptime(ts, "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (jst_today - pdate).days
        if age > window_days:          # 오래된 백로그 제외(최근창만)
            continue
        if m["id"] in used:            # 이미 광고화
            continue
        if age < D3_DAYS:              # D+3 미경과 → 대기
            early.append((m, age)); continue
        prod, lp = resolve_ih_product(m.get("caption"))
        if not prod:                   # 제품 미확정 → 보류(추측 X)
            hold.append(m); continue
        ready.append((m, prod, lp))
    return jst_today, ready, hold, early


def build(m, prod, lp, dry):
    media = m["id"]
    theme = theme_from_caption(m.get("caption"))
    ymd = (m.get("timestamp") or "")[2:10].replace("-", "")   # YYMMDD
    name = f"{ymd}_{prod}_{theme}"
    if dry:
        return ("would_upload", f"{name} (media {media}) {m.get('permalink')}")
    utm = f"utm_source=traffic&utm_medium=meta&utm_campaign=IHV_Grosmimi&utm_content={prod}_" + urllib.parse.quote(theme)
    live, sysk = w.envget("META_JP_ACCESS_TOKEN"), w.envget("META_JP_SYSUSER_TOKEN")
    fbv = post(f"{ACT}/advideos", sysk, {"source_instagram_media_id": media})
    if "id" not in fbv:
        mm, sc = emsg(fbv); return ("fail_advideos", f"{name} — advideos 실패(sub {sc}): {mm}")
    def make_crea(dof):
        return post(f"{ACT}/adcreatives", live, {
            "name": name, "source_instagram_media_id": media, "instagram_user_id": GROS_IG,
            "call_to_action": json.dumps({"type": "LEARN_MORE", "value": {"link": lp}}),
            "url_tags": utm, "degrees_of_freedom_spec": json.dumps(dof),
            "contextual_multi_ads": json.dumps({"enroll_status": "OPT_IN"})})
    cr = make_crea(DOF_FULL)
    if "id" not in cr:
        mm, sc = emsg(cr)
        if sc == 3858504:
            cr = make_crea(DOF_NOSE)
        if "id" not in cr:
            mm, sc = emsg(cr); return ("fail_creative", f"{name} — 크리에이티브 실패(sub {sc}): {mm}")
    aset = post(f"{ACT}/adsets", live, {
        "name": name, "campaign_id": IH_CAMP, "daily_budget": DAILY_BUDGET, "billing_event": "IMPRESSIONS",
        "optimization_goal": "LANDING_PAGE_VIEWS", "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": json.dumps(TARGETING), "status": "ACTIVE"})
    if "id" not in aset:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://graph.facebook.com/{VER}/{cr['id']}?access_token={urllib.parse.quote(live)}", method="DELETE"), timeout=30)
        except Exception:
            pass
        mm, sc = emsg(aset); return ("fail_adset", f"{name} — adset 실패(크리에이티브 정리 시도, sub {sc}): {mm}")
    ad = post(f"{ACT}/ads", live, {"name": name, "adset_id": aset["id"],
                                   "creative": json.dumps({"creative_id": cr["id"]}), "status": "ACTIVE"})
    if "id" not in ad:
        mm, sc = emsg(ad); return ("fail_ad", f"{name} — 광고 실패(adset {aset['id']} 빈 상태, sub {sc}): {mm}")
    return ("uploaded", f"{name} (ad {ad['id']}) → ON")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--window-days", type=int, default=21)
    args = ap.parse_args()
    live, sysk = w.envget("META_JP_ACCESS_TOKEN"), w.envget("META_JP_SYSUSER_TOKEN")
    if not live or not sysk:
        print("FATAL: META_JP_ACCESS_TOKEN / META_JP_SYSUSER_TOKEN 미설정"); sys.exit(1)

    jst_today, ready, hold, early = candidates(sysk, args.window_days)
    lines = [f"[IH D+3 자동광고화] {jst_today} {'(DRY-RUN)' if args.dry_run else ''} — "
             f"대상 {len(ready)} · 보류(제품미상) {len(hold)} · D+3대기 {len(early)}"]
    uploaded, fails = [], []
    for m, prod, lp in ready:
        st, detail = build(m, prod, lp, args.dry_run)
        (uploaded if st in ("uploaded", "would_upload") else fails).append(detail)
        lines.append(f"  [{st}] {detail}")
    if hold:
        lines.append("■ 보류(제품 캡션 미확정 — 세은 확인):")
        for m in hold:
            cap = (m.get("caption") or "").replace("\n", " ")[:40]
            lines.append(f"   - {m.get('permalink')} | {cap}")
    if early:
        lines.append("■ D+3 대기(아직 이름):")
        for m, age in early:
            lines.append(f"   - D+{age} {m.get('permalink')}")
    report = "\n".join(lines)
    print(report)
    if not args.no_notify and not args.dry_run and (uploaded or fails or hold):
        try:
            print("알림:", w.notify(report, subject=f"[IH D+3] {jst_today} 생성{len(uploaded)}·보류{len(hold)}"))
        except Exception as e:
            print(f"WARN 알림 예외: {str(e)[:100]}")


if __name__ == "__main__":
    main()
