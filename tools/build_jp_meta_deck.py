"""
JP Meta 운영 발표 HTML 덱 빌더 (주간 — 2026-07-20 개편).

덱 구조 = 레퍼런스(HSTest Creative Feedback 7/13 · SBV D+14 디스포지션 · Onzenna Academy) 관례:
**콘텐츠(크리에이티브) 단위 리뷰가 본체** + 전수 디스포지션 표(행마다 판정+사유).
  표지 → JP 채널구조 → 운영구조(게이트) → 이번 주 한눈(4색 분포)
  → 최근 1달 런칭 전수 디스포지션 → 지난 7일 영상 리뷰 카드 → 성과 변동(prev7 vs 7d)
  → 승격 전후 효율 → 운영 성과

주간 구성 룰 (세은 2026-07-20):
  - 리뷰 풀 = 최근 1달 내 첫 라이브 콘텐츠 / 본체 = 지난 7일 영상 + 이전 대비 성과 변동
  - 판정 4색: 좋음=파랑 / 중간=초록 / 안 좋음=빨강 / 빨리 죽여야=검정 (게이트 로직 재사용)
  - creator type(WL-P 유상/WL-G 무상) + 3초 이상 시청률 태깅, 잘/안 된 이유 축 분해 기재

1) collect: Meta Graph API 직접 실측(성과·status·permalink·썸네일·계정 구조)
   + Content Tags (JP) 시트(KM/훅) → .tmp/jp_meta_deck/ssot.json
   ※ 성과 소스가 DK 가 아닌 Graph 인 이유: DK gk_meta_ads_daily JP 히스토리
     4/5~6/14 소실 + 마지막 날 부분치 실측 확인 (2026-07-13). DK 는 교차검증 축.
2) render : ssot.json 만 읽어 self-contained HTML 덱 생성.
   계산 숫자는 전부 SSOT 재계산. 외부 분석 인용 수치는 cited_facts 에 출처와 함께 저장·병기.

콘텐츠 리뷰 선별 기준(덱에 명시, 크리에이터 단위 생애 합산·OFF 포함 전 기간):
  BEST 3 + WORST 3 = 생애 CPLPV 순 (spend<₩20K 소액 제외) / 최근 4 = 첫 라이브 최신순 중 D+7 이상.

CPLPV 는 LPV=0 이면 None(미산출) — 0(공짜) 오독 방지, 렌더는 '—' 표기.

Usage:
  PYTHONIOENCODING=utf-8 python tools/build_jp_meta_deck.py            # collect + render
  PYTHONIOENCODING=utf-8 python tools/build_jp_meta_deck.py --render   # ssot.json 재사용
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# 게이트/정규화/판정 로직은 전부 meta_jp_daily SSOT 재사용 (하드코딩 금지)
try:
    from meta_jp_daily import (
        ACCT, BASE, TOKEN, api_get, live_ad_statuses, off_rule_check,
        _dk_norm, extract_lpv, to_float,
        adset_stage, parse_paid_flag, calc_days_live,
        GRAD_CPC_MAX, GRAD_CTR_MIN, GRAD_CPLPV_MAX, GRAD_MIN_DAYS,
        OFF_D3_CPC_MAX, OFF_D3_CTR_MIN, OFF_D3_CPLPV_OFF,
        KPI_WL_CTR, KPI_IMG_CTR,
    )
    from data_keeper_client import DataKeeper
    from sheets_utils import get_sheets_client
except ImportError as e:
    sys.exit(f"[FATAL] 의존 모듈 로드 실패: {e} — SE 루트에서 실행 + tools/ 경로 확인")

OUT_DIR = ROOT / ".tmp" / "jp_meta_deck"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SSOT_PATH = OUT_DIR / "ssot.json"
# 산출물 경로 = operations 폴더 고정 (세은 7/20 — 구 Desktop\s\메타 폴더 재생성 금지)
_OPS_DIR = Path(r"C:\Users\orbit\Desktop\s\performance marketing\META ADS\operations")


def _weekly_deck_path() -> str:
    """주차별 새 번호 파일 (세은 7/27 — 고정 파일명이 저번 주 덱을 덮어쓴 사고 재발 방지).

    같은 주(월요일 stamp) 재실행 = 같은 파일 덮어쓰기 (발표 아침 재실행 룰 호환),
    새 주 = 폴더 내 최대 NN+1 로 신규 파일.
    """
    monday = date.today() - timedelta(days=date.today().weekday())
    stamp = monday.strftime("%Y%m%d")
    if not _OPS_DIR.is_dir():  # 폴더 부재 = 채번 불가 — mkdir 금지(세은 7/20)라 즉시 중단
        sys.exit(f"[FATAL] operations 폴더 없음: {_OPS_DIR} — 경로 확인 (재생성 금지)")
    week_pat = re.compile(r"^(\d+)_jp_meta_weekly_deck_(\d{8})\.html$")
    num_pat = re.compile(r"^(\d+)_")
    max_n = 0
    for p in _OPS_DIR.glob("*.html"):
        m = week_pat.match(p.name)
        if m and m.group(2) == stamp:
            return str(p)  # 이번 주 파일 이미 존재 → 재실행 덮어쓰기
    for p in _OPS_DIR.iterdir():  # 폴더 전체 NN_ 프리픽스 통합 채번
        m = num_pat.match(p.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return str(_OPS_DIR / f"{max_n + 1}_jp_meta_weekly_deck_{stamp}.html")


DEFAULT_DECK = os.getenv("JP_DECK_OUT") or _weekly_deck_path()

# --ref-date 재빌드 앵커 (기본 = 오늘). 과거 주 재빌드 시 insights 창은 해당 시점으로 재현되지만
# live status·계정 구조·태그 시트는 현재 시점 스냅샷 — 완전 재현 아님 (7/27 11번 덱 복구용)
REF_TODAY = date.today()

TAG_SHEET_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
TAG_TAB = "Content Tags (JP)"
DK_META_BRAND = "Grosmimi JP"
KM_RE = re.compile(r"S\d{2}_F\d{2}")
HOOK_RE = re.compile(r"H[VC]-\d{2}")
SC_RE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")
AD_DATE_RE = re.compile(r"Y(\d{2})M(\d{2})D(\d{2})")
CTNUM_RE = re.compile(r"CT-(\d+)")   # ad_name CT 토큰 = DK content_posts id = 시트 ct_pk

# 메타몽 앱과 동일한 콘텐츠 식별 소스 — 콜라보 시트 Grosmimi 탭 (meta-app lib/sheets.ts fetchCollabs)
COLLAB_SHEET_ID = "1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU"
COLLAB_GID = 386147805

DATA_FROM = "2026-03-01"      # JP 운영 전체 이력 시작
LIFE_LABEL = "생애(3/1~)"
OFF30_MIN_SPEND = 3000        # OFF 사례 최소 30d spend (노이즈 컷)
THUMB_MAX_BYTES = 400_000

CITED_FACTS = {
    "supersale_roas": {
        "sale": "3.30x", "offsale": "0.38x",
        "source": "6월 슈퍼세일 사후분석, Meta-귀속 Rakuten 매출 실측 (2026-06-17)",
    },
    "d3_d7_corr": {
        "value": "0.93~0.97",
        "source": "졸업 판정 D+3 vs D+7 지표 상관 자체 역산 (2026-06-16)",
    },
    "off150_sim": {
        "save": "약 ₩76.7K", "false_kill": "0건",
        # 구체 임계 수치는 덱 노출 X (세은 7/13 — 내부 운영값이라 발표 자리에서 생략)
        "source": "OFF 게이트 하향 시뮬레이션 (2026-07-08, 확정 대기)",
    },
    "stainless_bep": {
        "value": "≈₩100",
        "source": "제품 손익분기 CPLPV 계산 (2026-07-08)",
    },
    "gate_basis_grad": {
        "value": "실제 졸업 소재 성과 역산으로 확정",
        "source": "졸업 기준 확정 2026-06-16 · CPLPV 135→130 하향 2026-07-09",
    },
    "gate_basis_off": {
        "value": "운영 풀 CPLPV 분포 하위 15% 컷 (그 밑은 경제성 없음)",
        "source": "OFF 기준 도출 근거 분석 (2026-07-08)",
    },
}


def cplpv_calc(spend, lpv):
    """CPLPV 단일 계산 헬퍼. LPV=0 → None(미산출)."""
    return (spend / lpv) if lpv and lpv > 0 else None


def extract_v3(actions):
    """3초 이상 시청 수 = Graph actions[video_view] (Meta 정의: 3-second video plays).

    전용 필드 video_3_sec_watched_actions 는 현 API 버전에서 400 (2026-07-20 실측)
    → actions 배열의 video_view 가 동일 정의의 유일한 소스.
    """
    for a in actions or []:
        if a.get("action_type") == "video_view":
            return to_float(a.get("value"))
    return 0.0


# ── collect ──────────────────────────────────────────────────────────────

def _norm_user(u):
    return re.sub(r"[^a-z0-9]", "", (u or "").lower())


def _wl_slug(name):
    """ad_name 의 WL 크리에이터 슬러그 (정규화). 없으면 ''."""
    m = re.search(r"WL-[PG]_(.+?)_B0", name or "")
    return _norm_user(m.group(1)) if m else ""


# 구/신 명명이 갈린 동일 크리에이터 (세은 확인: haru=haruyoshi09126 2026-07-13)
CREATOR_ALIAS = {"bebimon": "bebimonikuji", "komugiko": "komugiko126", "haru": "haruyoshi09126"}


def creator_slug(name):
    """WL 광고의 크리에이터 슬러그 — 신 명명(WL-P/G_슬러그) + 구 명명(… | 크리에이터 | PAID/GIFT | 날짜).

    구 명명은 PAID/GIFT 토큰 바로 앞 토큰이 크리에이터 (AD 프리픽스 유무 모두 대응).
    이미지 소재 등 비WL 은 '' 반환.
    """
    sl = _wl_slug(name)
    if not sl:
        parts = [p.strip() for p in (name or "").split("|")]
        try:
            i = next(j for j, p in enumerate(parts) if p in ("PAID", "GIFT"))
            sl = _norm_user(parts[i - 1]) if i >= 1 else ""
        except StopIteration:
            sl = ""
    return CREATOR_ALIAS.get(sl, sl)


def load_tags():
    """Content Tags (JP) → {"by_sc": shortcode→태그, "by_user": 정규화username→[태그…]}."""
    try:
        ws = get_sheets_client().open_by_key(TAG_SHEET_ID).worksheet(TAG_TAB)
        vals = ws.get_all_values()
    except Exception as e:
        raise RuntimeError(f"Content Tags (JP) 시트 읽기 실패: {e} — 크레덴셜/시트 확인") from e
    if not vals:
        raise RuntimeError("Content Tags (JP) 탭이 비어 있음 — 구조 확인")
    hdr = [h.strip() for h in vals[0]]
    ix = {h: i for i, h in enumerate(hdr)}
    need = [c for c in ("shortcode", "km_primary", "km_manual") if c not in ix]
    if need:
        raise RuntimeError(f"Content Tags (JP) 헤더 누락: {need} — 구조 변경됨, 중단")

    def cell(row, col):
        i = ix.get(col)
        return (row[i] if i is not None and len(row) > i else "").strip()

    by_sc, by_user, by_ct = {}, defaultdict(list), {}
    for r in vals[1:]:
        sc = cell(r, "shortcode")
        if not sc:
            continue
        km_src = cell(r, "km_manual") or cell(r, "km_primary")
        hook_src = cell(r, "hook_manual") or " ".join(
            [cell(r, "hook_visual"), cell(r, "hook_caption"), cell(r, "hook_primary")])
        kms = KM_RE.findall(km_src)
        hooks = HOOK_RE.findall(hook_src)
        entry = {
            "km": kms[0] if kms else "", "km_all": kms, "km_label": km_src,
            "hooks": hooks, "hook_label": cell(r, "hook_manual") or cell(r, "hook_primary"),
            "username": cell(r, "username"),
            "review_note": cell(r, "review_note"),   # 이유(사람) — Promise/Proof/CTA 수기 (플랜 B)
        }
        by_sc[sc] = entry
        u = _norm_user(cell(r, "username"))
        if u and entry["km"]:
            by_user[u].append(entry)
        ctv = cell(r, "ct_pk")
        if ctv and entry["km"]:
            by_ct[ctv] = entry
    return {"by_sc": by_sc, "by_user": dict(by_user), "by_ct": by_ct}


def load_collabs():
    """콜라보 시트 Grosmimi 탭 → handle(정규화) → [{sc, upload}] — 메타몽 앱의 콘텐츠 식별 SSOT.

    앱 태그 편집기는 이 탭의 원본 릴 shortcode 에 태그를 붙인다 (meta-app fetchCollabs 와 동일 파싱:
    row 3부터, handle=col 3, upload=col 13, url=col 16). 공개 CSV export — 인증 불요.
    """
    import csv
    url = f"https://docs.google.com/spreadsheets/d/{COLLAB_SHEET_ID}/export?format=csv&gid={COLLAB_GID}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    out = defaultdict(list)
    for r in rows[3:]:
        if len(r) <= 16:
            continue
        handle = _norm_user(r[3].strip().lstrip("@"))
        m = SC_RE.search(r[16].strip())
        if handle and m:
            out[handle].append({"sc": m.group(1), "upload": (r[13] or "").strip()})
    return dict(out)


def load_dk_ct_map():
    """CT 번호(=DK content_posts id) → (원본 릴 shortcode 맵, 오가닉 지표 맵).

    대형 테이블이라 fields 필수 (7/8 룰). 오가닉 = 소재 본질 vs 배달 문제 분리용 (분석 플랜 A-3).
    """
    fields = "id,url,region,views_30d,engagement_rate,followers"
    try:
        rows = DataKeeper().get("content_posts", fields=fields, days=400)
    except TypeError:   # 구버전 client — fields 미지원
        rows = DataKeeper().get("content_posts", days=400)
    sc_map, organic = {}, {}
    for r in rows or []:
        if str(r.get("region") or "").lower() != "jp":
            continue
        if r.get("id") is None:
            continue
        i = str(r.get("id"))
        m = SC_RE.search(str(r.get("url") or ""))
        if m:
            sc_map[i] = m.group(1)
        organic[i] = {"views": to_float(r.get("views_30d")),
                      "er": to_float(r.get("engagement_rate")),
                      "followers": to_float(r.get("followers"))}
    return sc_map, organic


def _ad_launch_date(name):
    m = AD_DATE_RE.search(name or "")
    return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _parse_date_loose(s):
    s = (s or "").strip()
    for pat in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%m/%d", "%m.%d"):
        try:
            d = datetime.strptime(s, pat)
            return d.date().replace(year=2026) if pat in ("%m/%d", "%m.%d") else d.date()
        except ValueError:
            continue
    return None


def _resolve_tag(name, sc, tags):
    """태그 조인 — 메타몽 앱에 등록된 값 기준 (세은 7/20):
    ① 광고 permalink shortcode 직접 일치
    ② 콜라보 시트의 그 크리에이터 원본 릴 shortcode 매칭 (앱 태그 편집기의 콘텐츠 키와 동일) —
       릴 복수면 광고 런칭일(ad_name 날짜 토큰) ↔ 업로드일 근접 선택 (앱 매칭 룰)
    ③ 크리에이터 단위 (KM 유일할 때만, 훅 union)

    파트너십 광고 permalink 는 광고 생성 시 새 미디어라 원본 shortcode 와 불일치 (7/13 실측) → ②가 본선.
    """
    t = tags["by_sc"].get(sc)
    if t and t.get("km"):
        return t, "post"
    # CT 토큰 = 앱/시트/DK 공통 콘텐츠 ID — 릴 단위 정확 매칭의 본선
    mct = CTNUM_RE.search(name or "")
    ct = mct.group(1) if mct else ""
    if ct:
        t = (tags.get("by_ct") or {}).get(ct)
        if t and t.get("km"):
            return t, "ct"
        sc2 = (tags.get("ct_sc") or {}).get(ct)
        if sc2:
            t = tags["by_sc"].get(sc2)
            if t and t.get("km"):
                return t, "ct"
    slug = _norm_user(creator_slug(name or "") or "")
    collabs = tags.get("collabs") or {}
    if slug and not ct:   # CT 있는 광고가 여기 오면 그 콘텐츠 연결고리가 없다는 뜻 — 구 릴 오귀속 방지
        cands = []
        for h, rs in collabs.items():
            if h == slug or h.startswith(slug) or slug.startswith(h) or h in slug:
                cands.extend(rs)
        tagged = [(c, tags["by_sc"].get(c["sc"])) for c in cands]
        tagged = [(c, t2) for c, t2 in tagged if t2 and t2.get("km")]
        if len(tagged) == 1:
            return tagged[0][1], "collab"
        if len(tagged) > 1:
            ld = _ad_launch_date(name)

            def _dist(item):
                u = _parse_date_loose(item[0].get("upload"))
                return abs((ld - u).days) if ld and u else 9999
            tagged.sort(key=_dist)
            if _dist(tagged[0]) < 9999:
                return tagged[0][1], "collab"
            kms = {t2["km"] for _, t2 in tagged}
            if len(kms) == 1:   # 날짜 판별 불가 — KM 유일하면 채택, 훅 union
                merged = dict(tagged[0][1])
                merged["hooks"] = sorted({h for _, t2 in tagged for h in t2["hooks"]})
                return merged, "collab"
    rows = _creator_tag_rows(name, tags)
    kms = {r["km"] for r in rows}
    if len(kms) == 1:
        # 릴 복수여도 KM 유일하면 채택 — 훅은 행 전체 union (첫 행만 쓰면 구형식 행에 걸려 유실)
        merged = dict(rows[0])
        merged["hooks"] = sorted({h for r in rows for h in r["hooks"]})
        return merged, "creator"
    return {}, ""


def _creator_tag_rows(name, tags):
    """ad_name → 그 크리에이터의 시트 태그 행 전부. WL 신·구 명명 모두 creator_slug 로 추출."""
    slug = _norm_user(creator_slug(name or "") or "")
    if not slug:
        return []
    rows = []
    for u, rs in tags["by_user"].items():
        if u == slug or u.startswith(slug) or slug.startswith(u) or u in slug:
            rows.extend(rs)
    return rows


def creator_sheet_kms(name, tags):
    """다KM 크리에이터 카드 병기용 — 시트에 태깅된 KM/훅 전부 (릴↔광고 1:1 확정 불가 시 union이 사실)."""
    rows = _creator_tag_rows(name, tags)
    kms = sorted({r["km"] for r in rows if r["km"]})
    hooks = sorted({h for r in rows for h in r["hooks"]})
    return kms, hooks


def fetch_creatives(ad_ids):
    """ad_id → {permalink, thumb_url}. Graph batch (50개씩) · 배치당 1회 재시도."""
    out = {}
    ids = [i for i in set(ad_ids) if i]
    for i in range(0, len(ids), 50):
        params = {
            "ids": ",".join(ids[i:i + 50]),
            "fields": "id,creative{instagram_permalink_url,thumbnail_url}",
            "access_token": TOKEN,
        }
        for attempt in (1, 2):
            try:
                qs = urllib.parse.urlencode(params)
                with urllib.request.urlopen(f"{BASE}/?{qs}", timeout=30) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
                for ad_id, ad in d.items():
                    cr = (ad or {}).get("creative") or {}
                    out[ad_id] = {"permalink": cr.get("instagram_permalink_url") or "",
                                  "thumb_url": cr.get("thumbnail_url") or ""}
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [warn] creative batch fail(재시도 후): {e}", file=sys.stderr)
    missing = [i for i in ids if i not in out]
    if missing:
        print(f"  [warn] creative 미수신 {len(missing)}건 — 해당 광고는 permalink/썸네일 없이 렌더됨", file=sys.stderr)
    return out


def b64_image(url):
    """리뷰 카드 썸네일 base64 embed (self-contained). 실패/과대 시 빈 문자열."""
    if not url:
        return ""
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            data = r.read()
        if len(data) > THUMB_MAX_BYTES or not ctype.startswith("image/"):
            return ""
        return f"data:{ctype};base64," + base64.b64encode(data).decode()
    except Exception:
        return ""


def graph_ad_insights(since, until):
    """Graph ad-level insights (기간 합산 per ad). ctr/cpc 는 게이트 정의와 동일 재계산."""
    rows = api_get(f"{ACCT}/insights", {
        "level": "ad",
        "fields": "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
                  "spend,impressions,clicks,inline_link_clicks,reach,frequency,actions",
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 500,
    })
    out = []
    for r in rows:
        spend = to_float(r.get("spend"))
        impr = to_float(r.get("impressions"))
        clicks = to_float(r.get("clicks"))
        out.append({
            "campaign_id": r.get("campaign_id", ""), "campaign_name": r.get("campaign_name", ""),
            "adset_id": r.get("adset_id", ""), "adset_name": r.get("adset_name", ""),
            "ad_id": r.get("ad_id", ""), "ad_name": r.get("ad_name", ""),
            "spend": spend, "impressions": impr, "clicks": clicks,
            "link_clicks": to_float(r.get("inline_link_clicks")),   # 링크 클릭 (CPM 기준표 CTR 산식)
            "ctr": (clicks / impr * 100) if impr else 0.0,
            "cpc": (spend / clicks) if clicks else 0.0,
            "frequency": to_float(r.get("frequency")), "reach": to_float(r.get("reach")),
            "actions": r.get("actions") or [],
        })
    return out


def graph_weekly_account(since, until):
    rows = api_get(f"{ACCT}/insights", {
        "level": "account", "fields": "spend,impressions,clicks,actions",
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": 7,
    })
    weekly = []
    for r in rows:
        t = _totals([{"spend": r.get("spend"), "impressions": r.get("impressions"),
                      "clicks": r.get("clicks"), "actions": r.get("actions") or []}])
        ds, de = r.get("date_start", ""), r.get("date_stop", "")
        t["label"] = f"{int(ds[5:7])}/{int(ds[8:10])}~{int(de[5:7])}/{int(de[8:10])}" if len(ds) >= 10 and len(de) >= 10 else ""
        weekly.append(t)
    return weekly


def graph_account_totals(since, until):
    """계정 레벨 기간 총괄 — 월간 집행 성과 슬라이드용 (세은 8/3)."""
    rows = api_get(f"{ACCT}/insights", {
        "level": "account", "fields": "spend,impressions,clicks,actions",
        "time_range": json.dumps({"since": since, "until": until}),
    })
    return _totals([{"spend": r.get("spend"), "impressions": r.get("impressions"),
                     "clicks": r.get("clicks"), "actions": r.get("actions") or []} for r in rows])


def graph_structure(statuses):
    """계정 실측 구조: 캠페인별 ACTIVE adset/ad 수 + objective/optimization_goal."""
    camps = api_get(f"{ACCT}/campaigns", {"fields": "name,objective,effective_status", "limit": 100})
    adsets = api_get(f"{ACCT}/adsets", {"fields": "name,campaign_id,effective_status,optimization_goal,daily_budget", "limit": 500})
    ads = api_get(f"{ACCT}/ads", {"fields": "id,adset_id,effective_status", "limit": 500})
    adset_by_camp = defaultdict(list)
    for a in adsets:
        if a.get("effective_status") == "ACTIVE":
            adset_by_camp[a.get("campaign_id")].append(a)
    ads_by_adset = defaultdict(int)
    for a in ads:
        if a.get("effective_status") == "ACTIVE":
            ads_by_adset[a.get("adset_id")] += 1
    out = []
    for c in camps:
        if c.get("effective_status") != "ACTIVE":
            continue
        asets = adset_by_camp.get(c.get("id"), [])
        n_ads = sum(ads_by_adset.get(a.get("id"), 0) for a in asets)
        goals = {a.get("optimization_goal") for a in asets}
        budgets = {a.get("daily_budget") for a in asets if a.get("daily_budget")}
        out.append({
            "name": c.get("name", ""), "objective": c.get("objective", ""),
            "stage": adset_stage("", c.get("name", "")),
            "n_adsets": len(asets), "n_ads": n_ads,
            "goals": sorted(g for g in goals if g),
            "budgets": sorted(budgets),
            # adset 1개 = 크리에이터 릴 1개 시각화용 — adset 이름에서 크리에이터 추출
            "adset_creators": [creator_slug(a.get("name", "")) or "?" for a in asets],
        })
    return out


def dk_xcheck_totals(d_from, d_to):
    try:
        raw = DataKeeper().get("meta_ads_daily", date_from=d_from, date_to=d_to, brand=DK_META_BRAND)
        return _totals([_dk_norm(r) for r in raw]) if raw else None
    except Exception as e:
        print(f"  [warn] DK xcheck fail: {e}", file=sys.stderr)
        return None


def _ad_record(row, ref_date, statuses, creatives, tags):
    spend = to_float(row.get("spend"))
    lpv = extract_lpv(row.get("actions"))
    name = row.get("ad_name", "") or ""
    ad_id = row.get("ad_id", "") or ""
    cr = creatives.get(ad_id, {})
    perm = cr.get("permalink", "")
    m = SC_RE.search(perm)
    sc = m.group(1) if m else ""
    tag, km_source = _resolve_tag(name, sc, tags)
    paid = parse_paid_flag(name)
    is_wl = ("WL" in name) or ("@" in name) or paid in ("PAID", "GIFT")
    clicks = to_float(row.get("clicks"))
    impr = to_float(row.get("impressions"))
    v3 = extract_v3(row.get("actions"))
    return {
        "ad_id": ad_id, "ad_name": name,
        "campaign_name": row.get("campaign_name", ""), "adset_name": row.get("adset_name", ""),
        "stage": adset_stage(row.get("adset_name", ""), row.get("campaign_name", "")),
        "status": statuses.get(ad_id, ""),
        "paid_flag": paid, "is_wl": is_wl,
        "days_live": calc_days_live(name, ref_date),
        "spend": spend, "impressions": impr,
        "clicks": clicks,
        "link_clicks": to_float(row.get("link_clicks")),
        "v3": v3, "rate3s": (v3 / impr * 100) if impr else 0,
        "ctr": to_float(row.get("ctr")), "cpc": to_float(row.get("cpc")),
        "freq": to_float(row.get("frequency")),
        "lpv": lpv, "cplpv": cplpv_calc(spend, lpv),
        "click_to_lpv": (lpv / clicks * 100) if clicks else 0,   # 클릭→LP 도달률
        "permalink": perm, "shortcode": sc, "km_source": km_source,
        "thumb_url": cr.get("thumb_url", ""), "thumb_b64": "",
        "km": tag.get("km", ""), "km_label": tag.get("km_label", ""),
        "hooks": tag.get("hooks", []), "hook_label": tag.get("hook_label", ""),
        "ig_username": tag.get("username", ""),
        "review_note": tag.get("review_note", ""),
    }


def _totals(rows):
    spend = sum(to_float(r.get("spend")) for r in rows)
    impr = sum(to_float(r.get("impressions")) for r in rows)
    clicks = sum(to_float(r.get("clicks")) for r in rows)
    lpv = sum(extract_lpv(r.get("actions")) for r in rows)
    v3 = sum(extract_v3(r.get("actions")) for r in rows)
    return {
        "spend": spend, "impressions": impr, "clicks": clicks, "lpv": lpv,
        "ctr": (clicks / impr * 100) if impr else 0,
        "cpc": (spend / clicks) if clicks else 0,
        "cplpv": cplpv_calc(spend, lpv),
        "v3": v3, "rate3s": (v3 / impr * 100) if impr else 0,
    }


def collect():
    ref = REF_TODAY - timedelta(days=1)
    d7_from = (ref - timedelta(days=6)).isoformat()
    p7_from = (ref - timedelta(days=13)).isoformat()
    p7_to = (ref - timedelta(days=7)).isoformat()
    d30_from = (ref - timedelta(days=29)).isoformat()
    p30_from = (ref - timedelta(days=59)).isoformat()
    p30_to = (ref - timedelta(days=30)).isoformat()

    print("[1/7] Graph ad insights (7d/prev7/30d/prev30/생애)…")
    agg7 = graph_ad_insights(d7_from, ref.isoformat())
    aggP = graph_ad_insights(p7_from, p7_to)
    agg30 = graph_ad_insights(d30_from, ref.isoformat())
    aggP30 = graph_ad_insights(p30_from, p30_to)   # 직전 30일 (운영 성과 월간 비교, 세은 7/27)
    aggL = graph_ad_insights(DATA_FROM, ref.isoformat())
    if not agg7 and not aggL:
        sys.exit("[FATAL] Graph insights 0건 — META_JP_ACCESS_TOKEN/계정 확인")
    if not agg7:
        print("  [warn] 최근 7일 insights 0건 (생애 데이터만 수신) — 7d 표는 빈 값으로 렌더됨", file=sys.stderr)

    print("[2/7] Graph 주간 시계열…")
    weekly = graph_weekly_account((ref - timedelta(days=55)).isoformat(), ref.isoformat())
    # 전월 월간 총괄 (세은 8/3 지시 — 전월 vs 전전월, 달력 월 기준 계정 실측)
    _m1e = ref.replace(day=1) - timedelta(days=1)
    _m1s = _m1e.replace(day=1)
    _m0e = _m1s - timedelta(days=1)
    _m0s = _m0e.replace(day=1)
    totals_month = graph_account_totals(_m1s.isoformat(), _m1e.isoformat())
    totals_month_prev = graph_account_totals(_m0s.isoformat(), _m0e.isoformat())

    print("[3/7] Graph 실시간 status + 계정 구조…")
    statuses = live_ad_statuses()
    structure = graph_structure(statuses)
    # 크리에이터별 현재 ACTIVE 단계 — 계정 전체 광고 기준 (오늘 승격된 새 Proven ad 는
    # 아직 insights 에 없어 성과 rows 만으론 live 판정이 늦는다. 세은 7/20 승격 반영)
    live_stages = defaultdict(set)
    try:
        _ads_all = api_get(f"{ACCT}/ads", {
            "fields": "name,effective_status,adset{name,campaign{name}}", "limit": 500})
    except Exception as e:
        _ads_all = []
        print(f"  [warn] 계정 광고 목록 조회 실패 — 성과 rows 기준 live 판정만 사용: {e}", file=sys.stderr)
    live_cts = defaultdict(set)   # CT 토큰 단위 ACTIVE 단계 — 재편성된 콘텐츠의 신버전 추적
    for a in _ads_all:
        if a.get("effective_status") != "ACTIVE":
            continue
        nm = a.get("name", "")
        sl = creator_slug(nm)
        if not sl:
            continue
        _as = a.get("adset") or {}
        stg = adset_stage(_as.get("name", ""), (_as.get("campaign") or {}).get("name", ""))
        live_stages[sl].add(stg)
        mct = CTNUM_RE.search(nm)
        if mct:
            live_cts[mct.group(1)].add(stg)

    print("[4/7] Graph permalink/썸네일…")
    need_ids = [r["ad_id"] for r in agg7 if r["impressions"] > 0] + \
               [r["ad_id"] for r in sorted(aggL, key=lambda x: -x["spend"])[:60]] + \
               [r["ad_id"] for r in sorted(agg30, key=lambda x: -x["spend"])[:30]]
    creatives = fetch_creatives(need_ids)

    print("[5/7] Content Tags (JP) 시트 + 콜라보 시트(앱 콘텐츠 키)…")
    tags = None
    for attempt in (1, 2, 3):
        try:
            tags = load_tags()
            break
        except RuntimeError as e:
            if attempt == 3:
                raise
            print(f"  [warn] 태그 시트 읽기 실패 (시도 {attempt}/3) — 30s 후 재시도: {e}", file=sys.stderr)
            time.sleep(30)
    try:
        tags["collabs"] = load_collabs()
        print(f"  collab handles {len(tags['collabs'])}")
    except Exception as e:
        tags["collabs"] = {}
        print(f"  [warn] 콜라보 시트 로드 실패 — 콘텐츠 단위 매칭 없이 진행: {e}", file=sys.stderr)
    ct_organic = {}
    try:
        tags["ct_sc"], ct_organic = load_dk_ct_map()
        print(f"  DK ct→shortcode {len(tags['ct_sc'])} · organic {len(ct_organic)}")
    except Exception as e:
        tags["ct_sc"] = {}
        print(f"  [warn] DK content_posts ct 맵 로드 실패: {e}", file=sys.stderr)

    # ── 시청 지속(p25~p100·평균시청) + 지면 breakdown — BEST/WORST '왜' 분석 축 (플랜 A-1/A-3) ──
    print("[5b] Graph 시청 지속 + 지면 breakdown (7d)…")
    W_FIELDS = ["video_play_actions", "video_p25_watched_actions", "video_p50_watched_actions",
                "video_p75_watched_actions", "video_p95_watched_actions", "video_p100_watched_actions",
                "video_avg_time_watched_actions"]

    def _vv(row, f):
        for a in row.get(f) or []:
            if a.get("action_type") == "video_view":
                return to_float(a.get("value"))
        return 0.0
    watch_by_slug = defaultdict(lambda: defaultdict(float))
    try:
        wrows = api_get(f"{ACCT}/insights", {
            "level": "ad", "fields": "ad_id,ad_name,impressions," + ",".join(W_FIELDS),
            "time_range": json.dumps({"since": d7_from, "until": ref.isoformat()}), "limit": 500})
        for r in wrows:
            sl = creator_slug(r.get("ad_name", ""))
            if not sl:
                continue
            w = watch_by_slug[sl]
            im = to_float(r.get("impressions"))
            w["impr"] += im
            for f in W_FIELDS[:-1]:
                w[f] += _vv(r, f)
            w["avg_t_wsum"] += _vv(r, "video_avg_time_watched_actions") * im
    except Exception as e:
        print(f"  [warn] 시청 지속 fetch 실패 — 카드 '왜' 분석은 3축만: {e}", file=sys.stderr)
    place_by_slug = defaultdict(lambda: defaultdict(lambda: {"impr": 0.0, "clicks": 0.0}))
    try:
        prows = api_get(f"{ACCT}/insights", {
            "level": "ad", "fields": "ad_id,ad_name,impressions,clicks",
            "breakdowns": "publisher_platform,platform_position",
            "time_range": json.dumps({"since": d7_from, "until": ref.isoformat()}), "limit": 1000})
        for r in prows:
            sl = creator_slug(r.get("ad_name", ""))
            if not sl:
                continue
            pos = f"{r.get('publisher_platform', '')}:{r.get('platform_position', '')}"
            place_by_slug[sl][pos]["impr"] += to_float(r.get("impressions"))
            place_by_slug[sl][pos]["clicks"] += to_float(r.get("clicks"))
    except Exception as e:
        print(f"  [warn] 지면 breakdown fetch 실패: {e}", file=sys.stderr)
    # 코드→자연어 라벨 (KM desc + 훅 이름KO) — 코드만 표기 금지 (세은 7/13 "숫자로만 쓰면 어떻게 아니")
    try:
        from tag_jp_content import load_taxonomy
        km_map, hook_map, _hd = load_taxonomy()
    except Exception as e:
        print(f"  [warn] 택소노미 라벨 로드 실패 — 코드만 표기됨, 시트 확인 필요: {e}", file=sys.stderr)
        km_map, hook_map = {}, {}

    life_by_id = {r["ad_id"]: r for r in aggL}
    ads7 = []
    for row in agg7:
        if row["impressions"] <= 0:
            continue
        rec = _ad_record(row, ref, statuses, creatives, tags)
        lr = life_by_id.get(rec["ad_id"])
        lrec = _ad_record(lr, ref, statuses, creatives, tags) if lr else None
        rec["life_spend"] = lrec["spend"] if lrec else rec["spend"]
        rec["life_lpv"] = lrec["lpv"] if lrec else rec["lpv"]
        rec["life_cplpv"] = lrec["cplpv"] if lrec else rec["cplpv"]
        rec["life_ctr"] = lrec["ctr"] if lrec else rec["ctr"]
        ads7.append(rec)

    # 꺼진 광고 분류 — 절대 룰 (7/7·7/9·7/13 세은 3회 교정): non-ACTIVE ≠ OFF.
    # 졸업 승격은 Testing 원본을 끄고 Proven 에 새 ad 로 재생성하므로, 동일 크리에이터
    # 신버전이 ACTIVE Proven 에 있으면 그건 "졸업 재편성"이지 죽인 게 아니다.
    act_proven_slugs = {_wl_slug(a["ad_name"]) for a in ads7
                        if a["status"] == "ACTIVE" and a["stage"] == "proven" and _wl_slug(a["ad_name"])}
    off30 = []
    for row in agg30:
        rec = _ad_record(row, ref, statuses, creatives, tags)
        if rec["spend"] >= OFF30_MIN_SPEND and rec["status"] and rec["status"] != "ACTIVE":
            lr = life_by_id.get(rec["ad_id"])
            lrec = _ad_record(lr, ref, statuses, creatives, tags) if lr else None
            rec["life_spend"] = lrec["spend"] if lrec else rec["spend"]
            rec["life_cplpv"] = lrec["cplpv"] if lrec else rec["cplpv"]
            sl = _wl_slug(rec["ad_name"])
            if sl and sl in act_proven_slugs:
                rec["off_class"] = "promoted"   # 졸업 재편성 — OFF 아님
            elif off_rule_check({"ctr": rec["ctr"], "cpc": rec["cpc"],
                                 "cplpv": rec["cplpv"] or 0})["off_recommend"]:
                rec["off_class"] = "gate"       # OFF 게이트 재현 hit — 죽임 확정
            else:
                rec["off_class"] = "stopped"    # 게이트 미달 아님 — 재편성/수동 여부 데이터로 판별 불가
            off30.append(rec)

    # ── 크리에이터(콘텐츠) 단위 생애 합산 — WL만, 이미지 제외 (2026-07-13 세은 확정 구성) ──
    # BEST3 = 생애 CPLPV 최저 3 / WORST3 = 최고 3 (첫 라이브 D+7 미만 신생 제외, OFF 포함 전수)
    # 최근 4 = 첫 라이브 최신순 중 D+7 이상 + BEST/WORST 미중복. spend < ₩20K 소액은 풀에서 제외.
    today = REF_TODAY
    groups = defaultdict(list)
    for r in aggL:
        sl = creator_slug(r.get("ad_name", ""))
        if sl:
            groups[sl].append(r)
    ads7_by_slug = defaultdict(list)
    for a in ads7:
        sl = creator_slug(a["ad_name"])
        if sl:
            ads7_by_slug[sl].append(a)
    prev_by_slug = defaultdict(list)   # 직전 7일 (성과 변동 비교축)
    for r in aggP:
        sl = creator_slug(r.get("ad_name", ""))
        if sl:
            prev_by_slug[sl].append(r)
    creators = []
    for sl, rs in groups.items():
        spend = sum(r["spend"] for r in rs)
        impr = sum(r["impressions"] for r in rs)
        clicks = sum(r["clicks"] for r in rs)
        lpv = sum(extract_lpv(r["actions"]) for r in rs)
        v3 = sum(extract_v3(r["actions"]) for r in rs)
        lives = [d for d in (calc_days_live(r.get("ad_name", ""), ref) for r in rs) if d is not None]
        first_live = (ref - timedelta(days=max(lives))).isoformat() if lives else ""
        days_since = (today - date.fromisoformat(first_live)).days if first_live else None
        rep = max(rs, key=lambda r: r["spend"])            # 대표 광고 = 생애 spend 최대 버전
        rep_rec = _ad_record(rep, ref, statuses, creatives, tags)
        # 다KM 크리에이터(릴↔광고 1:1 확정 불가)는 시트 태그 전체를 병기 — 미태깅 방치 X (세은 7/13 재태깅 반영)
        km_multi, hooks_multi = ([], [])
        if not rep_rec["km"]:
            km_multi, hooks_multi = creator_sheet_kms(rep_rec["ad_name"], tags)
        w7 = ads7_by_slug.get(sl, [])
        spend7 = sum(a["spend"] for a in w7)
        lpv7 = sum(a["lpv"] for a in w7)
        im7 = sum(a["impressions"] for a in w7)
        ck7 = sum(a["clicks"] for a in w7)
        lk7 = sum(a.get("link_clicks", 0) for a in w7)
        v37 = sum(a["v3"] for a in w7)
        pr = prev_by_slug.get(sl, [])
        sp_p = sum(r["spend"] for r in pr)
        im_p = sum(r["impressions"] for r in pr)
        ck_p = sum(r["clicks"] for r in pr)
        lv_p = sum(extract_lpv(r["actions"]) for r in pr)
        v3_p = sum(extract_v3(r["actions"]) for r in pr)
        # '왜' 분석 축 (플랜 A): 시청 지속·빈도·지면 구성·오가닉 (7d)
        wt = watch_by_slug.get(sl)
        if wt and wt["impr"] > 0:
            _wi = wt["impr"]
            watch7 = {"plays": wt["video_play_actions"] / _wi * 100,
                      "p25": wt["video_p25_watched_actions"] / _wi * 100,
                      "p50": wt["video_p50_watched_actions"] / _wi * 100,
                      "p75": wt["video_p75_watched_actions"] / _wi * 100,
                      "p95": wt["video_p95_watched_actions"] / _wi * 100,
                      "p100": wt["video_p100_watched_actions"] / _wi * 100,
                      "avg_t": wt["avg_t_wsum"] / _wi}
        else:
            watch7 = None
        freq7 = (sum(a["freq"] * a["impressions"] for a in w7) / im7) if im7 else 0
        _pl = place_by_slug.get(sl) or {}
        _tp = sum(v["impr"] for v in _pl.values())
        place7 = (sorted(((k, v["impr"] / _tp * 100, (v["clicks"] / v["impr"] * 100 if v["impr"] else 0))
                          for k, v in _pl.items()), key=lambda x: -x[1])[:3] if _tp else [])
        _ct = next((CTNUM_RE.search(a["ad_name"]).group(1)
                    for a in w7 if CTNUM_RE.search(a["ad_name"])), "")
        organic = ct_organic.get(_ct) if _ct else None
        creators.append({
            "slug": sl, "n_ads": len(rs), "is_wl": True,
            "spend": spend, "lpv": lpv,
            "impressions": impr, "clicks": clicks,
            "ctr": clicks / impr * 100 if impr else 0,
            "cpc": spend / clicks if clicks else 0,
            "cplpv": cplpv_calc(spend, lpv),
            "click_to_lpv": (lpv / clicks * 100) if clicks else 0,
            "v3": v3, "rate3s": v3 / impr * 100 if impr else 0,
            "first_live": first_live, "days_since": days_since,
            # live/단계 = 성과 rows 의 ACTIVE + 계정 전체 광고의 ACTIVE (신규 승격분 즉시 반영)
            "live": any(statuses.get(r.get("ad_id", "")) == "ACTIVE" for r in rs) or bool(live_stages.get(sl)),
            "stage_live": ("proven" if "proven" in live_stages.get(sl, set())
                           else next((a["stage"] for a in w7 if a["status"] == "ACTIVE"),
                                     "testing" if "testing" in live_stages.get(sl, set()) else "")),
            "spend7": spend7, "cplpv7": cplpv_calc(spend7, lpv7),
            "clicks7": ck7, "lpv7": lpv7, "im7": im7, "v37": v37, "link7": lk7,
            "link_ctr7": lk7 / im7 * 100 if im7 else 0,
            "ctr7": ck7 / im7 * 100 if im7 else 0,
            "cpc7": spend7 / ck7 if ck7 else 0,
            "rate3s7": v37 / im7 * 100 if im7 else 0,
            "click_to_lpv7": (lpv7 / ck7 * 100) if ck7 else 0,
            "spend_p7": sp_p, "cplpv_p7": cplpv_calc(sp_p, lv_p),
            "ctr_p7": ck_p / im_p * 100 if im_p else 0,
            "rate3s_p7": v3_p / im_p * 100 if im_p else 0,
            "watch7": watch7, "freq7": freq7, "place7": place7, "organic": organic,
            "km": rep_rec["km"], "km_label": rep_rec["km_label"], "km_multi": km_multi,
            "hooks": rep_rec["hooks"] or hooks_multi,
            "ig_username": rep_rec["ig_username"], "ad_name": rep_rec["ad_name"],
            "review_note": rep_rec.get("review_note", ""),
            "permalink": rep_rec["permalink"], "shortcode": rep_rec["shortcode"],
            "thumb_url": rep_rec["thumb_url"], "thumb_b64": "",
            "paid_flag": rep_rec["paid_flag"],
        })
    # 주간 리뷰 = BEST 4 / WORST 4 (세은 7/20 7차) — 지난 7일 CPLPV 상·하위 4, 소액(<₩3,000) 제외
    wpool = [c for c in creators if c["spend7"] >= OFF30_MIN_SPEND]
    week_best = sorted([c for c in wpool if c["cplpv7"]], key=lambda c: c["cplpv7"])[:4]
    _bset = {b["slug"] for b in week_best}
    week_worst = sorted([c for c in wpool if c["slug"] not in _bset],
                        key=lambda c: -(c["cplpv7"] or 9e9))[:4]
    week_cards = week_best + week_worst
    # ── 승격 전후 효율 (Testing 구버전 vs Proven 신버전 — 같은 크리에이터 릴) ──
    promotion = []
    for sl, rs in groups.items():
        by_stage = defaultdict(list)
        for r in rs:
            by_stage[adset_stage(r.get("adset_name", ""), r.get("campaign_name", ""))].append(r)
        if by_stage.get("testing") and by_stage.get("proven"):
            def _m(xs):
                sp = sum(x["spend"] for x in xs)
                im = sum(x["impressions"] for x in xs)
                ck = sum(x["clicks"] for x in xs)
                lv = sum(extract_lpv(x["actions"]) for x in xs)
                return {"spend": sp, "lpv": lv, "ctr": ck / im * 100 if im else 0,
                        "cpc": sp / ck if ck else 0, "cplpv": cplpv_calc(sp, lv)}
            tm, pm = _m(by_stage["testing"]), _m(by_stage["proven"])
            if tm["cplpv"] and pm["cplpv"] and tm["spend"] > 5000 and pm["spend"] > 5000:
                live = any(statuses.get(x.get("ad_id", "")) == "ACTIVE" for x in by_stage["proven"])
                promotion.append({"slug": sl, "t": tm, "p": pm, "live": live})
    promotion.sort(key=lambda x: x["p"]["cplpv"])

    # ── 소재 형태별 생애 실측 (WL vs 이미지) — "현재 왜 WL만 운영하나" 근거 표 ──
    def _is_wl_name(name):
        return ("WL" in (name or "")) or ("@" in (name or "")) or \
               parse_paid_flag(name or "") in ("PAID", "GIFT")

    def _fmt_perf(rows):
        sp = sum(r["spend"] for r in rows)
        im = sum(r["impressions"] for r in rows)
        ck = sum(r["clicks"] for r in rows)
        lv = sum(extract_lpv(r["actions"]) for r in rows)
        return {"n": len(rows), "spend": sp, "lpv": lv,
                "ctr": ck / im * 100 if im else 0,
                "cpc": sp / ck if ck else 0, "cplpv": cplpv_calc(sp, lv)}
    format_perf = {"wl": _fmt_perf([r for r in aggL if _is_wl_name(r.get("ad_name"))]),
                   "img": _fmt_perf([r for r in aggL if not _is_wl_name(r.get("ad_name"))])}

    # ── 캠페인/Ad Set 단위 최근 7일 집계 (운영 성과 페이지, 세은 7/13) ──
    adset_groups = defaultdict(list)
    for r in agg7:
        if r["spend"] > 0:
            adset_groups[(r["campaign_name"], r["adset_name"])].append(r)
    adsets_7d = []
    for (cn, an), rs in adset_groups.items():
        sp = sum(r["spend"] for r in rs)
        im = sum(r["impressions"] for r in rs)
        ck = sum(r["clicks"] for r in rs)
        lv = sum(extract_lpv(r["actions"]) for r in rs)
        adsets_7d.append({
            "campaign": cn, "adset": an, "n_ads": len(rs),
            "stage": adset_stage(an, cn),
            "live": any(statuses.get(r.get("ad_id", "")) == "ACTIVE" for r in rs),
            "spend": sp, "lpv": lv, "ctr": ck / im * 100 if im else 0,
            "cpc": sp / ck if ck else 0, "cplpv": cplpv_calc(sp, lv)})
    adsets_7d.sort(key=lambda x: (x["stage"] != "testing", x["campaign"], -x["spend"]))

    # ── 오디언스/지면 브레이크다운 (최근 30일, 계정 레벨) ──
    def _bd(breakdowns):
        try:
            return api_get(f"{ACCT}/insights", {
                "level": "account", "fields": "impressions,clicks",
                "time_range": json.dumps({"since": d30_from, "until": ref.isoformat()}),
                "breakdowns": breakdowns, "limit": 100})
        except Exception as e:
            print(f"  [warn] breakdown fail({breakdowns}): {e}", file=sys.stderr)
            return []
    placements = [{"platform": r.get("publisher_platform", ""), "position": r.get("platform_position", ""),
                   "impressions": to_float(r.get("impressions")), "clicks": to_float(r.get("clicks"))}
                  for r in _bd("publisher_platform,platform_position")]
    ages = [{"age": r.get("age", ""), "impressions": to_float(r.get("impressions")),
             "clicks": to_float(r.get("clicks"))} for r in _bd("age")]

    # 이번 주 신규 런칭 — 광고(콘텐츠) 단위 (세은 7/20 5차: 기존 크리에이터의 신규 릴도
    # 포함해야 하므로 크리에이터 단위 first_live 로 잡으면 누락. ad_name 날짜 토큰 기준)
    week_days = (ref - date.fromisoformat(d7_from)).days
    new_ads, _seen_nl = [], set()
    for row in sorted(agg7, key=lambda r: -r["spend"]):
        rec = _ad_record(row, ref, statuses, creatives, tags)
        dl = rec["days_live"]
        if dl is None or dl > week_days:
            continue
        key = (creator_slug(rec["ad_name"]), rec["shortcode"] or rec["ad_name"])
        if key in _seen_nl:
            continue
        _seen_nl.add(key)
        if not rec["km"]:   # 릴 복수 크리에이터는 시트 태그 union 병기 (미태깅 방치 X)
            km_multi, hooks_multi = creator_sheet_kms(rec["ad_name"], tags)
            rec["km_multi"] = km_multi
            if not rec["hooks"]:
                rec["hooks"] = hooks_multi
        rec["launch_date"] = (ref - timedelta(days=dl)).isoformat()
        _mct = CTNUM_RE.search(rec["ad_name"])
        rec["ct_live_stages"] = sorted(live_cts.get(_mct.group(1), set())) if _mct else []
        new_ads.append(rec)
    new_ads.sort(key=lambda r: r["launch_date"])

    print("[6/7] 리뷰 카드 썸네일 embed…")
    for c in week_cards:
        c["thumb_b64"] = b64_image(c["thumb_url"])
    for rec in new_ads:
        rec["thumb_b64"] = b64_image(rec["thumb_url"])

    launches = defaultdict(int)
    for row in aggL:
        d = calc_days_live(row.get("ad_name", ""), ref)
        if d is not None:
            launch = ref - timedelta(days=d)
            launches[launch.strftime("%Y-%m")] += 1

    # 풀 기준선 — 시청 지속·지면 (카드 '왜' 판정의 비교축)
    _wp = defaultdict(float)
    for w in watch_by_slug.values():
        for k, v in w.items():
            _wp[k] += v
    watch_pool = None
    if _wp.get("impr"):
        _wi = _wp["impr"]
        watch_pool = {"plays": _wp["video_play_actions"] / _wi * 100,
                      "p25": _wp["video_p25_watched_actions"] / _wi * 100,
                      "p50": _wp["video_p50_watched_actions"] / _wi * 100,
                      "p75": _wp["video_p75_watched_actions"] / _wi * 100,
                      "p95": _wp["video_p95_watched_actions"] / _wi * 100,
                      "p100": _wp["video_p100_watched_actions"] / _wi * 100,
                      "avg_t": _wp["avg_t_wsum"] / _wi}
    _pp = defaultdict(lambda: {"impr": 0.0, "clicks": 0.0})
    for _pl in place_by_slug.values():
        for k, v in _pl.items():
            _pp[k]["impr"] += v["impr"]
            _pp[k]["clicks"] += v["clicks"]
    _tot_p = sum(v["impr"] for v in _pp.values())
    place_pool = ({k: v["impr"] / _tot_p * 100 for k, v in _pp.items()} if _tot_p else {})

    print("[7/7] DK 교차검증 (7d)…")
    xcheck = dk_xcheck_totals(d7_from, ref.isoformat())

    # ── 일별 시계열 (경향성 코호트 — 세은 7/20: 승격군/잔류군 주간 CPLPV 추이) ──
    print("[7b] Graph 일별 ad 시계열 (경향성)…")
    daily = []
    for attempt in (1, 2):
        try:
            daily = api_get(f"{ACCT}/insights", {
                "level": "ad",
                "fields": "ad_id,ad_name,adset_name,campaign_name,spend,impressions,clicks,actions",
                "time_range": json.dumps({"since": DATA_FROM, "until": ref.isoformat()}),
                "time_increment": 1,
                "limit": 500,
            })
            break
        except Exception as e:
            print(f"  [warn] daily fetch 실패 (시도 {attempt}/2): {e}", file=sys.stderr)
            if attempt == 1:
                time.sleep(60)   # Graph 레이트리밋(403) 회복 대기
    _prev_dc = []
    if not daily and SSOT_PATH.exists():
        # 무거운 일별 fetch 실패로 수집 전체를 죽이지 않는다 — 직전 ssot 시계열 재사용 (명시 warn)
        try:
            _prev_dc = json.loads(SSOT_PATH.read_text(encoding="utf-8")).get("daily_creator") or []
        except (OSError, json.JSONDecodeError):
            _prev_dc = []
        if _prev_dc:
            print(f"  [warn] 직전 ssot 의 ad-day {len(_prev_dc)}행 재사용 — 경향성 슬라이드만 직전 수집 기준",
                  file=sys.stderr)
    daily_creator = []   # ad-day 단위 (ad_id 보존 — Testing 잔류군은 콘텐츠=광고 단위 전수 집계)
    for r in daily:
        sl = creator_slug(r.get("ad_name", ""))
        d = r.get("date_start", "")
        if not sl or not d:
            continue
        daily_creator.append({
            "slug": sl, "date": d,
            "ad_id": r.get("ad_id", ""), "ad_name": r.get("ad_name", ""),
            "stage": adset_stage(r.get("adset_name", ""), r.get("campaign_name", "")),
            "spend": to_float(r.get("spend")), "lpv": extract_lpv(r.get("actions")),
        })
    daily_creator.sort(key=lambda x: (x["slug"], x["date"]))
    if not daily_creator and _prev_dc:
        daily_creator = _prev_dc
    print(f"  daily rows {len(daily)} → ad-day {len(daily_creator)}")

    ssot = {
        "pulled_at": datetime.now().isoformat(timespec="seconds"),
        "ref_date": ref.isoformat(),
        "window_7d": [d7_from, ref.isoformat()],
        "window_prev7": [p7_from, p7_to],
        "data_from": DATA_FROM,
        "gates": {
            "grad": {"cpc": GRAD_CPC_MAX, "ctr": GRAD_CTR_MIN, "cplpv": GRAD_CPLPV_MAX, "days": GRAD_MIN_DAYS},
            "off": {"cpc": OFF_D3_CPC_MAX, "ctr": OFF_D3_CTR_MIN, "cplpv": OFF_D3_CPLPV_OFF},
            "kpi": {"wl_ctr": KPI_WL_CTR, "img_ctr": KPI_IMG_CTR},
        },
        "cited_facts": CITED_FACTS,
        "totals_7d": _totals(agg7),
        "totals_prev7": _totals(aggP),
        "ads_7d": sorted(ads7, key=lambda a: (a["cplpv"] or 9e9)),
        "creators": sorted(creators, key=lambda c: (c["cplpv"] or 9e9)),
        "week_cards": [c["slug"] for c in week_cards],
        "week_best": [c["slug"] for c in week_best],
        "week_worst": [c["slug"] for c in week_worst],
        "week_pool_n": len(wpool),
        "watch_pool": watch_pool,
        "place_pool": place_pool,
        "new_launch_ads": new_ads,
        "off_30d": sorted(off30, key=lambda a: -a["spend"]),
        "weekly": weekly,
        "structure": structure,
        "promotion": promotion,
        "format_perf": format_perf,
        "adsets_7d": adsets_7d,
        "totals_30d": _totals(agg30),
        "totals_prev30": _totals(aggP30),
        "window_30d": [d30_from, ref.isoformat()],
        "window_prev30": [p30_from, p30_to],
        "totals_month": totals_month,
        "totals_month_prev": totals_month_prev,
        "window_month": [_m1s.isoformat(), _m1e.isoformat()],
        "window_month_prev": [_m0s.isoformat(), _m0e.isoformat()],
        "taxonomy": {"km": km_map, "hook": hook_map},
        "audience": {"placements": placements, "ages": ages},
        "launches_by_month": dict(sorted(launches.items())),
        "xcheck_dk_7d": xcheck,
        "daily_creator": daily_creator,
    }
    try:
        SSOT_PATH.write_text(json.dumps(ssot, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        sys.exit(f"[FATAL] ssot.json 저장 실패 ({SSOT_PATH}): {e}")
    print(f"saved → {SSOT_PATH}")
    try:  # 날짜별 사본 — 고정 파일 덮어쓰기로 과거 주 데이터 소실 방지 (7/27 11번 덱 사고)
        dated = OUT_DIR / f"ssot_{(ref + timedelta(days=1)).strftime('%Y%m%d')}.json"
        dated.write_text(json.dumps(ssot, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved → {dated}")
    except OSError as e:
        print(f"  [warn] ssot 날짜 사본 저장 실패: {e}", file=sys.stderr)
    return ssot


# ── render helpers ───────────────────────────────────────────────────────

def won(v):
    return f"₩{int(round(to_float(v))):,}"


def won_or_dash(v):
    v = to_float(v)
    return won(v) if v > 0 else "—"


def band(ad):
    """색 밴드 = 운영 판정 로직 그대로 (off_rule_check 재사용)."""
    cpc, ctr = ad["cpc"], ad["ctr"]
    cplpv = ad["cplpv"] or 0
    if cpc > 0 and cplpv > 0 and cpc <= GRAD_CPC_MAX and ctr >= GRAD_CTR_MIN and cplpv <= GRAD_CPLPV_MAX:
        return "g"
    chk = off_rule_check({"ctr": ctr, "cpc": cpc, "cplpv": cplpv})
    if chk["off_recommend"]:
        return "r"
    if chk["monitoring"]:
        return "y2"
    return "y"


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def content_name(ad):
    if ad["ig_username"]:
        return "@" + ad["ig_username"]
    n = ad["ad_name"]
    m = re.search(r"@([A-Za-z0-9_.]+)", n)
    if m:
        return "@" + m.group(1)
    m = re.search(r"WL-[PG]_(.+?)_B0", n)
    if m:
        return "@" + m.group(1).lower()
    parts = [p.strip() for p in n.split("|")]
    if len(parts) >= 3:
        return parts[2]
    return (n[:28] + "…") if len(n) > 28 else n


def km_short(ad, km_tax=None):
    """KM 표기 = 코드 + 자연어 라벨 병기 의무 (세은 7/13 '숫자로만 쓰면 어떻게 아니')."""
    km_tax = km_tax or {}
    if ad["km"]:
        lbl = ad["km_label"] or ""
        m = KM_RE.search(lbl)
        rest = (lbl[m.end():] if m else lbl).strip(" -–:,")
        if not rest:   # km_manual 에 코드만 저장된 행 — 택소노미 이름으로 폴백 (코드 단독 표기 금지)
            rest = (km_tax.get(ad["km"], "") or "").strip(" -–:,")
        rest = rest.split(",")[0][:26]
        return f"{ad['km']}<span class=dim> {esc(rest)}</span>" if rest else ad["km"]
    multi = ad.get("km_multi") or []
    if multi:  # 다KM 크리에이터 — 릴↔광고 1:1 매칭 불가라 시트 태그 전부 병기
        parts = []
        for k in multi:
            nm = km_tax.get(k, "").split(",")[0][:14]
            parts.append(f"{esc(k)}<span class=dim> {esc(nm)}</span>" if nm else esc(k))
        return " · ".join(parts) + "<span class=dim> (릴 복수)</span>"
    return "<span class=dim>미태깅</span>" if ad["is_wl"] else "<span class=dim>이미지</span>"


def verdict_of(ad):
    """리뷰 카드 판정 뱃지 — 실제 상태·게이트 그대로. 졸업 재편성은 절대 OFF 로 표기 금지.

    'OFF(죽임)' 표기는 OFF 게이트 재현 hit 일 때만. 그 외 정지는 사유 단정 금지.
    """
    if ad.get("off_class") == "promoted":
        return ("keep", "졸업 재편성 — 신버전 Proven 라이브")
    if ad.get("off_class") == "gate":
        return ("kill", "OFF — 게이트가 잘랐다")
    if ad["status"] and ad["status"] != "ACTIVE":
        return ("watch", "정지 — 게이트 미달 아님 (사유 별도)")
    if ad["stage"] == "proven":
        return ("keep", "Proven — 살림·증액 대상")
    b = band(ad)
    if b == "g":
        return ("keep", "졸업 게이트 통과 — 승격 대기")
    if b == "y2":
        return ("watch", "D+5 유예 — 관찰")
    return ("watch", "Testing — 관찰 중")


def review_story(ad, g):
    """'무엇이 얼마나' 압축 1줄 — 훅 축(CTR) · 랜딩 축(CPLPV) 지표 관찰만 (추측 어휘 금지)."""
    ctr, cplpv = ad["ctr"], ad["cplpv"] or 0
    c2l = ad.get("click_to_lpv", 0)
    if ctr >= g["grad"]["ctr"]:
        hook_ax = f"훅 강함 — CTR {ctr:.1f}% (기준 {g['grad']['ctr']:.0f}%↑)"
    elif ctr < g["off"]["ctr"]:
        hook_ax = f"훅 약함 — CTR {ctr:.1f}% (OFF 기준 미달)"
    else:
        hook_ax = f"훅 중간 — CTR {ctr:.1f}%"
    if not cplpv:
        land_ax = "CPLPV 미산출"
    elif cplpv <= g["grad"]["cplpv"]:
        land_ax = f"랜딩 우수 — CPLPV {won(cplpv)} (기준 {int(g['grad']['cplpv'])}↓ · 클릭→LP {c2l:.0f}%)"
    elif cplpv >= g["off"]["cplpv"]:
        land_ax = f"랜딩 손실 — CPLPV {won(cplpv)} (OFF 기준 초과 · 클릭→LP {c2l:.0f}%)"
    else:
        land_ax = f"랜딩 중간 — CPLPV {won(cplpv)}"
    return f"{hook_ax} · {land_ax}"


def creator_story(c, avg):
    """왜 잘/안 됐나 — 퍼널 2축(훅=CTR, 랜딩=클릭→LP 도달률)을 풀 평균과 비교 분해. 관찰 수치만, 추측 X."""
    d_ctr = c["ctr"] - avg["ctr"]
    d_c2l = c["click_to_lpv"] - avg["c2l"]
    line1 = (f"훅(CTR) <b>{c['ctr']:.1f}%</b> (풀 {avg['ctr']:.1f}%, {d_ctr:+.1f}pt) · "
             f"랜딩 도달(클릭→LP) <b>{c['click_to_lpv']:.0f}%</b> (풀 {avg['c2l']:.0f}%, {d_c2l:+.0f}pt) · "
             f"CPC {won(c['cpc'])} (풀 {won(avg['cpc'])})")
    if d_ctr >= 0 and d_c2l >= 0:
        concl = "훅·랜딩 두 축 모두 풀 평균 위 — 낮은 CPLPV의 구성 그 자체"
    elif d_ctr >= 0:
        concl = "훅으로 모은 클릭이 LP 로드 전에 이탈 — CPLPV를 깎는 축은 랜딩"
    elif d_c2l >= 0:
        concl = "클릭 이후는 정상인데 훅에서 안 멈춤 — CPLPV를 깎는 축은 훅"
    else:
        concl = "훅·랜딩 두 축 모두 풀 평균 아래 — 전 퍼널 열세"
    return f"{line1}<br><b>{concl}</b>"


def render(ssot, deck_path):
    g = ssot["gates"]
    cf = CITED_FACTS   # 코드 상수가 SSOT — ssot.json 사본은 수집 시점 기록용 (stale 출처 문구 방지)
    t7, tp = ssot["totals_7d"], ssot["totals_prev7"]
    ads = ssot["ads_7d"]
    by_id = {a["ad_id"]: a for a in ads}
    off_by_id = {a["ad_id"]: a for a in ssot["off_30d"]}
    act = [a for a in ads if a["status"] == "ACTIVE"]
    # 요약 박스 카운트는 계정 구조 실측(현재 등록 ACTIVE) 기준 — 7d 노출 유무와 무관
    n_test = sum(c["n_ads"] for c in ssot["structure"] if c["stage"] == "testing")
    n_prov = sum(c["n_ads"] for c in ssot["structure"] if c["stage"] == "proven")

    def wow(cur, prev, lower_is_better=False, neutral=False):
        cur, prev = to_float(cur), to_float(prev)
        if prev <= 0:
            return ""
        d = (cur - prev) / prev * 100
        good = (d < 0) if lower_is_better else (d > 0)
        cls = "nt" if neutral else ("up" if good else "dn")
        return f"<span class='wow {cls}'>{'+' if d>0 else ''}{d:.0f}%</span>"

    # ── 구조 시각화 (실측) ──
    st = ssot["structure"]
    testing_c = [c for c in st if c["stage"] == "testing"]
    proven_c = [c for c in st if c["stage"] == "proven"]

    def _budsort(cs):  # adset daily_budget 실측값 (unique, 오름차순)
        out = set()
        for c in cs:
            for b in c["budgets"]:
                try:
                    out.add(int(b))
                except (TypeError, ValueError):
                    pass
        return sorted(out)
    test_buds, prov_buds = _budsort(testing_c), _budsort(proven_c)
    test_bud_label = (f"₩{test_buds[0]:,}/day" if len(test_buds) == 1 else
                      f"₩{test_buds[0]:,}~{test_buds[-1]:,}/day" if test_buds else "")
    prov_bud_label = (f"₩{prov_buds[0]:,}~{prov_buds[-1]:,}/day" if len(prov_buds) > 1 else
                      f"₩{prov_buds[0]:,}/day" if prov_buds else "")

    def camp_box(c, cls):
        budget = ""
        if c["budgets"]:
            try:
                budget = " · ".join(f"₩{int(b):,}/day" for b in sorted({int(x) for x in c["budgets"]}))
            except (TypeError, ValueError):
                budget = ""
        # 구조 트리: Campaign 루트 → Ad Set 가지 → Ad 잎 (누가의 ad인지는 표기 X — 구조 자체만, 세은 7/13)
        if c["stage"] == "testing":   # 1:1 — 캠페인 하나에서 Ad Set이 가지로 N개, 각 가지 끝에 Ad 1개
            shown = min(c["n_adsets"], 6)
            bud_span = f"<span>{budget}</span>" if budget else ""   # 실측 adset daily_budget
            branch = (f"<div class=tbranch><div class='tnode tas'>Ad Set{bud_span}</div>"
                      "<div class=tstem2></div><div class='tnode tad'>Ad<span>릴 1개</span></div></div>")
            branches = branch * shown
            if c["n_adsets"] > shown:
                branches += f"<div class=tbranch><div class='tnode tmore'>+{c['n_adsets']-shown}</div></div>"
                shown += 1
            tree = (f"<div class=tree><div class='tnode tcamp'>Campaign</div><div class=tstem></div>"
                    f"<div class=tbranches style='--n:{shown}'>{branches}</div></div>")
        else:                          # Proven = 캠페인 하나 → Ad Set 하나(통합) → 그 아래 Ad만 여러 개
            nads = c["n_ads"]
            leaves = "<div class=tbranch><div class='tnode tad'>Ad<span>릴 1개</span></div></div>" * nads
            tree = (f"<div class=tree><div class='tnode tcamp'>Campaign</div><div class=tstem></div>"
                    f"<div class=tbranches style='--n:1'><div class=tbranch>"
                    f"<div class='tnode tas'>Ad Set (통합){('<span>' + budget + '</span>') if budget else ''}</div>"
                    f"<div class=tstem2></div>"
                    f"<div class=tbranches style='--n:{nads}'>{leaves}</div>"
                    f"</div></div></div>")
        return f"""
      <div class='campbox {cls}'>
        <div class=campname>{esc(c['name'])}</div>
        <div class=campmeta>Objective: Traffic · 최적화: Landing Page Views{(' · adset ' + budget) if budget else ''}</div>
        <div class=campstats>Ad Set <b>{c['n_adsets']}</b>개 · Ads <b>{c['n_ads']}</b>개 (ACTIVE)</div>
        {tree}
      </div>"""

    structure_html = f"""
  <div class=structexplain>인플루언서 릴 하나가 들어오면 <b>전용 Ad Set(독립 지갑{', ' + test_bud_label if test_bud_label else ''}) 하나</b>를 만들어 Testing 캠페인에 넣는다.
  지갑이 분리돼 있어 릴끼리 예산을 뺏고 뺏기지 않음 → 성과 판정이 릴 단위로 깨끗하게 나온다.
  D+{g['grad']['days']}에 <b>졸업 게이트</b>(아래 3과목 시험)를 보고, 통과하면 Proven 캠페인으로 승격해 예산을 키운다.</div>
  <div class=structwrap>
    <div class=structcol>
      <div class=structcolh>① TESTING — 신규 릴 검증 (릴 1개 = Ad Set 1개)</div>
      {"".join(camp_box(c, 'tbox') for c in testing_c)}
      <div class=offarrow>↓ <b>OFF</b> — CPLPV가 내부 기준을 넘으면 OFF (CPC·CTR 나빠도 CPLPV 정상이면 D+5 유예)</div>
    </div>
    <div class=gradarrow>
      <div class=garr>➜</div>
      <div class=galabel><b>졸업 게이트 (D+{g['grad']['days']})</b><br>CPC ≤ {won(g['grad']['cpc'])}<br>CTR ≥ {g['grad']['ctr']:.0f}%<br>CPLPV ≤ {won(g['grad']['cplpv'])}<br>셋 다 통과 → 승격·증액</div>
    </div>
    <div class=structcol>
      <div class=structcolh>② PROVEN — 검증 완료 · 증액 운영</div>
      {"".join(camp_box(c, 'pbox') for c in proven_c)}
    </div>
  </div>"""

    # ── 판정 4색 (세은 7/20): 좋음=파랑 / 중간=초록 / 안 좋음=빨강 / 빨리 죽여야=검정 ──
    # 매핑 = 기존 게이트 로직 그대로 재사용 (새 임계값 발명 X):
    #   졸업 게이트 통과=파랑 · OFF 게이트 hit=검정 · CPC/CTR 열위(D+5 유예 관찰)=빨강 · 그 사이=초록
    C_CLS = {"g": "cb", "y": "cg", "y2": "cr", "r": "ck"}
    C_DOT = {"g": "🔵", "y": "🟢", "y2": "🔴", "r": "⚫"}
    C_ORD = {"g": 0, "y": 1, "y2": 2, "r": 3}
    R_TXT = {"g": "졸업 게이트 통과 — 늘릴 것",
             "y": "게이트 사이 — 관찰",
             "y2": "CPC·CTR 열위, CPLPV 정상 — D+5 유예 관찰",
             "r": "OFF 게이트 해당"}

    def ctype(c):
        """creator type = ad_name 명명 토큰 (WL-P 유상 / WL-G 무상) — HSTest 덱 (type) 관례."""
        return {"PAID": "WL-P 유상", "GIFT": "WL-G 무상"}.get(c.get("paid_flag", ""), "WL")

    def judge_metrics(c):
        """판정용 지표 — 지난 7일 노출 있으면 7d, 없으면 생애(1달 풀은 곧 전 기간)."""
        if c["spend7"] > 0:
            return {"spend": c["spend7"], "cplpv": c["cplpv7"], "ctr": c["ctr7"],
                    "cpc": c["cpc7"], "rate3s": c["rate3s7"], "c2l": c["click_to_lpv7"]}
        return {"spend": c["spend"], "cplpv": c["cplpv"], "ctr": c["ctr"],
                "cpc": c["cpc"], "rate3s": c["rate3s"], "c2l": c["click_to_lpv"]}

    def cband(c):
        m = judge_metrics(c)
        return band({"cpc": m["cpc"] or 0, "ctr": m["ctr"] or 0, "cplpv": m["cplpv"]})

    def reason4(c, b):
        if b == "r":
            return "OFF 게이트 해당 — " + ("지금 꺼야 함" if c["live"] else "이미 꺼짐 (게이트 판정)")
        if not c["live"]:
            # 게이트 미달 아닌데 꺼짐 — 사유 단정 금지 (7/13 룰: 재편성/수동 여부 데이터로 판별 불가)
            return R_TXT[b].split(" — ")[0] + " 지표 — 현재 OFF (사유 별도)"
        if c.get("stage_live") == "proven":
            return ("졸업 게이트 통과 — Proven 승격·운영 중" if b == "g"
                    else "Proven 운영 중 — " + R_TXT[b].split(" — ")[0])
        return R_TXT[b]

    c_by_slug = {c["slug"]: c for c in ssot["creators"]}
    creators_all = ssot["creators"]
    # 리뷰 풀 = 최근 1달 내 첫 라이브 (세은 7/20 — 이번 주 덱 기준)
    month_pool = sorted(
        [c for c in creators_all if c["days_since"] is not None and c["days_since"] <= 31],
        key=lambda c: (C_ORD[cband(c)], judge_metrics(c)["cplpv"] or 9e9))
    week_cards = [c_by_slug[s] for s in ssot.get("week_cards", []) if s in c_by_slug]
    # 성과 변동 = 직전 7일·최근 7일 양쪽 spend ≥ OFF30_MIN_SPEND 표본의 CPLPV 변화
    movers = []
    for c in creators_all:
        if (c["spend7"] >= OFF30_MIN_SPEND and c.get("spend_p7", 0) >= OFF30_MIN_SPEND
                and c["cplpv7"] and c.get("cplpv_p7")):
            movers.append(((c["cplpv7"] - c["cplpv_p7"]) / c["cplpv_p7"] * 100, c))
    movers.sort(key=lambda x: x[0])   # 개선(음수) 먼저

    # 코드→자연어 라벨 (세은 7/13 "숫자로만 쓰면 어떻게 아니" — 코드 단독 표기 금지)
    tax = ssot.get("taxonomy") or {}
    km_tax = tax.get("km", {})

    # 사유 분석 기준선 = 지난 7일 풀 전체 합산 평균 — 카드마다 이 선과의 편차로 3축 분해
    _ck7 = t7.get("clicks", 0)
    pool_avg = {"r3": t7.get("rate3s", 0), "ctr": t7.get("ctr", 0),
                "c2l": (t7.get("lpv", 0) / _ck7 * 100) if _ck7 else 0}

    wpool_w = ssot.get("watch_pool") or {}
    ppool = ssot.get("place_pool") or {}

    def story3(c):
        """왜 잘/안 됐나 (플랜 A) — 퍼널 5단계(훅→지속→클릭→랜딩→CPLPV) 풀 대비 분해
        + 소재 외 요인(지면·빈도·오가닉) 배제 + 이유(사람) review_note 병기. 관찰 수치만, 추측 X."""
        m = judge_metrics(c)
        d3 = m["rate3s"] - pool_avg["r3"]
        dc = m["ctr"] - pool_avg["ctr"]
        dl = m["c2l"] - pool_avg["c2l"]
        axes = [("훅(3S율)", d3), ("클릭(CTR)", dc), ("랜딩(클릭→LP)", dl)]
        seg = [f"3S <b>{m['rate3s']:.0f}%</b> ({d3:+.0f}pt)"]
        w = c.get("watch7")
        if w and wpool_w.get("p50") is not None:
            d50 = w["p50"] - wpool_w["p50"]
            axes.insert(1, ("지속(p50 시청)", d50))
            seg.append(f"p50 <b>{w['p50']:.0f}%</b> ({d50:+.0f}pt) · 평균시청 {w['avg_t']:.0f}s")
        seg.append(f"CTR <b>{m['ctr']:.1f}%</b> ({dc:+.1f}pt)")
        seg.append(f"클릭→LP <b>{m['c2l']:.0f}%</b> ({dl:+.0f}pt)")
        line1 = " · ".join(seg) + " <span class=dim>(풀 대비)</span>"
        ups = [n for n, d in axes if d >= 0]
        if len(ups) == len(axes):
            concl = "전 축 풀 평균 위 — 낮은 CPLPV의 구성 그 자체"
        elif not ups:
            concl = "전 축 풀 평균 아래 — 전 퍼널 열세"
        else:
            best_ax = max(axes, key=lambda x: x[1])[0]
            worst_ax = min(axes, key=lambda x: x[1])[0]
            concl = f"{best_ax} 우위 — 새는 축은 {worst_ax}"
        # 소재 외 요인 배제 (A-3) — 지면 구성·빈도·오가닉 관찰
        extras = []
        if c.get("place7") and ppool:
            top = c["place7"][0]
            psh = ppool.get(top[0], 0)
            pos = top[0].split(":")[-1].replace("facebook_", "fb ").replace("instagram_", "ig ")
            extras.append(f"지면 {esc(pos)} {top[1]:.0f}%<span class=dim>(풀 {psh:.0f}%)</span>"
                          + ("<b> — 구성 특이</b>" if abs(top[1] - psh) >= 15 else ""))
        if c.get("freq7"):
            extras.append(f"빈도 {c['freq7']:.1f}" + ("<b> — 피로 신호</b>" if c["freq7"] >= 4 else ""))
        og = c.get("organic")
        if og and og.get("views"):
            extras.append(f"오가닉 {int(og['views']):,}뷰")
        line2 = " · ".join(extras)
        out = f"{line1}<br><b>이유(데이터)</b> {concl}"
        if line2:
            out += f"<br><span class=dim>{line2}</span>"
        return out

    def reason_lines(c, mode):
        """지표 → 해석 가능성 (세은 7/20 발표 형식): BEST=잘 된 축만, WORST=부족한 축만.

        해석 문구는 보편 통념 프레임 — '가능성' 라벨 명시 (세은 지시 형식).
        """
        m = judge_metrics(c)
        w = c.get("watch7")
        wp50 = wpool_w.get("p50") if wpool_w else None
        cand = [
            ("3S율", m["rate3s"], pool_avg["r3"], 0,
             "첫 프레임·첫 자막이 스크롤을 세움 — 훅이 통했을 가능성",
             "첫 3초에서 시선을 못 세움 — 첫 프레임·오프닝이 약했을 가능성"),
            ("p50 시청 유지", (w or {}).get("p50"), wp50, 0,
             "훅이 건 기대를 전개가 유지 — 중간 이탈 적었을 가능성",
             "훅 이후 전개에서 이탈 — 본문이 늘어지거나 기대와 어긋났을 가능성"),
            ("CTR", m["ctr"], pool_avg["ctr"], 1,
             "누를 이유(소구·궁금증) 전달이 잘 됐을 가능성",
             "봤지만 누를 이유 부족 — 소구·클릭 유도가 약했을 가능성"),
            ("클릭→LP", m["c2l"], pool_avg["c2l"], 0,
             "클릭 의도가 진성 — 훅의 기대와 랜딩이 일치했을 가능성",
             "클릭 후 LP 도달 이탈 — 기대 불일치 가능성"),
        ]
        rows = [(n, v, p, v - p, dec, gt, bt) for n, v, p, dec, gt, bt in cand
                if v is not None and p]
        if mode == "best":
            sel = sorted([r for r in rows if r[3] > 0], key=lambda r: -r[3] / r[2])[:2]
        elif mode == "worst":
            sel = sorted([r for r in rows if r[3] < 0], key=lambda r: r[3] / r[2])[:2]
        else:   # 신규 등 — 절대 편차 큰 축 2개, 부호대로
            sel = sorted(rows, key=lambda r: -abs(r[3] / r[2]))[:2]
        if not sel:
            sel = sorted(rows, key=lambda r: -abs(r[3] / r[2]))[:1]
        lines = []
        for n, v, p, d, dec, gt, bt in sel:
            vs = f"{v:.{dec}f}%"
            ds = f"{d:+.{dec}f}pt"
            tag = "높음" if d > 0 else "부족"
            lines.append(f"<b>{esc(n)} {tag}</b> ({vs}, 풀 대비 {ds}) → {gt if d > 0 else bt}")
        return "<br>".join(lines)

    def week_card(c, i, mode="auto"):
        b = cband(c)
        m = judge_metrics(c)
        sc = c.get("shortcode", "")
        inner = (f"<img src='{c['thumb_b64']}'>" if c.get("thumb_b64") else "<div class=phbox>썸네일<br>없음</div>")
        playable = f" data-sc='{sc}'" if sc else ""
        playbtn = "<div class=playbtn>▶</div>" if sc else ""
        fl = c["first_live"][5:].replace("-", "/") if c["first_live"] else "?"
        name = "@" + (c["ig_username"] or c["slug"])
        return f"""
    <div class=rc>
      <div class=player{playable}>{inner}{playbtn}</div>
      <div class=rcinfo>
        <div class=rchead><span class=ridx>{i}</span> <b>{esc(name)}</b> <span class=ctype>{ctype(c)}</span> <span class=dim>{fl} 라이브</span></div>
        <div><span class='vb {C_CLS[b]}'>{C_DOT[b]} {reason4(c, b)}</span></div>
        <div class=tagchips>
          <span class=chipkm>KM {km_short(c, km_tax)}</span>
          <span class=chip3s>3S율 {m['rate3s']:.0f}%</span>
        </div>
        <div class=rmetrics4>
          <div><i>7d Spend</i><b>{won(m['spend'])}</b></div>
          <div><i>CTR</i><b>{m['ctr']:.1f}%</b></div>
          <div><i>CPC</i><b>{won(m['cpc'])}</b></div>
          <div class=hl><i>CPLPV</i><b>{won_or_dash(m['cplpv'])}</b></div>
        </div>
        <div class=rstory2>{reason_lines(c, mode)}</div>
      </div>
    </div>"""

    # 이번 주 신규 런칭 카드 — 광고(콘텐츠) 단위 (기존 크리에이터의 신규 릴 포함, 세은 7/20 5차)
    def _ad_card_c(rec):
        """ad 레코드 → 카드 빌더(week_card)가 먹는 콘텐츠 dict."""
        return {
            "spend7": rec["spend"], "cplpv7": rec["cplpv"], "ctr7": rec["ctr"], "cpc7": rec["cpc"],
            "rate3s7": rec["rate3s"], "click_to_lpv7": rec["click_to_lpv"],
            "spend": rec["spend"], "cplpv": rec["cplpv"], "ctr": rec["ctr"], "cpc": rec["cpc"],
            "rate3s": rec["rate3s"], "click_to_lpv": rec["click_to_lpv"],
            # 콘텐츠 단위 라이브 판정 — 이 광고가 꺼졌어도 같은 CT 의 신버전(승격 재편성)이 ACTIVE 면 라이브
            "live": rec["status"] == "ACTIVE" or bool(rec.get("ct_live_stages")),
            "stage_live": ("proven" if "proven" in (rec.get("ct_live_stages") or [])
                           else (rec["stage"] if rec["status"] == "ACTIVE"
                                 else ("testing" if rec.get("ct_live_stages") else ""))),
            "ig_username": rec["ig_username"], "slug": creator_slug(rec["ad_name"]) or rec["ad_name"][:16],
            "shortcode": rec["shortcode"], "thumb_b64": rec.get("thumb_b64", ""),
            "km": rec["km"], "km_label": rec["km_label"], "km_multi": rec.get("km_multi", []),
            "hooks": rec["hooks"], "is_wl": rec["is_wl"], "paid_flag": rec["paid_flag"],
            "first_live": rec.get("launch_date", ""), "n_ads": 1,
            "review_note": rec.get("review_note", ""),
        }
    new_launch = sorted([_ad_card_c(r) for r in ssot.get("new_launch_ads", [])],
                        key=lambda c: (C_ORD[cband(c)], judge_metrics(c)["cplpv"] or 9e9))

    # BEST 4 / WORST 4 (세은 7/20 7차 — 각각 + 잘/안 된 이유)
    week_best = [c_by_slug[s] for s in ssot.get("week_best", []) if s in c_by_slug]
    week_worst = [c_by_slug[s] for s in ssot.get("week_worst", []) if s in c_by_slug]
    n_wpool = ssot.get("week_pool_n", len(week_best) + len(week_worst))
    if new_launch:
        nl_cards = "".join(week_card(c, f"NEW {i}") for i, c in enumerate(new_launch, 1))
        nl_grid = "rcards2" if len(new_launch) <= 2 else ("rcards4" if len(new_launch) <= 4 else "rcards6")
        new_launch_html = f"<div class={nl_grid}>{nl_cards}</div>"
    else:
        new_launch_html = "<div class=dim style='padding:40px;font-size:16px'>이번 주 신규 런칭 콘텐츠 없음</div>"

    best_cards = "".join(week_card(c, f"BEST {i}", mode="best") for i, c in enumerate(week_best, 1))
    worst_cards = "".join(week_card(c, f"WORST {i}", mode="worst") for i, c in enumerate(week_worst, 1))
    _wsub = (f"{ssot['window_7d'][0][5:]}~{ssot['window_7d'][1][5:]} 노출 · 7d spend ₩{OFF30_MIN_SPEND:,}↑ 풀 {n_wpool}개 중 "
             f"7d CPLPV 기준 · 이유 = 3축(훅 3S율 · 클릭 CTR · 랜딩 클릭→LP) 풀 평균 대비 · 썸네일 클릭 = 릴 재생")
    review_slides = f"""
