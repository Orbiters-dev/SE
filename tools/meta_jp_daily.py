"""
Meta JP (Grosmimi) 광고 자동 분석 + Gmail 리포트.

Modes:
  1d  : 어제 1일 스냅샷 (캠페인별 + 광고 TOP5 + 알림)
  7d  : 최근 7일 트렌드 (일별 차트 + WoW + 광고 ranking)
  14d : 14일 진단 (학습단계 + 크리에이티브 분류 + Freq 매트릭스)

Usage:
  python tools/meta_jp_daily.py --mode 1d
  python tools/meta_jp_daily.py --mode 7d --no-send
  python tools/meta_jp_daily.py --mode 14d --to se.heo@orbiters.co.kr
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from env_loader import load_env  # noqa: E402

load_env()

TOKEN = os.getenv("META_JP_ACCESS_TOKEN")
ACCT = os.getenv("META_JP_AD_ACCOUNT_ID")
BASE = "https://graph.facebook.com/v18.0"

DEFAULT_TO = "se.heo@orbiters.co.kr"
TMP_DIR = ROOT / ".tmp" / "meta_jp_daily"
TMP_DIR.mkdir(parents=True, exist_ok=True)

CTR_BENCH = 1.71  # JP 6-24m mom benchmark
CTR_LOW = 1.0
FREQ_HIGH = 3.0
CPC_SPIKE_PCT = 30.0

# 5/15 KPI = 북극성 (고정). Off Rule 과 분리.
KPI_WL_CTR = 8.0    # 인플루언서 화이트리스팅 (PAID/GIFT) CTR 목표
KPI_IMG_CTR = 4.0   # 이미지 광고 (UNKNOWN) CTR 목표
KPI_CPC = 100       # CPC 목표 (₩)


def api_get(path, params=None):
    params = dict(params or {})
    params["access_token"] = TOKEN
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    out = []
    while True:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        out.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        req = urllib.request.Request(nxt)
    return out


def fetch(level, time_range=None, date_preset=None, with_daily=False):
    fields = [
        "campaign_id", "campaign_name", "adset_id", "adset_name",
        "ad_id", "ad_name", "spend", "impressions", "clicks",
        "ctr", "cpc", "cpm", "frequency", "reach", "actions",
    ]
    params = {
        "fields": ",".join(fields),
        "level": level,
        "limit": 500,
    }
    if with_daily:
        params["time_increment"] = 1
    if time_range:
        params["time_range"] = json.dumps(time_range)
    elif date_preset:
        params["date_preset"] = date_preset
    return api_get(f"{ACCT}/insights", params)


def extract_lpv(actions):
    """actions 리스트에서 landing_page_view 카운트 추출."""
    if not actions:
        return 0
    for a in actions:
        if a.get("action_type") == "landing_page_view":
            return to_float(a.get("value"))
    return 0


def build_post_url_map(ad_ids):
    """ad_id 리스트 → IG/FB 게시물 URL 매핑. Graph API batch."""
    if not ad_ids:
        return {}
    url_map = {}
    ids = list(set(ad_ids))
    for i in range(0, len(ids), 50):
        batch = ids[i:i+50]
        params = {
            "ids": ",".join(batch),
            "fields": "id,creative{instagram_permalink_url,effective_instagram_media_id}",
            "access_token": TOKEN,
        }
        try:
            qs = urllib.parse.urlencode(params)
            with urllib.request.urlopen(f"{BASE}/?{qs}", timeout=30) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            for ad_id, ad in d.items():
                cr = (ad or {}).get("creative") or {}
                perma = cr.get("instagram_permalink_url")
                if perma:
                    url_map[ad_id] = perma
                elif cr.get("effective_instagram_media_id"):
                    url_map[ad_id] = f"https://www.instagram.com/p/?media_id={cr['effective_instagram_media_id']}"
        except Exception as e:
            print(f"  [warn] post_url fetch failed: {e}", file=sys.stderr)
    return url_map


def to_float(v, default=0.0):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def fmt_won(v):
    return f"₩{int(round(to_float(v))):,}"


def fmt_pct(v):
    return f"{to_float(v):.2f}%"


def fmt_num(v, decimals=0):
    f = to_float(v)
    if decimals == 0:
        return f"{int(round(f)):,}"
    return f"{f:,.{decimals}f}"


def adset_stage(adset_name):
    """adset 이름에서 운영 stage 추출 (Testing / Proven / Other)."""
    n = (adset_name or "").lower()
    if "proven" in n:
        return "proven"
    if "testing" in n or "test" in n:
        return "testing"
    return "other"


def parse_paid_flag(ad_name):
    """ad_name에서 PAID/GIFT 라벨 추출. 끝 yymmdd 바로 앞에 박힌 형식.

    예: 'AD N | Stainless 300ml | komugiko | PAID | 20260424' → 'PAID'
        'AD D | PPSU 300ml | ichikuru_fufu | GIFT | 20260320' → 'GIFT'
        라벨 없으면 'UNKNOWN' (이미지 광고 등).
    """
    n = ad_name or ""
    if "| PAID |" in n:
        return "PAID"
    if "| GIFT |" in n:
        return "GIFT"
    return "UNKNOWN"


def calc_days_live(ad_name, ref_date):
    """ad_name 끝 8자리 (yymmdd) → launch_date → D+N 계산.

    예: 'AD G | ... | 20260303' + ref 2026-05-15 → 73 (D+73)
    파싱 실패 시 None 반환.
    """
    if not ad_name:
        return None
    tail = ad_name.strip().split("|")[-1].strip() if "|" in ad_name else ad_name.strip()[-8:]
    digits = "".join(c for c in tail if c.isdigit())[-8:]
    if len(digits) != 8:
        return None
    try:
        launch = datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None
    return (ref_date - launch).days


def lifecycle_stage(days_live):
    """D+N → lifecycle stage. 신생 / Testing / Proven 분류 (PDF 5장 룰)."""
    if days_live is None:
        return "unknown"
    if days_live < 7:
        return "newborn"
    if days_live < 15:
        return "testing"
    return "proven"


def calc_percentiles(values, ascending_is_better=False):
    """리스트의 P10/P20/P50/P80/P90 산출. 빈 리스트면 None 반환.

    ascending_is_better=True → CPC (낮을수록 좋음, P10이 best)
    ascending_is_better=False → CTR (높을수록 좋음, P90이 best)
    리턴은 항상 정렬 후 percentile 값.
    """
    vals = sorted([v for v in values if v is not None and v > 0])
    n = len(vals)
    if n == 0:
        return None
    def pct(p):
        idx = max(0, min(n - 1, int(round(p / 100 * (n - 1)))))
        return vals[idx]
    return {
        "p10": pct(10), "p20": pct(20), "p50": pct(50),
        "p80": pct(80), "p90": pct(90),
        "n": n,
    }


def off_rule_check(ad, pool_pcts, ref_date, sunset_days=60):
    """3축 Off Rule 평가 (5/15 재설계).

    축 1: 풀 P20 미달 + spend ≥ ₩30K  (메인 트리거 — Bottom 20%)
    축 2: D+sunset_days (60일) 도달  (시간 sunset — 자연 노화)
    축 3: Freq ≥ 3.0  (피로도, spend 무관)

    velocity (Proven D+15+ trailing 7d CTR delta < -15%)는 별도 함수에서 호출.

    리턴: {"off_recommend": bool, "triggers": [str, ...], "reason": str}
    """
    triggers = []
    spend = ad.get("spend", 0)
    ctr = ad.get("ctr", 0)
    freq = ad.get("freq", 0)
    days_live = ad.get("days_live")

    if freq >= 3.0:
        triggers.append(f"Freq {freq:.2f} ≥ 3.0 (피로도)")

    if pool_pcts and ctr > 0 and spend >= 30000:
        p20 = pool_pcts.get("p20")
        if p20 and ctr < p20:
            triggers.append(f"CTR {ctr:.2f}% < 풀 P20 ({p20:.2f}%) + spend ≥ ₩30K")

    if days_live is not None and days_live >= sunset_days:
        triggers.append(f"D+{days_live} ≥ D+{sunset_days} (시간 sunset)")

    return {
        "off_recommend": len(triggers) > 0,
        "triggers": triggers,
        "reason": " · ".join(triggers) if triggers else "",
    }


def best_worst_from_rows(ad_rows, min_impr=200, ref_date=None):
    """광고 단위 BEST/WORST TOP3 by CTR/CPC.

    추가 (5/15): paid_flag + days_live + lifecycle_stage 파싱.
    PAID/GIFT × Testing/Proven 4-way pool split + percentile 산출도 함께.
    """
    if ref_date is None:
        ref_date = date.today()
    ads = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < min_impr:
            continue
        lpv = extract_lpv(row.get("actions"))
        spend = to_float(row.get("spend"))
        ad_name = row.get("ad_name", "")
        days_live = calc_days_live(ad_name, ref_date)
        ads.append({
            "ad_id": row.get("ad_id", ""),
            "ad_name": ad_name,
            "campaign_name": row.get("campaign_name", ""),
            "adset_name": row.get("adset_name", ""),
            "stage": adset_stage(row.get("adset_name", "")),
            "paid_flag": parse_paid_flag(ad_name),
            "days_live": days_live,
            "lifecycle": lifecycle_stage(days_live),
            "spend": spend,
            "impressions": impr,
            "clicks": to_float(row.get("clicks")),
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
            "lpv": lpv,
            "cplpv": (spend / lpv) if lpv > 0 else 0,
        })
    ctr_pool = [a for a in ads if a["ctr"] > 0]
    cpc_pool = [a for a in ads if a["cpc"] > 0]

    # 4-way pool split: PAID/GIFT × Testing/Proven (newborn/unknown 제외)
    pools = {}
    for paid in ("PAID", "GIFT"):
        for lc in ("testing", "proven"):
            key = f"{paid}_{lc}"
            members = [a for a in ads if a["paid_flag"] == paid and a["lifecycle"] == lc]
            pools[key] = {
                "members": members,
                "ctr_pct": calc_percentiles([a["ctr"] for a in members]),
                "cpc_pct": calc_percentiles([a["cpc"] for a in members], ascending_is_better=True),
                "cplpv_pct": calc_percentiles([a["cplpv"] for a in members], ascending_is_better=True),
            }

    # 풀이 작을 때(≤6) BEST·WORST 겹침 방지 — BEST 먼저 뽑고 WORST는 BEST 제외 후 N개.
    # 풀 크기에 따라 N 동적 조정 (6→3, 5→2, 4→2, 3→1, ≤2→0).
    def _split(pool, key, reverse_best):
        n = min(3, len(pool) // 2)
        if n == 0:
            return [], []
        best = sorted(pool, key=lambda x: x[key], reverse=reverse_best)[:n]
        best_ids = {id(a) for a in best}
        worst = [a for a in sorted(pool, key=lambda x: x[key], reverse=not reverse_best) if id(a) not in best_ids][:n]
        return best, worst

    ctr_best, ctr_worst = _split(ctr_pool, "ctr", reverse_best=True)
    cpc_best, cpc_worst = _split(cpc_pool, "cpc", reverse_best=False)

    return {
        "ctr_best": ctr_best,
        "ctr_worst": ctr_worst,
        "cpc_best": cpc_best,
        "cpc_worst": cpc_worst,
        "all_ads": ads,
        "pools": pools,
    }


def budget_increase_candidates(ads, min_spend=30000):
    """예산 증액 후보: 계정 평균 대비 효율 좋고 학습단계 통과한 ad."""
    if not ads:
        return []
    # 5/15: 신생(D+7 미만) + sunset(D+60+) 광고는 증액 후보에서 제외 (Off Rule 일관성)
    def _stage_ok(a):
        dl = a.get("days_live")
        if dl is None:
            return True  # 라벨 없는 이미지 광고는 통과
        return 7 <= dl < 60
    qualified = [a for a in ads if a["spend"] >= min_spend and a["lpv"] > 0 and a["ctr"] > 0 and a["freq"] <= 3.0 and _stage_ok(a)]
    if not qualified:
        return []
    avg_cplpv = sum(a["cplpv"] for a in qualified) / len(qualified)
    avg_ctr   = sum(a["ctr"] for a in qualified) / len(qualified)
    candidates = []
    for a in qualified:
        cplpv_ratio = a["cplpv"] / avg_cplpv if avg_cplpv > 0 else 1
        ctr_ratio = a["ctr"] / avg_ctr if avg_ctr > 0 else 1
        if cplpv_ratio <= 0.85 and ctr_ratio >= 1.1:
            improvement = (1 - cplpv_ratio) * 100
            if improvement >= 50: bump = 30
            elif improvement >= 20: bump = 20
            elif improvement >= 15: bump = 10
            else: bump = 10
            candidates.append({**a,
                "cplpv_ratio": cplpv_ratio, "ctr_ratio": ctr_ratio,
                "bump_pct": bump, "avg_cplpv": avg_cplpv, "avg_ctr": avg_ctr})
    return sorted(candidates, key=lambda x: x["cplpv_ratio"])[:5]


def build_advice_1d(d):
    """1d 운용 조언 — 판단·근거·배경 3축."""
    tips = []
    t = d["total"]
    ctr = t["ctr"]
    if ctr >= CTR_BENCH * 1.5:
        tips.append({
            "action": "현재 운용 유지 + 예산 점진 증액 (20% 이내)",
            "evidence": f"전체 CTR {ctr:.2f}% (벤치 {CTR_BENCH}% × 1.5 이상)",
            "context": "벤치는 전 산업 평균. 1.5배 이상은 소재·타겟 정합성 우수 신호. 단 1회 ≤20% 증액이 Meta 학습 단계 보호 가이드.",
        })
    elif ctr < CTR_LOW:
        tips.append({
            "action": "WORST 광고 즉시 일시정지 + BEST 광고 변형 추가",
            "evidence": f"전체 CTR {ctr:.2f}% (임계 {CTR_LOW}% 미달)",
            "context": "CTR 저조 = 소재 매력도 부족. 같은 소재로 예산 늘려도 효율 X. WORST 정지 + BEST 변형으로 신규 학습 진입.",
        })
    if d["delta"]["cpc_pct"] > 30:
        tips.append({
            "action": "예산·타겟 변경 24h 동결",
            "evidence": f"CPC 전일 +{d['delta']['cpc_pct']:.1f}% 급등",
            "context": "학습 재진입 진행 중일 때 변경 시 학습 reset → 효율 추가 하락. 24h 안정화 후 재진단 안전.",
        })
    if d["delta"]["spend_pct"] > 50:
        tips.append({
            "action": "일별 cap 재설정 검토",
            "evidence": f"Spend 전일 +{d['delta']['spend_pct']:.1f}% 급증",
            "context": "캠페인 cap 도달 또는 입찰 자동 조정. cap 미설정 시 야간 trafic 폭주로 단가 무너질 수 있음.",
        })
    bw = d.get("best_worst", {})
    if bw.get("ctr_best") and bw.get("ctr_worst"):
        b = bw["ctr_best"][0]["ctr"]
        w = bw["ctr_worst"][0]["ctr"]
        if b > 0 and w > 0 and b > w * 3:
            tips.append({
                "action": "WORST 3개 즉시 정지 + BEST 소재 카피·앵글 변형 3개 투입",
                "evidence": f"BEST/WORST CTR 격차 3배 이상 ({b:.2f}% vs {w:.2f}%)",
                "context": "ad 단위 격차는 학습 알고리즘이 자동 정리 X (CBO도 ad set까지만 재분배). 직접 정리 + BEST 변형으로 학습 풀 확대.",
            })
    if not tips:
        tips.append({
            "action": "현재 운용 유지, 7일 추세 누적 후 재평가",
            "evidence": "모든 지표 임계 통과 (CTR/CPC/Freq/격차 정상)",
            "context": "데이터 부족 상태에서 변경은 Meta 학습 재진입 유발 → 효율 일시 하락. 변경 X가 안전.",
        })
    return tips


def build_advice_7d(d):
    tips = []
    w = d["wow"]
    if w["spend_pct"] > 30 and w["ctr_pct"] < -10:
        tips.append({
            "action": "예산 원복 + 소재 교체",
            "evidence": f"Spend WoW +{w['spend_pct']:.0f}% / CTR WoW {w['ctr_pct']:.0f}%",
            "context": "예산 늘렸는데 CTR 하락 = 신규 도달층이 기존 소재에 반응 X. 예산만 늘리면 더 넓은 비관심층에 노출 → 효율 추가 악화. 소재 변경이 정답.",
        })
    elif w["spend_pct"] > 30 and w["ctr_pct"] >= 0:
        tips.append({
            "action": "추가 +20% 증액 실행",
            "evidence": f"Spend WoW +{w['spend_pct']:.0f}% / CTR {w['ctr_pct']:+.0f}% (안정)",
            "context": "증액 후 CTR 유지 = 신규 도달층도 기존 소재 매력 인정. 학습 알고리즘 안정 → 1회 ≤20% 범위 내 추가 증액 (Meta 학습 보호선).",
        })
    if w["cpc_pct"] > 20:
        tips.append({
            "action": "오디언스 만료 후 신규 LAL/Interest 추가",
            "evidence": f"CPC WoW +{w['cpc_pct']:.0f}% 상승",
            "context": "동일 오디언스 반복 노출 → 경매 경쟁 ↑ + 소재 피로 → CPC 상승. 신규 오디언스 풀로 입찰 경쟁 분산.",
        })

    spends = [x["spend"] for x in d["daily_trend"]]
    if spends and sum(spends) > 0:
        avg = sum(spends) / len(spends)
        std_pct = ((max(spends) - min(spends)) / avg * 100) if avg else 0
        if std_pct > 80:
            tips.append({
                "action": "CBO 권장 + 일별 cap 균등화",
                "evidence": f"일별 spend 변동폭 ±{std_pct:.0f}%",
                "context": "변동폭 80%+ = 학습 algorithm이 매일 다른 데이터로 학습 → 학습 단계 못 빠져나감. CBO + cap으로 균등 분배 시 학습 안정.",
            })

    bw = d.get("best_worst", {})
    if bw.get("ctr_worst"):
        worst = bw["ctr_worst"]
        spend_loss = sum(a["spend"] for a in worst)
        if spend_loss > 0 and worst:
            ctr_lo = min(a["ctr"] for a in worst)
            ctr_hi = max(a["ctr"] for a in worst)
            tips.append({
                "action": "WORST 광고 즉시 정지 + BEST 컨셉 변형 3종 투입",
                "evidence": f"WORST 3 CTR {ctr_lo:.2f}~{ctr_hi:.2f}% / 7일 누적 spend {fmt_won(spend_loss)}",
                "context": "7일 누적해도 효율 회복 X = 소재 자체 한계. 잔존 예산도 비효율 누적되니 즉시 정지가 ROI 보호.",
            })

    camps = d.get("campaigns", [])
    if len(camps) >= 2:
        camps_sorted = sorted(camps, key=lambda x: x["ctr"], reverse=True)
        top, bot = camps_sorted[0], camps_sorted[-1]
        if top["ctr"] > 0 and bot["ctr"] > 0 and top["ctr"] > bot["ctr"] * 2:
            tips.append({
                "action": f"저성과 캠페인 ({bot['name'][:30]}) 예산 30% 삭감 → 고성과 ({top['name'][:30]})로 이전",
                "evidence": f"캠페인 CTR 격차 2배+ ({top['ctr']:.2f}% vs {bot['ctr']:.2f}%)",
                "context": "캠페인 단위 격차는 CBO도 자동 분배 X (캠페인 간은 수동). 예산 이동 시 고성과 캠페인 학습 풀 확대 효과.",
            })

    if not tips:
        tips.append({
            "action": "현재 운용 유지, 14일 진단까지 변경 X",
            "evidence": "WoW 변동폭 정상 + 캠페인/광고 격차 임계 미만",
            "context": "주간 안정 = 학습 단계 통과. 변경은 학습 재진입 유발 → 안정성 손실. 14일 누적 후 종합 진단이 안전.",
        })
    return tips


def build_advice_14d(d):
    tips = []
    learning = d.get("learning", [])
    stable = [x for x in learning if x["stability"] == "안정"]
    learning_only = [x for x in learning if x["stability"] == "학습중"]
    if learning_only and not stable:
        tips.append({
            "action": "예산·소재·타겟 변경 7일간 동결",
            "evidence": "전 캠페인 학습 단계 (안정 0개)",
            "context": "Meta 학습 종료 조건: 주 50건 전환 또는 CPC 변동 ±30% 이내. 학습중 변경 시 reset → 효율 일시 추락. 인내가 정답.",
        })
    elif stable and learning_only:
        tips.append({
            "action": "학습중 캠페인 변경 X / 안정 캠페인부터 점진 증액",
            "evidence": f"안정 {len(stable)}개 / 학습중 {len(learning_only)}개",
            "context": "안정 = 학습 통과 → 증액 안전 윈도우. 학습중 = 데이터 부족 → 변경 시 학습 리셋 발생. 둘 분리 운영이 알고리즘 친화적.",
        })

    cc = d.get("creative_class", {})
    img = cc.get("image")
    vid = cc.get("video")
    wl = cc.get("wl")
    if img and vid:
        if vid["ctr"] > img["ctr"] * 1.3:
            tips.append({
                "action": "영상 슬롯 비중 60%+ 확대 + 이미지는 hook 컷 위주로 재구성",
                "evidence": f"영상 CTR {vid['ctr']:.2f}% vs 이미지 {img['ctr']:.2f}% (1.3배+)",
                "context": "영상은 정보량·감정 환기 ↑ → 클릭 의지 자극. Meta 알고리즘도 영상 노출 가중치 부여. 이미지는 hook (첫 1초) 강화로 보완.",
            })
        elif img["ctr"] > vid["ctr"] * 1.3:
            tips.append({
                "action": "이미지 변형 5종 추가 + 영상은 컷 길이·썸네일 재테스트",
                "evidence": f"이미지 CTR {img['ctr']:.2f}% vs 영상 {vid['ctr']:.2f}% (1.3배+)",
                "context": "이미지가 영상보다 효율 = 모바일 피드에서 빠른 메시지 전달이 통함. 영상은 첫 3초·썸네일이 약점.",
            })
    if wl and (img or vid):
        ref_ctr = max((cc[k]["ctr"] for k in ("image", "video") if cc.get(k)), default=0)
        if ref_ctr > 0 and wl["ctr"] > ref_ctr * 1.2:
            tips.append({
                "action": "WL 광고 비중 확대 + Use existing post 추가 협업 발굴",
                "evidence": f"WL CTR {wl['ctr']:.2f}% / 자체 소재 대비 +{(wl['ctr']/ref_ctr-1)*100:.0f}%",
                "context": "WL = 인플루언서 신뢰도 + 자연스러운 톤 → 광고 인식 ↓ + 클릭 ↑. 단 WL 풀이 좁으면 fatigue 빠르게 옴 (피로도 모니터 필요).",
            })

    fatigue = d.get("fatigue", [])
    if len(fatigue) >= 3:
        spend = sum(f["spend"] for f in fatigue)
        tips.append({
            "action": "피로도 광고 즉시 정지 + 신규 소재 동수 투입",
            "evidence": f"피로도 경고 {len(fatigue)}개 (14일 누적 spend {fmt_won(spend)})",
            "context": "Freq>3.0 또는 Freq>2.0+CTR<1% = 같은 사람한테 반복 노출되어 클릭 안 함. 잔존 예산은 비효율 누적만 야기. 신규 소재로 학습 풀 갱신 필수.",
        })

    bw = d.get("best_worst", {})
    if bw.get("ctr_best") and bw.get("ctr_worst"):
        b = bw["ctr_best"][0]
        w = bw["ctr_worst"][0]
        if b["ctr"] > 0 and w["ctr"] > 0 and b["ctr"] > w["ctr"] * 4:
            tips.append({
                "action": f"BEST '{b['ad_name'][:30]}' 컨셉 변형 5종 추가 + WORST 3개 영구 폐기",
                "evidence": f"광고 CTR 격차 4배+ ({b['ctr']:.2f}% vs {w['ctr']:.2f}%)",
                "context": "14일 누적 4배 격차 = WORST 회복 불가 (단순 학습 미통과 X). BEST 컨셉이 명확한 winner → 변형으로 풀 확대가 효율 정답.",
            })

    if not tips:
        tips.append({
            "action": "현재 운용 유지 + 신규 소재 정기 투입 (주 3개)",
            "evidence": "14일 진단상 즉시 액션 항목 없음",
            "context": "안정기 진입 = 효율 양호. 그러나 같은 소재 장기 운영 시 fatigue 누적 → 주 3개 신규 소재 투입으로 풀 회전 필요.",
        })
    return tips


def render_advice_section(tips, header="메타몽 운용 조언"):
    cards = []
    for i, t in enumerate(tips, 1):
        if isinstance(t, str):
            cards.append(f'<div style="margin:10px 0;padding:10px 14px;background:#fff;border-left:3px solid #2563eb;border-radius:3px;">{t}</div>')
            continue
        cards.append(
            f'<div style="margin:12px 0;padding:12px 16px;background:#fff;border-left:3px solid #2563eb;border-radius:3px;">'
            f'<p style="margin:0 0 6px;"><b>판단 {i}.</b> {t.get("action","")}</p>'
            f'<p class=meta style="margin:4px 0;"><b>근거</b> · {t.get("evidence","")}</p>'
            f'<p class=meta style="margin:4px 0;"><b>배경</b> · {t.get("context","")}</p>'
            f'</div>'
        )
    return f"""
