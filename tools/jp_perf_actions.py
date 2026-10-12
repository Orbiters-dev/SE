# -*- coding: utf-8 -*-
"""JP 퍼포먼스 판정 보드 — 일일 액셔너블 아이템 생성기.

보드(https://jp-perf-board.vercel.app)에 박힌 확정 룰을 매일 실데이터에 적용해
actions.json 을 산출한다. 보드가 이 파일을 fetch 해 「오늘의 액션」 패널로 표시.

채널별 룰 (전부 세은 확정 정본 — 임의 변경 금지):
- Meta WL  : 졸업/OFF 판정 = meta_jp_daily 빌더 재사용 (meta_jp_grad_off_executor 가
             JST 09:12 자동 집행 — 여기선 같은 판정을 '자동집행 예정/완료' 로 표시만)
- Meta IHV : D3~9 창 CPLPV 3갈래 (2026-10-08 확정) — ≤130 증액 후보(주1회 +20~25%) /
             130~190 잔류 / >190 OFF트랙 (>230 즉시 OFF · 190~230 1주 유예 후 재판정).
             10일 미만 = 판정 전. CTR 단독 컷 금지 (보조선만).
- Amazon SBV: v1.1 (2026-10-08 확정) — BEP ROAS 1.0 기준.
             1차 게이트 누적 ¥25K: ROAS<0.30 → OFF / 2차 게이트 누적 ¥45K: I=ROAS/BEP
             사다리 (<0.6 OFF · 0.6~0.8 예산 반감 · ≥1.0 증액). 판정 운영 = 격주 월
             (여기선 룰 충족 여부를 매일 표시 — 집행은 판정일에 세은).
- Amazon SP : 판정룰 정본 없음 → 현황 정보만 (최근 14일 지출·ROAS).
- RPP/TikTok: API 불가 → 보드에 수동 채널 안내만.

안내문 속 수치도 전부 세은 확정 정본 (임의 수치 아님):
- Meta WL Proven OFF = CPLPV>150 (14d&30d, 2026-09-15 위임 룰 — meta_jp_daily 구현)
- RPP OFF컷 = ¥5,000 소진 + 전환 0 (2026-09-30 확정)
- TikTok OFF룰 = D3+ 판정일 CPLPV>4엔 or CTR<8% 3연속 (2026-10-08 확정)

사용: PYTHONIOENCODING=utf-8 python tools/jp_perf_actions.py [--skip-amz] [--skip-meta]
     [--amz-cache PATH]  # 신선한 로컬 풀 재사용 (로컬 테스트용)
출력: .tmp/jp_perf_actions/actions.json
"""
import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from env_loader import load_env
load_env()

KST = timezone(timedelta(hours=9))
OUT_DIR = BASE / ".tmp" / "jp_perf_actions"

# ── IHV 룰 (build_ihv_criteria_report.py 와 동일 상수) ──
# 효율 판정 제외 광고 (세은 2026-10-12): 이름에 아래 문자열 포함 = 목적성 광고(모집 등).
# モニター募集 = 모니터 모집용 상시 운영 — 효율이 어떻게 나와도 절대 OFF 금지.
IHV_JUDGMENT_EXEMPT = ["モニター募集"]
IHV_PROMOTE = 130
IHV_KILL = 190
IHV_KILL_NOW = 230
IHV_MIN_DAYS = 10          # 집행 10일 미만 = 판정 전
IHV_GRACE_END = 17         # 190~230 유예 재판정 시점 (D16 컷 백테스트)
# 증액 스텝 (세은 보드 편집본): 회당 +20~25%, 주 1회
IHV_BUDGET_LADDER = [8000, 10000, 12000, 15000, 18000]

