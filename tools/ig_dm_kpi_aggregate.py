"""IG DM 원장 → 리치아웃/답장/계약 코호트 집계 → 트래커 시트 "Outreach Auto" 탭.

Python 3.10+ (repo 표준 3.14).

코호트 정의 (2026-08-25 세은 확정 — 담당자 분해 없음, 계정 단위):
- 리치아웃: 원장에서 첫 메시지(가장 오래된 관측 메시지)가 우리 발신인 스레드.
  귀속일 = 그 첫 발신 시각 (JST). peer 당 1회 (최초 리치아웃 채택).
- 답장: 리치아웃 스레드에서 첫 발신 이후 상대의 첫 수신 발생.
  귀속 = 리치아웃 주차 (코호트 — 늦은 답장도 발송 주차로 귀속).
- 계약: WL Code & Payment 탭(계약서 받은 사람만 기재)의 Creator ID 를
  리치아웃 스레드 peer 와 매칭. 핸들 단위 dedup — 행이 여러 개(복수 딜리버러블)여도
  계약 1건. 귀속 = 해당 스레드의 리치아웃 주차.
  DM 스레드가 없는 계약(타 경로)은 별도 카운트로 표기만.
- capped 스레드(20개 창 가득)는 첫 발신 시각이 실제보다 늦을 수 있어
  Low Confidence 컬럼으로 따로 표기.

Usage:
    python tools/ig_dm_kpi_aggregate.py            # 집계 + 시트 반영
    python tools/ig_dm_kpi_aggregate.py --dry-run  # 시트 반영 없이 표만 출력
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

LEDGER = ROOT / "data" / "ig_dm_ledger.json"
FOLLOWERS_CACHE = ROOT / "data" / "ig_dm_followers.json"   # ig_dm_follower_enrich.py 산출
TRACKER_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
WL_TAB_GID = 751080099          # "WL Code & Payment"
OUT_TAB = "Outreach Auto"
OUT_TAB_MONTHLY = "Outreach Auto Monthly"
OUT_TAB_TIER = "Outreach Auto Tier"
OUT_TAB_JOURNEY = "Outreach Journey"   # 인플루언서별 여정 맵핑 (2026-08-27 대표님 지시)
# 최초 원장 백필 시각 (UTC) — 그 전에 이미 20개 초과였던 스레드 = 시작 소급불가.
# 비교는 parse_ts 로 datetime 파싱 후 수행 (문자열 비교는 tz 표기 편차에 취약).
BACKFILL_AT = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)
# 팔로워 티어 컷 — KPI 목표(Projection_26)·meta-app influencer-kpi-targets.ts 와 동일 구간
TIERS = [("0-5K", 0, 5_000), ("5-10K", 5_000, 10_000), ("10-20K", 10_000, 20_000),
         ("20-50K", 20_000, 50_000), ("50K+", 50_000, None)]
JST = timezone(timedelta(hours=9))
# 집계 시작점 — 2026-08-01 (JST) 이후 리치아웃만 코호트에 포함 (2026-08-25 세은 지시:
# "8월부터 누적 시작". 원장 수집은 전 기간 그대로, 집계·표시만 컷).
COHORT_START = datetime(2026, 8, 1, tzinfo=JST)


def parse_ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
    except (ValueError, TypeError):
        return None


def week_start(d: datetime) -> str:
    """월요일 시작 주차 라벨 (JST)."""
    monday = d.date() - timedelta(days=d.weekday())
    return monday.isoformat()


def norm_handle(s: str) -> str:
    return (s or "").strip().lstrip("@").lower()


def load_ledger() -> dict:
    if not LEDGER.exists():
        raise SystemExit(f"ERROR: 원장 없음 — 먼저 ig_dm_collector.py 실행 ({LEDGER})")
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"ERROR: 원장 JSON 손상 ({LEDGER}): {e}") from e
    if not isinstance(d.get("threads"), dict):
        raise SystemExit(f"ERROR: 원장 스키마 손상 — threads 키 없음 ({LEDGER})")
    return d


def analyze_threads(ledger: dict) -> dict[str, dict]:
    """peer 핸들별 {reachout_ts, reply_ts, capped} — 우리가 먼저 연 스레드만."""
    out: dict[str, dict] = {}
    for t in ledger["threads"].values():
        msgs = t.get("messages") or []
        if not msgs:
            continue
        first = msgs[0]
        if first.get("dir") != "out":
            continue  # 상대가 먼저 연 스레드 (인바운드 문의) = 리치아웃 아님
        reachout_ts = parse_ts(first.get("ts", ""))
        if not reachout_ts:
            continue
        reply_ts = None
        for m in msgs:
            ts = parse_ts(m.get("ts", ""))
            if m.get("dir") == "in" and ts and ts > reachout_ts:
                reply_ts = ts
                break
        peer = norm_handle(t.get("peer", ""))
        if not peer:
            continue
        # 같은 peer 와 스레드 복수 → 가장 이른 리치아웃 1건만 (동시각이면 먼저 본 것 유지)
        if peer in out and out[peer]["reachout_ts"] <= reachout_ts:
            continue
        out[peer] = {
            "reachout_ts": reachout_ts,
            "reply_ts": reply_ts,
            "capped": bool(t.get("capped")),
        }
    return out


def fetch_contract_handles(gc) -> set[str]:
    """WL 탭 Creator ID 열 전체 → 핸들 set (행 중복 = 계약 1건으로 dedup)."""
    sh = gc.open_by_key(TRACKER_ID)
    ws = next(w for w in sh.worksheets() if w.id == WL_TAB_GID)
    rows = ws.get_values("D4:D")  # D = Creator ID (헤더 3행). 상한 없음 — 전 행.
    return {h for r in rows if r for h in [norm_handle(r[0])] if h}


def build_weekly(threads: dict, contract_set: set[str], all_peers: set[str],
                 first_posts: dict[str, str] | None = None) -> tuple[list[list], dict]:
    """주별 코호트 퍼널 — 그 주 리치아웃 인원 중 답장/계약/포스팅 도달 수 (2026-08-27 세은 확정 축)."""
    weekly = defaultdict(lambda: {"reachout": 0, "reply": 0, "contract": 0, "post": 0, "low_conf": 0})
    # 표기 편차 흡수: 앞뒤 언더스코어 제거 키로도 매칭 (WL "_musukono_kiroku_" vs DM "musukono_kiroku" 류)
    us = lambda s: s.strip("_")
    contract_us = {us(h): h for h in contract_set}
    posts = first_posts or {}
    posts_us = {us(h): d for h, d in posts.items()}
    matched_contracts = set()
    for peer, info in threads.items():
        wk = week_start(info["reachout_ts"])
        weekly[wk]["reachout"] += 1
        if info["capped"]:
            weekly[wk]["low_conf"] += 1
        if info["reply_ts"]:
            weekly[wk]["reply"] += 1
        hit = peer if peer in contract_set else contract_us.get(us(peer), "")
        if hit and hit not in matched_contracts:
            weekly[wk]["contract"] += 1  # peer 는 threads 키라 주 1회만 진입 — 중복 불가
            matched_contracts.add(hit)
        if peer in posts or us(peer) in posts_us:
            weekly[wk]["post"] += 1
    unmatched = sorted(contract_set - matched_contracts)
    # 미매칭 분해: DM 스레드는 있으나 시작 소급 판정 불가(과거 20개 캡) vs DM 자체 없음
    all_us = {us(p) for p in all_peers}
    origin_unknown = [h for h in unmatched if h in all_peers or us(h) in all_us]
    no_dm = [h for h in unmatched if not (h in all_peers or us(h) in all_us)]

    rows = []
    rate = lambda n, d: f"{n / d:.0%}" if d else "-"
    for wk in sorted(weekly):
        w = weekly[wk]
        rows.append([wk, w["reachout"], w["reply"], rate(w["reply"], w["reachout"]),
                     w["contract"], rate(w["contract"], w["reachout"]),
                     w["post"], rate(w["post"], w["reachout"]), w["low_conf"]])
    meta = {
        "total_reachout": sum(w["reachout"] for w in weekly.values()),
        "total_reply": sum(w["reply"] for w in weekly.values()),
        "total_contract": sum(w["contract"] for w in weekly.values()),
        "contracts_origin_unknown": origin_unknown,
        "contracts_no_dm": no_dm,
    }
    return rows, meta


def load_followers() -> dict[str, int]:
    """팔로워 캐시 (핸들→수). 없으면 빈 dict — 티어 표는 전원 '미확인'으로 표기."""
    if not FOLLOWERS_CACHE.exists():
        return {}
    try:
        d = json.loads(FOLLOWERS_CACHE.read_text(encoding="utf-8"))
    except ValueError:
        print(f"  [WARN] 팔로워 캐시 JSON 손상 ({FOLLOWERS_CACHE}) — 티어 전원 미확인 처리")
        return {}
    out = {}
    for h, e in (d.get("handles") or {}).items():
        f = (e or {}).get("followers")
        if isinstance(f, (int, float)) and f >= 0:
            out[h] = int(f)
    return out


def tier_of(followers: int | None) -> str:
    if followers is None:
        return "미확인"
    for name, lo, hi in TIERS:
        if followers >= lo and (hi is None or followers < hi):
            return name
    return "미확인"


def build_tier(threads: dict, contract_set: set[str], followers: dict[str, int]) -> list[list]:
    """팔로워 티어별 코호트 — scope 별 분해 (2026-08-27 세은 지시: 전체 + 주별/월별 선택).

    행 = [scope, tier, reachout, reply, reply%, contract, contract%].
    scope = "ALL" / "M:YYYY-MM" / "W:YYYY-MM-DD"(월요일 시작 주차, 주간 표와 동일 귀속).
    각 리치아웃은 ALL·자기 월·자기 주 3개 scope 에 동시 기여 — scope 내부 합계는 서로 일치.
    """
    us = lambda s: s.strip("_")
    contract_us = {us(h): h for h in contract_set}
    followers_us = {us(h): f for h, f in followers.items()}
    agg = defaultdict(lambda: {"reachout": 0, "reply": 0, "contract": 0})
    matched = set()
    for peer, info in threads.items():
        f = followers.get(peer)
        if f is None:
            f = followers_us.get(us(peer))
        t = tier_of(f)
        hit = peer if peer in contract_set else contract_us.get(us(peer), "")
        is_contract = bool(hit and hit not in matched)
        if is_contract:
            matched.add(hit)
        scopes = ["ALL",
                  f"M:{info['reachout_ts'].strftime('%Y-%m')}",
                  f"W:{week_start(info['reachout_ts'])}"]
        for sc in scopes:
            a = agg[(sc, t)]
            a["reachout"] += 1
            if info["reply_ts"]:
                a["reply"] += 1
            if is_contract:
                a["contract"] += 1
    rate = lambda n, d: f"{n / d:.0%}" if d else "-"
    tier_order = [name for name, *_ in TIERS] + ["미확인"]
    scope_keys = sorted({sc for sc, _ in agg}, key=lambda s: (s != "ALL", s))
    rows = []
    for sc in scope_keys:
        for t in tier_order:
            a = agg.get((sc, t))
            if not a:
                continue
            rows.append([sc, t, a["reachout"], a["reply"], rate(a["reply"], a["reachout"]),
                         a["contract"], rate(a["contract"], a["reachout"])])
        tr = sum(a["reachout"] for (s, _), a in agg.items() if s == sc)
        tp = sum(a["reply"] for (s, _), a in agg.items() if s == sc)
        tc = sum(a["contract"] for (s, _), a in agg.items() if s == sc)
        rows.append([sc, "TOTAL", tr, tp, rate(tp, tr), tc, rate(tc, tr)])
    return rows


def write_tier_sheet(gc, rows: list[list], coverage: str) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB_TIER)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB_TIER, rows=max(300, len(rows) + 20), cols=8)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Scope", "Tier (Followers)", "Reachout", "Reply", "Reply %",
               "Contract", "Contract %", f"updated {now}"]]
    note = [[f"팔로워 소스: DK→Master DB→Apify (ig_dm_follower_enrich.py 캐시) · {coverage}"]]
    try:
        if ws.row_count < len(rows) + 7:
            ws.resize(rows=len(rows) + 20)
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
        ws.update(values=note, range_name=f"A{len(rows) + 3}")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB_TIER}' 탭) — {e}") from e


def fetch_contract_periods(gc) -> dict[str, str]:
    """WL 탭 핸들별 계약(운영시작)일 — 운영기간 원문 최선 파싱. 일 단위 실패 시 월, 전부 실패 시 ''."""
    import re
    sh = gc.open_by_key(TRACKER_ID)
    ws = next(w for w in sh.worksheets() if w.id == WL_TAB_GID)
    rows = ws.get_values("A4:D")   # A=운영기간, D=Creator ID (헤더 3행)
    out: dict[str, str] = {}
    for r in rows:
        if len(r) < 4:
            continue
        h = (r[3] or "").strip().lstrip("@").lower()
        period = (r[0] or "").strip()
        if not h:
            continue
        d = ""
        m = re.search(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})", period)
        if m:
            d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            m = re.search(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})", period)
            if m:
                d = f"{m.group(1)}-{int(m.group(2)):02d}"
        # 핸들당 가장 이른 계약일 채택
        if h not in out or (d and (not out[h] or d < out[h])):
            out[h] = d
    return out


def fetch_dk_first_posts() -> dict[str, str]:
    """DK 실투고 (grosmimi 키워드, post_date >= 2026-08) — 핸들별 최초 투고일.
    실패 시 빈 dict (여정 표의 포스팅 컬럼만 공란 — 다음 실행 재시도)."""
    import os
    import urllib.request
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    from ig_dm_follower_enrich import DK_TOKEN_FALLBACK
    tok = os.environ.get("DK_SE_READ_TOKEN") or DK_TOKEN_FALLBACK
    out: dict[str, str] = {}
    # limit=20000 은 서버 상한 흡수용 여유값 — content_posts 는 서버가 항상 "최신 1만행"만
    # 반환 (2026-08-24 실측, lib/influencer-kpi.ts 동일 주석). region=jp + 글로벌 유니온으로
    # region 오기록분 구제 (meta-app fetchGrosmimiPosts 와 동일 전략).
    for extra in ["&region=jp", ""]:
        url = ("https://orbitools.orbiters.co.kr/api/datakeeper/query/?table=content_posts"
               "&limit=20000&fields=post_date,username,source_keywords" + extra)
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
            d = json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            print(f"  [WARN] DK 투고 조회 실패({extra or 'global'}): {str(e)[:80]}")
            continue
        for r in (d if isinstance(d, list) else d.get("rows", [])):
            pd = (r.get("post_date") or "")[:10]
            if pd < "2026-08":
                continue
            if "grosmimi" not in (r.get("source_keywords") or "").lower():
                continue
            h = (r.get("username") or "").strip().lstrip("@").lower()
            if h and (h not in out or pd < out[h]):
                out[h] = pd
    return out


def build_journey(ledger: dict, contract_periods: dict[str, str],
                  followers: dict[str, int], first_posts: dict[str, str]) -> list[list]:
    """인플루언서별 여정 행 — [handle, followers, tier, reachout, reply, contract, post, note].

    대상 = 리치아웃 스레드 전체(코호트 이전 포함 — 완전 보존 스레드는 7월 이전 발신일도 정확)
    ∪ 계약/투고 실적 있는 핸들. reachout: 잘린 스레드(백필 시점 20개 초과)는 '미상(잘림)'.
    """
    us = lambda s: s.strip("_")
    followers_us = {us(h): f for h, f in followers.items()}
    posts_us = {us(h): d for h, d in first_posts.items()}
    contracts_us = {us(h): d for h, d in contract_periods.items()}

    # 스레드 분석 (peer 별 최선 스레드 = 가장 이른 첫 관측)
    th: dict[str, dict] = {}
    for t in ledger["threads"].values():
        p = (t.get("peer") or "").strip().lower()
        msgs = t.get("messages") or []
        if not p or not msgs:
            continue
        first_ts = parse_ts(msgs[0].get("ts", ""))
        if not first_ts:
            continue
        pre = sum(1 for m in msgs
                  if (mts := parse_ts(m.get("ts", ""))) is not None and mts < BACKFILL_AT)
        reply_ts = None
        if msgs[0].get("dir") == "out":
            for m in msgs:
                ts = parse_ts(m.get("ts", ""))
                if m.get("dir") == "in" and ts and ts > first_ts:
                    reply_ts = ts
                    break
        cur = {"first_dir": msgs[0].get("dir"), "first_ts": first_ts,
               "reply_ts": reply_ts, "complete": pre < 20}
        if p not in th or first_ts < th[p]["first_ts"]:
            th[p] = cur

    th_us = {us(p): v for p, v in th.items()}
    peers = set(th)
    # 언더스코어 표기 편차 dedup — 같은 인물이 WL "_h_" / DM "h" 로 2행 나지 않게
    # 정규화 키당 대표 표기 1개 (DM peer 표기 우선)
    canon: dict[str, str] = {}
    for h in sorted(peers):
        canon.setdefault(us(h), h)
    for h in sorted(contract_periods):
        canon.setdefault(us(h), h)
    for h in sorted(first_posts):
        if us(h) in canon or h in peers:   # 투고만 있는 US 혼입 배제 (DM·계약 연고 있는 핸들만)
            canon.setdefault(us(h), h)
    targets = set(canon.values())

    rows = []
    for h in sorted(targets):
        t = th.get(h) or th_us.get(us(h))
        f = followers.get(h)
        if f is None:
            f = followers_us.get(us(h))
        contract = contract_periods.get(h) or contracts_us.get(us(h), "")
        post = first_posts.get(h) or posts_us.get(us(h), "")
        if t is None and not contract and not post:
            continue
        reachout = reply = ""
        note = ""
        if t is None:
            note = "DM 없음"
        elif t["first_dir"] == "out":
            if t["complete"]:
                reachout = t["first_ts"].date().isoformat()
            else:
                reachout = "미상(잘림)"   # 실발신은 관측 첫 메시지보다 이전 — 20개 창 소급불가
                note = "잘림"
            reply = t["reply_ts"].date().isoformat() if t["reply_ts"] else ""
        else:
            if t["complete"]:
                note = "인바운드"          # 상대 선발신 — 리치아웃 아님
            else:
                reachout = "미상(잘림)"
                note = "잘림"
        # 표시 범위 = 8월~ 만 (2026-08-27 세은 확정: "8월 리치아웃 기준/8월 업로드 기준 두 가지,
        # 그 전 정보 불필요") — 8월 이후 리치아웃이거나 8월 이후 투고가 있는 행만.
        aug_reachout = reachout not in ("", "미상(잘림)") and reachout >= "2026-08"
        aug_post = bool(post)   # first_posts 는 이미 2026-08~ 컷
        if not (aug_reachout or aug_post):
            continue
        rows.append([h, f if f is not None else "", tier_of(f), reachout, reply, contract, post, note])
    # 최근 활동 순 (리치아웃일 우선, 미상은 계약/투고일)
    rows.sort(key=lambda r: max(r[3] if r[3] and r[3] != "미상(잘림)" else "", r[5], r[6]), reverse=True)
    return rows


def write_follower_cache_sheet(gc) -> int:
    """팔로워 캐시 전량 → 'Follower Cache' 탭 — meta-app KPI 티어(Unknown 제거)의 최종 폴백 소스.
    (앱은 로컬 data/ 파일을 못 읽으므로 시트로 발행, 2026-08-27 세은 지시)"""
    if not FOLLOWERS_CACHE.exists():
        return 0
    try:
        d = json.loads(FOLLOWERS_CACHE.read_text(encoding="utf-8"))
    except ValueError:
        print("  [WARN] 팔로워 캐시 손상 — Follower Cache 탭 갱신 스킵")
        return 0
    rows = [[h, e.get("followers"), e.get("source", ""), e.get("at", "")]
            for h, e in sorted((d.get("handles") or {}).items())
            if isinstance((e or {}).get("followers"), (int, float))]
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet("Follower Cache")
    except Exception:
        ws = sh.add_worksheet(title="Follower Cache", rows=max(1000, len(rows) + 20), cols=6)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    try:
        if ws.row_count < len(rows) + 5:
            ws.resize(rows=len(rows) + 20)
        ws.clear()
        ws.update(values=[["Handle", "Followers", "Source", "At", f"updated {now}"]] + rows,
                  range_name="A1")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('Follower Cache' 탭) — {e}") from e
    return len(rows)


def write_journey_sheet(gc, rows: list[list]) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB_JOURNEY)
    except Exception:
        # cols=10 = 데이터 9열 + 여유 1열 (수기 메모용 헤드룸)
        ws = sh.add_worksheet(title=OUT_TAB_JOURNEY, rows=max(1200, len(rows) + 20), cols=10)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Handle", "Followers", "Tier", "Reachout", "Reply", "Contract", "Post", "Note", f"updated {now}"]]
    note = [["여정 = 리치아웃(DM 원장)→답장→계약(WL 운영기간)→포스팅(DK 실투고 최초일). "
             "미상(잘림) = 2026-08-25 수집 개시 전 20개 창 초과 스레드 — 발신일 소급불가"]]
    try:
        if ws.row_count < len(rows) + 7:
            ws.resize(rows=len(rows) + 20)
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
        ws.update(values=note, range_name=f"A{len(rows) + 3}")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB_JOURNEY}' 탭) — {e}") from e


def build_monthly(threads: dict, contract_set: set[str]) -> list[list]:
    """월별 코호트 (리치아웃 날짜 기준 — 주간 합산 아님, 월 경계 정확) + TOTAL 행."""
    us = lambda s: s.strip("_")
    contract_us = {us(h): h for h in contract_set}
    monthly = defaultdict(lambda: {"reachout": 0, "reply": 0, "contract": 0})
    matched = set()
    for peer, info in threads.items():
        mo = info["reachout_ts"].strftime("%Y-%m")
        monthly[mo]["reachout"] += 1
        if info["reply_ts"]:
            monthly[mo]["reply"] += 1
        hit = peer if peer in contract_set else contract_us.get(us(peer), "")
        if hit and hit not in matched:
            monthly[mo]["contract"] += 1
            matched.add(hit)
    rate = lambda n, d: f"{n / d:.0%}" if d else "-"
    rows = []
    for mo in sorted(monthly):
        m = monthly[mo]
        rows.append([mo, m["reachout"], m["reply"], rate(m["reply"], m["reachout"]),
                     m["contract"], rate(m["contract"], m["reachout"])])
    tr = sum(m["reachout"] for m in monthly.values())
    tp = sum(m["reply"] for m in monthly.values())
    tc = sum(m["contract"] for m in monthly.values())
    rows.append(["TOTAL", tr, tp, rate(tp, tr), tc, rate(tc, tr)])
    return rows


def write_monthly_sheet(gc, rows: list[list]) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB_MONTHLY)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB_MONTHLY, rows=200, cols=8)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Month", "Reachout", "Reply", "Reply %", "Contract", "Contract %", "", f"updated {now}"]]
    try:
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB_MONTHLY}' 탭) — {e}") from e


def write_sheet(gc, rows: list[list], meta: dict) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB, rows=max(1000, len(rows) + 20), cols=10)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Week Start (Mon, JST)", "Reachout", "Reply", "Reply %",
               "Contract", "Contract %", "Post", "Post %", "Low Confidence", f"updated {now}"]]
    ou, nd = meta["contracts_origin_unknown"], meta["contracts_no_dm"]
    ps = meta.get("contracts_pre_start", [])
    trunc = lambda lst: ", ".join(lst[:30]) + (f" 외 {len(lst) - 30}건" if len(lst) > 30 else "")
    try:
        if ws.row_count < len(rows) + 7:
            ws.resize(rows=len(rows) + 20)
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
        note_row = len(rows) + 3
        ws.update(values=[
            [f"집계 범위 = 2026-08-01(JST)~ 리치아웃 코호트"],
            [f"8월 이전 리치아웃 계약 {len(ps)}건 (범위 외): {trunc(ps)}"],
            [f"코호트 미귀속 계약 {len(ou)}건 — DM 있으나 최초 발송일 소급불가(과거 20개 캡): {trunc(ou)}"],
            [f"DM 스레드 없는 계약 {len(nd)}건 (타 경로/표기 상이): {trunc(nd)}"],
        ], range_name=f"A{note_row}")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB}' 탭) — {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ledger = load_ledger()
    threads = analyze_threads(ledger)
    print(f"리치아웃 스레드(우리가 먼저 발신): {len(threads)}개 "
          f"/ 전체 {len(ledger['threads'])}개")

    try:
        from sheets_utils import get_sheets_client
    except ImportError as e:
        raise SystemExit(f"ERROR: sheets_utils import 실패 — {e}") from e
    gc = get_sheets_client()
    contract_set = fetch_contract_handles(gc)
    print(f"WL 계약 핸들(고유): {len(contract_set)}건")

    all_peers = {norm_handle(t.get("peer", "")) for t in ledger["threads"].values()}
    all_peers.discard("")

    # 8월 이전 리치아웃은 집계 범위 외 — 그쪽에 매칭되는 계약은 별도 각주로만
    us = lambda s: s.strip("_")
    pre = {p: i for p, i in threads.items() if i["reachout_ts"] < COHORT_START}
    threads = {p: i for p, i in threads.items() if i["reachout_ts"] >= COHORT_START}
    pre_us = {us(p) for p in pre}
    pre_matched = sorted(h for h in contract_set if h in pre or us(h) in pre_us)
    contract_set = contract_set - set(pre_matched)
    print(f"집계 범위: {COHORT_START:%Y-%m-%d}~ — 범위 내 리치아웃 {len(threads)}개"
          f" / 범위 외(8월 이전) {len(pre)}개, 범위 외 매칭 계약 {len(pre_matched)}건")

    first_posts = fetch_dk_first_posts()
    rows, meta = build_weekly(threads, contract_set, all_peers, first_posts)
    meta["contracts_pre_start"] = pre_matched
    print(f"\n{'주차(월)':<12}{'리치아웃':>8}{'답장':>6}{'답장률':>8}{'계약':>6}{'계약률':>8}{'포스팅':>7}{'포스팅률':>9}{'저신뢰':>8}")
    for r in rows:
        print(f"{r[0]:<12}{r[1]:>8}{r[2]:>6}{r[3]:>8}{r[4]:>6}{r[5]:>8}{r[6]:>7}{r[7]:>9}{r[8]:>8}")
    print(f"\n합계 — 리치아웃 {meta['total_reachout']} / 답장 {meta['total_reply']}"
          f" / 계약(DM매칭) {meta['total_contract']}"
          f" / 소급불가 계약 {len(meta['contracts_origin_unknown'])}건"
          f" / DM 없는 계약 {len(meta['contracts_no_dm'])}건")

    monthly_rows = build_monthly(threads, contract_set)
    print("\n월별:")
    for r in monthly_rows:
        print(f"  {r[0]:<9}{r[1]:>6}{r[2]:>6}{r[3]:>7}{r[4]:>6}{r[5]:>7}")

    # 팔로워 티어별 (2026-08-27 세은 지시 — 티어별 응답률, 전체/월/주 scope 분해)
    followers = load_followers()
    tier_rows = build_tier(threads, contract_set, followers)
    # 행 = [scope, tier, reachout, reply, reply%, contract, contract%] — 커버리지는 ALL scope 기준
    unknown = next((r[2] for r in tier_rows if r[0] == "ALL" and r[1] == "미확인"), 0)
    total_r = next((r[2] for r in tier_rows if r[0] == "ALL" and r[1] == "TOTAL"), 0)
    coverage = f"팔로워 확보 {total_r - unknown}/{total_r}명 (미확인 {unknown}명)"
    n_scopes = len({r[0] for r in tier_rows})
    print(f"\n티어별 — ALL scope ({coverage} · 시트엔 월/주 포함 {n_scopes}개 scope):")
    for r in tier_rows:
        if r[0] != "ALL":
            continue
        print(f"  {r[1]:<8}{r[2]:>6}{r[3]:>6}{r[4]:>7}{r[5]:>6}{r[6]:>7}")

    # 인플루언서별 여정 맵핑 (2026-08-27 대표님 지시 — 리치아웃→답장→계약→포스팅 개인 단위)
    contract_periods = fetch_contract_periods(gc)
    journey_rows = build_journey(ledger, contract_periods, followers, first_posts)
    n_known = sum(1 for r in journey_rows if r[3] and r[3] != "미상(잘림)")
    print(f"\n여정 맵핑: {len(journey_rows)}명 (리치아웃일 확실 {n_known} / "
          f"투고일 확보 {sum(1 for r in journey_rows if r[6])})")

    if args.dry_run:
        print("\nDRY RUN — 시트 미반영")
        return 0
    write_sheet(gc, rows, meta)
    write_monthly_sheet(gc, monthly_rows)
    write_tier_sheet(gc, tier_rows, coverage)
    write_journey_sheet(gc, journey_rows)
    n_cache = write_follower_cache_sheet(gc)
    print(f"\n시트 반영 완료 → '{OUT_TAB}' + '{OUT_TAB_MONTHLY}' + '{OUT_TAB_TIER}' + "
          f"'{OUT_TAB_JOURNEY}' + 'Follower Cache'({n_cache}행) 탭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