<h2>{header}</h2>
<div style="background:#eff6ff;padding:14px 18px;border-radius:4px;">
  {''.join(cards)}
  <p class=meta style="margin:10px 0 0;">룰 기반 자동 생성. 최종 의사결정은 세은 직접.</p>
</div>
"""


def build_findings(d, ref_date=None):
    """오늘의 발견 — 4-way 풀 + Off Rule + S 후보 + 신생 동결 (5/15 재설계).

    축:
      1) Off 권장 (off_rule_check 트리거 hit): 풀 P20 미달 + spend ≥ ₩30K, Freq ≥ 3, D+60 sunset
      2) S 후보 (Top 10%, Proven 풀만): 풀 P90 이상 → 증액 우선
      3) 신생 동결 (D+7 미만): 변경·증액 금지 안내
      4) delta 알림 (전체 CTR/CPC 급변): 기존 유지
    우선순위: Off > S 후보 > 신생 > delta. 상위 3개만 반환.
    """
    if ref_date is None:
        ref_date = date.today()
    findings = []
    bw = d.get("best_worst", {})
    all_ads = bw.get("all_ads", [])
    pools = bw.get("pools", {})
    if not all_ads:
        return findings

    off_cards, s_cards = [], []

    for paid in ("PAID", "GIFT"):
        for lc in ("testing", "proven"):
            key = f"{paid}_{lc}"
            pool = pools.get(key, {})
            members = pool.get("members", [])
            if not members:
                continue
            ctr_pct = pool.get("ctr_pct")
            pool_label = f"{paid}×{lc.capitalize()}"
            paid_strict = (paid == "PAID")  # PAID는 더 strict 해석

            # 1) Off 권장 — off_rule_check 적용
            for a in members:
                check = off_rule_check(a, ctr_pct, ref_date)
                if not check["off_recommend"]:
                    continue
                ad_short = a["ad_name"][:40]
                ctx = (
                    "PAID 풀 — 회수 압력 큼 → P20 + spend ≥ ₩30K 만으로도 Off 충분."
                    if paid_strict else
                    "GIFT 풀 — 비용 회수 압력 약함 → 즉시 Off 보단 신규 변형 우선 검토."
                )
                off_cards.append({
                    "_sort_spend": a.get("spend", 0),
                    "_ad_id": a.get("ad_id", ""),
                    "finding": f"<b>{ad_short}</b> <span style=\"color:#6b7280;font-size:13px;\">[{pool_label}]</span> Off 검토 — {check['reason']}",
                    "evidence": f"CTR {a['ctr']:.2f}% · CPC {fmt_won(a['cpc'])} · Freq {a.get('freq',0):.2f} · spend {fmt_won(a.get('spend',0))} · D+{a.get('days_live','?')}",
                    "context": ctx,
                })

            # 2) S 후보 — Proven 풀 P90 이상 (Top 10%) + spend ≥ ₩30K + 풀 n ≥ 6 (percentile 의미 보장)
            #    Off 트리거 hit 광고는 제외 (sunset/Freq/P20 hit 시 증액 권장 모순 방지)
            if lc == "proven" and ctr_pct and ctr_pct.get("p90") and ctr_pct.get("n", 0) >= 6:
                p90 = ctr_pct["p90"]
                off_ad_ids = {c["_ad_id"] for c in off_cards if c.get("_ad_id")}
                for a in members:
                    if a.get("ad_id") in off_ad_ids:
                        continue
                    if a["ctr"] >= p90 and a.get("spend", 0) >= 30000:
                        ad_short = a["ad_name"][:40]
                        ctx = (
                            "PAID Proven 풀 Top 10% — 회수 검증된 winner. 증액 1회 ≤30% (Meta 학습 보호선)."
                            if paid_strict else
                            "GIFT Proven 풀 Top 10% — 무료 수급 winner. 증액 대신 PAID 풀로 캐스팅 우선 검토."
                        )
                        s_cards.append({
                            "_sort_spend": a.get("spend", 0),
                            "finding": f"<b>{ad_short}</b> <span style=\"color:#6b7280;font-size:13px;\">[{pool_label} P90+]</span> S 후보 — 증액 우선순위",
                            "evidence": f"CTR {a['ctr']:.2f}% (풀 P90 {p90:.2f}% 이상) · spend {fmt_won(a['spend'])} · D+{a.get('days_live','?')}",
                            "context": ctx,
                        })

    # 3) velocity 하락 (B-6) — 7d 모드에서 채워짐. Off hit 광고는 제외.
    vel_cards = []
    off_ad_ids = {c["_ad_id"] for c in off_cards if c.get("_ad_id")}
    for v in bw.get("velocity_decay", []):
        if v.get("ad_id") in off_ad_ids:
            continue
        ad_short = v["ad_name"][:40]
        paid = v.get("paid_flag", "")
        ctx = (
            "PAID Proven 풀 7d CTR 하락 = 소재 피로 자연 진행. 즉시 Off 보단 신규 변형 투입 우선."
            if paid == "PAID" else
            "GIFT Proven 풀 7d CTR 하락 = 자연 진행. 신규 변형 의뢰 or 다음 협업 우선순위 조정."
        )
        vel_cards.append({
            "_sort_spend": v.get("spend", 0),
            "finding": f"<b>{ad_short}</b> <span style=\"color:#6b7280;font-size:13px;\">[{paid}×Proven velocity]</span> CTR 하락 — 신규 변형 검토",
            "evidence": f"CTR 이전7d {v['prev_ctr']:.2f}% → 최근7d {v['cur_ctr']:.2f}% ({v['delta_pct']:+.1f}%) · D+{v.get('days_live','?')} · spend {fmt_won(v.get('spend',0))}",
            "context": ctx,
        })

    off_cards.sort(key=lambda x: -x["_sort_spend"])
    s_cards.sort(key=lambda x: -x["_sort_spend"])
    vel_cards.sort(key=lambda x: -x["_sort_spend"])
    for c in off_cards + s_cards + vel_cards:
        c.pop("_sort_spend", None)
        c.pop("_ad_id", None)
        findings.append(c)

    # 4) 신생 (D+7 미만) — 변경·증액 동결 안내. spend 있는 광고만.
    newborn_ads = [a for a in all_ads if a.get("lifecycle") == "newborn" and a.get("spend", 0) > 0]
    if newborn_ads:
        names = ", ".join(a["ad_name"][:25] for a in newborn_ads[:3])
        more = f" 외 {len(newborn_ads)-3}건" if len(newborn_ads) > 3 else ""
        findings.append({
            "finding": f"신생 풀 {len(newborn_ads)}건 동결 안내 — D+7까지 변경·증액 금지",
            "evidence": f"{names}{more}",
            "context": "D+7 미만 = Meta 학습 초기. 노출 누적 전 변경·증액·OFF 시 학습 리셋 → 단가 폭증. 노출 ≥1,000 + D+7 도달 후 재진단.",
        })

    # 5) delta 알림 (전체 CTR/CPC 급변) — 기존 유지
    if d.get("delta"):
        delta = d["delta"]
        if delta.get("ctr_pct", 0) <= -15 and abs(delta.get("spend_pct", 0)) < 20:
            findings.append({
                "finding": "전체 CTR 급락, spend는 안정 — 오디언스/소재 피로 신호",
                "evidence": f"CTR 전일 {delta['ctr_pct']:.1f}% / spend ±{abs(delta['spend_pct']):.0f}%",
                "context": "spend 안정 + CTR만 하락 = 입찰·예산 변경 X = 오디언스 피로 또는 소재 피로. 캠페인 단위 점검 필요.",
            })
        elif delta.get("cpc_pct", 0) >= 30:
            findings.append({
                "finding": "전체 CPC 급등 — 학습 재진입 또는 경매 경쟁",
                "evidence": f"CPC 전일 +{delta['cpc_pct']:.1f}%",
                "context": "단발적 변동은 경매 경쟁(다른 광고주 입찰 ↑)에서 발생. 변경 시 학습 리셋 → 24h 동결 후 재관찰.",
            })

    return findings[:3]


def render_findings_section(findings):
    if not findings:
        return """