# ── SBV 룰 v1.1 ──
SBV_BEP = 1.0
SBV_GATE1 = 25000          # 1차 게이트 (누적 ¥)
SBV_GATE2 = 45000          # 2차 게이트
SBV_GATE1_ROAS = 0.30
SBV_LADDER_OFF = 0.6       # I < 0.6 → OFF
SBV_LADDER_HALF = 0.8      # 0.6~0.8 → 예산 반감
SBV_LADDER_UP = 1.0        # ≥ 1.0 → 증액
SBV_START = date(2026, 9, 1)
SBV_WINDOW_LAG = 3         # 4주창 D−3 (귀속 지연 보정)

AMZ_HOST = "https://advertising-api-fe.amazon.com"
# v21.0~v25.0 전부 동작 실측 (2026-10-12, act_4117678028561958) — EOL 여유를 위해 v23.0
GRAPH_VER = os.environ.get("META_GRAPH_VER", "v23.0")


def item(severity, title, detail, execute, metrics=None, entity_id=None):
    """severity: off|half|scale|watch|pre|info / execute: auto|manual|proposal"""
    return {"severity": severity, "title": title, "detail": detail,
            "execute": execute, "metrics": metrics or {}, "entity_id": entity_id}


# ═══════════════ Meta WL (졸업/OFF — 자동집행 미러) ═══════════════

def channel_meta_wl():
    import meta_jp_grad_off_executor as E
    yday, grads, offs, dfails, provens = E.today_candidates()
    actions = []
    for a in grads:
        actions.append(item(
            "scale", f"졸업 → Proven 이동: {a.get('ad_name', '?')[:60]}",
            "Testing 졸업컷 통과 — Proven adset 에 재생성 + Testing PAUSE",
            "auto", {"CPLPV": a.get("cplpv"), "ad_id": a.get("ad_id")}, a.get("ad_id")))
    for a, why in ([(x, "Testing OFF 룰") for x in offs]
                   + [(x, "delivery 실패") for x in dfails]
                   + [(x, "Proven CPLPV>150") for x in provens]):
        actions.append(item(
            "off", f"OFF: {a.get('ad_name', '?')[:60]}", why,
            "auto", {"CPLPV": a.get("cplpv"), "ad_id": a.get("ad_id")}, a.get("ad_id")))
    return {"key": "meta_wl", "tab": "meta", "title": "Meta WL (졸업/OFF 자동집행)",
            "status": "ok", "ref_date": yday.isoformat(), "actions": actions, "info": [],
            "note": "판정·집행 = meta_jp_grad_off (JST 09:12 자동). 여기 항목은 당일 집행분 미러."}


# ═══════════════ Meta IHV (D3~9 CPLPV 3갈래) ═══════════════

def _graph_status_map():
    token = os.environ["META_JP_ACCESS_TOKEN"]
    acct = os.environ.get("META_JP_AD_ACCOUNT_ID", "act_4117678028561958")
    url = f"https://graph.facebook.com/{GRAPH_VER}/{acct}/ads"
    params = {"fields": "id,name,effective_status,adset{id,daily_budget}",
              "limit": 500, "access_token": token}
    out = {}
    while url:
        with urllib.request.urlopen(
                url + "?" + urllib.parse.urlencode(params) if params else url,
                timeout=60) as r:
            j = json.load(r)
        for ad in j.get("data", []):
            out[str(ad["id"])] = ad
        url = (j.get("paging") or {}).get("next")
        params = None
    return out


def _cplpv(days):
    sp = sum(d["spend"] for d in days)
    lv = sum(d["lpv"] for d in days)
    return (sp / lv) if lv else None