<section class=wide>
  <h2>지난 7일 BEST 4 — 왜 잘 됐나 <span class=h2sub>{_wsub}</span></h2>
  <div class=rcards4>{best_cards}</div>
</section>
<section class=wide>
  <h2>지난 7일 WORST 4 — 왜 안 됐나 <span class=h2sub>{_wsub}</span></h2>
  <div class=rcards4>{worst_cards}</div>
</section>"""

    # ── 부속: KM·훅별 성과(A-4). 잔존 오버레이(A-2)는 svg_trend 정의 후(경향성 블록 뒤)에 조립 ──
    def _grp_rows(keyf):
        # CPM 룰 (세은 8/3): 콘텐츠 퍼포먼스는 집행 7일 이상 숙성 기준
        g = defaultdict(lambda: {"n": 0, "sp": 0.0, "lpv": 0.0, "im": 0.0, "v3": 0.0, "lk": 0.0})
        for c in creators_all:
            if c["spend7"] < OFF30_MIN_SPEND:
                continue
            if (c.get("days_since") or 0) < 7:
                continue
            for k in keyf(c):
                g[k]["n"] += 1
                g[k]["sp"] += c["spend7"]
                g[k]["im"] += c.get("im7", 0)
                g[k]["v3"] += c.get("v37", 0)
                g[k]["lk"] += c.get("link7", 0)
                if c["cplpv7"]:
                    g[k]["lpv"] += c["spend7"] / c["cplpv7"]
        return [(k, v["n"], v["sp"], cplpv_calc(v["sp"], v["lpv"]),
                 (v["v3"] / v["im"] * 100) if v["im"] else 0,
                 (v["lk"] / v["im"] * 100) if v["im"] else 0) for k, v in g.items()]

    def _tag_table(title, rows, taxmap, sort="cplpv"):
        # KM별 = CPLPV 기준 (JP는 픽셀 매출 없음 — CPM 룰의 ROAS 축 대체) / 훅별 = 3초 생존률·링크CTR 기준
        rows = sorted(rows, key=(lambda r: (r[3] or 9e9)) if sort == "cplpv" else (lambda r: -r[4]))
        tr = "".join(
            f"<tr><td class=l>{esc(k)} <span class=dim>{esc((taxmap.get(k, '') or '').split(',')[0][:22])}</span></td>"
            f"<td>{n}</td><td>{won(sp)}</td><td>{r3:.0f}%</td><td>{lc:.1f}%</td><td class=b>{won_or_dash(cp)}</td></tr>"
            for k, n, sp, cp, r3, lc in rows[:5])
        return (f"<div class=boxh style='margin-top:8px'>{title}</div>"
                f"<table class=rank style='font-size:12px'>"
                f"<tr><th class=l>코드</th><th>콘텐츠</th><th>7d Spend</th><th>3S율</th><th>링크CTR</th><th>CPLPV</th></tr>{tr}</table>")
    # ── KM(소구)별 생애 실적 (세은 8/10: 훅 제거 · 지금까지 잘 나온 콘텐츠 위주로 KM 정리) ──
    _km_g = defaultdict(lambda: {"n": 0, "sp": 0.0, "lpv": 0.0, "ex": []})
    for c in creators_all:
        if (c.get("spend") or 0) < 20000 or not c.get("km"):
            continue
        k = c["km"]
        _km_g[k]["n"] += 1
        _km_g[k]["sp"] += c["spend"]
        if c.get("cplpv"):
            _km_g[k]["lpv"] += c["spend"] / c["cplpv"]
            _km_g[k]["ex"].append((c["cplpv"], c.get("ig_username") or c["slug"]))
    _km_rows_all = []
    for k, v in _km_g.items():
        _km_rows_all.append((k, v["n"], v["sp"], cplpv_calc(v["sp"], v["lpv"]), sorted(v["ex"])[:2]))
    _km_rows_all.sort(key=lambda r: (r[3] or 9e9))

    def _km_desc(k, nch=46):
        return esc((km_tax.get(k, "") or "").split(",")[0][:nch])
    # 순위 = 검증(n≥2) KM 만 경쟁 순위, 관찰(n<2)은 순위 밖
    km_body = ""
    _rk = 0
    for k, n, sp, cp, ex in _km_rows_all[:10]:
        _cls = "" if n >= 2 else " class=dim"
        _exs = " · ".join("@" + esc(h) for _, h in ex) or "—"
        _ntag = f"{n}" if n >= 2 else f"{n} <span class=dim>(관찰)</span>"
        if n >= 2:
            _rk += 1
            _rkcell = f"<td class=b style='color:#1256b0'>{_rk}위</td>"
        else:
            _rkcell = "<td class=dim>관찰</td>"
        km_body += (f"<tr{_cls}>{_rkcell}<td class=l><b>{esc(k)}</b></td>"
                    f"<td class=l>{_km_desc(k)}</td>"
                    f"<td>{_ntag}</td><td class=dim>{won(sp)}</td>"
                    f"<td>{won_or_dash(cp)}</td>"
                    f"<td class=l>{_exs}</td></tr>")
    km_table = (f"<table class=rank style='font-size:13px'>"
                f"<tr><th>순위</th><th class=l>KM 코드</th><th class=l>소구 내용</th><th>콘텐츠</th>"
                f"<th>누적 Spend</th><th>방문 1명 비용</th><th class=l>대표 콘텐츠</th></tr>{km_body}</table>")
    # Top3 카드 — 순위를 히어로로 (세은 8/10: 숫자(CPLPV)보다 '몇 위 KM'이 핵심)
    _top3 = [r for r in _km_rows_all if r[1] >= 2][:3]
    top_cards = ""
    for _i, (k, n, sp, cp, ex) in enumerate(_top3):
        _tc = ["tw-b", "tw-g", "tw-r"][_i]
        top_cards += (f"<div class='twcard {_tc} kmrank'><div class=twnum>{_i + 1}위</div>"
                      f"<b class=kmcode>{esc(k)}</b>"
                      f"<p class=kmdesc>{_km_desc(k, 64)}</p>"
                      f"<div class=kmmeta>방문 1명 <b>{won_or_dash(cp)}</b> · 콘텐츠 {n}개 · 누적 {won(sp)}</div></div>")
    tag_tables = (f"<div class=twrow>{top_cards}</div>"
                  f"<div class=boxh>KM 순위 — 방문 비용 낮은(=잘 먹힌) 순 (n≥2만 순위 · 관찰=흐림)</div>"
                  f"{km_table}")
    # (ret_slide 는 svg_trend 정의 후 조립 — slides 에 {ret_slide} 로 삽입)

    act_wl = [a for a in act if a["is_wl"]]   # 운영 성과 계산용 (이미지 소재 제외, 세은 7/13)

    # ── 최근 1달 런칭 전수 디스포지션 표 (SBV D+14 관례 — 행마다 판정 배지 + 사유) ──
    def disp_row(c):
        b = cband(c)
        m = judge_metrics(c)
        fl = c["first_live"][5:].replace("-", "/") if c["first_live"] else "?"
        st = ("Proven" if c["stage_live"] == "proven" else "Testing") if c["live"] else "OFF"
        win = "7d" if c["spend7"] > 0 else "생애"
        return (f"<tr class={C_CLS[b]}><td>{C_DOT[b]}</td>"
                f"<td class=l>@{esc(c['ig_username'] or c['slug'])}</td>"
                f"<td>{ctype(c)}</td>"
                f"<td class=l>{km_short(c, km_tax)}</td>"
                f"<td>{fl}</td><td>{st}</td><td>{win}</td><td>{won(m['spend'])}</td>"
                f"<td class=b>{m['rate3s']:.0f}%</td><td>{m['ctr']:.1f}%</td><td>{won(m['cpc'])}</td>"
                f"<td class=b>{won_or_dash(m['cplpv'])}</td>"
                f"<td class=l>{reason4(c, b)}</td></tr>")
    disp_rows = "\n".join(disp_row(c) for c in month_pool)

    # 한눈 4색 분포 + 3S율 인사이트 (노출 가중 평균, 파랑군 vs 빨강·검정군)
    bc = {k: 0 for k in ("g", "y", "y2", "r")}
    for c in month_pool:
        bc[cband(c)] += 1

    def _wavg3(cs):
        im = sum(c["impressions"] for c in cs)
        v = sum(c.get("v3", 0) for c in cs)
        return v / im * 100 if im else 0
    good_r3 = _wavg3([c for c in month_pool if cband(c) == "g"])
    bad_r3 = _wavg3([c for c in month_pool if cband(c) in ("y2", "r")])

    # ── 성과 변동 표 (직전 7일 vs 최근 7일 — 움직인 축 병기) ──
    def mover_axis(c):
        d3 = c["rate3s7"] - c["rate3s_p7"]
        dc = c["ctr7"] - c["ctr_p7"]
        parts = []
        if abs(d3) >= 2:
            parts.append(f"3S율 {d3:+.0f}pt")
        if abs(dc) >= 0.5:
            parts.append(f"CTR {dc:+.1f}pt")
        return " · ".join(parts) if parts else "훅·클릭 유지 — 단가만 변동"

    # (변동 표 행 빌드는 코호트 경향 계산 뒤 movers_sel 로 — 아래에서 수행)

    # ── 경향성 코호트 (세은 7/20 2차): 승격군 vs Testing 잔류군 주간 CPLPV 시계열 ──
    dc_rows = ssot.get("daily_creator") or []
    by_slug_daily = defaultdict(list)
    for r in dc_rows:
        by_slug_daily[r["slug"]].append(r)
    WK_MIN_SPEND = 3000   # 주 단위 CPLPV 산출 최소 spend (노이즈 컷)
    PRE_W, TEST_W = 2, 6
    # POST_W 동적 (세은 7/27 「같은 콘텐츠면 9주차까지 나와야지」): 승격군의 40% 이상이
    # 관측되는 최대 주차까지 — 코호트가 나이 들면 축이 매주 자연 확장. 표본 급감 꼬리(<40%)는
    # median 왜곡이라 컷. 최소 8주 보장 (기존 고정값과 하위호환).
    _cov, _np = defaultdict(int), 0
    for _rows in by_slug_daily.values():
        _pd = sorted(r["date"] for r in _rows if r["stage"] == "proven" and r["spend"] > 0)
        if not _pd:
            continue
        _np += 1
        _p0 = date.fromisoformat(_pd[0])
        for _w in {(date.fromisoformat(r["date"]) - _p0).days // 7
                   for r in _rows if r["stage"] == "proven" and r["spend"] > 0}:
            _cov[_w] += 1
    POST_W = max([8] + [w + 1 for w, c in _cov.items() if c >= 0.4 * _np]) if _np else 8

    def _wk_cplpv(rows):
        sp = sum(r["spend"] for r in rows)
        lv = sum(r["lpv"] for r in rows)
        return cplpv_calc(sp, lv) if sp >= WK_MIN_SPEND else None

    # 전 이력(3/1~) 전수 집계 (세은 7/20 3차: "5월 이후 돌아간 모든 광고 데이터 집계").
    # 단계 = Graph 가 반환하는 '현재' 캠페인 소속 기준 — 6/19 재편 전 지출도 그 광고가
    # 지금 속한 캠페인(Proven) 으로 잡힘 (3~5월 지출이 proven 으로 집계되는 것 실측).
    # 따라서 Proven 군 정렬축 = 현 Proven 캠페인 첫 지출일. Testing 캠페인은 6/19 신설이라
    # '승격 전 2주' 선은 6/19 이후 승격 관측분에만 존재.
    promo_series, test_series = [], []
    n_promo_observed = 0
    promo_first = {}   # slug → 첫 Proven 지출일 (성과 변동 슬라이드 경향 매칭에도 사용)
    for sl, rows_all in by_slug_daily.items():
        tdates = sorted(r["date"] for r in rows_all if r["stage"] == "testing" and r["spend"] > 0)
        pdates = sorted(r["date"] for r in rows_all if r["stage"] == "proven" and r["spend"] > 0)
        if pdates:
            # Proven 군 — 편입일(첫 Proven spend) 기준 전 PRE_W주(Testing)·후 POST_W주(Proven, 동적)
            p0 = date.fromisoformat(pdates[0])
            promo_first[sl] = pdates[0]
            if tdates and tdates[0] < pdates[0]:
                n_promo_observed += 1
            vals = []
            for w in range(-PRE_W, POST_W):
                lo, hi = p0 + timedelta(days=w * 7), p0 + timedelta(days=w * 7 + 6)
                sub = [r for r in rows_all
                       if lo <= date.fromisoformat(r["date"]) <= hi
                       and r["stage"] == ("testing" if w < 0 else "proven")]
                vals.append(_wk_cplpv(sub))
            if any(v is not None for v in vals):
                promo_series.append({"label": sl, "vals": vals})

    # 잔류군 — 콘텐츠(CT 토큰) 단위 전수 (세은 7/20: "이때까지 돌린 거 전부").
    # 같은 CT 의 Proven 광고가 존재하면 졸업 콘텐츠 → 승격군 pre 구간에서 다루므로 제외.
    CT_RE = re.compile(r"CT-(\d+)")

    def _content_key(r):
        m = CT_RE.search(r.get("ad_name", ""))
        return m.group(1) if m else (r.get("ad_id") or r["slug"])
    cont_rows = defaultdict(list)
    for r in dc_rows:
        if r["spend"] > 0:
            cont_rows[_content_key(r)].append(r)
    graduated = {k for k, rs in cont_rows.items() if any(x["stage"] == "proven" for x in rs)}
    for k, rs in cont_rows.items():
        trs = [x for x in rs if x["stage"] == "testing"]
        if k in graduated or not trs:
            continue
        first = date.fromisoformat(min(x["date"] for x in trs))
        vals = []
        for w in range(TEST_W):
            lo, hi = first + timedelta(days=w * 7), first + timedelta(days=w * 7 + 6)
            sub = [x for x in trs if lo <= date.fromisoformat(x["date"]) <= hi]
            vals.append(_wk_cplpv(sub))
        if any(v is not None for v in vals):
            test_series.append({"label": k, "vals": vals})

    def _median(xs):
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    def med_series(series, nbuck):
        out = []
        for i in range(nbuck):
            vs = [s["vals"][i] for s in series if s["vals"][i] is not None]
            out.append(_median(vs) if vs else None)
        return out

    def svg_trend(series, med, labels, ref, vline_idx=None, w=620, h=320, band=None, vmax_override=None):
        """선형 그래프 (self-contained SVG) — 굵은 선=median, 음영=분포 25~75% 밴드, 점선=졸업 기준.

        가시성 (세은 7/20 6차): 콘텐츠별 스파게티 선 대신 밴드로 분포 표현. series 는 빈 리스트 가능.
        """
        pad_l, pad_r, pad_t, pad_b = 48, 14, 16, 30
        allv = [v for s in series for v in s["vals"] if v is not None] + [v for v in (med or []) if v is not None]
        if band:
            allv += [v for arr in band for v in arr if v is not None]
        if not allv:
            return "<div class=dim style='padding:30px'>표본 없음</div>"
        vmax = vmax_override or max(allv + ([ref] if ref else [])) * 1.12
        iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
        n = len(labels)

        def X(i):
            return pad_l + iw * i / (n - 1)

        def Y(v):
            return pad_t + ih * (1 - v / vmax)
        parts = [f"<svg viewBox='0 0 {w} {h}' style='width:100%;max-width:{w}px'>"]
        for gi in range(5):
            gv = vmax * gi / 4
            parts.append(f"<line x1='{pad_l}' y1='{Y(gv):.1f}' x2='{w - pad_r}' y2='{Y(gv):.1f}' stroke='#e3e9f5'/>")
            parts.append(f"<text x='{pad_l - 6}' y='{Y(gv) + 4:.1f}' text-anchor='end' font-size='10' fill='#8a93a6'>{int(gv):,}</text>")
        for i, lb in enumerate(labels):
            parts.append(f"<text x='{X(i):.1f}' y='{h - 8}' text-anchor='middle' font-size='10.5' fill='#5a6478'>{lb}</text>")
        if vline_idx is not None:
            xv = (X(vline_idx - 1) + X(vline_idx)) / 2
            parts.append(f"<line x1='{xv:.1f}' y1='{pad_t}' x2='{xv:.1f}' y2='{h - pad_b}' stroke='#6d5bd0' stroke-dasharray='5 4' stroke-width='1.6'/>")
            parts.append(f"<text x='{xv + 5:.1f}' y='{pad_t + 12}' font-size='10.5' fill='#6d5bd0' font-weight='700'>승격</text>")
        if ref and ref < vmax:
            parts.append(f"<line x1='{pad_l}' y1='{Y(ref):.1f}' x2='{w - pad_r}' y2='{Y(ref):.1f}' stroke='#c0392b' stroke-dasharray='4 4'/>")
            parts.append(f"<text x='{w - pad_r}' y='{Y(ref) - 5:.1f}' text-anchor='end' font-size='10' fill='#c0392b'>졸업 기준 {int(ref)}</text>")
        if band:
            q1s, q3s = band
            run = []
            for i in range(n):
                if q1s[i] is not None and q3s[i] is not None:
                    run.append(i)
                else:
                    if len(run) >= 2:
                        top = " ".join(f"{X(i):.1f},{Y(q3s[i]):.1f}" for i in run)
                        bot = " ".join(f"{X(i):.1f},{Y(q1s[i]):.1f}" for i in reversed(run))
                        parts.append(f"<polygon points='{top} {bot}' fill='#1877f2' opacity='0.13'/>")
                    run = []
            if len(run) >= 2:
                top = " ".join(f"{X(i):.1f},{Y(q3s[i]):.1f}" for i in run)
                bot = " ".join(f"{X(i):.1f},{Y(q1s[i]):.1f}" for i in reversed(run))
                parts.append(f"<polygon points='{top} {bot}' fill='#1877f2' opacity='0.13'/>")

        def draw(vals, color, sw, op, dots=False):
            seg = []

            def flush():
                if len(seg) >= 2:
                    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
                    parts.append(f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='{sw}' opacity='{op}'/>")
                elif len(seg) == 1:   # 고립 주차(양옆 미산출)도 점으로 표기 — 표본 누락 방지
                    parts.append(f"<circle cx='{seg[0][0]:.1f}' cy='{seg[0][1]:.1f}' r='2.6' fill='{color}' opacity='{op}'/>")
            for i, v in enumerate(vals):
                if v is None:
                    flush()
                    seg = []
                else:
                    seg.append((X(i), Y(v)))
                    if dots:
                        parts.append(f"<circle cx='{X(i):.1f}' cy='{Y(v):.1f}' r='4' fill='{color}'/>")
            flush()
        for s in series:
            draw(s["vals"], s.get("color", "#9db8e8"), s.get("sw", 1.4), s.get("op", 0.75),
                 dots=s.get("dots", False))
        if med:
            draw(med, "#1877f2", 3.2, 1, dots=True)
        parts.append("</svg>")
        return "".join(parts)

    def trend_txt(med, labels):
        pts = [(labels[i], med[i]) for i in range(len(med)) if med[i] is not None]
        if len(pts) < 2:
            return "median 산출 가능 주차 부족."
        path = " → ".join(f"{lb} {won(v)}" for lb, v in pts)
        dd = (pts[-1][1] - pts[0][1]) / pts[0][1] * 100
        word = "상승(악화)" if dd > 5 else ("하락(개선)" if dd < -5 else "횡보")
        return f"median CPLPV {path} — 구간 {dd:+.0f}%, {word}"

    promo_labels = [f"승격 전{PRE_W - i}주" for i in range(PRE_W)] + [f"후 {i + 1}주" for i in range(POST_W)]
    test_labels = [f"W{i + 1}" for i in range(TEST_W)]
    promo_med = med_series(promo_series, PRE_W + POST_W)
    test_med = med_series(test_series, TEST_W)

    def quart_series(series, nbuck):
        """버킷별 분포 25~75% 구간 (표본 3 미만이면 min~max)."""
        q1s, q3s = [], []
        for i in range(nbuck):
            vs = sorted(s["vals"][i] for s in series if s["vals"][i] is not None)
            if len(vs) >= 3:
                q1s.append(vs[int(len(vs) * 0.25)])
                q3s.append(vs[int(len(vs) * 0.75)])
            elif vs:
                q1s.append(vs[0])
                q3s.append(vs[-1])
            else:
                q1s.append(None)
                q3s.append(None)
        return q1s, q3s
    promo_band = quart_series(promo_series, PRE_W + POST_W)
    test_band = quart_series(test_series, TEST_W)
    # 두 차트 y축 동일 스케일 — 좌우 비교 가능하게
    _shared = [v for arr in (promo_med, test_med, *promo_band, *test_band) for v in arr if v is not None]
    vmax_shared = (max(_shared + [g["grad"]["cplpv"]]) * 1.15) if _shared else None
    svg_promo = svg_trend([], promo_med, promo_labels, g["grad"]["cplpv"], vline_idx=PRE_W,
                          band=promo_band, vmax_override=vmax_shared, h=262)
    svg_test = svg_trend([], test_med, test_labels, g["grad"]["cplpv"],
                         band=test_band, vmax_override=vmax_shared, h=262)

    # ── 부속: 시청 잔존 오버레이 (플랜 A-2 — BEST 파랑 vs WORST 빨강) ──
    RET_LABELS = ["3초", "25%", "50%", "75%", "95%"]

    def _rmed(xs):
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    def _ret_vals(c):
        w = c.get("watch7")
        return [c["rate3s7"], w["p25"], w["p50"], w["p75"], w["p95"]] if w else None
    ret_series, ret_b, ret_w = [], [], []
    for c in week_best:
        v = _ret_vals(c)
        if v:
            ret_b.append(v)
            ret_series.append({"vals": v, "color": "#1877f2", "op": 0.45})
    for c in week_worst:
        v = _ret_vals(c)
        if v:
            ret_w.append(v)
            ret_series.append({"vals": v, "color": "#c0392b", "op": 0.45})
    for grp, col in ((ret_b, "#1877f2"), (ret_w, "#c0392b")):
        if grp:
            ret_series.append({"vals": [_rmed([g[i] for g in grp]) for i in range(len(RET_LABELS))],
                               "color": col, "sw": 3.4, "op": 1, "dots": True})
    svg_ret = svg_trend(ret_series, None, RET_LABELS, None, w=620, h=330)

    def _gmed(grp, key):
        vs = [c.get(key) for c in grp if c.get(key)]
        return _rmed(vs) if vs else None
    b_ctr, w_ctr = _gmed(week_best, "ctr7"), _gmed(week_worst, "ctr7")
    b_p75 = _rmed([v[3] for v in ret_b]) if ret_b else None
    w_p75 = _rmed([v[3] for v in ret_w]) if ret_w else None
    click_exit = (b_ctr and w_ctr and b_p75 is not None and w_p75 is not None
                  and b_ctr > w_ctr * 1.15 and b_p75 < w_p75)
    if click_exit:
        ret_note = (f"BEST 곡선이 뒤로 갈수록 낮은 건 <b>클릭 이탈</b> — 링크를 누르면 재생이 멈추기 때문 "
                    f"(75% 지점 잔존 BEST {b_p75:.0f}% vs WORST {w_p75:.0f}%인데 클릭은 BEST가 많음). "
                    f"즉 WORST 는 시청은 붙잡지만 <b>클릭을 못 만드는</b> 소재.")
    else:
        ret_note = ("격차가 3초 지점에서 이미 벌어지면 <b>훅</b>, 3초 이후 더 벌어지면 <b>전개(중반 이탈)</b> 문제 — "
                    "곡선이 어디서 갈라지는지가 원인 축을 지목한다.")

    # ── BEST vs WORST 축별 해부 (세은 8/10: 어디서 갈렸나 · 무엇을 의미하나) ──
    def _amed(grp, getf):
        vs = [getf(c) for c in grp if getf(c) is not None]
        return _rmed(vs) if vs else None
    def _pget(k):
        return lambda c: (c.get("watch7") or {}).get(k)
    AX = [
        ("3초율 (훅)",        lambda c: c.get("rate3s7"),       "hi", "pct0", "훅",   "첫 3초 훅에서 갈림"),
        ("25% 잔존",          _pget("p25"),                     "hi", "pct0", "전개", "도입부 유지력"),
        ("50% 잔존",          _pget("p50"),                     "hi", "pct0", "전개", "중반 전개에서 갈림"),
        ("75% 잔존",          _pget("p75"),                     "hi", "pct0", "전개", "후반까지 붙잡는 힘"),
        ("클릭율 (CTR)",      lambda c: c.get("ctr7"),          "hi", "pct1", "클릭", "누르게 만드는 힘"),
        ("클릭→랜딩 도달",    lambda c: c.get("click_to_lpv7"), "hi", "pct0", "랜딩", "누른 뒤 라쿠텐까지 연결"),
        ("클릭 단가 (CPC)",   lambda c: c.get("cpc7"),          "lo", "won",  "클릭", "클릭 1건 비용"),
        ("빈도",              lambda c: c.get("freq7"),         "lo", "freq", "빈도", "반복 노출 피로도"),
        ("방문 단가 (CPLPV)", lambda c: c.get("cplpv7"),        "lo", "won",  None,   "최종 방문 1명 비용 — 결과"),
    ]
    def _fv(v, unit):
        if unit == "won":  return won(v)
        if unit == "freq": return f"{v:.1f}"
        if unit == "pct1": return f"{v:.1f}%"
        return f"{v:.0f}%"
    axis_data = []
    for _lab, _getf, _dirn, _unit, _bkey, _mean in AX:
        b, w = _amed(week_best, _getf), _amed(week_worst, _getf)
        if b is None or w is None or not w:
            continue
        adv = ((b - w) / w * 100) if _dirn == "hi" else ((w - b) / w * 100)
        axis_data.append({"lab": _lab, "b": b, "w": w, "adv": adv, "unit": _unit,
                          "bkey": _bkey, "mean": _mean, "dirn": _dirn, "getf": _getf})
    _inputs = [a for a in axis_data if a["bkey"]]
    primary = max(_inputs, key=lambda a: a["adv"]) if _inputs else None
    _second = None
    if primary:
        _rest = [a for a in _inputs if a is not primary and a["adv"] >= 8]
        _second = max(_rest, key=lambda a: a["adv"]) if _rest else None

    # 고객 여정 퍼널 — 9개 지표를 고객이 밟는 순서(멈춤→시청→클릭→도착→결과)로 재배치.
    # 갈린 단계(primary)만 파랑 강조, 나머지는 회색으로 눌러 '어디서 갈렸나'를 한눈에.
    adict = {a["lab"]: a for a in axis_data}
    FRIEND = {"클릭→랜딩 도달": "라쿠텐 도착", "클릭율 (CTR)": "링크 누름",
              "3초율 (훅)": "스크롤 멈춤", "75% 잔존": "끝까지 봄"}
    FUNNEL = [
        ("①", "스크롤 멈춤", "첫 3초 훅에서 스크롤을 세움",   "3초율 (훅)"),
        ("②", "끝까지 봄",   "후반까지 시청 유지",           "75% 잔존"),
        ("③", "링크 누름",   "누를 이유가 전달됨 (CTR)",      "클릭율 (CTR)"),
        ("④", "라쿠텐 도착", "누른 뒤 라쿠텐까지 연결",       "클릭→랜딩 도달"),
    ]
    _steps = []
    for _n, _lab, _desc, _axlab in FUNNEL:
        a = adict.get(_axlab)
        if not a:
            continue
        adv = a["adv"]
        is_hot = bool(primary and a["bkey"] == primary["bkey"])
        _bv, _wv = _fv(a["b"], a["unit"]), _fv(a["w"], a["unit"])
        if is_hot:      _tag = f"◀ 여기서 갈렸다 · BEST +{adv:.0f}%"
        elif adv >= 8:  _tag = f"BEST +{adv:.0f}%"
        elif adv <= -8: _tag = f"WORST +{abs(adv):.0f}%"
        else:           _tag = "비슷"
        _steps.append(
            f"<div class='fstep{' hot' if is_hot else ''}'><div class=fn>{_n}</div>"
            f"<div class=fl>{_lab}<span>{_desc}</span></div>"
            f"<div class=fv><b>{_bv}</b> ▸ {_wv}</div>"
            f"<div class=ft>{_tag}</div></div>")
    fn_rows = "<div class=fdrop>▽</div>".join(_steps)
    # 결과 행 (CPLPV) — 원인이 아니라 위 여정의 '결과'임을 분리 표기
    _res = adict.get("방문 단가 (CPLPV)")
    res_row = ""
    if _res:
        _ratio = (_res["w"] / _res["b"]) if _res["b"] else None
        _rtag = (f"BEST가 {_ratio:.1f}배 싸게 방문 확보" if _ratio and _ratio >= 1.1 else "")
        res_row = ("<div class=fdrop>▽</div>"
                   "<div class=fresult><div class=fn>결과</div>"
                   "<div class=fl>방문 1명 비용 <span class=dim style='font-weight:400;font-size:11px'>CPLPV</span></div>"
                   f"<div class=fv>{won(_res['b'])} ▸ {won(_res['w'])}</div>"
                   f"<div class=ft>{_rtag}</div></div>")
    # 기타 지표(참고) — 회색 각주로 눌러 유실 없이 정리
    _foot = [f"{_fl} {_fv(adict[_fl]['b'], adict[_fl]['unit'])}▸{_fv(adict[_fl]['w'], adict[_fl]['unit'])}"
             for _fl in ["25% 잔존", "50% 잔존", "클릭 단가 (CPC)", "빈도"] if _fl in adict]
    foot_line = ("<div class=funnote>기타 지표(참고): " + " · ".join(_foot) + "</div>") if _foot else ""
    # 한 줄 해석 + '왜 이게 방문 비용이 되나' 연결 (세은 8/10)
    read_line = ""
    if primary and primary["adv"] >= 8:
        _pf = FRIEND.get(primary["lab"], primary["lab"])
        _cp = adict.get("방문 단가 (CPLPV)")
        _bridge = ""
        if _cp and _cp["b"] and _cp["w"]:
            _rr = _cp["w"] / _cp["b"]
            if primary["lab"] == "클릭→랜딩 도달":
                _bridge = (f"<b>→ 왜 비용이 되나:</b> 누른 사람이 라쿠텐까지 <b>도착해야 '방문 1명'</b>으로 잡힌다. "
                           f"도착률이 높을수록 같은 광고비로 방문이 더 쌓여 방문 1명 값이 내려간다. "
                           f"그래서 방문 1명 비용 <b>BEST {won(_cp['b'])} vs WORST {won(_cp['w'])}</b> (약 {_rr:.1f}배 차).")
            else:
                _bridge = (f"<b>→</b> 이 단계 격차가 뒤로 이어져 최종 방문 1명 비용까지 벌어진다 — "
                           f"<b>BEST {won(_cp['b'])} vs WORST {won(_cp['w'])}</b> (약 {_rr:.1f}배 차).")
        read_line = (f"<div class=funread><b>가장 크게 갈린 지점 = {_pf}</b> "
                     f"(BEST {_fv(primary['b'], primary['unit'])} vs WORST {_fv(primary['w'], primary['unit'])}, +{primary['adv']:.0f}%)<br>"
                     f"{_bridge} <span class=dim>개선 1순위 → 다음 장 처방.</span></div>")
    axis_table = f"""
      <div class=boxh>고객 여정 — 어디서 갈렸나 <span class=dim style='font-weight:400;font-size:11px'>BEST ▸ WORST · median</span></div>
      <div class=funnel>{fn_rows}{res_row}</div>
      {read_line}
      {foot_line}"""

    # 구성(범주형) 차이 — 주력 지면
    PLACE_KO = {"instagram_reels": "IG 릴스", "facebook_reels": "FB 릴스", "feed": "피드",
                "instagram_stories": "IG 스토리", "facebook_stories": "FB 스토리",
                "instagram_explore_grid_home": "IG 탐색", "facebook_reels_overlay": "FB 릴스오버레이",
                "instream_video": "인스트림", "marketplace": "마켓", "search": "검색"}
    def _dom_place(grp):
        agg = defaultdict(float)
        for c in grp:
            pl = c.get("place7") or []
            if pl:
                agg[pl[0][0]] += 1
        if not agg:
            return None
        k = max(agg, key=agg.get)
        return PLACE_KO.get(k.split(":")[-1], k.split(":")[-1])
    _bp, _wp = _dom_place(week_best), _dom_place(week_worst)
    place_line = (f"<div class=note style='margin-top:6px'><b>주력 지면</b> — BEST {_bp} · WORST {_wp}</div>"
                  if _bp and _wp else "")

    if primary and primary["adv"] >= 8:
        diag = (f"이번 주 최대 갈림 = <b>{primary['lab']}</b> — BEST가 WORST보다 <b>{primary['adv']:.0f}% 우위</b> "
                f"({primary['mean']}). 개선 축은 다음 장 처방 참조.")
    else:
        diag = "이번 주는 특정 축에서 크게 갈리지 않음 — 표본(각 4개)이 작아 방문 단가 편차가 큼. 다음 주 재확인."

    ret_slide = f"""