<h2>오늘의 발견</h2>
<div style="background:#fefce8;padding:14px 18px;border-radius:4px;">
  <p class=meta style="margin:6px 0;">특이 신호 없음. peer 격차·피로도·트렌드 변화 모두 정상 범위.</p>
</div>
"""
    cards = []
    for i, f in enumerate(findings, 1):
        if isinstance(f, str):
            cards.append(f'<div style="margin:10px 0;padding:10px 14px;background:#fff;border-left:3px solid #eab308;border-radius:3px;">{f}</div>')
            continue
        cards.append(
            f'<div style="margin:12px 0;padding:12px 16px;background:#fff;border-left:3px solid #eab308;border-radius:3px;">'
            f'<p style="margin:0 0 6px;"><b>발견 {i}.</b> {f.get("finding","")}</p>'
            f'<p class=meta style="margin:4px 0;"><b>근거</b> · {f.get("evidence","")}</p>'
            f'<p class=meta style="margin:4px 0;"><b>배경</b> · {f.get("context","")}</p>'
            f'</div>'
        )
    return f"""
<h2>오늘의 발견</h2>
<div style="background:#fefce8;padding:14px 18px;border-radius:4px;">
  {''.join(cards)}
  <p class=meta style="margin:10px 0 0;">peer 격차 / 학습 단계 / 트렌드 변화. 매일 1~3개. 누적되면 세은 기준 후보 발굴 재료.</p>