def channel_meta_ihv():
    from data_keeper_client import DataKeeper
    rows = DataKeeper().get("meta_ads_daily", brand="Grosmimi JP", date_from="2026-04-01")
    if not rows:
        raise RuntimeError("DK meta_ads_daily 0행 — 도구 실패 가능성 (빈 결과 단정 금지)")
    ads = {}
    for r in rows:
        if "_IH_" not in (r.get("campaign_name") or ""):
            continue
        aid = str(r.get("ad_id"))
        a = ads.setdefault(aid, {"name": r.get("ad_name"), "series": {}})
        a["name"] = r.get("ad_name") or a["name"]
        d = r.get("date")
        s = a["series"].setdefault(d, {"date": d, "spend": 0.0, "lpv": 0, "imp": 0, "clicks": 0})
        s["spend"] += float(r.get("spend") or 0)
        s["lpv"] += int(float(r.get("landing_page_view") or 0))
        s["imp"] += int(r.get("impressions") or 0)
        s["clicks"] += int(r.get("clicks") or 0)

    graph = _graph_status_map()
    actions, info = [], []
    for aid, a in ads.items():
        g = graph.get(aid) or {}
        status = g.get("effective_status", "NOT_IN_GRAPH")
        days = sorted(a["series"].values(), key=lambda x: x["date"])
        days = [d for d in days if d["spend"] > 0]   # 집행일 나이 기준 (빌더와 동일)
        if not days or status != "ACTIVE":
            continue
        age = len(days)
        name = (a["name"] or aid)[:60]
        sp = sum(d["spend"] for d in days)
        im = sum(d["imp"] for d in days)
        ck = sum(d["clicks"] for d in days)
        ctr = ck / im * 100 if im else 0.0
        d39 = _cplpv(days[3:10])
        m = {"집행일수": age, "지출₩": round(sp), "D3-9 CPLPV": round(d39) if d39 else None,
             "CTR%": round(ctr, 1), "ad_id": aid}
        if any(x in (name or "") for x in IHV_JUDGMENT_EXEMPT):
            info.append(item("info", f"판정 제외 (모집 목적 상시 운영): {name}",
                             "효율 무관 계속 운영 — OFF 절대 금지 (세은 2026-10-12)",
                             "manual", m, aid))
            continue
        if age < IHV_MIN_DAYS:
            cur = _cplpv(days[3:])
            info.append(item("pre", f"판정 전 (D{age - 1}): {name}",
                             f"D9 판정까지 {IHV_MIN_DAYS - age}일 — 현재 D3~ CPLPV "
                             f"{cur:,.0f}" if cur else f"D9 판정까지 {IHV_MIN_DAYS - age}일 — LPV 0",
                             "manual", m, aid))
            continue
        if d39 is None:
            info.append(item("watch", f"판정 불가 (LPV 0): {name}",
                             "D3~9 창 LPV 0 — CPLPV 계산 불가, 수동 확인 필요", "manual", m, aid))
            continue
        if d39 > IHV_KILL_NOW:
            actions.append(item("off", f"즉시 OFF: {name}",
                                f"D3~9 CPLPV {d39:,.0f} > {IHV_KILL_NOW} — 즉시 OFF 트랙",
                                "proposal", m, aid))
        elif d39 > IHV_KILL:
            if age >= IHV_GRACE_END:
                late = _cplpv(days[10:17])
                m["D10-16 CPLPV"] = round(late) if late else None
                if late is None or late > IHV_KILL:
                    actions.append(item("off", f"유예 만료 OFF: {name}",
                                        f"D3~9 {d39:,.0f} (190~230 유예) → D10~16 "
                                        f"{late:,.0f} — 여전히 {IHV_KILL} 초과" if late
                                        else f"D3~9 {d39:,.0f} 유예 후 D10~16 LPV 0",
                                        "proposal", m, aid))
                else:
                    info.append(item("watch", f"유예 재판정 통과: {name}",
                                     f"D3~9 {d39:,.0f} → D10~16 {late:,.0f} ≤ {IHV_KILL} — 잔류",
                                     "manual", m, aid))
            else:
                actions.append(item("watch", f"OFF트랙 유예 중: {name}",
                                    f"D3~9 CPLPV {d39:,.0f} (190~230) — 1주 유예, "
                                    f"D16 재판정까지 {IHV_GRACE_END - age}일", "manual", m, aid))
        elif d39 <= IHV_PROMOTE:
            budget = None
            adset = g.get("adset") or {}
            if adset.get("daily_budget"):
                budget = int(adset["daily_budget"])
                m["adset 일예산₩"] = budget
            nxt = next((b for b in IHV_BUDGET_LADDER if budget and b > budget), None)
            actions.append(item("scale", f"증액 후보: {name}",
                                f"D3~9 CPLPV {d39:,.0f} ≤ {IHV_PROMOTE} — Testing 내 adset 증액 "
                                f"(주 1회 +20~25%{f', 다음 스텝 ₩{nxt:,}' if nxt else ''}) "
                                "— Proven 이동 아님", "proposal", m, aid))
        else:
            info.append(item("watch", f"잔류 관찰: {name}",
                             f"D3~9 CPLPV {d39:,.0f} (130~190) — 유지", "manual", m, aid))
    return {"key": "meta_ihv", "tab": "meta", "title": "Meta IHV (D3~9 CPLPV 판정)",
            "status": "ok", "actions": actions, "info": info,
            "note": "판정창 D3~9 (D0~2 학습기 제외) · CTR 단독컷 금지 · 증액은 주 1회 동기."}