<section class=wide>
  <h2>BEST vs WORST — 어디서 갈렸나 <span class=h2sub>좌: 노출 대비 시청 유지율(3초→95%) · 파랑 BEST · 빨강 WORST · 굵은 선=그룹 median / 우: 고객 여정 5단계 — 갈린 단계만 강조 (BEST n=4 · WORST n=4)</span></h2>
  <div class=cols2>
    <div>
      <div class=legend4 style='font-weight:700'>
        <span style='color:#1877f2'>━━ BEST 4 median</span>
        <span style='color:#9db8e8'>── BEST 개별</span>
        <span style='color:#c0392b'>━━ WORST 4 median</span>
        <span style='color:#e0a9a3'>── WORST 개별</span>
      </div>
      {svg_ret}
      <div class=note>{ret_note}</div>
    </div>
    <div>
      {axis_table}
      {place_line}
    </div>
  </div>
</section>"""

    # ── 신규 슬라이드 (세은 7/27, 7/27b 쉬운 말 재작성): 같은 풀을 지표별로 반 갈라 실제 비용 비교 ──
    life_pool = [c for c in creators_all if (c.get("spend") or 0) >= 20000 and c.get("cplpv")]

    def _half_cmp(getter):
        """지표 좋은 절반 vs 나쁜 절반의 median 생애 CPLPV. (good, bad, n) 또는 None."""
        vs = [c for c in life_pool if getter(c)]
        if len(vs) < 8:
            return None
        vs.sort(key=getter, reverse=True)
        half = len(vs) // 2
        return (_rmed([c["cplpv"] for c in vs[:half]]),
                _rmed([c["cplpv"] for c in vs[-half:]]), len(vs))

    half_axes = [
        ("클릭율 좋은 절반 vs 나쁜 절반", "영상을 본 사람 중 링크를 누른 비율", lambda c: c.get("ctr")),
        ("3초 시청률 좋은 절반 vs 나쁜 절반", "첫 3초를 넘긴 비율 (훅)", lambda c: c.get("rate3s")),
        ("클릭→랜딩 도달 좋은 절반 vs 나쁜 절반", "누른 사람이 라쿠텐까지 간 비율", lambda c: c.get("click_to_lpv")),
        ("오가닉 조회수 많은 절반 vs 적은 절반", "광고 전 원본 릴의 조회수", lambda c: (c.get("organic") or {}).get("views")),
    ]
    half_rows_data = []   # (라벨, 설명, good, bad, n)
    for lab, desc, getf in half_axes:
        got = _half_cmp(getf)
        if got:
            half_rows_data.append((lab, desc, *got))
    # ── 개선 처방 (세은 8/10: 규칙 처방 라이브러리 + 주간 코멘트) ──
    RX = {
        "훅": ("훅 (첫 3초)", [
            "첫 프레임에 <b>결과·변화</b>를 먼저 — 사용 전/후를 3초 안에 보여주기",
            "텍스트 훅(첫 자막) A/B — 질문형 vs 단언형",
            "무음 시청 대비 <b>큰 자막</b>·강한 첫 컷으로 재편집"]),
        "전개": ("전개 (중반 이탈)", [
            "핵심 소구를 <b>15초 안</b>으로 당기기",
            "지루한 구간 컷편집 — 데모→결과로 압축",
            "한 영상 = 한 메시지, 곁가지 제거"]),
        "클릭": ("클릭 (누를 이유)", [
            "<b>CTA 문구 명시</b> — '지금 라쿠텐에서' 같은 행동 지시",
            "혜택·소구점을 영상·캡션 <b>앞</b>으로 배치",
            "가격·프로모(쿠폰/세일) 노출로 클릭 동기 부여",
            "캡션 첫 줄 = 링크 유도 문구"]),
        "랜딩": ("랜딩 연결", [
            "광고 메시지와 <b>랜딩 페이지 메시지 일치</b> — 기대 불일치로 인한 이탈 방지",
            "랜딩 로딩 속도·모바일 정합 점검",
            "클릭 유도 소구와 랜딩 첫 화면(오퍼·리뷰) 정합 확인"]),
        "빈도": ("노출 피로", [
            "오디언스 <b>확장</b> (유사·관심사 추가)",
            "소재 로테이션 — 같은 소재 장기 노출 회피"]),
    }
    _CIRC = "①②③④⑤"
    # 주간 코멘트 = 진단 파생 자동 문장 (수동 오버라이드: .tmp/jp_meta_deck/weekly_note.txt)
    _note_override = ""
    _np_path = OUT_DIR / "weekly_note.txt"
    if _np_path.exists():
        _note_override = _np_path.read_text(encoding="utf-8").strip()
    if _note_override:
        wk_comment = esc(_note_override)
    elif primary and primary["adv"] >= 8:
        _rxt = RX.get(primary["bkey"], RX["클릭"])[0]
        _pf = FRIEND.get(primary["lab"], primary["lab"])
        wk_comment = (f"이번 주 성패는 <b>{_pf}</b>에서 갈렸다 — {primary['mean']}. "
                      f"BEST가 WORST보다 <b>{primary['adv']:.0f}% 앞섰다</b>. "
                      f"그래서 아래 <b>{_rxt}</b> 처방을 우선한다.")
    else:
        wk_comment = "이번 주는 특정 축에서 크게 갈리지 않았다(표본 각 4개). 방문 단가 편차가 커 다음 주 재확인을 권장한다."

    # 처방 카드 (여러 방법) — 진단된 병목 기준
    rx_cards, rx_title = "", ""
    if primary and primary["adv"] >= 8:
        rx_title, _methods = RX.get(primary["bkey"], RX["클릭"])
        _rxcls = "tw-b"
    else:
        rx_title, _methods = "표본 확대 · 재확인", [
            "신규 Testing 소재 투입으로 풀 확대",
            "저지출 소재는 D+3 조기 판정으로 회전",
            "다음 주 같은 축 재측정 후 처방 확정"]
        _rxcls = "tw-g"
    for _i, _mtd in enumerate(_methods):
        rx_cards += (f"<div class='twcard {_rxcls} actcard'><div class=actn>{_CIRC[_i]}</div>"
                     f"<p class=acttext>{_mtd}</p></div>")

    # 근거 — 그 축에서 이긴 BEST 실측
    ev_line = ""
    if primary and primary["adv"] >= 8:
        _gp = [(primary["getf"](c), c) for c in week_best if primary["getf"](c) is not None]
        if _gp:
            _champ = (max(_gp, key=lambda t: t[0]) if primary["dirn"] == "hi"
                      else min(_gp, key=lambda t: t[0]))[1]
            _cv = primary["getf"](_champ)
            ev_line = (f"<b>근거</b> — 이 축 최고 BEST @{esc(_champ.get('ig_username') or _champ['slug'])} "
                       f"({primary['lab']} {_fv(_cv, primary['unit'])}) 가 이 방법으로 통했다.")
    _sec_line = (f" · 2순위 갈림 = <b>{_second['lab']}</b>({_second['adv']:.0f}% 우위)" if _second else "")

    # 생애풀 검증 (split-half CTR 1줄 — 소표본 BEST/WORST 보강)
    _ctr_hd = next((d for d in half_rows_data if d[0].startswith("클릭율")), None)
    life_line = ""
    if _ctr_hd:
        _, _, _gv, _bv, _nn = _ctr_hd
        life_line = (f"<b>생애풀 검증</b> — 여태 돌린 {_nn}개에서도 클릭율 좋은 절반이 방문 1명을 "
                     f"{won(_gv)}에, 나쁜 절반은 {won(_bv)}에 데려온다. 최종 비용을 가르는 건 시청 시간이 아니라 <b>클릭</b>이다.")

    # 병목 → 목표 배너 (시각적 before→after: 부진 소재 현재값 → 우수 소재 수준)
    fix_banner = ""
    if primary and primary["adv"] >= 8:
        _pf = FRIEND.get(primary["lab"], primary["lab"])
        _cp = adict.get("방문 단가 (CPLPV)")
        _goalsub = (f"방문 1명 비용 {won(_cp['w'])} → {won(_cp['b'])} 로" if _cp and _cp["b"] and _cp["w"] else "")
        fix_banner = (
            "<div class=fixbanner>"
            f"<div class=fixnow><div class=fixlbl>지금 · 부진 소재</div>"
            f"<div class=fixbig>{_fv(primary['w'], primary['unit'])}</div>"
            f"<div class=fixsub>{_pf}</div></div>"
            "<div class=fixarrow><div class=dim style='font-size:12px'>여기까지 끌어올리면</div>▶</div>"
            f"<div class=fixgoal><div class=fixlbl>목표 · 우수 소재 수준</div>"
            f"<div class=fixbig>{_fv(primary['b'], primary['unit'])}</div>"
            f"<div class=fixsub>{_goalsub}</div></div>"
            "</div>")
    corr_slide = f"""