</div>
"""


def post_link_cell(post_url):
    if post_url and post_url.startswith("https://www.instagram.com/") and "?media_id=" not in post_url:
        return f'<td class=c><a href="{post_url}">view</a></td>'
    return '<td class=c>—</td>'


def render_kpi_counter(all_ads):
    """KPI 북극성 카운터 (5/15) — 달성/미달 카운트만. 평균 X (Off Rule과 분리)."""
    if not all_ads:
        return ""
    wl_ads = [a for a in all_ads if a.get("paid_flag") in ("PAID", "GIFT") and a.get("ctr", 0) > 0]
    img_ads = [a for a in all_ads if a.get("paid_flag") == "UNKNOWN" and a.get("ctr", 0) > 0]
    cpc_ads = [a for a in all_ads if a.get("cpc", 0) > 0]

    wl_hit = sum(1 for a in wl_ads if a["ctr"] >= KPI_WL_CTR)
    img_hit = sum(1 for a in img_ads if a["ctr"] >= KPI_IMG_CTR)
    cpc_hit = sum(1 for a in cpc_ads if a["cpc"] <= KPI_CPC)

    def row(label, hit, total):
        miss = total - hit
        if total == 0:
            return f"<tr><td class=l>{label}</td><td colspan=3 class=meta>해당 광고 없음</td></tr>"
        rate = hit / total * 100
        return (
            f"<tr><td class=l>{label}</td>"
            f"<td><b style='color:#16a34a'>{hit}</b></td>"
            f"<td><b style='color:#dc2626'>{miss}</b></td>"
            f"<td>{hit}/{total} ({rate:.0f}%)</td></tr>"
        )

    return f"""
<h2>KPI 달성 카운터 (북극성)</h2>
<table>
  <tr><th>KPI</th><th>달성</th><th>미달</th><th>비율</th></tr>
  {row(f"WL CTR ≥ {KPI_WL_CTR}% (PAID + GIFT)", wl_hit, len(wl_ads))}
  {row(f"이미지 CTR ≥ {KPI_IMG_CTR}% (이미지 광고)", img_hit, len(img_ads))}
  {row(f"CPC ≤ ₩{KPI_CPC}", cpc_hit, len(cpc_ads))}
</table>
<p class=meta>KPI = 북극성 목표 (고정). Off Rule (작동 임계) 과 분리. 평균값 비교 X.</p>
"""


def render_off_recommend_box(bw, ref_date=None):
    """Off 권장 일람표 (5/15) — Off Rule 트리거 hit 광고 전체."""
    if ref_date is None:
        ref_date = date.today()
    pools = bw.get("pools", {})
    if not pools:
        return ""
    candidates = []
    for paid in ("PAID", "GIFT"):
        for lc in ("testing", "proven"):
            pool = pools.get(f"{paid}_{lc}", {})
            members = pool.get("members", [])
            ctr_pct = pool.get("ctr_pct")
            for a in members:
                check = off_rule_check(a, ctr_pct, ref_date)
                if check["off_recommend"]:
                    candidates.append({
                        "ad_name": a["ad_name"],
                        "pool": f"{paid}×{lc.capitalize()}",
                        "ctr": a["ctr"], "cpc": a["cpc"], "freq": a.get("freq", 0),
                        "spend": a.get("spend", 0), "days_live": a.get("days_live"),
                        "reason": check["reason"],
                    })
    if not candidates:
        return """
<h2>Off 권장 (Off Rule 트리거)</h2>
<div style="background:#ecfdf5;padding:14px 18px;border-radius:4px;">
  <p class=meta style="margin:6px 0;">Off 권장 광고 없음. 풀 전체 임계 통과.</p>
</div>
"""
    candidates.sort(key=lambda x: -x["spend"])
    rows = "".join(
        f"<tr><td class=l>{c['ad_name'][:55]}</td><td>{c['pool']}</td>"
        f"<td>{fmt_pct(c['ctr'])}</td><td>{fmt_won(c['cpc'])}</td>"
        f"<td>{c['freq']:.2f}</td><td>{fmt_won(c['spend'])}</td>"
        f"<td>D+{c['days_live'] if c['days_live'] is not None else '?'}</td>"
        f"<td class=l style='font-size:13px'>{c['reason']}</td></tr>"
        for c in candidates
    )
    return f"""
<h2>Off 권장 (Off Rule 트리거 {len(candidates)}건)</h2>
<table>
  <tr><th>광고</th><th>풀</th><th>CTR</th><th>CPC</th><th>Freq</th><th>Spend</th><th>D+N</th><th>트리거</th></tr>
  {rows}