# ═══════════════ Amazon SBV / SP ═══════════════

def _amz_token():
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": os.environ["AMZ_ADS_JP_REFRESH_TOKEN"],
        "client_id": os.environ["AMZ_ADS_JP_CLIENT_ID"],
        "client_secret": os.environ["AMZ_ADS_JP_CLIENT_SECRET"]}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            "https://api.amazon.com/auth/o2/token", data=data), timeout=30) as r:
        return json.load(r)["access_token"]


def _amz_report(tok, ad_product, report_type, cols, sd, ed):
    """리포트 생성→폴링→다운로드 (pull_amz_ads_daily_direct.py 패턴)."""
    hdr = {"Authorization": "Bearer " + tok,
           "Amazon-Advertising-API-ClientId": os.environ["AMZ_ADS_JP_CLIENT_ID"],
           "Amazon-Advertising-API-Scope": os.environ.get("AMZ_ADS_JP_PROFILE_ID", "3736142261021843"),
           "Content-Type": "application/vnd.createasyncreportrequest.v3+json"}
    body = json.dumps({"name": f"{report_type}_{sd}_{ed}", "startDate": sd, "endDate": ed,
                       "configuration": {"adProduct": ad_product, "groupBy": ["campaign"],
                                         "columns": cols, "reportTypeId": report_type,
                                         "timeUnit": "DAILY", "format": "GZIP_JSON"}}).encode()
    req = urllib.request.Request(f"{AMZ_HOST}/reporting/reports", data=body, headers=hdr)
    with urllib.request.urlopen(req, timeout=60) as r:
        rid = json.load(r)["reportId"]
    for _ in range(90):                          # 최대 ~15분
        time.sleep(10)
        q = urllib.request.Request(f"{AMZ_HOST}/reporting/reports/{rid}", headers=hdr)
        with urllib.request.urlopen(q, timeout=60) as r:
            st = json.load(r)
        if st["status"] == "COMPLETED":
            with urllib.request.urlopen(st["url"], timeout=120) as r:
                return json.loads(gzip.decompress(r.read()))
        if st["status"] == "FAILURE":
            raise RuntimeError(f"Amazon 리포트 실패: {st}")
    raise RuntimeError("Amazon 리포트 폴링 타임아웃 (15분)")


def _month_windows(start, end):
    wins, cur = [], start
    while cur <= end:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
        wins.append((cur.isoformat(), min(end, nxt - timedelta(days=1)).isoformat()))
        cur = nxt
    return wins