<section class=wide>
  <h2>그래서 뭘·어떻게 개선하나 <span class=h2sub>앞 장 병목 → 목표치 + 구체 액션 (무엇을 · 어떻게)</span></h2>
  <div class=fixhead>{wk_comment}</div>
  {fix_banner}
  <div class=boxh>구체 액션 — {rx_title}</div>
  <div class=twrow>{rx_cards}</div>
  <div class=note style='margin-top:10px'>{ev_line}</div>
</section>""" if week_best else ""
    pre_v, post_v = promo_med[PRE_W - 1] if PRE_W >= 1 else None, promo_med[PRE_W]
    if pre_v and post_v:
        promo_concl = (f"승격 직전 주 median {won(pre_v)} → 승격 1주차 {won(post_v)} "
                       f"({(post_v - pre_v) / pre_v * 100:+.0f}%) · 승격 후 {trend_txt(promo_med[PRE_W:], promo_labels[PRE_W:])}")
    else:
        promo_concl = trend_txt(promo_med, promo_labels)
    test_concl = trend_txt(test_med, test_labels)

    # ── 경향성 분석 (세은 7/20 6차 — 가시성: 핵심 특징 3카드 + 차트 밑 '왜' 1줄) ──
    post_meds = [(i, v) for i, v in enumerate(promo_med[PRE_W:], 1) if v is not None]
    test_meds = [(i, v) for i, v in enumerate(test_med, 1) if v is not None]
    gate_c = g["grad"]["cplpv"]
    tw_cards = ""
    promo_analysis = "편입 전후 median 산출 주차 부족 — 경향 판정 보류."
    test_analysis = "잔류군 median 산출 주차 부족 — 경향 판정 보류."
    if pre_v and post_v and len(post_meds) >= 2:
        _jump = (post_v - pre_v) / pre_v * 100
        _last_w, _last_v = post_meds[-1]
        _rec = (_last_v - post_v) / post_v * 100
        n_over = sum(1 for _, v in post_meds if v > gate_c)
        tw_cards += (
            f"<div class='twcard tw-b'><div class=twnum>{_jump:+.0f}%</div><b>① 승격하면 단가가 먼저 뛴다</b>"
            f"<p>편입 직전 {won(pre_v)} → 편입 1주차 {won(post_v)}. 지갑 통합·증액으로 오디언스가 한 번에 넓어지는 구조 요인.</p></div>"
            f"<div class='twcard tw-g'><div class=twnum>{_rec:+.0f}%</div><b>② 수주에 걸쳐 도로 내려온다</b>"
            f"<p>1주차 {won(post_v)} → {_last_w}주차 {won(_last_v)}. 게이트 컷 + 배분 최적화. "
            f"편입 후 median이 졸업 기준 위인 주 {n_over}/{len(post_meds)} — 증액 내성.</p></div>")
        promo_analysis = (f"<b>점프 → 회복.</b> median {won(pre_v)} → {won(post_v)}({_jump:+.0f}%) → "
                          f"{won(_last_v)}({_last_w}주차). 승격 소재는 증액을 대체로 견딘다.")
    if len(test_meds) >= 2:
        _t0, _t1 = test_meds[0][1], test_meds[-1][1]
        _td = (_t1 - _t0) / _t0 * 100
        _tword = "악화" if _td > 5 else ("개선" if _td < -5 else "횡보")
        over_w = sum(1 for _, v in test_meds if v > gate_c)
        tw_cards += (
            f"<div class='twcard tw-r'><div class=twnum>{_td:+.0f}%</div><b>③ 잔류군은 기다려도 안 좋아진다</b>"
            f"<p>W{test_meds[0][0]} {won(_t0)} → W{test_meds[-1][0]} {won(_t1)} ({_tword}). "
            f"졸업 기준 위인 주 {over_w}/{len(test_meds)} — D+3 조기 판정·조기 OFF의 근거.</p></div>")
        test_analysis = (f"<b>{_tword}.</b> median W{test_meds[0][0]} {won(_t0)} → W{test_meds[-1][0]} {won(_t1)} "
                         f"({_td:+.0f}%). 노출이 쌓여도 소재 지표는 스스로 좋아지지 않는다.")

    # ── 성과 변동 선별 (세은 7/20: 유의미 |Δ|≥15% + 위 경향성과 일치하는 것만) ──
    MOVER_SIG = 15
    ref_d = date.fromisoformat(ssot["ref_date"])

    def trend_tag(c, d):
        pf = promo_first.get(c["slug"])
        if pf:
            dsp = (ref_d - date.fromisoformat(pf)).days
            if d > 0 and dsp <= 21:
                return f"경향 ① 전반 일치 — 승격(D+{dsp}) 직후 단가 점프 구간"
            if d < 0 and dsp > 7:
                return f"경향 ① 후반 일치 — 승격(D+{dsp}) 후 회복 구간"
        return ""
    movers_sel = []
    for d, c in movers:
        if abs(d) < MOVER_SIG:
            continue
        tag = trend_tag(c, d)
        if tag:
            movers_sel.append((d, c, tag))
    mover_rows = ""
    for d, c, tag in movers_sel:
        cls = "mvup" if d < 0 else "mvdn"    # CPLPV 하락 = 개선
        arrow = "▼ 개선" if d < 0 else "▲ 악화"
        mover_rows += (f"<tr><td class=l>@{esc(c['ig_username'] or c['slug'])}</td>"
                       f"<td>{ctype(c)}</td>"
                       f"<td class=dim>{won(c['spend_p7'])}</td><td>{c['rate3s_p7']:.0f}%</td>"
                       f"<td>{c['ctr_p7']:.1f}%</td><td>{won_or_dash(c['cplpv_p7'])}</td>"
                       f"<td class=arrowcell>➜</td>"
                       f"<td class=dim>{won(c['spend7'])}</td><td>{c['rate3s7']:.0f}%</td>"
                       f"<td>{c['ctr7']:.1f}%</td><td class=b>{won_or_dash(c['cplpv7'])}</td>"
                       f"<td class='{cls}'>{arrow} {abs(d):.0f}%</td>"
                       f"<td class=l>{esc(tag)}<br><span class=dim>{mover_axis(c)}</span></td></tr>\n")

    # 주간 트렌드는 슬라이드 대신 시그널 1줄로 흡수 — 첫 주 vs 마지막 주 비교치만 사용
    wk = ssot["weekly"]
    wk0, wk1 = (wk[0], wk[-1]) if len(wk) >= 2 else (None, None)

    # 승격 전후 효율 표 (같은 크리에이터 릴: Testing 버전 vs Proven 버전) — CPLPV+CTR+CPC+LPV (세은 7/13)
    promo = ssot.get("promotion", [])

    def _stage_cells(m, hl=False):
        b = " class=b" if hl else ""
        return (f"<td class=dim>{won(m['spend'])}</td><td>{m['ctr']:.1f}%</td>"
                f"<td>{won(m['cpc'])}</td><td>{int(m['lpv']):,}</td><td{b}>{won_or_dash(m['cplpv'])}</td>")
    promo_rows = "\n".join(
        f"<tr><td class=l>@{esc(p['slug'])}</td>{_stage_cells(p['t'])}"
        f"<td class=arrowcell>➜</td>{_stage_cells(p['p'], hl=True)}"
        f"<td>{'라이브' if p['live'] else 'OFF'}</td></tr>"
        for p in promo)

    # ── 졸업후 효율 변화 리서치 (세은 8/10: asset별 + 풀 전체로 덱 반영) ──
    _grad = []   # (slug, t_cplpv, p_cplpv, Δ%, live)
    for p in promo:
        _tc, _pc = p["t"].get("cplpv"), p["p"].get("cplpv")
        if _tc and _pc:
            _grad.append((p["slug"], _tc, _pc, (_pc - _tc) / _tc * 100, p.get("live")))
    grad_research_slide = ""
    if len(_grad) >= 4:
        _deltas = sorted(d[3] for d in _grad)
        _n = len(_deltas)
        _med = _deltas[_n // 2] if _n % 2 else (_deltas[_n // 2 - 1] + _deltas[_n // 2]) / 2
        _imp = sum(1 for d in _deltas if d < 0)
        _wor = _n - _imp
        _prov_live = [c for c in creators_all if c.get("stage_live") == "proven" and c.get("live") and c.get("cplpv7")]
        _pl = sorted(c["cplpv7"] for c in _prov_live)
        _plmed = (_pl[len(_pl) // 2] if len(_pl) % 2 else (_pl[len(_pl) // 2 - 1] + _pl[len(_pl) // 2]) / 2) if _pl else None
        _gc = g["grad"]["cplpv"]
        # asset별 다이버징 바 (개선=파랑 왼쪽 · 악화=빨강 오른쪽), Δ 절대값순
        _mx = max((abs(d[3]) for d in _grad), default=1) or 1
        _bars = ""
        for slug, tc, pc, dd, live in sorted(_grad, key=lambda x: x[3]):
            _w = min(abs(dd) / _mx * 100, 100)
            _good = dd < 0
            _col = "#1877f2" if _good else "#c0392b"
            _lab = f"▼ {abs(dd):.0f}% 개선" if _good else f"▲ {dd:.0f}% 악화"
            _side = "right:50%" if _good else "left:50%"
            _bars += (
                f"<div class=gradbar><div class=gbname>@{esc(slug)}</div>"
                f"<div class=gbtrack><div class=gbmid></div>"
                f"<div class=gbfill style='{_side};width:{_w/2:.1f}%;background:{_col}'></div></div>"
                f"<div class=gbval style='color:{_col}'>{_lab} <span class=dim>({won(tc)}→{won(pc)})</span></div></div>")
        # 판단 문장 — 최대 악화(최우수 회귀)·최대 개선 실측 지목
        _worst = max(_grad, key=lambda x: x[3])
        _best = min(_grad, key=lambda x: x[3])
        _mword = "거의 그대로 유지" if abs(_med) < 8 else ("전반적으로 개선" if _med < 0 else "전반적으로 악화")
        grad_research_slide = f"""