</table>
<p class=meta>축: 풀 P20 미달+spend≥₩30K / Freq≥3.0 / D+60 sunset. PAID는 즉시 Off, GIFT는 신규 변형 우선.</p>
"""


def render_best_worst_table(bw, post_url_map=None):
    post_url_map = post_url_map or {}
    def rows(items):
        if not items:
            return f"<tr><td colspan=7 class=meta>데이터 부족</td></tr>"
        out = []
        for a in items:
            url = post_url_map.get(a.get("ad_id", ""), "")
            out.append(
                f"<tr><td class=l>{a['ad_name'][:55]}</td><td>{fmt_pct(a['ctr'])}</td>"
                f"<td>{fmt_won(a['cpc'])}</td><td>{a.get('freq', 0):.2f}</td>"
                f"<td>{fmt_won(a['spend'])}</td><td>{fmt_num(a['impressions'])}</td>"
                f"{post_link_cell(url)}</tr>"
            )
        return "".join(out)
    head = "<tr><th>광고</th><th>CTR</th><th>CPC</th><th>Freq</th><th>Spend</th><th>Impr</th><th>게시물</th></tr>"
    return f"""
<h2>광고 BEST / WORST</h2>
<table>
  <tr><th colspan=7 style="background:#dcfce7;color:#065f46">▲ CTR BEST 3 (높은 순)</th></tr>
  {head}
  {rows(bw['ctr_best'])}
  <tr><th colspan=7 style="background:#fee2e2;color:#991b1b">▼ CTR WORST 3 (낮은 순)</th></tr>
  {head}
  {rows(bw['ctr_worst'])}
  <tr><th colspan=7 style="background:#dcfce7;color:#065f46">▲ CPC BEST 3 (낮은 순 = 효율)</th></tr>
  {head}
  {rows(bw['cpc_best'])}
  <tr><th colspan=7 style="background:#fee2e2;color:#991b1b">▼ CPC WORST 3 (높은 순)</th></tr>
  {head}
  {rows(bw['cpc_worst'])}
</table>
<p class=meta>최소 노출수 필터: 1d≥100 / 7d≥200 / 14d≥500</p>
"""


def render_budget_increase_table(candidates, post_url_map=None):
    post_url_map = post_url_map or {}
    if not candidates:
        return """
<h2>예산 증액 후보</h2>
<div class=meta>해당 기간 학습단계 통과 + 효율 우수 ad 없음 (조건: spend ≥ ₩30,000, freq ≤ 3.0, CPLPV ≤ 평균×0.85, CTR ≥ 평균×1.1).</div>
"""
    rows_html = []
    for a in candidates:
        url = post_url_map.get(a.get("ad_id", ""), "")
        rows_html.append(
            f"<tr><td class=l>{a['ad_name'][:55]}</td>"
            f"<td>{fmt_won(a['spend'])}</td>"
            f"<td>{fmt_won(a['cplpv'])} ({(a['cplpv_ratio']-1)*100:+.0f}%)</td>"
            f"<td>{fmt_pct(a['ctr'])} ({(a['ctr_ratio']-1)*100:+.0f}%)</td>"
            f"<td>{a['freq']:.2f}</td>"
            f"<td><b>+{a['bump_pct']}%</b></td>"
            f"{post_link_cell(url)}</tr>"
        )
    return f"""
<h2>예산 증액 후보</h2>
<table>
  <tr><th>광고</th><th>Spend</th><th>CPLPV (vs 평균)</th><th>CTR (vs 평균)</th><th>Freq</th><th>추천 증액</th><th>게시물</th></tr>
  {''.join(rows_html)}