def _amz_rows(cache_path=None):
    """SBV 전기간 + SP 최근 28일 일별 행. cache_path 지정 + 24h 내 신선이면 재사용."""
    if cache_path:
        p = Path(cache_path)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            pulled = datetime.strptime(d["pulled_at"], "%Y-%m-%d %H:%M")
            if datetime.now() - pulled < timedelta(hours=24):
                rows = []
                for v in d["data"].values():
                    rows += v
                return rows, f"캐시 재사용 ({d['pulled_at']})"
    tok = _amz_token()
    yday = date.today() - timedelta(days=1)
    rows = []
    sb_cols = ["date", "campaignId", "campaignName", "campaignStatus",
               "impressions", "clicks", "cost", "purchases", "sales"]
    for sd, ed in _month_windows(SBV_START, yday):
        for r in _amz_report(tok, "SPONSORED_BRANDS", "sbCampaigns", sb_cols, sd, ed):
            r["adType"] = "SBV"
            r["sales14d"] = r.pop("sales", 0)
            r["purchases14d"] = r.pop("purchases", 0)
            rows.append(r)
    sp_cols = ["date", "campaignId", "campaignName", "campaignStatus",
               "impressions", "clicks", "cost", "purchases14d", "sales14d"]
    sp_start = yday - timedelta(days=27)
    for sd, ed in _month_windows(sp_start, yday):
        for r in _amz_report(tok, "SPONSORED_PRODUCTS", "spCampaigns", sp_cols, sd, ed):
            r["adType"] = "SP"
            rows.append(r)
    return rows, "API 직접 풀"


def channel_amazon(cache_path=None):
    rows, src = _amz_rows(cache_path)
    today = date.today()
    sbv, sp = {}, {}
    skipped = 0
    for r in rows:
        key = r.get("campaignName")
        if not key or not r.get("date"):
            skipped += 1
            continue
        bucket = sbv if r.get("adType") == "SBV" else sp
        c = bucket.setdefault(key, {"status": r.get("campaignStatus"), "days": []})
        c["status"] = r.get("campaignStatus")  # 최신 행 기준
        c["days"].append(r)
    if skipped:
        print(f"[WARN] amz: 필수 필드 누락 행 {skipped}건 제외")

    actions, info = [], []
    w_end = today - timedelta(days=SBV_WINDOW_LAG)
    w_start = w_end - timedelta(days=27)
    for name, c in sbv.items():
        if c["status"] != "ENABLED":
            continue
        cum_cost = sum(d["cost"] for d in c["days"])
        cum_sales = sum(d["sales14d"] for d in c["days"])
        roas_cum = cum_sales / cum_cost if cum_cost else 0.0
        w = [d for d in c["days"] if w_start.isoformat() <= d["date"] <= w_end.isoformat()]
        wc = sum(d["cost"] for d in w)
        ws = sum(d["sales14d"] for d in w)
        roas_4w = ws / wc if wc else 0.0
        m = {"누적지출¥": round(cum_cost), "누적ROAS": round(roas_cum, 2),
             "4주창ROAS(D−3)": round(roas_4w, 2)}
        if cum_cost >= SBV_GATE2:
            i_val = roas_4w / SBV_BEP
            if i_val < SBV_LADDER_OFF:
                actions.append(item("off", f"SBV 2차 OFF: {name}",
                                    f"누적 ¥{cum_cost:,.0f} ≥ {SBV_GATE2:,} · I={i_val:.2f} < "
                                    f"{SBV_LADDER_OFF} — OFF (격주 월 판정 집행)", "proposal", m))
            elif i_val < SBV_LADDER_HALF:
                actions.append(item("half", f"SBV 예산 반감: {name}",
                                    f"I={i_val:.2f} (0.6~0.8) — 예산 반감 (격주 월 판정 집행)",
                                    "proposal", m))
            elif i_val >= SBV_LADDER_UP:
                actions.append(item("scale", f"SBV 증액: {name}",
                                    f"I={i_val:.2f} ≥ 1.0 — 증액 (격주 월 판정 집행)",
                                    "proposal", m))
            else:
                info.append(item("watch", f"SBV 잔류 (0.8~1.0): {name}",
                                 f"I={i_val:.2f} — 유지", "manual", m))
        elif cum_cost >= SBV_GATE1:
            if roas_cum < SBV_GATE1_ROAS:
                actions.append(item("off", f"SBV 1차 컷: {name}",
                                    f"누적 ¥{cum_cost:,.0f} ≥ {SBV_GATE1:,} · ROAS "
                                    f"{roas_cum:.2f} < {SBV_GATE1_ROAS} — OFF "
                                    "(격주 월 판정 집행)", "proposal", m))
            else:
                info.append(item("watch", f"SBV 1차 통과: {name}",
                                 f"ROAS {roas_cum:.2f} — 2차 게이트 ¥{SBV_GATE2:,} 까지 관찰",
                                 "manual", m))
        else:
            info.append(item("pre", f"SBV 게이트 전: {name}",
                             f"누적 ¥{cum_cost:,.0f} < 1차 ¥{SBV_GATE1:,} — 데이터 축적 중",
                             "manual", m))

    for name, c in sp.items():
        if c["status"] != "ENABLED":
            continue
        cost14 = sum(d["cost"] for d in c["days"] if d["date"] >= (today - timedelta(days=14)).isoformat())
        sales14 = sum(d["sales14d"] for d in c["days"] if d["date"] >= (today - timedelta(days=14)).isoformat())
        info.append(item("info", f"SP 현황: {name}",
                         f"최근 14일 지출 ¥{cost14:,.0f} · ROAS {sales14 / cost14 if cost14 else 0:.2f} "
                         "(판정룰 정본 없음 — 현황만)", "manual",
                         {"14d지출¥": round(cost14), "14dROAS": round(sales14 / cost14, 2) if cost14 else 0}))
    return {"key": "amz", "tab": "amz", "title": "Amazon SBV (v1.1) / SP", "status": "ok",
            "actions": actions, "info": info,
            "note": f"SBV 판정 운영 = 격주 월 (4주창 D−3) — 룰 충족 여부만 매일 표시. 데이터: {src}"}