<section class=wide>
  <h2>졸업하면 효율이 유지되나 — 풀 전체 검증 <span class=h2sub>졸업 asset {_n}개 · 생애 Testing 방문비용 → Proven 방문비용 변화 · 게이트 기준 {won(_gc)}</span></h2>
  <div class=twrow>
    <div class='twcard tw-b'><div class=twnum>{_med:+.0f}%</div><b>풀 전체 방문비용 변화 (중앙값)</b><p>졸업해도 <b>{_mword}</b> — 게이트가 증액 내성 있는 소재를 골라낸 결과.</p></div>
    <div class='twcard tw-g'><div class=twnum>{_imp} : {_wor}</div><b>개선 : 악화 (asset 수)</b><p>졸업 {_n}개 중 개선 {_imp}개 · 악화 {_wor}개. 반반에 가까움 = 평균 회귀.</p></div>
    <div class='twcard tw-b'><div class=twnum>{won(_plmed) if _plmed else '—'}</div><b>현재 Proven 라이브 {len(_prov_live)}개 · 최근 7일</b><p>졸업 기준 {won(_gc)} 대비 한참 <b>안쪽</b> = 풀 건강.</p></div>
  </div>
  <div class=boxh>asset별 졸업후 방문비용 변화 — ◀ 개선(파랑) · 악화(빨강) ▶</div>
  <div class=gradbars>{_bars}</div>
  <div class=note style='margin-top:10px'><b>판단</b> — 평균적으로 졸업이 효율을 깎지 않는다(중앙값 {_med:+.0f}%). 단 <b>Testing 최우수 소재는 증액 시 평균 회귀</b> 경향 — 최대 악화 @{esc(_worst[0])} {won(_worst[1])}→{won(_worst[2])}({_worst[3]:+.0f}%)는 Testing 때 가장 쌌던 소재. 오디언스가 넓어지며 CTR도 대체로 소폭 하락. 반대로 부진했던 소재는 게이트·배분으로 회복(@{esc(_best[0])} {_best[3]:+.0f}%).</div>