</table>
<p class=meta>기준: 학습단계 통과(spend≥₩30,000) + Freq≤3.0 + CPLPV ≤ 평균×0.85 + CTR ≥ 평균×1.1. 증액 폭은 1회 ≤30% (Meta 학습 단계 보호).</p>
"""


# ============================================================
# 1d Analysis
# ============================================================
def analyze_1d(target_date):
    yday = target_date
    dby = target_date - timedelta(days=1)
    cur = fetch("ad", time_range={"since": yday.isoformat(), "until": yday.isoformat()})
    prev = fetch("ad", time_range={"since": dby.isoformat(), "until": dby.isoformat()})

    by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "freq_sum": 0, "n": 0})
    for row in cur:
        c = by_camp[row.get("campaign_name", "(unknown)")]
        c["spend"] += to_float(row.get("spend"))
        c["impressions"] += to_float(row.get("impressions"))
        c["clicks"] += to_float(row.get("clicks"))
        c["reach"] += to_float(row.get("reach"))
        c["freq_sum"] += to_float(row.get("frequency"))
        c["n"] += 1

    camp_rows = []
    for name, v in by_camp.items():
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        freq = (v["freq_sum"] / v["n"]) if v["n"] else 0
        camp_rows.append({
            "name": name, "spend": v["spend"], "impressions": v["impressions"],
            "clicks": v["clicks"], "ctr": ctr, "cpc": cpc, "freq": freq, "reach": v["reach"],
        })
    camp_rows.sort(key=lambda x: x["spend"], reverse=True)

    ad_rows = []
    for row in cur:
        impr = to_float(row.get("impressions"))
        clicks = to_float(row.get("clicks"))
        if impr < 100:
            continue
        ad_rows.append({
            "ad_name": row.get("ad_name", ""),
            "campaign_name": row.get("campaign_name", ""),
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "clicks": clicks,
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    top5 = sorted(ad_rows, key=lambda x: x["ctr"], reverse=True)[:5]

    prev_by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0})
    for row in prev:
        p = prev_by_camp[row.get("campaign_name", "(unknown)")]
        p["spend"] += to_float(row.get("spend"))
        p["impressions"] += to_float(row.get("impressions"))
        p["clicks"] += to_float(row.get("clicks"))
    cur_total = {
        "spend": sum(c["spend"] for c in camp_rows),
        "impressions": sum(c["impressions"] for c in camp_rows),
        "clicks": sum(c["clicks"] for c in camp_rows),
    }
    prev_total = {
        "spend": sum(p["spend"] for p in prev_by_camp.values()),
        "impressions": sum(p["impressions"] for p in prev_by_camp.values()),
        "clicks": sum(p["clicks"] for p in prev_by_camp.values()),
    }
    cur_ctr = (cur_total["clicks"] / cur_total["impressions"] * 100) if cur_total["impressions"] else 0
    cur_cpc = (cur_total["spend"] / cur_total["clicks"]) if cur_total["clicks"] else 0
    prev_ctr = (prev_total["clicks"] / prev_total["impressions"] * 100) if prev_total["impressions"] else 0
    prev_cpc = (prev_total["spend"] / prev_total["clicks"]) if prev_total["clicks"] else 0

    delta = {
        "spend_pct": ((cur_total["spend"] - prev_total["spend"]) / prev_total["spend"] * 100) if prev_total["spend"] else 0,
        "ctr_pct": ((cur_ctr - prev_ctr) / prev_ctr * 100) if prev_ctr else 0,
        "cpc_pct": ((cur_cpc - prev_cpc) / prev_cpc * 100) if prev_cpc else 0,
    }

    alerts = []
    for c in camp_rows:
        if c["impressions"] >= 1000 and 0 < c["ctr"] < CTR_LOW:
            alerts.append(f"CTR 낮음: {c['name']} ({fmt_pct(c['ctr'])})")
        if c["freq"] > FREQ_HIGH:
            alerts.append(f"Freq 피로: {c['name']} ({c['freq']:.2f})")
    if delta["cpc_pct"] > CPC_SPIKE_PCT and prev_cpc > 0:
        alerts.append(f"CPC 급등: 전일 대비 +{delta['cpc_pct']:.1f}%")

    bw = best_worst_from_rows(cur, min_impr=100, ref_date=yday)
    ad_ids = [a.get("ad_id") for a in bw.get("all_ads", []) if a.get("ad_id")]
    post_url_map = build_post_url_map(ad_ids)
    candidates = budget_increase_candidates(bw.get("all_ads", []), min_spend=30000)
    return {
        "date": yday, "prev_date": dby,
        "ref_date": yday,
        "total": {**cur_total, "ctr": cur_ctr, "cpc": cur_cpc},
        "campaigns": camp_rows, "top5": top5, "alerts": alerts, "delta": delta,
        "best_worst": bw,
        "post_url_map": post_url_map,
        "budget_candidates": candidates,
    }


# ============================================================
# 7d Analysis
# ============================================================
def analyze_7d(end_date):
    start = end_date - timedelta(days=6)
    prev_start = end_date - timedelta(days=13)
    prev_end = end_date - timedelta(days=7)

    cur_daily = fetch("campaign",
                      time_range={"since": start.isoformat(), "until": end_date.isoformat()},
                      with_daily=True)
    prev_daily = fetch("campaign",
                       time_range={"since": prev_start.isoformat(), "until": prev_end.isoformat()},
                       with_daily=True)
    ad_rows = fetch("ad", time_range={"since": start.isoformat(), "until": end_date.isoformat()})

    daily_agg = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0})
    for row in cur_daily:
        d = row.get("date_start", "")
        daily_agg[d]["spend"] += to_float(row.get("spend"))
        daily_agg[d]["impressions"] += to_float(row.get("impressions"))
        daily_agg[d]["clicks"] += to_float(row.get("clicks"))
    daily_trend = []
    cur_d = start
    while cur_d <= end_date:
        ds = cur_d.isoformat()
        v = daily_agg.get(ds, {"spend": 0, "impressions": 0, "clicks": 0})
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        daily_trend.append({"date": ds, "spend": v["spend"], "ctr": ctr, "cpc": cpc, "impressions": v["impressions"]})
        cur_d += timedelta(days=1)

    by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "freq_sum": 0, "n": 0})
    for row in cur_daily:
        c = by_camp[row.get("campaign_name", "(unknown)")]
        c["spend"] += to_float(row.get("spend"))
        c["impressions"] += to_float(row.get("impressions"))
        c["clicks"] += to_float(row.get("clicks"))
        c["freq_sum"] += to_float(row.get("frequency"))
        c["n"] += 1
    camp_rows = []
    for name, v in by_camp.items():
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        freq = (v["freq_sum"] / v["n"]) if v["n"] else 0
        camp_rows.append({"name": name, "spend": v["spend"], "impressions": v["impressions"],
                          "clicks": v["clicks"], "ctr": ctr, "cpc": cpc, "freq": freq})
    camp_rows.sort(key=lambda x: x["spend"], reverse=True)

    ads = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 200:
            continue
        ads.append({
            "ad_name": row.get("ad_name", ""),
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    top10 = sorted(ads, key=lambda x: x["spend"], reverse=True)[:10]

    cur_sum = {"spend": 0, "impressions": 0, "clicks": 0}
    prev_sum = {"spend": 0, "impressions": 0, "clicks": 0}
    for row in cur_daily:
        for k in cur_sum:
            cur_sum[k] += to_float(row.get(k))
    for row in prev_daily:
        for k in prev_sum:
            prev_sum[k] += to_float(row.get(k))
    cur_ctr = (cur_sum["clicks"] / cur_sum["impressions"] * 100) if cur_sum["impressions"] else 0
    cur_cpc = (cur_sum["spend"] / cur_sum["clicks"]) if cur_sum["clicks"] else 0
    prev_ctr = (prev_sum["clicks"] / prev_sum["impressions"] * 100) if prev_sum["impressions"] else 0
    prev_cpc = (prev_sum["spend"] / prev_sum["clicks"]) if prev_sum["clicks"] else 0
    wow = {
        "spend": cur_sum["spend"], "spend_prev": prev_sum["spend"],
        "spend_pct": ((cur_sum["spend"] - prev_sum["spend"]) / prev_sum["spend"] * 100) if prev_sum["spend"] else 0,
        "ctr": cur_ctr, "ctr_prev": prev_ctr,
        "ctr_pct": ((cur_ctr - prev_ctr) / prev_ctr * 100) if prev_ctr else 0,
        "cpc": cur_cpc, "cpc_prev": prev_cpc,
        "cpc_pct": ((cur_cpc - prev_cpc) / prev_cpc * 100) if prev_cpc else 0,
    }

    bw7 = best_worst_from_rows(ad_rows, min_impr=500, ref_date=end_date)  # 5/15: 풀 percentile 신뢰 위한 최소 노출 상향
    ad_ids7 = [a.get("ad_id") for a in bw7.get("all_ads", []) if a.get("ad_id")]
    post_url_map7 = build_post_url_map(ad_ids7)
    candidates7 = budget_increase_candidates(bw7.get("all_ads", []), min_spend=30000)

    # B-6: velocity 추적 — Proven D+15+ ad 의 trailing 7d CTR delta < -15%
    prev_ad_rows = fetch("ad", time_range={"since": prev_start.isoformat(), "until": prev_end.isoformat()})
    prev_ad_map = {row.get("ad_id"): row for row in prev_ad_rows if row.get("ad_id")}
    velocity_decay = []
    for a in bw7.get("all_ads", []):
        if a.get("lifecycle") != "proven" or (a.get("days_live") or 0) < 15:
            continue
        prev_row = prev_ad_map.get(a.get("ad_id"))
        if not prev_row:
            continue
        prev_impr = to_float(prev_row.get("impressions"))
        if prev_impr < 200:
            continue
        prev_ctr_val = to_float(prev_row.get("ctr"))
        cur_ctr_val = a.get("ctr", 0)
        if prev_ctr_val <= 0 or cur_ctr_val <= 0:
            continue
        delta_pct = (cur_ctr_val - prev_ctr_val) / prev_ctr_val * 100
        if delta_pct < -15:
            velocity_decay.append({
                "ad_id": a.get("ad_id"),
                "ad_name": a["ad_name"],
                "paid_flag": a.get("paid_flag"),
                "days_live": a.get("days_live"),
                "cur_ctr": cur_ctr_val,
                "prev_ctr": prev_ctr_val,
                "delta_pct": delta_pct,
                "spend": a.get("spend", 0),
            })
    bw7["velocity_decay"] = velocity_decay

    return {
        "start": start, "end": end_date,
        "total": {**cur_sum, "ctr": cur_ctr, "cpc": cur_cpc},
        "daily_trend": daily_trend, "campaigns": camp_rows, "top10": top10, "wow": wow,
        "best_worst": bw7,
        "post_url_map": post_url_map7,
        "budget_candidates": candidates7,
    }


# ============================================================
# 14d Analysis
# ============================================================
def analyze_14d(end_date):
    start = end_date - timedelta(days=13)
    cur_daily = fetch("campaign",
                      time_range={"since": start.isoformat(), "until": end_date.isoformat()},
                      with_daily=True)
    ad_rows = fetch("ad", time_range={"since": start.isoformat(), "until": end_date.isoformat()})

    by_camp_day = defaultdict(lambda: defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0}))
    for row in cur_daily:
        c = row.get("campaign_name", "(unknown)")
        d = row.get("date_start", "")
        by_camp_day[c][d]["spend"] += to_float(row.get("spend"))
        by_camp_day[c][d]["impressions"] += to_float(row.get("impressions"))
        by_camp_day[c][d]["clicks"] += to_float(row.get("clicks"))
    learning = []
    for camp, days in by_camp_day.items():
        ds = sorted(days.keys())
        if len(ds) < 5:
            continue
        recent5 = ds[-5:]
        cpc_recent = []
        for d in recent5:
            v = days[d]
            cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
            cpc_recent.append(cpc)
        cpc_avg = sum(cpc_recent) / len(cpc_recent) if cpc_recent else 0
        cpc_var = max(cpc_recent) - min(cpc_recent) if cpc_recent else 0
        stability = "안정" if cpc_avg > 0 and cpc_var / cpc_avg < 0.3 else "학습중"
        learning.append({"campaign": camp, "cpc_avg": cpc_avg, "stability": stability,
                         "days_active": len(ds)})
    learning.sort(key=lambda x: x["days_active"], reverse=True)

    creative_groups = {"image": [], "video": [], "wl": []}
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 100:
            continue
        ad_name = row.get("ad_name", "").lower()
        if "wl" in ad_name or "partner" in ad_name or "@" in row.get("ad_name", ""):
            grp = "wl"
        elif "video" in ad_name or "reel" in ad_name or "动画" in ad_name or "動画" in ad_name:
            grp = "video"
        else:
            grp = "image"
        creative_groups[grp].append({
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "clicks": to_float(row.get("clicks")),
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    creative_class = {}
    for grp, rows in creative_groups.items():
        if not rows:
            creative_class[grp] = None
            continue
        spend = sum(r["spend"] for r in rows)
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        freq_avg = sum(r["freq"] for r in rows) / len(rows)
        creative_class[grp] = {
            "n": len(rows), "spend": spend, "impressions": impr,
            "ctr": (clicks / impr * 100) if impr else 0,
            "cpc": (spend / clicks) if clicks else 0,
            "freq": freq_avg,
        }

    fatigue = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 500:
            continue
        freq = to_float(row.get("frequency"))
        ctr = to_float(row.get("ctr"))
        if freq > FREQ_HIGH or (freq > 2.0 and ctr < CTR_LOW):
            fatigue.append({
                "ad_name": row.get("ad_name", ""),
                "campaign_name": row.get("campaign_name", ""),
                "freq": freq, "ctr": ctr, "spend": to_float(row.get("spend")),
            })
    fatigue.sort(key=lambda x: x["freq"], reverse=True)

    actions = []
    if fatigue:
        actions.append(f"폐기 검토: Freq>3.0 광고 {len(fatigue)}개 (총 spend {fmt_won(sum(f['spend'] for f in fatigue))})")
    if creative_class.get("image") and creative_class.get("video"):
        ic = creative_class["image"]["ctr"]
        vc = creative_class["video"]["ctr"]
        if vc > ic * 1.3:
            actions.append(f"영상 우세: video CTR {vc:.2f}% vs image {ic:.2f}% — 영상 비중 증액 검토")
        elif ic > vc * 1.3:
            actions.append(f"이미지 우세: image CTR {ic:.2f}% vs video {vc:.2f}% — 이미지 슬롯 확대")

    bw14 = best_worst_from_rows(ad_rows, min_impr=500, ref_date=end_date)
    ad_ids14 = [a.get("ad_id") for a in bw14.get("all_ads", []) if a.get("ad_id")]
    post_url_map14 = build_post_url_map(ad_ids14)
    candidates14 = budget_increase_candidates(bw14.get("all_ads", []), min_spend=50000)
    return {
        "start": start, "end": end_date,
        "learning": learning, "creative_class": creative_class,
        "fatigue": fatigue[:10], "actions": actions,
        "best_worst": bw14,
        "post_url_map": post_url_map14,
        "budget_candidates": candidates14,
    }


# ============================================================
# Charts (matplotlib, base64-inline PNG)
# ============================================================
def chart_daily_trend(daily_trend):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    dates = [d["date"][5:] for d in daily_trend]
    spend = [d["spend"] for d in daily_trend]
    ctr = [d["ctr"] for d in daily_trend]
    cpc = [d["cpc"] for d in daily_trend]
    fig, ax1 = plt.subplots(figsize=(10, 4))
    color1 = "#2563eb"
    ax1.bar(dates, spend, color=color1, alpha=0.4, label="Spend (₩)")
    ax1.set_ylabel("Spend (₩)", color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax2 = ax1.twinx()
    ax2.plot(dates, ctr, color="#dc2626", marker="o", label="CTR (%)")
    ax2.plot(dates, cpc, color="#059669", marker="s", label="CPC (₩)", linestyle="--")
    ax2.set_ylabel("CTR (%) / CPC (₩)")
    fig.legend(loc="upper right", bbox_to_anchor=(0.95, 0.95))
    plt.title("Daily Trend (Spend / CTR / CPC)")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


# ============================================================
# HTML Render
# ============================================================
CSS = """
<style>
  body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1f2937; max-width: 1040px; margin: 0 auto; padding: 24px; line-height: 1.5; }
  h1 { font-size: 24px; border-bottom: 2px solid #2563eb; padding-bottom: 10px; margin-bottom: 18px; }
  h2 { font-size: 19px; margin-top: 40px; margin-bottom: 14px; color: #1f2937; padding-top: 8px; border-top: 1px solid #f3f4f6; }
  h2:first-of-type { border-top: none; }
  table { border-collapse: collapse; width: 100%; margin: 14px 0 36px; font-size: 15px; }
  th, td { border: 1px solid #e5e7eb; padding: 11px 14px; text-align: right; }
  th { background: #f3f4f6; text-align: center; font-weight: 600; }
  td.l { text-align: left; }
  td.c { text-align: center; }
  .alert { background: #fef2f2; border-left: 4px solid #dc2626; padding: 12px 16px; margin: 14px 0; border-radius: 4px; }
  .ok { background: #f0fdf4; border-left: 4px solid #059669; padding: 12px 16px; margin: 14px 0; border-radius: 4px; }
  .delta-up { color: #dc2626; font-weight: 600; }
  .delta-down { color: #059669; font-weight: 600; }
  .delta-bad { color: #dc2626; font-weight: 600; }
  .delta-good { color: #059669; font-weight: 600; }
  .meta { color: #6b7280; font-size: 13px; }
</style>
"""


def delta_span(pct, lower_is_better=False, neutral=False):
    # |pct| < 1.0 = 반올림 표시(₩80→₩80)와 충돌 가능. 변화 미미 처리.
    if pct == 0 or abs(pct) < 1.0:
        return '<span class="meta">±0%</span>'
    arrow = "▲" if pct > 0 else "▼"
    if neutral:
        return f'<span style="color:#6b7280">{arrow} {abs(pct):.1f}%</span>'
    is_bad = (pct > 0) if lower_is_better else (pct < 0)
    # 의미 명확화: delta-bad/delta-good (방향 ▲▼ ≠ 좋고나쁨)
    cls = "delta-bad" if is_bad else "delta-good"
    return f'<span class="{cls}">{arrow} {abs(pct):.1f}%</span>'


def render_1d(d):
    t = d["total"]
    rows = "".join(
        f"<tr><td class=l>{c['name']}</td><td>{fmt_won(c['spend'])}</td>"
        f"<td>{fmt_num(c['impressions'])}</td><td>{fmt_pct(c['ctr'])}</td>"
        f"<td>{fmt_won(c['cpc'])}</td><td>{c['freq']:.2f}</td>"
        f"<td>{fmt_num(c['reach'])}</td></tr>"
        for c in d["campaigns"]
    )
    top5 = "".join(
        f"<tr><td class=l>{a['ad_name'][:50]}</td><td>{fmt_pct(a['ctr'])}</td>"
        f"<td>{fmt_won(a['cpc'])}</td><td>{fmt_won(a['spend'])}</td>"
        f"<td>{fmt_num(a['impressions'])}</td></tr>"
        for a in d["top5"]
    )
    alerts_html = (
        '<div class="alert"><b>⚠ 알림</b><ul>' +
        "".join(f"<li>{a}</li>" for a in d["alerts"]) + "</ul></div>"
    ) if d["alerts"] else '<div class="ok">알림 없음 (모든 지표 정상 범위)</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Daily — {d['date']}</h1>
<p class=meta>비교: 전일 ({d['prev_date']}) · 계정: act_{ACCT.replace('act_', '')}</p>

<h2>전체 요약</h2>
<table>
  <tr><th>Spend</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>CPC</th></tr>
  <tr><td>{fmt_won(t['spend'])} {delta_span(d['delta']['spend_pct'], neutral=True)}</td>
      <td>{fmt_num(t['impressions'])}</td>
      <td>{fmt_num(t['clicks'])}</td>
      <td>{fmt_pct(t['ctr'])} {delta_span(d['delta']['ctr_pct'])}</td>
      <td>{fmt_won(t['cpc'])} {delta_span(d['delta']['cpc_pct'], lower_is_better=True)}</td></tr>
</table>

{alerts_html}

<h2>캠페인별</h2>
<table>
  <tr><th>캠페인</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th><th>Reach</th></tr>
  {rows}
</table>

<h2>광고 TOP 5 (CTR 순)</h2>
<table>
  <tr><th>광고</th><th>CTR</th><th>CPC</th><th>Spend</th><th>Impr</th></tr>
  {top5}
</table>

<p class=meta>알림 임계값: CTR&lt;{CTR_LOW}% / Freq&gt;{FREQ_HIGH} / CPC 전일 +{CPC_SPIKE_PCT}% (5/15: 외부 시장 평균 floor 폐기)</p>

{render_kpi_counter(d['best_worst'].get('all_ads', []))}

{render_off_recommend_box(d['best_worst'], ref_date=d.get('ref_date'))}

{render_best_worst_table(d['best_worst'], d.get('post_url_map'))}

{render_budget_increase_table(d.get('budget_candidates', []), d.get('post_url_map'))}

{render_findings_section(build_findings(d, ref_date=d.get('ref_date')))}

{render_advice_section(build_advice_1d(d))}
</body></html>"""


def render_7d(d):
    t = d["total"]
    w = d["wow"]
    img_b64 = chart_daily_trend(d["daily_trend"])
    chart_html = f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%;"/>' if img_b64 else "<p class=meta>(matplotlib 미설치)</p>"

    daily_rows = "".join(
        f"<tr><td class=l>{x['date']}</td><td>{fmt_won(x['spend'])}</td>"
        f"<td>{fmt_num(x['impressions'])}</td><td>{fmt_pct(x['ctr'])}</td>"
        f"<td>{fmt_won(x['cpc'])}</td></tr>"
        for x in d["daily_trend"]
    )
    camp_rows = "".join(
        f"<tr><td class=l>{c['name']}</td><td>{fmt_won(c['spend'])}</td>"
        f"<td>{fmt_num(c['impressions'])}</td><td>{fmt_pct(c['ctr'])}</td>"
        f"<td>{fmt_won(c['cpc'])}</td><td>{c['freq']:.2f}</td></tr>"
        for c in d["campaigns"]
    )
    top10 = "".join(
        f"<tr><td class=l>{a['ad_name'][:50]}</td><td>{fmt_won(a['spend'])}</td>"
        f"<td>{fmt_num(a['impressions'])}</td><td>{fmt_pct(a['ctr'])}</td>"
        f"<td>{fmt_won(a['cpc'])}</td><td>{a['freq']:.2f}</td></tr>"
        for a in d["top10"]
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Weekly — {d['start']} ~ {d['end']}</h1>
<p class=meta>WoW 비교: 전주 ({d['end'] - timedelta(days=13)} ~ {d['end'] - timedelta(days=7)})</p>

<h2>주간 요약 (WoW)</h2>
<table>
  <tr><th>지표</th><th>이번주</th><th>전주</th><th>변화</th></tr>
  <tr><td class=l>Spend</td><td>{fmt_won(w['spend'])}</td><td>{fmt_won(w['spend_prev'])}</td><td>{delta_span(w['spend_pct'], neutral=True)}</td></tr>
  <tr><td class=l>CTR</td><td>{fmt_pct(w['ctr'])}</td><td>{fmt_pct(w['ctr_prev'])}</td><td>{delta_span(w['ctr_pct'])}</td></tr>
  <tr><td class=l>CPC</td><td>{fmt_won(w['cpc'])}</td><td>{fmt_won(w['cpc_prev'])}</td><td>{delta_span(w['cpc_pct'], lower_is_better=True)}</td></tr>
</table>

<h2>일별 추이</h2>
{chart_html}
<table>
  <tr><th>날짜</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th></tr>
  {daily_rows}
</table>

<h2>캠페인 7일 합계</h2>
<table>
  <tr><th>캠페인</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {camp_rows}
</table>

<h2>광고 TOP 10 (Spend 순)</h2>
<table>
  <tr><th>광고</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {top10}
</table>

{render_kpi_counter(d['best_worst'].get('all_ads', []))}

{render_off_recommend_box(d['best_worst'], ref_date=d.get('end'))}

{render_best_worst_table(d['best_worst'], d.get('post_url_map'))}

{render_budget_increase_table(d.get('budget_candidates', []), d.get('post_url_map'))}

{render_findings_section(build_findings(d, ref_date=d.get('end')))}

{render_advice_section(build_advice_7d(d))}
</body></html>"""


def render_14d(d):
    learning_rows = "".join(
        f"<tr><td class=l>{x['campaign']}</td><td>{x['days_active']}일</td>"
        f"<td>{fmt_won(x['cpc_avg'])}</td><td>{x['stability']}</td></tr>"
        for x in d["learning"]
    ) or "<tr><td colspan=4>데이터 부족</td></tr>"

    cc_rows = ""
    for grp, label in [("image", "이미지"), ("video", "영상"), ("wl", "WL(인플루언서)")]:
        v = d["creative_class"].get(grp)
        if v:
            cc_rows += (f"<tr><td class=l>{label} ({v['n']}개)</td><td>{fmt_won(v['spend'])}</td>"
                        f"<td>{fmt_num(v['impressions'])}</td><td>{fmt_pct(v['ctr'])}</td>"
                        f"<td>{fmt_won(v['cpc'])}</td><td>{v['freq']:.2f}</td></tr>")
        else:
            cc_rows += f"<tr><td class=l>{label}</td><td colspan=5>없음</td></tr>"

    fatigue_rows = "".join(
        f"<tr><td class=l>{x['ad_name'][:50]}</td><td>{x['freq']:.2f}</td>"
        f"<td>{fmt_pct(x['ctr'])}</td><td>{fmt_won(x['spend'])}</td></tr>"
        for x in d["fatigue"]
    ) or "<tr><td colspan=4>피로도 경고 광고 없음</td></tr>"

    actions_html = (
        '<div class="alert"><b>Action Items</b><ul>' +
        "".join(f"<li>{a}</li>" for a in d["actions"]) + "</ul></div>"
    ) if d["actions"] else '<div class="ok">즉시 액션 항목 없음</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Bi-weekly Audit — {d['start']} ~ {d['end']}</h1>

<h2>학습 단계 진단</h2>
<table>
  <tr><th>캠페인</th><th>활성 일수</th><th>최근 5일 CPC 평균</th><th>안정성</th></tr>
  {learning_rows}
</table>
<p class=meta>최근 5일 CPC 변동폭이 평균의 30% 미만이면 "안정" 판정</p>

<h2>크리에이티브 분류</h2>
<table>
  <tr><th>유형</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {cc_rows}
</table>

<h2>피로도 경고 (Freq&gt;3.0 또는 Freq&gt;2.0+CTR&lt;1%)</h2>
<table>
  <tr><th>광고</th><th>Freq</th><th>CTR</th><th>Spend</th></tr>
  {fatigue_rows}
</table>

{actions_html}

{render_kpi_counter(d['best_worst'].get('all_ads', []))}

{render_off_recommend_box(d['best_worst'], ref_date=d.get('end'))}

{render_best_worst_table(d['best_worst'], d.get('post_url_map'))}

{render_budget_increase_table(d.get('budget_candidates', []), d.get('post_url_map'))}

{render_findings_section(build_findings(d, ref_date=d.get('end')))}

{render_advice_section(build_advice_14d(d))}
</body></html>"""


# ============================================================
# Auditor (rule-based + Gemini)
# ============================================================
REQUIRED_SECTIONS = {
    "1d": ["전체 요약", "캠페인별", "광고 TOP 5", "광고 BEST / WORST", "예산 증액 후보", "오늘의 발견", "메타몽 운용 조언"],
    "7d": ["주간 요약", "일별 추이", "캠페인 7일 합계", "광고 BEST / WORST", "예산 증액 후보", "오늘의 발견", "메타몽 운용 조언"],
    "14d": ["학습 단계", "크리에이티브 분류", "광고 BEST / WORST", "예산 증액 후보", "오늘의 발견", "메타몽 운용 조언"],
}


def audit_rule_based(analysis, html, mode):
    """Code-level integrity checks. Returns list of violations."""
    v = []
    total = analysis.get("total", {})

    if mode == "1d":
        camp_sum = sum(c["spend"] for c in analysis.get("campaigns", []))
        if total.get("spend") and camp_sum > 0:
            diff = abs(camp_sum - total["spend"]) / total["spend"]
            if diff > 0.02:
                v.append(f"SPEND_INCONSISTENT: camp_sum={camp_sum:.0f} vs total={total['spend']:.0f} ({diff*100:.1f}% off)")

    if total.get("impressions", 0) == 0 and mode != "14d":
        v.append("EMPTY_DATA: 0 impressions — Meta API fetch failure suspected")

    bw = analysis.get("best_worst", {})
    if bw.get("ctr_best") and len(bw["ctr_best"]) >= 2:
        ctrs = [a["ctr"] for a in bw["ctr_best"]]
        if ctrs != sorted(ctrs, reverse=True):
            v.append("CTR_BEST_NOT_DESC: BEST 정렬 오류")
    if bw.get("ctr_worst") and len(bw["ctr_worst"]) >= 2:
        ctrs = [a["ctr"] for a in bw["ctr_worst"]]
        if ctrs != sorted(ctrs):
            v.append("CTR_WORST_NOT_ASC: WORST 정렬 오류")
    if bw.get("cpc_best") and len(bw["cpc_best"]) >= 2:
        cpcs = [a["cpc"] for a in bw["cpc_best"]]
        if cpcs != sorted(cpcs):
            v.append("CPC_BEST_NOT_ASC: CPC BEST 정렬 오류")
    if bw.get("cpc_worst") and len(bw["cpc_worst"]) >= 2:
        cpcs = [a["cpc"] for a in bw["cpc_worst"]]
        if cpcs != sorted(cpcs, reverse=True):
            v.append("CPC_WORST_NOT_DESC: CPC WORST 정렬 오류")

    if bw.get("ctr_best") and bw.get("ctr_worst"):
        if bw["ctr_best"][0]["ctr"] < bw["ctr_worst"][0]["ctr"]:
            v.append("BEST_LT_WORST: CTR BEST가 WORST보다 낮음 (논리 오류)")

    for sec in REQUIRED_SECTIONS.get(mode, []):
        if sec not in html:
            v.append(f"MISSING_SECTION: '{sec}' 누락")

    forbidden = ["가능성", "추정", "추측", "아마도"]
    for word in forbidden:
        if word in html:
            v.append(f"SPECULATION_WORD: '{word}' 추측 표현 포함")
            break

    return v


def audit_gemini(html, mode):
    """Semantic audit via Gemini. Returns dict {pass, score, violations}."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"pass": True, "skip": True, "reason": "genai not installed"}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"pass": True, "skip": True, "reason": "GEMINI_API_KEY missing"}

    client = genai.Client(api_key=api_key)
    rules = """
[감사 규칙 — Meta JP 광고 리포트]
1. 본문 숫자(spend/CTR/CPC/Freq)와 조언 텍스트의 진단이 일치할 것
2. BEST/WORST 격차에 비례하는 액션 제안일 것 (격차 작은데 "즉시 폐기" 등 과잉 금지)
3. 표/테이블 형식 깨짐 없음 (빈 td, 잘못된 colspan 등)
4. 한국어 비즈니스 톤. "가능성/추정/추측" 등 추측 표현 금지
5. 단위 일관성: 금액은 ₩, 비율은 %, Freq는 소수점
6. 조언 섹션이 데이터 부족 시 "데이터 부족" 명시 (가짜 인사이트 금지)

JSON 응답 (mime=application/json):
{"pass": bool, "score": 0-100, "violations": [{"rule": "string", "fix": "string"}]}
score >= 80 일 때만 pass=true.
"""
    import re
    # base64 차트 데이터 제거 (감사 텍스트 분량 확보)
    audit_html = re.sub(r'data:image/png;base64,[^"]+', '[CHART_PNG]', html)
    prompt = f"다음 Meta JP {mode} 리포트 HTML을 감사하세요.\n\n{rules}\n\n[HTML]\n{audit_html[:50000]}"

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        text = (resp.text or "").strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        return result
    except Exception as e:
        return {"pass": False, "score": 0,
                "violations": [{"rule": "AUDITOR_ERROR", "fix": str(e)}],
                "error": str(e)}


def run_auditor(analysis, html, mode):
    """Combined: rule + Gemini. Returns (passed, report_str)."""
    rule_v = audit_rule_based(analysis, html, mode)
    gemini = audit_gemini(html, mode)

    lines = []
    lines.append(f"[AUDIT] mode={mode}")
    lines.append(f"  Rule violations: {len(rule_v)}")
    for x in rule_v:
        lines.append(f"    - {x}")
    if gemini.get("skip"):
        lines.append(f"  Gemini: SKIPPED ({gemini.get('reason')})")
    else:
        score = gemini.get("score", 0)
        lines.append(f"  Gemini score: {score}")
        for vv in gemini.get("violations", []):
            lines.append(f"    - {vv.get('rule')}: {vv.get('fix', '')[:120]}")

    rule_pass = len(rule_v) == 0
    gemini_pass = gemini.get("pass", False) or gemini.get("skip", False)
    passed = rule_pass and gemini_pass
    lines.append(f"  → {'PASS' if passed else 'FAIL'}")
    return passed, "\n".join(lines)


# ============================================================
# Send
# ============================================================
def send(to, subject, html_path):
    cmd = [sys.executable, str(TOOLS / "send_gmail.py"),
           "--to", to, "--subject", subject, "--body-file", str(html_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"[FAIL] send_gmail: {r.stderr}")
        return False
    print(f"[OK] sent to {to}")
    return True


# ============================================================
# Main
# ============================================================
def main():
    if not TOKEN or not ACCT:
        print("[ERROR] META_JP_ACCESS_TOKEN / META_JP_AD_ACCOUNT_ID missing in .env")
        sys.exit(1)

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["1d", "7d", "14d"], default="1d")
    p.add_argument("--to", default=DEFAULT_TO)
    p.add_argument("--no-send", action="store_true")
    p.add_argument("--skip-audit", action="store_true",
                   help="EMERGENCY ONLY — bypass auditor (logs warning)")
    p.add_argument("--date", help="reference date YYYY-MM-DD (default: yesterday)")
    args = p.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    print(f"[INFO] mode={args.mode} ref_date={ref}")

    if args.mode == "1d":
        analysis = analyze_1d(ref)
        html = render_1d(analysis)
        subject = f"[Meta JP] Daily {ref}"
    elif args.mode == "7d":
        analysis = analyze_7d(ref)
        html = render_7d(analysis)
        subject = f"[Meta JP] Weekly {analysis['start']} ~ {analysis['end']}"
    else:
        analysis = analyze_14d(ref)
        html = render_14d(analysis)
        subject = f"[Meta JP] Bi-weekly Audit {analysis['start']} ~ {analysis['end']}"

    out_path = TMP_DIR / f"meta_jp_{args.mode}_{ref.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] saved {out_path} ({len(html):,} bytes)")

    # Auditor gate
    if args.skip_audit:
        print("[WARN] --skip-audit: 감사 우회 (긴급 모드)")
    else:
        passed, audit_report = run_auditor(analysis, html, args.mode)
        print(audit_report)
        audit_log = TMP_DIR / f"meta_jp_{args.mode}_{ref.isoformat()}.audit.log"
        audit_log.write_text(audit_report, encoding="utf-8")
        if not passed:
            print(f"[BLOCKED] auditor FAIL — 발송 차단. 로그: {audit_log}")
            if not args.no_send:
                sys.exit(2)

    if args.no_send:
        print("[SKIP] --no-send")
        return

    send(args.to, subject, out_path)


if __name__ == "__main__":
    main()
