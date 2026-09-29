# -*- coding: utf-8 -*-
"""WL D+3 자동집행 — 감시견(wl_d3_watchdog)이 감지한 미부착 게시물 중
정성 심사 통과(인간 2차 집행) & 제품 확정된 것만 Meta WL 광고로 자동 생성 후 auto-ON 한다. 매일 JST 9시 실행.

파이프라인:
  1) 원장(DK ∪ 폼) ∪ Graph 커버 대조 → D+3 미부착 게시물 추출 (감시견 재사용)
  2) 정성 심사 게이트 — "JP Content Review" 시트에서 인간 2차 확정 & 집행 판정된 shortcode 만 통과
     (AI 1차만·미집행·미심사는 스킵. 심사 목록 로드 실패 시 안전측 집행 중단)
  3) 각 건: resolve(SYS 영구토큰) → 제품확정(폼 통합탭) → 크리에이티브(LIVE) → adset+광고 생성 → auto-ON
  4) 제품 미상 / WL권한 없음(resolve 실패) / 저작권 음악(2875030) = 업로드 안 함 → 보류 리스트
  5) 결과(업로드 N · 보류 M 사유별) → 세은 알림(감시견 notify 재사용). 하드 실패 있으면 exit 1.

절대 규칙:
  - 집행 대상 = 정성 심사 통과분만 (인간 2차 verdict=집행). AI 1차만으론 절대 집행 X.
  - 광고는 PAUSED 로 선생성(생성단계 실패 시 무지출 고아 방지) 후 즉시 auto-ON(adset+ad ACTIVE).
    세은 2026-09-22 위임. 예산 ₩8,000/day · LPV · Testing 캠페인.
  - 제품 확정 안 되면 절대 추측 업로드 X → 보류 알림만.
  - resolve/business_discovery/advideos = SYS(META_JP_SYSUSER_TOKEN, 만료없음)
    크리에이티브·광고·adset 생성 = LIVE(META_JP_ACCESS_TOKEN, dev모드 우회)
    (reference_meta_jp_sysuser_permanent_token · reference_meta_wl_branded_ad_api_creation)

사용: python tools/wl_auto_upload.py [--dry-run] [--no-notify]
      --dry-run  = 업로드/알림 없이 계획만 출력 (심사 게이트·제품매핑까지 판정)
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import wl_d3_watchdog as w   # covered_sets, ledger_dk, ledger_form, hnorm, envget, D3_CUT, notify

ACT = "act_4117678028561958"
GROS_IG = "17841473805016400"
GRAPH_VER = "v23.0"   # 2026-09 실측 생존(v21~v24 모두 OK). 만료 에러 시 이 상수만 상향 후 재검증.
CAMPAIGN_ID = "120248267687980223"   # Rakuten WL Testing 캠페인 (템플릿 adset의 campaign_id)
DAILY_BUDGET = "8000"                 # ₩8,000/day (게이트3 Testing 예산)
TODAY = date.today()
DATE_PREFIX = f"Y{TODAY.strftime('%y')}M{TODAY.strftime('%m')}D{TODAY.strftime('%d')}"

# 폼 통합 탭 (희망제품 원장) — 투고완료 탭(감시견 FORM_TAB_ID)과 별개
FORM_SHEET_ID = w.FORM_SHEET_ID
FORM_WISH_TAB = "통합"

# 정성 심사 게이트 (2026-09-23) — 인간 2차 확정 & 집행 판정된 게시물만 자동집행.
# 시트 = meta-app "JP Content Review" (review-store.ts 와 동일). AI 1차만(reviewed_at 없음)·미집행은 제외.
REVIEW_SHEET_ID = os.getenv("TAG_SHEET_ID") or "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
REVIEW_TAB = "JP Content Review"

TARGETING = {
    "age_max": 65, "age_min": 18,
    "geo_locations": {"countries": ["JP"], "location_types": ["frequently_in", "home", "recent"]},
    "brand_safety_content_filter_levels": ["FACEBOOK_RELAXED", "AN_RELAXED"],
    "targeting_automation": {"advantage_audience": 1},
}

# 제품 매핑 (product_color_size_options.md 기준) — 라쿠텐 LP
PPSU_LP = "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_strawcup300/"
STAINLESS_LP = "https://item.rakuten.co.jp/littlefingerusa/stainless_steel_strawcup_300/"
# ⚠️ onetouch 슬러그의 "srawcup"(t 누락)은 오타 아님 — 라쿠텐에 그 철자로 등록된 실제 상품 URL.
# 프로덕션 SSOT(.tmp/wl_complete_0902.py ohana 건·reference_meta_wl_branded_ad_api_creation)와 일치. 임의 "strawcup" 교정 금지.
ONETOUCH_LP = "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_onetouch_srawcup/"


def resolve_product(blob):
    """폼 행 텍스트 → (ASIN, LP, utm) 또는 None(제품 확정 불가).
    라인 확정은 색상/키워드 우선 — 용량만으론 라인 단정 금지(product_color_size_options 주의)."""
    b = blob.lower()
    has300, has200 = ("300" in b), ("200" in b)
    # 스텐: 색상명(ベアバター/オリーブピスタチオ/チェリーピーチ) 또는 ステンレス/スマート. 200/300 동일 ASIN(사이즈 variant)
    if any(k in blob for k in ("ステンレス", "スマート", "ベアバター", "オリーブピスタチオ", "チェリーピーチ")) or "stainless" in b:
        return ("B0G6CCJ24K", STAINLESS_LP, "Stainless")
    # 원터치/후립톱
    if any(k in blob for k in ("ワンタッチ", "フリップ")) or any(k in b for k in ("onetouch", "fliptop")):
        return ("B0DJNXD66N", ONETOUCH_LP, "Fliptop")
    # PPSU 스트로마그 (기본) — 색상 バター/ホワイト/チャコール/ピンク/スカイブルー
    if any(k in blob for k in ("ストローマグ", "PPSU", "バター", "ホワイト", "チャコール", "ピンク", "スカイブルー")) or "ppsu" in b:
        # 세은 2026-09-22: 메타 PPSU 영상은 목적지 LP 를 fliptop 으로 통일(채널 비교 — 틱톡=strawcup / 메타=fliptop).
        # ASIN(영상 제품 식별자)·라벨은 PPSU 유지, 목적지 LP 만 fliptop.
        if has300 and not has200:
            return ("B08TZY1TFY", ONETOUCH_LP, "PPSU")
        if has200 and not has300:
            return ("B0B9GLVWYN", ONETOUCH_LP, "PPSU")
        return None   # 사이즈 모호/부재 → 확정 불가 (추측 금지)
    return None


def load_approved_shortcodes():
    """정성 심사 게이트 — "JP Content Review" 시트에서 인간 2차 확정 & 집행 판정된 shortcode set.
    조건: reviewed_at 존재(인간 2차 완료) AND verdict == "집행". AI 1차만·미집행은 제외.
    실패 시 예외를 올림 → 호출자가 안전측(집행 중단)으로 처리."""
    from sheets_utils import get_sheets_client
    gc = get_sheets_client()
    ws = gc.open_by_key(REVIEW_SHEET_ID).worksheet(REVIEW_TAB)
    rows = ws.get_all_values()
    if not rows:
        return set()
    hdr = rows[0]
    def ix(n):
        return hdr.index(n) if n in hdr else -1
    i_sc, i_rev, i_verd = ix("shortcode"), ix("reviewed_at"), ix("verdict")
    if min(i_sc, i_rev, i_verd) < 0:
        raise RuntimeError(f"심사 시트 헤더 불일치 (shortcode/reviewed_at/verdict) — {hdr[:5]}")
    approved = set()
    for r in rows[1:]:
        def c(i):
            return r[i].strip() if 0 <= i < len(r) else ""
        if c(i_sc) and c(i_rev) and c(i_verd) == "집행":
            approved.add(c(i_sc))
    return approved


def load_form_wishes():
    """폼 통합 탭 → {hnorm(handle): (row_blob, is_paid)}.
    유상 판정: 행에 '유상/有償/paid/¥/円' 또는 금액 표기가 있으면 WL-P 후보(보수적으로 WL-G 기본)."""
    from google.oauth2.service_account import Credentials
    import gspread
    creds = Credentials.from_service_account_file(
        os.path.join(BASE, "credentials", "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    sh = gspread.authorize(creds).open_by_key(FORM_SHEET_ID)
    ws = next((x for x in sh.worksheets() if x.title == FORM_WISH_TAB), None)
    if ws is None:
        raise ValueError(f"폼 '{FORM_WISH_TAB}' 탭 없음 — 시트 구조 변경 확인")
    out = {}
    for row in ws.get_all_values():
        blob = " ".join(row)
        for cell in row:
            c = cell.strip()
            c = re.sub(r"^[@＠]+", "", c)   # 선행 @ / 전각＠(U+FF20) 제거 — 세은 폼에 전각＠ 혼용(nicogaku_log 누락 사고 2026-09-23)
            # 핸들 셀 = 영숫자_. (후행 （메모） 허용). IG 유저명 최대 30자. 이메일(@중간)·일본어명은 매칭 안 됨.
            if re.fullmatch(r"[A-Za-z0-9_.]{3,30}(（.*）)?", c) and re.search(r"[A-Za-z]", c):
                h = w.hnorm(re.split(r"[（(]", c)[0])
                if h and h not in out:
                    is_paid = bool(re.search(r"有償|有料|paid|¥|円|,000", blob, re.I))
                    out[h] = (blob, is_paid)
    return out


def _request(url, data=None):
    """Graph 요청 — HTTP/네트워크 오류를 err dict로 정규화(크래시·행 방지) + 429/500 백오프 재시도."""
    for i in range(3):
        try:
            req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=60) as r:
                obj = json.load(r)
            return obj if isinstance(obj, dict) else {"data": obj}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code in (429, 500, 503) and i < 2:
                time.sleep(10 * (i + 1))
                continue
            return {"err": e.code, "body": body}
        except (urllib.error.URLError, OSError, ValueError) as e:
            if i < 2:
                time.sleep(10 * (i + 1))
                continue
            return {"err": "network", "body": str(e)[:300]}
    return {"err": "network", "body": "retries exhausted"}


def get(path, tok, **p):
    p["access_token"] = tok
    return _request(f"https://graph.facebook.com/{GRAPH_VER}/{path}?" + urllib.parse.urlencode(p))


def post(path, tok, payload):
    payload["access_token"] = tok
    return _request(f"https://graph.facebook.com/{GRAPH_VER}/{path}", data=urllib.parse.urlencode(payload).encode())


def err_of(resp):
    try:
        return json.loads(resp["body"])["error"]
    except Exception:
        return {"message": str(resp.get("body") or resp.get("err"))[:200]}


def uncovered_d3(cov):
    """감시견 원장(DK ∪ 폼) vs 커버 → 미부착 D+3 건 [{sc, handle, ct, d}]."""
    ledger = {}
    for src in (w.ledger_dk, w.ledger_form):
        try:
            for k, v in src().items():
                ledger.setdefault(k, v)
        except Exception as e:
            print(f"WARN: 원장 소스 실패 — {str(e)[:120]}")
    items = []
    for key, info in sorted(ledger.items(), key=lambda kv: kv[1].get("d") or ""):
        if key.startswith("dm:"):
            continue  # URL 없는 DM 보고는 shortcode 없어 자동업로드 불가 (감시견 알림에 맡김)
        d = info.get("d")
        if d and d > w.D3_CUT:
            continue
        sc, ct, hn = key, info.get("ct"), w.hnorm(info.get("u"))
        if (ct and ct in cov["ad_ct"]) or (sc in cov["ad_sc"]):
            continue
        adset = (cov["adset_by_ct"].get(ct) if ct else None) or cov["adset_by_sc"].get(sc)
        if adset and adset["has_ads"]:
            continue
        items.append({"sc": sc, "handle": info.get("u"), "ct": ct, "d": d})
    return items


def build_name(handle, asin, ct, sc, deal):
    """광고명 7토큰(reference_adname_framework_v1). CT = DK 숫자 id 정본,
    미적재면 shortcode(CT-NEW 금지 — feedback_no_ctnew_placeholder). DK 적재 후 감시견이 숫자 CT로 정정."""
    htok = re.sub(r"[^A-Za-z0-9]", "_", handle or "").upper().strip("_")
    ctval = ct if ct else sc
    return f"{DATE_PREFIX}_Grosmimi_RKT_WL-{deal}_{htok}_{asin}_CT-{ctval}"


def upload_one(item, product, is_paid, dry=False):
    """단건 업로드. 반환 (status, detail).
    status: uploaded / would_upload / skip_music / hold_no_perm / hold_no_creator / fail_*"""
    sc, handle, ct = item["sc"], item["handle"], item["ct"]
    asin, lp, utmp = product
    deal = "P" if is_paid else "G"
    name = build_name(handle, asin, ct, sc, deal)
    live, sysk = w.envget("META_JP_ACCESS_TOKEN"), w.envget("META_JP_SYSUSER_TOKEN")
    utm = f"utm_source=traffic&utm_medium=meta&utm_campaign=UGC_Grosmimi&utm_content={utmp}_{re.sub(r'[^a-z0-9]', '', (handle or '').lower())}"

    # 1) resolve (WL 광고권한 실측). API 오류(err)=일시 실패로 분리 — 정상 200+빈 data 만 "권한없음"
    res = get(f"{GROS_IG}/branded_content_advertisable_medias", sysk, permalinks=json.dumps([sc]))
    if "err" in res:
        return ("fail_resolve", f"@{handle} {sc} — resolve API 오류(일시): {err_of(res).get('message', '')[:80]}")
    data = res.get("data") or []
    if not data:
        return ("hold_no_perm", f"@{handle} {sc} — WL광고권한 없음(advertisable 미반환)")
    media = data[0]["id"]
    # 2) creator ig. API 오류=일시 실패, 정상응답인데 id 없음=실제 조회불가
    bd = get(GROS_IG, sysk, fields=f"business_discovery.username({handle}){{id}}")
    if "err" in bd:
        return ("fail_creator", f"@{handle} — business_discovery API 오류(일시): {err_of(bd).get('message', '')[:80]}")
    cig = (bd.get("business_discovery") or {}).get("id")
    if not cig:
        return ("hold_no_creator", f"@{handle} — 크리에이터 IG 조회 불가(비공개/비즈니스계정 아님)")
    if dry:
        return ("would_upload", f"@{handle} {sc} → {name} (media {media})")
    # 3) FB 복사본 (REELS 필수) — 결과 검증(무시 시 후속 단계 오귀인)
    fbv = post(f"{ACT}/advideos", sysk, {"source_instagram_media_id": media})
    if "id" not in fbv:
        return ("fail_advideos", f"@{handle} {sc} — FB 복사 실패: {err_of(fbv).get('message')}")
    # 4) 크리에이티브 (LIVE) — 음악블록/기타 여기서 걸림
    cr = post(f"{ACT}/adcreatives", live, {
        "name": name, "source_instagram_media_id": media, "instagram_user_id": cig,
        "instagram_branded_content": json.dumps({"sponsor_id": GROS_IG}),
        "call_to_action": json.dumps({"type": "LEARN_MORE", "value": {"link": lp}}),
        "url_tags": utm, "contextual_multi_ads": json.dumps({"enroll_status": "OPT_IN"})})
    if "id" not in cr:
        e = err_of(cr)
        if e.get("error_subcode") == 2875030:
            return ("skip_music", f"@{handle} {sc} — 저작권 음악 릴스(광고 홍보 불가)")
        return ("fail_creative", f"@{handle} {sc} — 크리에이티브 실패: {e.get('error_user_msg') or e.get('message')}")
    # 5) adset (PAUSED). 실패 시 방금 만든 크리에이티브 정리(고아 방지)
    adset = post(f"{ACT}/adsets", live, {
        "name": name, "campaign_id": CAMPAIGN_ID, "daily_budget": DAILY_BUDGET,
        "billing_event": "IMPRESSIONS", "optimization_goal": "LANDING_PAGE_VIEWS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "targeting": json.dumps(TARGETING), "status": "PAUSED"})
    if "id" not in adset:
        try:   # 고아 크리에이티브 정리 — 진짜 HTTP DELETE.
            urllib.request.urlopen(urllib.request.Request(
                f"https://graph.facebook.com/{GRAPH_VER}/{cr['id']}?access_token={urllib.parse.quote(live)}",
                method="DELETE"), timeout=30)
        except Exception as ex:   # 삭제 실패해도 무해(미부착·무지출)나 추적 위해 로깅 — 수동 정리 대상
            print(f"WARN: 고아 크리에이티브 {cr['id']} 삭제 실패(수동 정리 필요): {str(ex)[:80]}")
        return ("fail_adset", f"@{handle} — adset 실패(크리에이티브 {cr['id']} 정리 시도됨): {err_of(adset).get('message')}")
    # 6) 광고 (PAUSED 로 생성 → 아래서 auto-ON. 생성단계 실패 시 무지출 고아 방지 위해 PAUSED 선생성)
    ad = post(f"{ACT}/ads", live, {"name": name, "adset_id": adset["id"],
                                    "creative": json.dumps({"creative_id": cr["id"]}), "status": "PAUSED"})
    if "id" not in ad:
        return ("fail_ad", f"@{handle} — 광고 실패(adset {adset['id']} 빈 상태): {err_of(ad).get('message')}")
    # 7) auto-ON — adset+ad 동반 ACTIVE (세은 2026-09-22 위임. Testing 1:1 구조라 동반 ON 안전).
    #    ON = adset 먼저(예산 게이트 열기) → ad. 실패해도 광고는 생성됨 → status 는 uploaded 유지하고
    #    ON 결과를 detail 에 붙여 보고(무음 X). 새 status 는 만들지 않음(main 버킷 정합).
    on_as = post(adset["id"], live, {"status": "ACTIVE"})
    on_ad = post(ad["id"], live, {"status": "ACTIVE"})
    as_ok, ad_ok = (on_as.get("success") or on_as.get("id")), (on_ad.get("success") or on_ad.get("id"))
    if as_ok and ad_ok:
        on_detail = "ON(adset+ad)"
    else:
        on_detail = ("⚠ auto-ON 실패 — "
                     f"adset ON={'OK' if as_ok else err_of(on_as).get('message','?')[:60]} / "
                     f"ad ON={'OK' if ad_ok else err_of(on_ad).get('message','?')[:60]}")
    return ("uploaded", f"@{handle} {name} (ad {ad['id']}) → {on_detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    live, sysk = w.envget("META_JP_ACCESS_TOKEN"), w.envget("META_JP_SYSUSER_TOKEN")
    if not sysk or not live:
        print("FATAL: META_JP_SYSUSER_TOKEN / META_JP_ACCESS_TOKEN 미설정")
        sys.exit(1)
    me = get("me", sysk, fields="id,name")   # SYS 토큰 생존 확인(만료없음이나 무효화 방어)
    if "id" not in me:
        print(f"FATAL: SYS 토큰 무효 — {me}")
        sys.exit(1)

    cov = w.covered_sets(live)
    items = uncovered_d3(cov)
    print(f"[{TODAY}] D+3 미부착 {len(items)}건 (컷 {w.D3_CUT})")

    # 정성 심사 게이트 — 인간 2차 확정 & 집행 판정된 게시물만 자동집행.
    # 로드 실패 = 승인 여부 판정 불가 → 안전측으로 집행 전면 중단(추측 집행 방지).
    try:
        approved = load_approved_shortcodes()
        print(f"[심사] 인간 2차 집행 승인 {len(approved)}건")
    except Exception as e:
        print(f"FATAL: 정성 심사 승인 목록 로드 실패 — 집행 중단: {str(e)[:150]}")
        sys.exit(1)

    try:
        wishes = load_form_wishes()
    except Exception as e:
        wishes = {}
        print(f"WARN: 폼 희망제품 로드 실패 — {str(e)[:150]}")

    uploaded, music, hold_product, hold_perm, hold_creator, hold_unreviewed, fails, would = [], [], [], [], [], [], [], []
    for it in items:
        # 게이트: 정성 심사(인간 2차 집행) 통과분만. 미심사·AI 1차만·미집행은 스킵.
        if it["sc"] not in approved:
            hold_unreviewed.append(f"@{it['handle']} {it['sc']} 게시{it['d']} — 정성 심사 미통과(인간 2차 집행 확정 아님)")
            print(f"  [hold_unreviewed] @{it['handle']} {it['sc']}")
            continue
        wish = wishes.get(w.hnorm(it["handle"]))
        product = resolve_product(wish[0]) if wish else None
        if not product:
            hold_product.append(f"@{it['handle']} {it['sc']} 게시{it['d']} — 제품미상(폼 매칭실패/모호)")
            print(f"  [hold_no_product] @{it['handle']} {it['sc']}")
            continue
        status, detail = upload_one(it, product, wish[1] if wish else False, dry=args.dry_run)
        bucket = {"uploaded": uploaded, "would_upload": would, "skip_music": music,
                  "hold_no_perm": hold_perm, "hold_no_creator": hold_creator}.get(status, fails)
        bucket.append(detail)
        print(f"  [{status}] {detail}")

    holds = hold_unreviewed + hold_product + hold_perm + hold_creator
    lines = [f"WL D+3 자동집행 ({TODAY}, JST 9시)",
             f"✅ 집행 {len(uploaded)} · ⏸ 저작권음악 {len(music)} · ⏳ 보류 {len(holds)} · ✗ 실패 {len(fails)}"]
    for group, tag in ((uploaded, "집행(생성+ON)"), (would, "집행예정(dry)"), (music, "저작권음악"),
                       (hold_unreviewed, "정성심사 미통과"), (hold_product, "제품미상(세은 제품 알려주면 집행)"),
                       (hold_perm, "WL권한없음"), (hold_creator, "크리에이터조회실패"), (fails, "실패")):
        for x in group:
            lines.append(f"  [{tag}] {x}")
    report = "\n".join(lines)
    print("\n" + report)

    # 알림 노이즈 감소: 실제 업로드 또는 하드 실패만 세은 알림.
    # 정적 보류(제품미상·저작권음악·WL권한없음)는 감시견(wl_d3_watchdog)이 매일 커버 → 중복 알림 회피.
    if not args.dry_run and not args.no_notify and (uploaded or fails):
        subject = f"[WL자동업로드] {TODAY} — 업로드 {len(uploaded)}·실패 {len(fails)}"
        try:
            print(f"\n알림 채널: {w.notify(report, subject=subject)}")
        except Exception as ex:
            print(f"WARN: 알림 발송 예외 — {str(ex)[:100]}")
    if fails:
        sys.exit(1)   # 하드 실패 = cron 이 감지하도록 비정상 종료


if __name__ == "__main__":
    main()