# ═══════════════ main ═══════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-meta", action="store_true")
    ap.add_argument("--skip-amz", action="store_true")
    ap.add_argument("--amz-cache", help="신선(24h)하면 재사용할 로컬 풀 JSON 경로")
    args = ap.parse_args()

    channels = []

    def run(fn, *a, label=""):
        try:
            ch = fn(*a)
            print(f"[OK] {ch['key']}: 액션 {len(ch['actions'])}건 · 정보 {len(ch['info'])}건")
            return ch
        except Exception as e:  # 채널 독립 실패 — 무음 금지, status=error 로 보드 표시
            print(f"[ERROR] {label}: {e}")
            return {"key": label, "tab": "meta" if "meta" in label else "amz",
                    "title": label, "status": "error", "error": str(e)[:300],
                    "actions": [], "info": []}

    if not args.skip_meta:
        channels.append(run(channel_meta_wl, label="meta_wl"))
        channels.append(run(channel_meta_ihv, label="meta_ihv"))
    if not args.skip_amz:
        channels.append(run(channel_amazon, args.amz_cache, label="amz"))

    channels.append({"key": "rpp", "tab": "rpp", "title": "라쿠텐 RPP", "status": "manual",
                     "actions": [], "info": [],
                     "note": "API 실행 불가 — 판정·집행은 RMS 콘솔 수동 (OFF컷 ¥5,000+전환0)."})
    channels.append({"key": "tiktok", "tab": "tiktok", "title": "TikTok Ads", "status": "manual",
                     "actions": [], "info": [],
                     "note": "Marketing API 승인 대기 — 성과는 수동 스크랩. 룰: D3+ CPLPV>4엔 or CTR<8% 3연속 OFF."})

    out = {"generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
           "ref_date": (date.today() - timedelta(days=1)).isoformat(),
           "channels": channels}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "actions.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(c["actions"]) for c in channels)
    print(f"\n산출: {path} — 액션 {total}건 / 채널 {len(channels)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