</section>"""

    # 운영 성과 페이지 (세은 7/27 개편) — asset 나열 제거, 7일 vs 직전 7일 / 30일 vs 직전 30일 두 갈래
    t30 = ssot.get("totals_30d") or {}
    tp30 = ssot.get("totals_prev30") or {}
    adsets7 = ssot.get("adsets_7d") or []
    # 전월 월간 집행 성과 (세은 8/3 지시)
    tm1 = ssot.get("totals_month") or {}
    tm0 = ssot.get("totals_month_prev") or {}
    wm1 = ssot.get("window_month") or ["", ""]
    wm0 = ssot.get("window_month_prev") or ["", ""]
    m1lab = f"{int(wm1[0][5:7])}월" if wm1[0] else "전월"
    m0lab = f"{int(wm0[0][5:7])}월" if wm0[0] else "전전월"
    _lbm = ssot.get("launches_by_month") or {}
    m1_launch = _lbm.get(wm1[0][:7], 0) if wm1[0] else 0
    m0_launch = _lbm.get(wm0[0][:7], 0) if wm0[0] else 0
    # 월간 리뷰 payload (노션 2607 Meta Ads 리뷰 구조 — 세은 8/3 「저 페이지 참고해서 덱」)
    # 생성 = .tmp/build_month_review_json.py (Total ROAS·RPP·매출·풀 분류·분해)
    mrev = None
    _mrev_p = OUT_DIR / "month_review.json"
    if _mrev_p.exists():
        try:
            mrev = json.loads(_mrev_p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [warn] month_review.json 로드 실패 — 간이 월간 슬라이드로 폴백: {e}", file=sys.stderr)

    if mrev:
        mp, md = mrev["pool"], mrev["decomp"]
        _L, _P = mrev["label"], mrev["prev_label"]
        _mm, _mm0 = mrev["meta"], mrev["meta_prev"]
        _rppk = mrev["rpp_jpy"] * mrev["fx"]
        _rppk0 = mrev["rpp_prev_jpy"] * mrev["fx_prev"]
        _tot, _tot0 = _mm["spend"] + _rppk, _mm0["spend"] + _rppk0
        _salk = mrev["sales_jpy"] * mrev["fx"]
        _mtot = mp["good_sp"] + mp["watch_sp"] + mp["bad_sp"] + mp["grad_sp"] + mp["off_sp"]

        def _mpct(x):
            return f"{x / _mtot * 100:.1f}%"

        _mtbl = "\n".join(f"<tr><td class=l>{a}</td><td class=b>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in [
            ("Meta spend", won(_mm["spend"]), won(_mm0["spend"]), f"{(_mm['spend']/_mm0['spend']-1)*100:+.1f}%"),
            ("RPP spend", f"¥{mrev['rpp_jpy']:,.0f} (≈{won(_rppk)})", f"¥{mrev['rpp_prev_jpy']:,.0f}", f"{(mrev['rpp_jpy']/mrev['rpp_prev_jpy']-1)*100:+.1f}%"),
            ("총 광고비", won(_tot), won(_tot0), f"{(_tot/_tot0-1)*100:+.1f}%"),
            ("라쿠텐 매출", f"¥{mrev['sales_jpy']:,.0f}", f"¥{mrev['sales_prev_jpy']:,.0f}", f"{(mrev['sales_jpy']/mrev['sales_prev_jpy']-1)*100:+.1f}%"),
            ("Total ROAS", f"{mrev['troas']:.2f}x", f"{mrev['troas_prev']:.2f}x", f"{mrev['troas']-mrev['troas_prev']:+.2f}"),
            ("Meta-only ROAS", f"{mrev['metaroas']:.2f}x", f"{mrev['metaroas_prev']:.2f}x", f"{mrev['metaroas']-mrev['metaroas_prev']:+.2f}"),
            ("CTR", f"{_mm['ctr']:.2f}%", f"{_mm0['ctr']:.2f}%", f"<span style='color:#1d4ed8;font-weight:700'>+{_mm['ctr']-_mm0['ctr']:.2f}%p</span>"),
            ("CPC", won(_mm["cpc"]), won(_mm0["cpc"]), f"<span style='color:#1d4ed8;font-weight:700'>{(_mm['cpc']/_mm0['cpc']-1)*100:.0f}%</span>"),
            ("CPLPV", won(_mm["cplpv"]), won(_mm0["cplpv"]), f"<span style='color:#1d4ed8;font-weight:700'>{(_mm['cplpv']/_mm0['cplpv']-1)*100:.0f}%</span>"),
            ("LPV", f"{_mm['lpv']:,.0f}", f"{_mm0['lpv']:,.0f}", f"<span style='color:#1d4ed8;font-weight:700'>+{(_mm['lpv']/_mm0['lpv']-1)*100:.0f}%</span>"),
        ])
        _t5 = "\n".join(
            f"<tr><td class=l>@{esc(t['slug'].lower())}</td><td>{won(t['spend'])}</td>"
            f"<td>{t['ctr']:.1f}%</td><td>{won(t['cpc'])}</td><td class=b>{won(t['cplpv'])}</td></tr>" for t in mrev["top5"])
        _seg = "".join(
            f"<span style='display:block;width:{w / _mtot * 100:.1f}%;background:{c}'></span>"
            for w, c in [(mp["good_sp"], "#16a34a"), (mp["watch_sp"], "#eab308"), (mp["bad_sp"], "#dc2626"),
                         (mp["grad_sp"], "#2563eb"), (mp["off_sp"], "#334155")])
        month_slides = f"""
<!-- 월간 리뷰 ① 총괄 (세은 8/3 — 노션 2607 Meta Ads 구조) -->
<section class=wide>
  <h2>{_L} 월간 총괄 — Total ROAS · 광고비 · 매출 <span class=h2sub>{mrev['window'][0]} ~ {mrev['window'][1]} 확정 · RPP·매출 = 라쿠텐 일별 실측 · 환율 {_P} {mrev['fx_prev']:.2f} → {_L} {mrev['fx']:.2f} KRW/JPY</span></h2>
  <div class=sumcards>
    <div class='sumcard sc-b'><div class=sumnum>{mrev['troas']:.2f}x</div><b>Total ROAS</b><p>매출 ÷ (Meta+RPP) · {_P} {mrev['troas_prev']:.2f}x</p></div>
    <div class='sumcard sc-g'><div class=sumnum>{won(_tot)}</div><b>총 광고비</b><p>Meta {won(_mm['spend'])} + RPP ¥{mrev['rpp_jpy']:,.0f} · {_P} 대비 {(_tot/_tot0-1)*100:+.1f}%</p></div>
    <div class='sumcard sc-g'><div class=sumnum>¥{mrev['sales_jpy']:,.0f}</div><b>라쿠텐 매출</b><p>≈{won(_salk)} · {_P} 대비 ¥ {(mrev['sales_jpy']/mrev['sales_prev_jpy']-1)*100:+.1f}%</p></div>
    <div class='sumcard sc-b'><div class=sumnum>{won(_mm['cplpv'])}</div><b>CPLPV</b><p>{_P} {won(_mm0['cplpv'])} · {(_mm['cplpv']/_mm0['cplpv']-1)*100:.0f}% 개선</p></div>
  </div>
  <div class=cols2eq style='margin-top:14px'>
    <div>
      <div class=boxh>{_L} vs {_P}</div>
      <table class=rank style='font-size:13px'>
        <tr><th class=l>지표</th><th>{_L}</th><th>{_P}</th><th>변화</th></tr>
        {_mtbl}
      </table>
    </div>
    <div>
      <div class=boxh>판정</div>
      <p style='font-size:14.5px;line-height:1.7'><b>Meta 예산 유지({(_mm['spend']/_mm0['spend']-1)*100:+.1f}%)하며 효율 전 지표 개선.</b> LPV {(_mm['lpv']/_mm0['lpv']-1)*100:+.0f}% ({_mm0['lpv']:,.0f}→{_mm['lpv']:,.0f}). Total ROAS 소폭 하락({mrev['troas']-mrev['troas_prev']:+.2f})은 매출 문제가 아니라 <b>RPP 증액(¥{mrev['rpp_prev_jpy']/1000:.0f}K→¥{mrev['rpp_jpy']/1000:.0f}K)과 환율 하락({mrev['fx_prev']:.2f}→{mrev['fx']:.2f})</b> 영향 — ¥ 매출은 {(mrev['sales_jpy']/mrev['sales_prev_jpy']-1)*100:+.1f}%.</p>
      <div class=boxh style='margin-top:10px'>제품별 CPLPV (광고명 ASIN 분류)</div>
      <p style='font-size:14.5px'>PPSU <b>{won(mrev['product_cplpv']['PPSU'])}</b> · Stainless <b>{won(mrev['product_cplpv']['Stainless'])}</b></p>
      <div class=note>DK 교차검증 spend 오차 {mrev['dk_xcheck_err_pct']}% · Meta-only ROAS {mrev['metaroas']:.2f}x ({_P} {mrev['metaroas_prev']:.2f}x)</div>
    </div>
  </div>
</section>

<!-- 월간 리뷰 ② 광고 풀 배분 -->
<section class=wide>
  <h2>{_L} 광고 풀 — 집행 {mp['ran']}개 · spend 배분 <span class=h2sub>분류 = 운영 게이트 기준 · on/off = Graph 실시간 · spend 합 = 계정 총액 일치 검증</span></h2>
  <div class=sumcards>
    <div class='sumcard sc-g'><div class=sumnum>{mp['ran']}</div><b>집행</b><p>{_L} spend 발생 기준</p></div>
    <div class='sumcard sc-b'><div class=sumnum>{mp['active']}</div><b>현재 ACTIVE</b><p>Graph 실시간 판정</p></div>
    <div class='sumcard sc-b'><div class=sumnum>{mp['grad_n']}</div><b>🎓 졸업</b><p>Testing 검증 통과 → Proven 이관 (OFF 아님)</p></div>
    <div class='sumcard sc-k'><div class=sumnum>{mp['off_n']}</div><b>⏹️ OFF</b><p>부진 종료 {mp['off_poor_n']} + 구소재 정리 {mp['off_tidy_n']}</p></div>
  </div>
  <div class=boxh style='margin-top:12px'>spend 배분 ({won(_mtot)})</div>
  <div style='display:flex;height:20px;border-radius:6px;overflow:hidden;margin:8px 0'>{_seg}</div>
  <div class=note>🟢 우수 {_mpct(mp['good_sp'])} · 🟡 모니터링 {_mpct(mp['watch_sp'])} · 🔴 미달 {_mpct(mp['bad_sp'])} · 🔵 졸업 {_mpct(mp['grad_sp'])} · ⚫ OFF {_mpct(mp['off_sp'])} — spend의 {_mpct(mp['good_sp'])}가 효율 우수 광고에 집행, 부진 손실은 {mp['off_poor_sp']/_mtot*100:.1f}%에서 컷</div>
  <div class=cols2eq style='margin-top:10px'>
    <div>
      <div class=boxh>🟢 효율 우수 TOP 5 (콘텐츠 단위 · 전부 Proven)</div>
      <table class=rank style='font-size:13px'>
        <tr><th class=l>크리에이터</th><th>spend</th><th>CTR</th><th>CPC</th><th>CPLPV</th></tr>
        {_t5}
      </table>
    </div>
    <div>
      <div class=boxh>분류별 spend</div>
      <table class=rank style='font-size:13px'>
        <tr><th class=l>구분</th><th>개수</th><th>spend</th><th>비중</th></tr>
        <tr><td class=l>🟢 효율 우수</td><td>{mp['good_n']}</td><td>{won(mp['good_sp'])}</td><td class=b>{_mpct(mp['good_sp'])}</td></tr>
        <tr><td class=l>🟡 모니터링 (경계선)</td><td>{mp['watch_n']}</td><td>{won(mp['watch_sp'])}</td><td>{_mpct(mp['watch_sp'])}</td></tr>
        <tr><td class=l>🔴 효율 미달 (OFF 검토)</td><td>{mp['bad_n']}</td><td>{won(mp['bad_sp'])}</td><td>{_mpct(mp['bad_sp'])}</td></tr>
        <tr><td class=l>🔵 졸업 (승격 이관)</td><td>{mp['grad_n']}</td><td>{won(mp['grad_sp'])}</td><td>{_mpct(mp['grad_sp'])}</td></tr>
        <tr><td class=l>⚫ OFF (부진+정리)</td><td>{mp['off_n']}</td><td>{won(mp['off_sp'])}</td><td>{_mpct(mp['off_sp'])}</td></tr>
      </table>
      <div class=note>🟡 모니터링: {esc(mrev['watch_names'])}<br>🔴 미달: {esc(mrev['bad_names'])} — 전부 Testing, 게이트 판정 도래 시 OFF 후보</div>
    </div>
  </div>
</section>

<!-- 월간 리뷰 ③ 졸업·OFF·운영 사이클 -->
<section>
  <h2>{_L} 졸업 · OFF · 운영 사이클 <span class=h2sub>졸업 = Testing 검증 통과 → Proven 이관 — 종료가 아니라 승격</span></h2>
  <div class=cols2eq>
    <div>
      <div class=boxh>🎓 졸업 {mp['grad_n']}건 (Testing → Proven)</div>
      <p style='font-size:14px;line-height:1.7'><b>{esc(mrev['grad_names'])}</b></p>
      <p style='font-size:13px;color:#555'>Testing에서 성과 검증 완료 → Proven 재편성. 동일 소재가 Proven에서 계속 집행 중.</p>
    </div>
    <div>
      <div class=boxh>⏹️ OFF {mp['off_n']}건</div>
      <p style='font-size:13.5px;line-height:1.7'><b>부진 종료 {mp['off_poor_n']}</b>: {esc(mrev['off_poor_txt'])} ({_L} CPLPV — 계정 평균의 1.6~2.7배)<br><b>구소재 정리 {mp['off_tidy_n']}</b>: {esc(mrev['off_tidy_txt'])}</p>
      <p style='font-size:13px;color:#555'>OFF 기준: 충분한 집행 후에도 CPLPV가 내부 OFF 라인 상회 시 종료 (CTR·CPC 보조 판단).</p>
    </div>
  </div>
  <div class=twrow style='margin-top:14px'>
    <div class='twcard tw-b'><div class=twnum>{mrev['cycle']['new_launch']}건</div><b>신규 Testing 론칭</b><p>{_L} 신규 소재 투입</p></div>
    <div class='twcard tw-g'><div class=twnum>{mrev['cycle']['grad']}건</div><b>졸업 → Proven 승격</b><p>월중 검증 통과 (6/30 론칭 1건 포함)</p></div>
    <div class='twcard tw-r'><div class=twnum>{mrev['cycle']['cut']}건</div><b>부진 종료</b><p>손실 {mp['off_poor_sp']/_mtot*100:.1f}%에서 컷</p></div>
  </div>
  <div class=note>테스트 → 검증 → 승격 사이클이 한 달 안에 회전 — 신규 소재의 절반 이상이 당월 내 승격 또는 컷 판정 완료.</div>
</section>

<!-- 월간 리뷰 ④ 개선 원인 분해 -->
<section class=wide>
  <h2>{_L} 개선 분해 — 왜 좋아졌나 <span class=h2sub>결론: 소재가 좋아진 게 아니라 예산 배분이 좋아졌다</span></h2>
  <div class=cols2eq>
    <div>
      <div class=boxh>① 개선의 경로 — CTR {(_mm['ctr']/_mm0['ctr']-1)*100:+.0f}% ▶ CPC {(_mm['cpc']/_mm0['cpc']-1)*100:.0f}% ▶ CPLPV {(_mm['cplpv']/_mm0['cplpv']-1)*100:.0f}%</div>
      <table class=rank style='font-size:13px'>
        <tr><th class=l>단계</th><th>{_P} → {_L}</th><th class=l>판정</th></tr>
        <tr><td class=l>CTR</td><td>{_mm0['ctr']:.2f}% → {_mm['ctr']:.2f}%</td><td class=l><b style='color:#1d4ed8'>🟢 개선의 발원지</b></td></tr>
        <tr><td class=l>CPC</td><td>{won(_mm0['cpc'])} → {won(_mm['cpc'])}</td><td class=l><b style='color:#1d4ed8'>🟢 CTR 상승이 만든 결과</b></td></tr>
        <tr><td class=l>CPM (노출 단가)</td><td>{won(_mm0['cpm'])} → {won(_mm['cpm'])}</td><td class=l>⚪ 기여 없음 — 시장은 +1.4% 역풍</td></tr>
        <tr><td class=l>클릭→LPV 도달률</td><td>{_mm0['c2l']:.1f}% → {_mm['c2l']:.1f}%</td><td class=l>⚪ 거의 동일 — 클릭 질 유지</td></tr>
      </table>
      <div class=boxh style='margin-top:10px'>② CTR 상승의 정체 — 배분 vs 소재</div>
      <div class=twrow>
        <div class='twcard tw-b'><div class=twnum>{md['mix_pp']:+.2f}%p</div><b>🔀 배분(믹스) 효과</b><p>고CTR 소재로 노출 이동 — 상승분의 사실상 전부</p></div>
        <div class='twcard tw-g'><div class=twnum>{md['creative_pp']:+.2f}%p</div><b>🎨 소재 자체 효과</b><p>같은 소재만 보면 피로로 소폭 하락</p></div>
      </div>
      <div class=note>검증: {_L} 노출 배분 × {_P} 소재 CTR 가상치({md['cf_ctr']:.2f}%) vs 실측({_mm['ctr']:.2f}%) vs {_P}({_mm0['ctr']:.2f}%)</div>
    </div>
    <div>
      <div class=boxh>③ 배분을 바꾼 두 가지 운영</div>
      <p style='font-size:13.5px;line-height:1.7'><b>1) 에이스 스케일업 (졸업 시스템)</b><br>{esc(md['ace']['slug'])} — {esc(md['ace']['path'])}<br>CTR {md['ace']['ctr']}% · CPLPV {won(md['ace']['cplpv'])} — 최고 효율 소재가 최대 지출처.<br>반대로 {esc(md['deboost']['slug'])}: {esc(md['deboost']['note'])}</p>
      <p style='font-size:13.5px;line-height:1.7'><b>2) 저효율 꼬리 절단 (게이트)</b><br>내부 OFF 라인 상회 소재 spend 비중 — {_P} <b>{md['lowcut_prev']}%</b> (₩{md['lowcut_prev_krw']/1e6:.2f}M) → {_L} <b>{md['lowcut']}%</b> (₩{md['lowcut_krw']/1e6:.2f}M). 새는 돈 1/3로.</p>
      <div class=boxh style='margin-top:10px'>④ 유의점</div>
      <div class=note style='border-left:3px solid #c0392b'><b>집중 리스크</b> — {esc(md['ace']['slug'])} 1개가 spend 29%, {esc(md['ace']['fatigue'])}. 8월 피로 진행 시 개선폭 일부 반납 가능. 유지 조건 = 신규 Testing 파이프라인({mrev['cycle']['new_launch']}건/월 페이스)의 에이스 공급.</div>
    </div>
  </div>
</section>"""
    else:
        # 폴백: month_review.json 없을 때 간이 월간 총괄 1장 (payload 생성 = .tmp/build_month_review_json.py)
        month_slides = f"""
<!-- 전월 월간 집행 성과 (간이 폴백) -->
<section>
  <h2>{m1lab} 월간 집행 성과 <span class=h2sub>{wm1[0]} ~ {wm1[1]} 계정 전체 실측 · 상세 월간 리뷰 = month_review.json 생성 후 재렌더</span></h2>
  <table class=rank style='font-size:15px;max-width:760px'>
    <tr><th class=l>지표</th><th>{m1lab}</th><th>{m0lab}</th></tr>
    <tr><td class=l>광고비</td><td class=b>{won(tm1.get('spend', 0))}</td><td>{won(tm0.get('spend', 0))}</td></tr>
    <tr><td class=l>라쿠텐 방문 수 (LPV)</td><td class=b>{int(tm1.get('lpv', 0)):,}</td><td>{int(tm0.get('lpv', 0)):,}</td></tr>
    <tr><td class=l>방문 1명 비용 (CPLPV)</td><td class=b>{won_or_dash(tm1.get('cplpv'))}</td><td>{won_or_dash(tm0.get('cplpv'))}</td></tr>
    <tr><td class=l>클릭율 (CTR)</td><td class=b>{tm1.get('ctr', 0):.2f}%</td><td>{tm0.get('ctr', 0):.2f}%</td></tr>
  </table>
  <div class=note>신규 런칭 — {m1lab} {m1_launch}개 (전월 {m0_launch}개)</div>
</section>"""

    def _cmp_table(cur, prev):
        """기간 비교 표 rows — Δ 색: 좋아진 방향 파랑 / 나빠진 방향 빨강 (CPLPV·CPC는 낮을수록 좋음)."""
        if not (cur and prev and prev.get("spend")):
            return "<tr><td colspan=4 class=dim>직전 기간 데이터 없음 — 수집 재실행 필요</td></tr>"

        def dl(c, p, low_good=None):
            if not p:
                return "—"
            pct = (c - p) / p * 100
            if abs(pct) < 5:   # 변화 크지 않음 → 색·수치 대신 '유지' (세은 7/27)
                return "<span class=dim>유지</span>"
            if low_good is None:   # Spend 는 좋고 나쁨 없음 — 중립
                return f"<span class=dim>{pct:+.0f}%</span>"
            good = (pct < 0) if low_good else (pct > 0)
            return f"<span style='color:{'#1d4ed8' if good else '#c0392b'};font-weight:700'>{pct:+.0f}%</span>"
        specs = [
            ("광고비", won(cur["spend"]), won(prev["spend"]), dl(cur["spend"], prev["spend"])),
            ("라쿠텐 방문 수 (LPV)", f"{int(cur['lpv']):,}", f"{int(prev['lpv']):,}",
             dl(cur["lpv"], prev["lpv"], low_good=False)),
            ("방문 1명 비용 (CPLPV)", won_or_dash(cur["cplpv"]), won_or_dash(prev["cplpv"]),
             dl(cur["cplpv"], prev["cplpv"], low_good=True) if cur.get("cplpv") and prev.get("cplpv") else "—"),
            ("클릭율 (CTR)", f"{cur['ctr']:.2f}%", f"{prev['ctr']:.2f}%",
             dl(cur["ctr"], prev["ctr"], low_good=False)),
            ("클릭 단가 (CPC)", won(cur["cpc"]), won(prev["cpc"]), dl(cur["cpc"], prev["cpc"], low_good=True)),
            ("3초 시청률 (3S율)", f"{cur['rate3s']:.0f}%", f"{prev['rate3s']:.0f}%",
             dl(cur["rate3s"], prev["rate3s"], low_good=False)),
        ]
        return "\n".join(f"<tr><td class=l>{a}</td><td class=b>{b}</td><td>{c}</td><td>{d}</td></tr>"
                         for a, b, c, d in specs)

    def _dirline(cur, prev, label):
        if cur and prev and cur.get("cplpv") and prev.get("cplpv"):
            pct = (cur["cplpv"] - prev["cplpv"]) / prev["cplpv"] * 100
            if abs(pct) < 5:   # 변화 표 '유지' 기준(±5%)과 동일 컷
                return f"{label} 방문 비용 {won(prev['cplpv'])} → {won(cur['cplpv'])} (<b>유지</b>)"
            word = "개선" if pct < 0 else "악화"
            return f"{label} 방문 비용 {won(prev['cplpv'])} → {won(cur['cplpv'])} ({pct:+.0f}%, <b>{word}</b>)"
        return f"{label} 직전 기간 비교 불가"

    def _adset_disp(an):
        sl = creator_slug(an or "")
        return f"@{sl}" if sl else esc((an or "?")[:30])
    ops_rows = []
    _camp_seen = None
    for r in adsets7:
        if r["campaign"] != _camp_seen:
            _camp_seen = r["campaign"]
            grp = [x for x in adsets7 if x["campaign"] == _camp_seen]
            gsp = sum(x["spend"] for x in grp)
            glv = sum(x["lpv"] for x in grp)
            ops_rows.append(
                f"<tr class=campsep><td class=l colspan=2>📣 {esc(_camp_seen)}</td>"
                f"<td>{won(gsp)}</td><td colspan=3 class=dim>Ad Set {len(grp)}개 · 소계 CPLPV {won_or_dash(cplpv_calc(gsp, glv))}</td><td></td></tr>")
        ops_rows.append(
            f"<tr><td class=l style='padding-left:26px'>{_adset_disp(r['adset'])}</td>"
            f"<td>{r['n_ads']}</td><td>{won(r['spend'])}</td><td>{r['ctr']:.1f}%</td>"
            f"<td>{won(r['cpc'])}</td><td class=b>{won_or_dash(r['cplpv'])}</td>"
            f"<td>{'라이브' if r['live'] else 'OFF'}</td></tr>")
    ops_table = "\n".join(ops_rows)
    # 30d 효율 평가 근거 (관찰 수치만)
    grad_in = [a for a in act_wl if a["cplpv"] and a["cplpv"] <= g["grad"]["cplpv"]]

    # ── P13 핵심 변화 히어로 (세은 8/10: 눈에 띄게 좋아진 지표 + 그 이유 판단) ──
    def _pctc(c, p):
        return ((c - p) / p * 100) if p else 0.0
    ops_hero = ""
    if t7 and tp and tp.get("spend"):
        _cands = []   # (개선폭, 라벨, 변화문구)
        if t7.get("cplpv") and tp.get("cplpv"):
            _v = _pctc(t7["cplpv"], tp["cplpv"])
            if _v < 0:
                _cands.append((-_v, "방문 1명 비용", f"{won(tp['cplpv'])} → {won(t7['cplpv'])} ({_v:+.0f}%)"))
        _v = _pctc(t7["ctr"], tp["ctr"])
        if _v > 0:
            _cands.append((_v, "클릭율(CTR)", f"{tp['ctr']:.2f}% → {t7['ctr']:.2f}% ({_v:+.0f}%)"))
        _v = _pctc(t7["cpc"], tp["cpc"])
        if _v < 0:
            _cands.append((-_v, "클릭 단가(CPC)", f"{won(tp['cpc'])} → {won(t7['cpc'])} ({_v:+.0f}%)"))
        _v = _pctc(t7.get("rate3s") or 0, tp.get("rate3s") or 0)
        if _v > 0:
            _cands.append((_v, "3초 시청률(3S율)", f"{tp.get('rate3s', 0):.0f}% → {t7.get('rate3s', 0):.0f}% ({_v:+.0f}%)"))
        _hero = max(_cands, key=lambda x: x[0], default=None)
        if _hero and _hero[0] >= 5:   # 유의미(≥5%) 개선만 히어로로
            _mag, _hlab, _hchg = _hero
            _spp = _pctc(t7["spend"], tp["spend"])
            if _hlab.startswith("방문"):
                if _pctc(t7["ctr"], tp["ctr"]) >= 5:
                    _why = "<b>클릭율이 올라서</b> — 같은 노출에서 더 많이 눌렀다."
                elif _pctc(t7["cpc"], tp["cpc"]) <= -5:
                    _why = "<b>클릭 단가가 싸져서</b> — 클릭 1건 값이 내려갔다."
                elif _spp >= 5:
                    _why = f"<b>규모를 키우며 효율 유지</b> — 광고비 {_spp:+.0f}%인데 방문 비용은 내려감. 게이트로 나쁜 소재를 갈아끼운 배분 효과."
                else:
                    _why = "<b>배분·게이트 최적화</b> — 소재 자체보다 예산이 좋은 소재로 이동한 효과."
            elif _hlab.startswith("클릭율"):
                _why = "<b>눌리는 힘 개선</b> — 소구·훅이 좋아졌거나, 잘 눌리는 소재로 노출이 이동."
            elif _hlab.startswith("클릭 단가"):
                _why = "<b>클릭이 싸짐</b> — 클릭율 상승 또는 경쟁 완화."
            else:
                _why = "<b>첫 3초 개선</b> — 첫 프레임·오프닝이 더 잘 붙잡음."
            ops_hero = (
                "<div class=opshero>"
                f"<div class=opsheroL><div class=opsherolbl>▲ 이번 주 가장 좋아진 지표</div>"
                f"<div class=opsheronum>{_hlab}</div><div class=opsherochg>{_hchg}</div></div>"
                f"<div class=opsheroR><div class=opsherolbl>왜 좋아졌나 — 판단</div>"
                f"<div class=opswhy>{_why}</div></div></div>")

    # 한눈 슬라이드 3S율 인사이트 — 방향까지 데이터 조건부 (하드코딩 서사 금지)
    if bc["g"] and (bc["y2"] + bc["r"]):
        _gap = good_r3 - bad_r3
        if _gap >= 3:
            _concl = "첫 3초 훅에서 이미 갈린다 — 소재는 첫 프레임·첫 카피가 승부."
        elif _gap <= -3:
            _concl = "열위군 3S율이 오히려 높음 — 판정을 가르는 축은 클릭·랜딩."
        else:
            _concl = "이번 풀은 3S율 격차 근소 — 판정을 가르는 축은 클릭(CTR)·랜딩(CPLPV)."
        r3_insight = (f"1달 풀 노출 가중 3S율(3초 이상 시청률) — 🔵 좋음군 <b>{good_r3:.0f}%</b> vs 🔴⚫ 열위군 "
                      f"<b>{bad_r3:.0f}%</b> ({_gap:+.1f}pt). {_concl}")
    else:
        r3_insight = "군별 3S율 비교는 표본 부족 (한쪽 군 0개) — 다음 주 재계산."

    launches = ssot["launches_by_month"]
    recent_launch = " · ".join(f"{k[5:]}월 {v}개" for k, v in list(launches.items())[-3:]) or "—"
    grads_now = [a for a in act if a["stage"] == "testing" and band(a) == "g"]
    top = min(act_wl, key=lambda a: (a["cplpv"] or 9e9)) if act_wl else None
    top_line = ("<p>—</p>" if not top else
                f"<p><b>{esc(content_name(top))}</b> — CPLPV {won_or_dash(top['cplpv'])} · "
                f"CTR {top['ctr']:.1f}% · 7d {won(top['spend'])}<br>{km_short(top)}</p>")

    # 소재 형태별 생애 실측 — "현재 WL만 운영" 근거 (슬라이드 3)
    fp = ssot.get("format_perf") or {}
    fw, fm = fp.get("wl"), fp.get("img")
    if fw and fm and fm["n"]:
        ratio_txt = ""
        if fw["cplpv"] and fm["cplpv"]:
            ratio_txt = f" — 같은 LPV 1건을 이미지가 <b>{fm['cplpv']/fw['cplpv']:.1f}배</b> 비싸게 삼"
        fmt_block = f"""
  <table class=rank style='max-width:980px;font-size:14.5px;margin-top:10px'>
    <tr><th class=l>소재 형태 ({esc(LIFE_LABEL)} 실측)</th><th>광고 수</th><th>Spend</th><th>CTR</th><th>CPC</th><th>CPLPV</th></tr>
    <tr><td class=l><b>인플루언서 WL</b></td><td>{fw['n']}</td><td>{won(fw['spend'])}</td><td class=b>{fw['ctr']:.1f}%</td><td>{won(fw['cpc'])}</td><td class=b>{won_or_dash(fw['cplpv'])}</td></tr>
    <tr><td class=l>인하우스 이미지</td><td>{fm['n']}</td><td>{won(fm['spend'])}</td><td>{fm['ctr']:.1f}%</td><td>{won(fm['cpc'])}</td><td>{won_or_dash(fm['cplpv'])}</td></tr>
  </table>"""
        n_img_live = len([a for a in act if not a["is_wl"]])   # 현재 ACTIVE 이미지 소재 수 (실측)
        now_txt = ("<b>현재 라이브 소재는 100% WL</b> — 이미지 소재는 현재 0개 라이브" if n_img_live == 0
                   else f"<b>현재 라이브: WL {len(act_wl)}개 · 이미지 {n_img_live}개</b>")
        wl_only_li = (f"<li>{now_txt}{ratio_txt}. 앞으로 <b>IHM·IHV</b>도 같은 Testing 게이트로 운영 예정.</li>")
    else:
        fmt_block = ""
        wl_only_li = "<li><b>현재 라이브 소재는 100% WL</b> — 앞으로 <b>IHM·IHV</b>도 같은 Testing 게이트로 운영 예정.</li>"

    slides = f"""
<!-- 1 표지 -->
<section class=title>
  <div class=kicker>GROSMIMI JAPAN · MODULE MARKETPLACE</div>
  <h1>JP Meta — Weekly Performance Read</h1>
  <div class=sub>WL 콘텐츠 주간 성과 리뷰 · {ssot['window_7d'][0][5:].replace('-', '/')}~{ssot['window_7d'][1][5:].replace('-', '/')} (지난 7일) · Testing→Proven 게이트 운영</div>
  <div class=meta>발표 허세은 · {(date.fromisoformat(ssot['ref_date']) + timedelta(days=1)).isoformat()} · 데이터 pull {esc(ssot['pulled_at'][:16])}</div>
  <div class=methbox>
    <b>방법론 — 시작 전 3가지</b>
    <ul>
      <li><b>측정 천장 = LPV</b> — JP는 랜딩이 Rakuten(외부몰)이라 전환 픽셀이 없음 → 가장 깊은 지표는 LPV(랜딩페이지뷰). 운영 1차 지표 = <b>CPLPV</b>(LPV당 비용).</li>
      <li><b>데이터</b> — 성과·on/off = Meta Graph API 실측. 계산 수치는 전부 SSOT JSON 재계산, 과거 분석 인용치는 출처 병기. 통화 = KRW(계정 통화).</li>
      <li><b>기간·풀</b> — 리뷰 풀 = <b>최근 1달 내 런칭 콘텐츠</b>. 본체 = 지난 7일({ssot['window_7d'][0]} ~ {ssot['window_7d'][1]}) 영상 + 직전 7일 대비 성과 변동.</li>
      <li><b>숙성 기준(CPM 룰)</b> — 콘텐츠 퍼포먼스 판단은 <b>집행 7일 이상 숙성</b> 기준. 이번 주 신규 런칭은 참고치로만 표기(게이트 판정 유보). KM별 Top 표의 CTR은 <b>링크 클릭 기준</b>(관리자 CTR(전체)과 산식이 다름).</li>
      <li><b>3S율(3초 이상 시청률)</b> — 3초 이상 시청 ÷ 노출 (Meta Graph 3-second video plays 실측). 전 표·카드에 표기.</li>
      <li><b>게이트 판정</b> — 졸업·OFF 모두 CPC·CTR·CPLPV 지표 게이트로 자동 판정. 졸업 기준은 {esc(cf['gate_basis_grad']['value'])}, OFF 기준은 CPLPV 중심 — {esc(cf['gate_basis_off']['value'])}.<br><span class=cite>출처: {esc(cf['gate_basis_off']['source'])} · {esc(cf['gate_basis_grad']['source'])}</span></li>
    </ul>
  </div>
</section>

<!-- 채널/운영 구조 슬라이드는 삭제 (세은 7/20 — 이미 발표한 내용, 주간 덱에서 제외) -->

<!-- 이번 주 한눈 — 4색 분포 -->
<section>
  <h2>이번 주 한눈 — 최근 1달 런칭 {len(month_pool)}개 판정 <span class=h2sub>판정 = 운영 게이트 자동 · 이 4색은 이후 모든 표·카드 동일</span></h2>
  <div class=sumcards>
    <div class='sumcard sc-b'><div class=sumnum>{bc['g']}</div><b>🔵 좋음</b><p>졸업 게이트 통과 — 늘릴 것</p></div>
    <div class='sumcard sc-g'><div class=sumnum>{bc['y']}</div><b>🟢 중간</b><p>게이트 사이 — 관찰 유지</p></div>
    <div class='sumcard sc-r'><div class=sumnum>{bc['y2']}</div><b>🔴 안 좋음</b><p>CPC·CTR 열위, CPLPV 정상 — D+5 유예</p></div>
    <div class='sumcard sc-k'><div class=sumnum>{bc['r']}</div><b>⚫ 빨리 OFF</b><p>OFF 게이트 해당 — 즉시 정리</p></div>
  </div>
  <div class=cols2eq style='margin-top:18px'>
    <div>
      <div class=boxh>최근 7일 총괄 ({ssot['window_7d'][0][5:]}~{ssot['window_7d'][1][5:]})</div>
      <table class=mini>
        <tr><td>Spend</td><td><b>{won(t7['spend'])}</b> {wow(t7['spend'], tp['spend'], neutral=True)}</td></tr>
        <tr><td>3S율(3초 이상 시청률)</td><td><b>{t7.get('rate3s', 0):.0f}%</b> <span class=dim>(직전 7일 {tp.get('rate3s', 0):.0f}%)</span></td></tr>
        <tr><td>CTR</td><td><b>{t7['ctr']:.2f}%</b></td></tr>
        <tr><td>CPLPV</td><td><b>{won_or_dash(t7['cplpv'])}</b> {wow(t7['cplpv'] or 0, tp['cplpv'] or 0, lower_is_better=True)}</td></tr>
      </table>
    </div>
    <div>
      <div class=boxh>3S율 × 판정 — 실측</div>
      <p style='font-size:15px;line-height:1.7'>{r3_insight}</p>
    </div>
  </div>
</section>

<!-- 최근 1달 런칭 전수 디스포지션 -->
<section class=wide>
  <h2>최근 1달 런칭 콘텐츠 전수 — 판정·사유 <span class=h2sub>{len(month_pool)}개 · 판정색→CPLPV순 · 지표 = 최근 7일(노출 없으면 생애) · 3S율 = 3초 이상 시청 ÷ 노출</span></h2>
  <div class=tscroll><table class=rank>
    <tr><th></th><th class=l>콘텐츠</th><th>type</th><th class=l>KM</th><th>첫 라이브</th><th>상태</th><th>기준</th><th>Spend</th><th>3S율</th><th>CTR</th><th>CPC</th><th>CPLPV</th><th class=l>판정 사유</th></tr>
    {disp_rows}
  </table></div>
</section>

<!-- 이번 주 신규 런칭 -->
<section class=wide>
  <h2>이번 주 새로 올라간 콘텐츠 — {len(new_launch)}개 <span class=h2sub>{ssot['window_7d'][0][5:]}~{ssot['window_7d'][1][5:]} 첫 라이브 · 초기 지표(D+{g['grad']['days']} 게이트 판정 전 참고치) · 썸네일 클릭 = 릴 재생</span></h2>
  {new_launch_html}
</section>

{review_slides}

{ret_slide}

{corr_slide}

<!-- KM·훅타입별 Top (CPM 룰, 세은 8/3 — 집행 7일+ 숙성 풀) -->
<section>
  <h2>어떤 KM(소구)이 먹혔나 — 생애 실적 기준 <span class=h2sub>지금까지 집행 소재 중 생애 지출 ₩20,000↑ · CPLPV 낮은 순 = 잘 먹힌 소구 · 대표 콘텐츠 병기 · JP는 픽셀 매출 없어 방문 단가(CPLPV)로 판정</span></h2>
  {tag_tables}
</section>

<!-- 경향성 — 승격군 vs 잔류군 -->
<section class=wide>
  <h2>성과가 변하는 방식 — Proven 승격군 vs Testing 잔류군 <span class=h2sub>주간 CPLPV · 굵은 선=median · 음영=콘텐츠 분포 25~75% · 점선=졸업 기준 · 전 이력(3/1~) 전수</span></h2>
  <div class=twrow>{tw_cards}</div>
  <div class=cols2eq>
    <div>
      <div class=boxh>① Proven 군 {len(promo_series)}개 — 편입 전 {PRE_W}주 → 편입 후 {POST_W}주</div>
      {svg_promo}
      <div class=note>{promo_analysis}</div>
    </div>
    <div>
      <div class=boxh>② Testing 잔류군 {len(test_series)}개 — 라이브 주차별</div>
      {svg_test}
      <div class=note>{test_analysis}</div>
    </div>
  </div>
  <div class=note style='margin-top:8px'>주간 값 = 주 spend ₩{WK_MIN_SPEND:,}↑ 주만 산출 · '편입 전 2주' 선은 6/19 이후 승격 관측분({n_promo_observed}개)에만 존재 · 잔류군 {len(test_series)}개 = Testing 캠페인 신설(6/19) 이후 콘텐츠 전수 중 미졸업 전부(졸업 콘텐츠 제외·OFF 포함).</div>
</section>

<!-- 성과 변동 (선별) -->
<section class=wide>
  <h2>성과가 유의미하게 바뀐 콘텐츠 — 경향성 일치 선별 <span class=h2sub>직전 7일({ssot['window_prev7'][0][5:]}~{ssot['window_prev7'][1][5:]}) vs 최근 7일 · |Δ CPLPV| ≥ {MOVER_SIG}% + 앞장 경향성과 일치하는 것만 ({len(movers_sel)}/{len(movers)}개 선별)</span></h2>
  <table class=rank style='font-size:13.5px'>
    <tr><th class=l rowspan=2>콘텐츠</th><th rowspan=2>type</th><th colspan=4>직전 7일</th><th rowspan=2></th><th colspan=4>최근 7일</th><th rowspan=2>Δ CPLPV</th><th class=l rowspan=2>일치 경향 · 움직인 축</th></tr>
    <tr><th>Spend</th><th>3S율</th><th>CTR</th><th>CPLPV</th><th>Spend</th><th>3S율</th><th>CTR</th><th>CPLPV</th></tr>
    {mover_rows if mover_rows else "<tr><td colspan=13 class=dim>유의미(±" + str(MOVER_SIG) + "%) + 경향 일치 표본 없음</td></tr>"}
  </table>
  <div class=note>Δ CPLPV ▼=개선(LPV 단가 하락) · ▲=악화. 선별 기준 = 변화 폭 {MOVER_SIG}% 이상이면서 앞장 경향(승격 직후 점프 / 승격 후 회복)에 부합하는 콘텐츠. 나머지 {len(movers) - len(movers_sel)}개는 변화 소폭이거나 경향 외 개별 요인 — 전수는 디스포지션 표 참조.</div>
</section>

<!-- 졸업 후에도 효율이 유지되나 -->
<section>
  <h2>졸업 → 증액 후에도 효율이 유지되나 <span class=h2sub>같은 크리에이터 릴의 Testing 버전 vs Proven 버전 실측 (생애 합산)</span></h2>
  <table class=rank style='font-size:13.5px'>
    <tr><th class=l rowspan=2>콘텐츠</th><th colspan=5>Testing 시절{(' (' + test_bud_label + ' 지갑)') if test_bud_label else ''}</th><th rowspan=2></th><th colspan=5>Proven 승격 후 (통합 지갑)</th><th rowspan=2>현재</th></tr>
    <tr><th>Spend</th><th>CTR</th><th>CPC</th><th>LPV</th><th>CPLPV</th><th>Spend</th><th>CTR</th><th>CPC</th><th>LPV</th><th>CPLPV</th></tr>
    {promo_rows if promo_rows else "<tr><td colspan=13 class=dim>비교 가능 표본 없음</td></tr>"}
  </table>
  <div class=note>Proven 승격 = 예산 증가({test_bud_label or 'Testing 개별 지갑'} → 통합 지갑 {prov_bud_label or '증액 운영'}, 실측). 증액하면 오디언스가 넓어져 단가가 오르는 게 보통인데, 대부분 졸업 기준({won(g['grad']['cplpv'])}) 안쪽을 유지 — 게이트가 증액 내성 있는 소재를 골라내고 있다는 증거. 유지 실패 사례(rii_mama)는 게이트가 다시 잘랐다.</div>
</section>

{grad_research_slide}

<!-- 운영 성과 (세은 7/27: 7일 vs 직전 7일 / 30일 vs 직전 30일 두 갈래 + 정리) -->
<section class=wide>
  <h2>운영 성과 — 최근 vs 직전 <span class=h2sub>좌: 최근 7일({ssot['window_7d'][0][5:]}~{ssot['window_7d'][1][5:]}) vs 직전 7일({ssot['window_prev7'][0][5:]}~{ssot['window_prev7'][1][5:]}) · 우: 최근 30일 vs 직전 30일</span></h2>
  {ops_hero}
  <div class=cols2eq>
    <div>
      <div class=boxh>최근 7일 vs 직전 7일</div>
      <table class=rank style='font-size:15px'>
        <tr><th class=l>지표</th><th>최근 7일</th><th>직전 7일</th><th>변화</th></tr>
        {_cmp_table(t7, tp)}
      </table>
    </div>
    <div>
      <div class=boxh>최근 30일 vs 직전 30일</div>
      <table class=rank style='font-size:15px'>
        <tr><th class=l>지표</th><th>최근 30일</th><th>직전 30일</th><th>변화</th></tr>
        {_cmp_table(t30, tp30)}
      </table>
    </div>
  </div>
  <div class=boxh style='margin-top:18px'>효과적으로 돌고 있나 — 정리</div>
  <ul class=big style='font-size:15px'>
    <li><b>방향</b> — {_dirline(t7, tp, "주간:")} · {_dirline(t30, tp30, "월간:")}</li>
    <li><b>규모를 키우면서 효율 유지</b> — {("8주 전 주간 " + won(wk0['spend']) + " → 지난주 " + won(wk1['spend']) + ", 같은 기간 방문 비용 " + won_or_dash(wk0['cplpv']) + " → " + won_or_dash(wk1['cplpv']) + ". 지출을 키우면 보통 효율이 깨지는데, 게이트로 소재를 갈아끼우며 버티는 중.") if wk0 and wk1 else "주간 시계열 표본 부족."}</li>
    <li><b>소재 풀 건강도</b> — 라이브 WL {len(act_wl)}개 중 {len(grad_in)}개가 졸업 기준 방문 비용({won(g['grad']['cplpv'])}) 안쪽. 졸업 게이트 통과로 승격 대기 중인 Testing {len(grads_now)}개.</li>
  </ul>
</section>

{""}
"""
    # 세은 8/10: 7월 월간 블록(P14~17) 주간 덱에서 삭제 — month_slides 미삽입
    html = HTML_TEMPLATE.replace("__SLIDES__", slides).replace("__TITLE__", "JP Meta — Weekly Performance Read · GROSMIMI JAPAN")
    deck_path = Path(deck_path)
    try:
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        deck_path.write_text(html, encoding="utf-8")
    except OSError as e:
        sys.exit(f"[FATAL] 덱 저장 실패 ({deck_path}): {e} — --out 으로 경로 지정")
    print(f"deck → {deck_path}")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=ko><head><meta charset=utf-8><title>__TITLE__</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
/* PPT 테마 (세은 7/20 "덱 자체를 좀 더 ppt 느낌 나게") — 네이비→블루 그라데이션 헤더 밴드
   + 슬라이드 하단 액센트 바 + 풋터 브랜드 스트립 + 다크 타이틀 슬라이드 */
:root{--navy:#0e1c3a;--navy2:#1c3a75;--blue:#1877f2;--violet:#6d5bd0;--ink:#1a2233;--dim:#8a93a6;--line:#dfe6f3;
--g:#e8f7ee;--gt:#127a43;--y:#fff8e1;--r:#fdecec;--rt:#c0392b}
*{box-sizing:border-box;margin:0}
body{font-family:'Segoe UI','Malgun Gothic',sans-serif;color:var(--ink);background:#0b1226}
section{position:relative;width:100vw;height:100vh;padding:0 64px 52px;display:none;flex-direction:column;background:#fbfcff;overflow:hidden}
section.on{display:flex}
section::before{content:'';position:absolute;left:0;right:0;bottom:0;height:7px;background:linear-gradient(90deg,var(--navy),var(--blue) 55%,var(--violet))}
section::after{content:'GROSMIMI JAPAN · JP META 주간 리뷰';position:absolute;bottom:16px;left:64px;font-size:10.5px;letter-spacing:2.5px;font-weight:700;color:#9aa7c4}
h1{font-size:52px;color:#fff;margin:14px 0 6px}
h2{font-size:27px;color:#fff;background:linear-gradient(90deg,var(--navy),var(--navy2) 62%,#2b57c4);margin:0 -64px 20px;padding:22px 64px 19px;box-shadow:0 2px 10px rgba(14,28,58,.25)}
.h2sub{font-size:13px;color:#aec4ef;font-weight:400;margin-left:10px}
.kicker{letter-spacing:3px;color:#8fb6ff;font-weight:700;font-size:14px}
.sub{font-size:20px;color:#c7d6f7}
.meta{margin-top:8px;font-size:13px;color:#93a5cd}
.title{justify-content:center;background:linear-gradient(135deg,#0b1226,#14275c 55%,#1a49a8);padding:64px}
.title::after{color:#7f92bf}
.methbox{margin-top:32px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);border-radius:12px;padding:18px 22px;max-width:1050px;color:#dde7fb}
.methbox b{color:#fff}
.methbox .cite{color:#93a5cd}
.methbox ul{margin:10px 0 0 18px;line-height:1.65;font-size:15px}
.cols3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;flex:1}
.cols2{display:grid;grid-template-columns:1.25fr 1fr;gap:26px;align-items:start}
.cols2eq{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}
.box{background:#f8fafd;border:1px solid var(--line);border-radius:12px;padding:20px}
.boxh{display:inline-block;font-weight:700;color:#fff;background:linear-gradient(90deg,var(--blue),var(--violet));font-size:13px;letter-spacing:1px;margin-bottom:12px;border-radius:20px;padding:5px 16px}
.survbox{background:var(--g)}.deadbox{background:var(--r)}
.survbox .boxh{color:var(--gt)}.deadbox .boxh{color:var(--rt)}
.bignum{font-size:40px;font-weight:800;color:var(--navy);margin-bottom:10px}
.unit{font-size:16px;color:var(--dim);font-weight:600;margin:0 8px 0 4px}
.box p{font-size:15px;line-height:1.6}
.kmtags{margin-top:10px;font-size:13px}
table{border-collapse:collapse;width:100%}
.mini td{padding:7px 4px;border-bottom:1px solid rgba(0,0,0,.07);font-size:16px}
.mini td:first-child{color:var(--dim)}
.wow{font-size:13px;font-weight:700;margin-left:6px}
.wow.up{color:var(--gt)}.wow.dn{color:var(--rt)}.wow.nt{color:var(--dim)}
.rank{font-size:14px}
.rank th{background:linear-gradient(90deg,var(--navy),var(--navy2));color:#fff;padding:8px 10px;font-weight:600;text-align:right;white-space:nowrap}
.rank td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.rank .l,.rank th.l{text-align:left}
.rank .b{font-weight:700}
tr.bg{background:var(--g)}tr.br{background:var(--r)}tr.by{background:#fffdf3}tr.by2{background:var(--y)}
/* 판정 4색 (세은 7/20): 파랑=좋음 · 초록=중간 · 빨강=안 좋음 · 검정=빨리 OFF */
tr.cb{background:#e8f1fe}tr.cg{background:#eef9f1}tr.cr{background:#fdecec}
tr.ck{background:#23272e;color:#fff}
tr.ck td{border-color:#3a3f47}
tr.ck .dim{color:#9aa3b5}
.vb{font-size:11px;border-radius:20px;padding:2px 10px;font-weight:700;display:inline-block}
.vb.cb{background:#dbe9fd;color:#1256b0}.vb.cg{background:#dcf2e3;color:#127a43}
.vb.cr{background:#fbdcdc;color:#c0392b}.vb.ck{background:#23272e;color:#fff}
.ctype{font-size:10.5px;border:1px solid var(--line);border-radius:4px;padding:1px 6px;color:var(--dim);font-weight:700}
.sumcards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.sumcard{border-radius:12px;padding:16px 20px;border:2px solid;font-size:14px}
.sumcard p{font-size:12.5px;margin-top:4px;line-height:1.45}
.sc-b{border-color:#1877f2;background:#e8f1fe}.sc-g{border-color:#3fa96b;background:#eef9f1}
.sc-r{border-color:#c0392b;background:#fdecec}
.sc-k{border-color:#23272e;background:#23272e;color:#fff}
.sumnum{font-size:42px;font-weight:800;line-height:1.1}
.mvup{color:#1256b0;font-weight:800;white-space:nowrap}
.mvdn{color:var(--rt);font-weight:800;white-space:nowrap}
.twrow{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:12px}
.twcard{border-radius:12px;padding:12px 16px;border:2px solid;font-size:13.5px}
.twcard p{font-size:12px;line-height:1.5;margin-top:3px;color:#3d4658}
.twnum{font-size:30px;font-weight:800;line-height:1.15}
.tw-b{border-color:#1877f2;background:#e8f1fe}.tw-b .twnum{color:#1256b0}
.tw-g{border-color:#3fa96b;background:#eef9f1}.tw-g .twnum{color:#127a43}
.tw-r{border-color:#c0392b;background:#fdecec}.tw-r .twnum{color:#c0392b}
/* 고객 여정 퍼널 (세은 8/10: BEST vs WORST — 어디서 갈렸나 직관화 · 갈린 단계만 강조·나머지 회색·결과 분리) */
.funnel{display:flex;flex-direction:column;gap:0;margin-top:2px}
.fstep{display:grid;grid-template-columns:30px 1fr auto auto;align-items:center;gap:12px;border:1px solid var(--line);border-radius:10px;padding:9px 14px;background:#fbfcff}
.fstep .fn{font-size:16px;font-weight:800;color:#b6c0d4;text-align:center}
.fstep .fl{font-size:14.5px;font-weight:700;color:#7a8496}
.fstep .fl span{display:block;font-weight:400;font-size:11px;color:#9aa3b5;margin-top:1px}
.fstep .fv{font-size:15px;font-weight:700;color:#8a93a6;white-space:nowrap}
.fstep .fv b{color:#6b7688}
.fstep .ft{font-size:11.5px;font-weight:700;color:#9aa3b5;white-space:nowrap;text-align:right}
.fstep.hot{background:#e8f1fe;border:2px solid var(--blue)}
.fstep.hot .fn{color:var(--blue)}
.fstep.hot .fl{color:var(--navy);font-size:15.5px}
.fstep.hot .fv{color:var(--navy);font-size:17px}
.fstep.hot .fv b{color:#1256b0}
.fstep.hot .ft{color:#1256b0;font-size:12.5px;font-weight:800}
.fdrop{color:#c3cbdb;font-size:11px;text-align:center;line-height:1;padding:2px 0}
.fresult{display:grid;grid-template-columns:30px 1fr auto auto;align-items:center;gap:12px;border:2px dashed #b9cdf2;border-radius:10px;padding:10px 14px;background:#f4f8ff}
.fresult .fn{font-size:11.5px;font-weight:800;color:var(--violet);text-align:center}
.fresult .fl{font-size:14.5px;font-weight:800;color:var(--navy)}
.fresult .fv{font-size:17px;font-weight:800;color:var(--navy);white-space:nowrap}
.fresult .ft{font-size:12px;font-weight:700;color:var(--gt);white-space:nowrap}
.funread{margin-top:11px;font-size:14.5px;line-height:1.55;color:var(--ink);background:#eef4ff;border-left:4px solid var(--blue);border-radius:8px;padding:9px 13px}
.funnote{margin-top:8px;font-size:11.5px;color:#9aa3b5;line-height:1.5}
/* P8 처방 — 병목→목표 배너 + 액션 카드 (세은 8/10: 직관·시각화) */
.fixhead{font-size:16px;line-height:1.55;color:var(--ink);background:#eef4ff;border-left:4px solid var(--blue);border-radius:8px;padding:11px 15px;margin-bottom:16px}
.fixbanner{display:grid;grid-template-columns:1fr auto 1fr;gap:22px;align-items:center;margin:4px 0 20px}
.fixnow,.fixgoal{border-radius:16px;padding:18px 24px;text-align:center;border:2px solid}
.fixnow{background:#fdecec;border-color:#f0b4b4}
.fixgoal{background:#e8f1fe;border-color:var(--blue)}
.fixlbl{font-size:13px;font-weight:700;color:var(--dim)}
.fixbig{font-size:52px;font-weight:800;line-height:1.05;margin:2px 0}
.fixnow .fixbig{color:var(--rt)}.fixgoal .fixbig{color:#1256b0}
.fixsub{font-size:13.5px;color:#5a6478;margin-top:2px}
.fixarrow{font-size:30px;font-weight:800;color:var(--navy);text-align:center;line-height:1.2}
.twcard.actcard{display:flex;gap:12px;align-items:flex-start;padding:16px 18px}
.actn{font-size:26px;font-weight:800;color:#1256b0;line-height:1;flex:none}
.acttext{font-size:15px!important;line-height:1.5;color:var(--ink)!important;margin-top:2px!important}
/* P9 KM 순위 카드 — 순위가 히어로 (세은 8/10) */
.twcard.kmrank{text-align:left}
.kmrank .twnum{font-size:34px}
.kmcode{font-size:17px;color:var(--navy);display:block;margin-top:2px}
.kmdesc{font-size:12.5px!important;line-height:1.45;color:#3d4658;margin-top:4px!important}
.kmmeta{font-size:12px;color:var(--dim);margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
.kmmeta b{color:#5a6478}
/* P13 핵심 변화 히어로 (세은 8/10: 좋아진 지표 + 이유) */
.opshero{display:grid;grid-template-columns:1fr 1.3fr;gap:18px;margin:6px 0 18px}
.opsheroL{background:#e8f1fe;border:2px solid var(--blue);border-radius:14px;padding:16px 22px}
.opsheroR{background:#f4fbf6;border:2px solid #3fa96b;border-radius:14px;padding:16px 22px}
.opsherolbl{font-size:13px;font-weight:800;color:var(--dim);letter-spacing:.5px}
.opsheronum{font-size:26px;font-weight:800;color:var(--navy);margin:4px 0 2px}
.opsherochg{font-size:19px;font-weight:800;color:#1256b0}
.opswhy{font-size:16px;line-height:1.55;color:var(--ink);margin-top:6px}
/* 졸업후 효율 변화 — asset별 다이버징 바 (세은 8/10) */
.gradbars{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.gradbar{display:grid;grid-template-columns:160px 1fr 210px;align-items:center;gap:12px}
.gbname{font-size:13.5px;font-weight:700;color:var(--ink);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gbtrack{position:relative;height:20px;background:#f4f6fb;border-radius:6px}
.gbmid{position:absolute;left:50%;top:-2px;bottom:-2px;width:2px;background:#c3cbdb}
.gbfill{position:absolute;top:3px;bottom:3px;border-radius:4px;min-width:3px}
.gbval{font-size:12.5px;font-weight:700;white-space:nowrap}
tr.tot td{background:#eef2fa;font-weight:700;border-top:2px solid var(--navy)}
.dim{color:var(--dim)}
.cite{font-size:11.5px;color:var(--dim)}
.tscroll{overflow-y:auto;flex:1}
.wide{padding:0 48px 48px}
.wide h2{margin:0 -48px 16px;padding:18px 48px 16px}
.gates{font-size:15px}
.gates th,.gates td{padding:12px 14px;border:1px solid var(--line)}
.gates th{background:var(--navy);color:#fff;text-align:left}
.gates .l{text-align:left}
.gates td.l:first-child{font-weight:700;white-space:nowrap}
ul.big{font-size:17px;line-height:1.75;margin-left:20px;max-width:1150px}
ul.big li{margin-bottom:14px}
.note{margin-top:14px;font-size:13.5px;color:#5a6478;background:#f2f6ff;border-left:4px solid var(--blue);border-radius:8px;padding:10px 14px}
.flow{display:flex;align-items:center;gap:10px;margin:10px 0 26px}
.fnode{background:var(--navy);color:#fff;border-radius:10px;padding:14px 20px;font-size:15px;font-weight:600;text-align:center;line-height:1.4}
.fnode .dim{color:#aab6d0;font-weight:400;font-size:12px}
.farr{font-size:22px;color:var(--blue);font-weight:800}
/* 구조 시각화 */
.structexplain{font-size:16px;line-height:1.7;background:#f6f9ff;border:1px solid var(--line);border-radius:10px;padding:12px 18px;margin-bottom:14px;max-width:1400px}
.structwrap{display:grid;grid-template-columns:1fr 150px 1fr;gap:10px;align-items:center;flex:1}
.tree{display:flex;flex-direction:column;margin-top:4px}
.tnode{border:1px solid var(--line);border-radius:8px;background:#fff;padding:5px 7px;font-size:11.5px;font-weight:700;color:var(--ink);text-align:center;line-height:1.3}
.tnode span{display:block;font-size:9.5px;font-weight:400;color:var(--dim);white-space:nowrap}
.tnode.tcamp{width:140px;margin:0 auto;background:var(--navy);color:#fff;border-color:var(--navy);letter-spacing:1px}
.tnode.tas{background:#eef4ff;border-color:#b9cdf2}
.tnode.tad{font-weight:600;background:#fafbfe}
.tnode.tmore{display:flex;align-items:center;justify-content:center;background:transparent;border:none;color:var(--dim);height:100%}
.tstem,.tstem2{width:2px;height:12px;background:#c3cbdb;margin:0 auto;flex:none}
.tbranches{display:flex;position:relative;padding-top:12px}
.tbranches::before{content:'';position:absolute;top:0;left:calc(50%/var(--n));right:calc(50%/var(--n));height:2px;background:#c3cbdb}
.tbranch{flex:1;min-width:0;position:relative;padding:0 3px;display:flex;flex-direction:column}
.tbranch::before{content:'';position:absolute;top:-12px;left:50%;margin-left:-1px;width:2px;height:12px;background:#c3cbdb}
tr.campsep td{background:var(--navy);color:#fff;font-weight:700;font-size:13px;padding:7px 10px}
.arrowcell{color:#3fa96b;font-weight:900;font-size:16px}
.structcol{display:flex;flex-direction:column;gap:14px}
.structcolh{font-size:14px;font-weight:800;letter-spacing:1.5px;color:var(--dim)}
.campbox{border:2px solid var(--line);border-radius:14px;padding:16px 18px;background:#fbfcff}
.campbox.tbox{border-color:#e8b93c;background:#fffdf4}
.campbox.pbox{border-color:#3fa96b;background:#f4fbf6}
.campname{font-weight:800;font-size:16px;color:var(--navy)}
.campmeta{font-size:12px;color:var(--dim);margin:4px 0 8px}
.campstats{font-size:14px;margin-bottom:10px}
.gradarrow{text-align:center}
.garr{font-size:52px;color:#3fa96b;font-weight:900;line-height:1}
.galabel{font-size:12.5px;color:var(--gt);font-weight:700;margin-top:6px;line-height:1.5}
.offarrow{font-size:13px;color:var(--rt);font-weight:700;padding:6px 0}
/* 리뷰 카드 (6개/장 · 3열×2행 · 썸네일 클릭=재생 모달) */
.rcards6{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:1fr 1fr;gap:14px;flex:1;min-height:0}
.rcards4{display:grid;grid-template-columns:repeat(2,1fr);grid-template-rows:1fr 1fr;gap:14px;flex:1;min-height:0}
.rcards2{display:grid;grid-template-columns:repeat(2,1fr);grid-auto-rows:330px;gap:14px}
.rc{display:flex;gap:12px;border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:#fbfcff;min-height:0}
.player{width:170px;border-radius:10px;overflow:hidden;position:relative;flex-shrink:0;background:#eef1f7}
.player[data-sc]{cursor:pointer}
.player img{width:100%;height:100%;object-fit:cover;display:block}
.phbox{display:flex;align-items:center;justify-content:center;height:100%;color:var(--dim);font-size:12px;text-align:center}
.playbtn{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:46px;height:46px;border-radius:50%;background:rgba(15,31,61,.75);color:#fff;font-size:18px;display:flex;align-items:center;justify-content:center;padding-left:4px}
.player[data-sc]:hover .playbtn{background:var(--blue)}
.rcinfo{flex:1;display:flex;flex-direction:column;gap:6px;min-width:0}
.rchead{font-size:15.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ridx{color:var(--blue);font-weight:800;font-size:14px;margin-right:2px}
.verdict{font-size:11px;border-radius:20px;padding:2px 10px;font-weight:700}
.verdict.keep{background:var(--g);color:var(--gt)}
.verdict.kill{background:var(--r);color:var(--rt)}
.verdict.watch{background:var(--y);color:#9a7b00}
.kmline2{font-size:12.5px;line-height:1.5}
.rmetrics4{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.rmetrics4 div{background:#fff;border:1px solid var(--line);border-radius:8px;padding:5px 4px;text-align:center}
.rmetrics4 i{display:block;font-style:normal;font-size:10px;color:var(--dim)}
.rmetrics4 b{font-size:13px}
.rmetrics4 .hl{background:var(--g);border-color:#bfe6cf}
.rstory2{font-size:14px;line-height:1.6;color:var(--ink);background:#f4f8ff;border-left:4px solid var(--blue);border-radius:6px;padding:8px 11px}
/* KM·훅 강조 칩 + 3S율 하이라이트 (세은 7/20 발표 — 가시성) */
.tagchips{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chipkm{background:var(--navy);color:#fff;font-size:13px;font-weight:700;padding:4px 10px;border-radius:7px;line-height:1.35}
.chipkm .dim{color:#bcd0f5;font-weight:600}
.chip3s{background:var(--blue);color:#fff;font-size:13px;font-weight:800;padding:4px 10px;border-radius:7px;line-height:1.35}
.rmetrics4 .hl3s{background:#e8f1fe;border-color:#9cc3ff}
.rmetrics4 i{font-size:10.5px}
.rmetrics4 b{font-size:14.5px}
/* 재생 모달 */
#vmodal{display:none;position:fixed;inset:0;background:rgba(10,16,30,.78);z-index:99;align-items:center;justify-content:center}
#vmodal.on{display:flex}
#vbox{position:relative}
#vframe{width:420px;height:780px;border:0;border-radius:14px;background:#fff}
#vclose{position:absolute;top:-36px;right:0;color:#fff;font-size:14px;cursor:pointer;font-weight:700}
.chart{display:flex;gap:18px;align-items:flex-end;flex:1;padding:20px 10px 0}
.bar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px}
.barfill{width:70%;background:linear-gradient(180deg,#4d94ff,var(--blue));border-radius:6px 6px 0 0}
.barv{font-size:13px;font-weight:700;color:var(--navy)}
.barl{font-size:12px;color:var(--dim);text-align:center;border-top:2px solid var(--line);padding-top:6px;width:100%}
.signals{display:grid;grid-template-columns:1fr 1fr;gap:22px;flex:1;align-content:start}
.sig{display:flex;gap:16px;background:#f8fafd;border:1px solid var(--line);border-radius:12px;padding:20px}
.signum{font-size:30px;font-weight:800;color:var(--blue)}
.sig b{font-size:17px;color:var(--navy)}
.sig p{font-size:14.5px;line-height:1.6;margin-top:6px}
ul.next{list-style:none;font-size:18px;line-height:1.7;max-width:1150px}
ul.next li{margin-bottom:22px;background:#f8fafd;border:1px solid var(--line);border-radius:12px;padding:18px 24px}
#nav{position:fixed;bottom:16px;right:24px;font-size:13px;color:var(--dim);background:#fff;border:1px solid var(--line);border-radius:20px;padding:5px 14px;z-index:9}
a{color:var(--blue);text-decoration:none}
@media print{section{display:flex!important;page-break-after:always;height:auto;min-height:100vh}#nav{display:none}}
</style></head><body>
__SLIDES__
<div id=nav></div>
<div id=vmodal><div id=vbox><div id=vclose>✕ 닫기 (Esc)</div><iframe id=vframe allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe></div></div>
<script>
const S=[...document.querySelectorAll('section')];let i=0;
const M=document.getElementById('vmodal'),F=document.getElementById('vframe');
function go(n){i=Math.max(0,Math.min(S.length-1,n));S.forEach((s,k)=>s.classList.toggle('on',k===i));
document.getElementById('nav').textContent=(i+1)+' / '+S.length;}
function openv(sc){F.src='https://www.instagram.com/reel/'+sc+'/embed/';M.classList.add('on');}
function closev(){M.classList.remove('on');F.src='';}
addEventListener('keydown',e=>{
if(e.key==='Escape'){closev();return;}
if(M.classList.contains('on'))return;
if(['ArrowRight','PageDown',' '].includes(e.key))go(i+1);
if(['ArrowLeft','PageUp'].includes(e.key))go(i-1);if(e.key==='Home')go(0);if(e.key==='End')go(S.length-1);});
addEventListener('click',e=>{
const pl=e.target.closest('.player[data-sc]');
if(pl){openv(pl.dataset.sc);return;}
if(e.target.closest('#vclose')||e.target===M){closev();return;}
if(M.classList.contains('on'))return;
if(!e.target.closest('a')&&!e.target.closest('table')&&!e.target.closest('#vmodal'))go(i+1);});
go(0);
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--collect", action="store_true", help="수집만 (렌더 X)")
    mode.add_argument("--render", action="store_true", help="기존 ssot.json 재사용 렌더만")
    ap.add_argument("--out", default=DEFAULT_DECK, help="덱 HTML 출력 경로")
    ap.add_argument("--ref-date", help="빌드 앵커일 YYYY-MM-DD (기본 오늘) — 과거 주 재빌드용. "
                                       "insights 창만 재현, live status·구조·태그는 현재 스냅샷")
    a = ap.parse_args()
    if a.ref_date:
        global REF_TODAY
        REF_TODAY = date.fromisoformat(a.ref_date)
        print(f"[ref-date] 앵커 {REF_TODAY} — status/구조는 현재 시점 근사")
    if a.render:
        if not SSOT_PATH.exists():
            sys.exit(f"[FATAL] {SSOT_PATH} 없음 — 먼저 수집 실행 (옵션 없이 실행)")
        ssot = json.loads(SSOT_PATH.read_text(encoding="utf-8"))
    else:
        ssot = collect()
        if a.collect:
            return
    render(ssot, a.out)


if __name__ == "__main__":
    main()
