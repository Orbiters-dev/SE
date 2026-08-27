"""IG DM 리치아웃 peer 팔로워 확보 → data/ig_dm_followers.json 캐시.

티어별 리치아웃/답장률 분해용 (2026-08-27 세은 지시). 소스 3단 폴백:
1. DK content_posts (무료) — 콜라보 이력 있는 핸들
2. 트래커 Master DB 팔로워 텍스트 (무료) — 등록 크리에이터
3. Apify instagram-profile-scraper (유료, 미확보분만) — 핸들당 1회 영구 캐시

캐시 스키마: {"handles": {handle: {"followers": int|null, "source": str, "at": "YYYY-MM-DD"}}}
- followers=null = 조회 실패 (비공개/삭제 계정 등). RETRY_FAILED_DAYS 경과 후 자동 재시도,
  즉시 재시도는 --retry-failed. followers=0 은 유효값 (실패 아님).
- 무료 소스 로드 실패 시 그 실행에선 Apify 스킵 (무료로 채울 수 있는 핸들에
  과금 방지 — 다음 일일 실행에서 재시도).

Usage:
    python tools/ig_dm_follower_enrich.py               # 미확보 핸들만 증분
    python tools/ig_dm_follower_enrich.py --no-apify    # 무료 소스만
    python tools/ig_dm_follower_enrich.py --retry-failed
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "ig_dm_ledger.json"
CACHE = ROOT / "data" / "ig_dm_followers.json"
TRACKER_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
MASTER_GID = 1589913586
DK_URL = ("https://orbitools.orbiters.co.kr/api/datakeeper/query/"
          "?table=content_posts&limit=20000&fields=username,followers")
# meta-app lib/datakeeper.ts 와 동일 read 토큰 (로테이션 시 함께 교체)
DK_TOKEN_FALLBACK = "dk_SE_7de6ec154f3d7b7bd0cc571a9e5b7220e125af197cf9dc1d40b893b086e13023"
APIFY_ACTOR = "apify~instagram-profile-scraper"
APIFY_BATCH = 15          # actor timeout=280s(아래 URL 파라미터) 내 안전 배치 — run-sync API 한도 300s 미만으로 설정
RETRY_FAILED_DAYS = 30    # 실패(null) 기록 자동 재시도 주기

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def norm(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


def load_cache() -> dict:
    if CACHE.exists():
        try:
            d = json.loads(CACHE.read_text(encoding="utf-8"))
        except ValueError as e:
            raise SystemExit(f"ERROR: 캐시 JSON 손상 ({CACHE}): {e} — 수동 확인 필요(침묵 초기화 금지)") from e
        if isinstance(d.get("handles"), dict):
            return d
    return {"handles": {}}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(CACHE)


JST = timezone(timedelta(hours=9))
# 집계 코호트 시작점 (ig_dm_kpi_aggregate.py COHORT_START 와 동일) — 이전 리치아웃은
# 집계 범위 외라 유료 조회 대상에서 제외 (Apify 낭비 방지)
COHORT_START = datetime(2026, 8, 1, tzinfo=JST)


def reachout_peers() -> list[str]:
    """우리가 먼저 연 스레드의 peer — 집계 코호트(2026-08~, JST) 범위만."""
    if not LEDGER.exists():
        raise SystemExit(f"ERROR: DM 원장 없음 — 먼저 ig_dm_collector.py 실행 ({LEDGER})")
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"ERROR: DM 원장 JSON 손상 ({LEDGER}): {e}") from e
    if not isinstance(ledger.get("threads"), dict):
        raise SystemExit(f"ERROR: DM 원장 스키마 손상 — threads 키 없음 ({LEDGER})")
    peers = set()
    for t in ledger["threads"].values():
        msgs = t.get("messages") or []
        if not (msgs and msgs[0].get("dir") == "out"):
            continue
        try:
            ts = datetime.strptime(msgs[0].get("ts", ""), "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
        except (ValueError, TypeError):
            continue
        if ts < COHORT_START:
            continue
        p = norm(t.get("peer", ""))
        if p:
            peers.add(p)
    return sorted(peers)


def fetch_dk_followers() -> dict[str, int] | None:
    """실패 시 None (빈 dict 와 구분 — 호출부에서 Apify 스킵 판단)."""
    tok = os.environ.get("DK_SE_READ_TOKEN") or DK_TOKEN_FALLBACK
    try:
        req = urllib.request.Request(DK_URL, headers={"Authorization": f"Bearer {tok}"})
        d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  [WARN] DK 조회 실패: {str(e)[:120]}")
        return None
    rows = d if isinstance(d, list) else d.get("rows", [])
    out: dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        h = norm(str(r.get("username") or ""))
        f = r.get("followers")
        if h and isinstance(f, (int, float)) and f > 0:   # DK 의 0/None = 미수집 (유효 0 아님)
            out[h] = max(out.get(h, 0), int(f))
    return out


def parse_followers_text(s: str) -> int | None:
    """'91k' / '12,345' / '1.2M' → int. 파싱 불가/0 = None (Master DB 공란·오기입 취급)."""
    m = re.match(r"^([\d,.]+)\s*([km])?$", (s or "").strip().lower())
    if not m:
        return None
    try:
        base = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"m": 1_000_000, "k": 1_000}.get(m.group(2) or "", 1)
    return round(base * mult) or None


def fetch_master_followers() -> dict[str, int] | None:
    """실패 시 None. 컬럼 인덱스는 헤더 어서션으로 검증 (lib/influencer-kpi.ts 와 동일 규약)."""
    url = f"https://docs.google.com/spreadsheets/d/{TRACKER_ID}/export?format=csv&gid={MASTER_GID}"
    try:
        text = urllib.request.urlopen(url, timeout=60).read().decode("utf-8")
        rows = list(csv.reader(io.StringIO(text)))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  [WARN] Master DB 조회 실패: {str(e)[:120]}")
        return None
    # 헤더 r2(인덱스 1) 실측(2026-08-27): [0]='Creator ID' · [16]='@ID (link)' · [18]='Followers'
    # 세 컬럼 전부 어서션 — 불일치 시 이 소스 스킵 (침묵 오염 방지)
    hdr = rows[1] if len(rows) > 1 else []
    at = lambda i: (hdr[i] if len(hdr) > i else "").strip()
    if at(0) != "Creator ID" or at(16) != "@ID (link)" or at(18) != "Followers":
        print(f"  [WARN] Master DB 헤더 불일치: [0]={at(0)!r} [16]={at(16)!r} [18]={at(18)!r} — 이 소스 스킵")
        return None
    out: dict[str, int] = {}
    for r in rows[2:]:
        if len(r) > 18:
            h, f = norm(r[16]), parse_followers_text(r[18])
            if h and f:
                out[h] = f
    return out


def fetch_apify_batch(handles: list[str]) -> dict[str, int | None]:
    """배치 조회 (배치당 1회 재시도). 응답에 없는 핸들 = 실패(null) 확정 기록 (비공개/삭제)."""
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("  [WARN] APIFY_API_TOKEN 없음 — Apify 단계 스킵")
        return {}
    out: dict[str, int | None] = {}
    for i in range(0, len(handles), APIFY_BATCH):
        batch = handles[i:i + APIFY_BATCH]
        url = (f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
               f"?token={urllib.parse.quote(token)}&timeout=280")
        items = None
        for attempt in range(2):
            req = urllib.request.Request(
                url, data=json.dumps({"usernames": batch}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                items = json.loads(urllib.request.urlopen(req, timeout=300).read())
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                print(f"  [WARN] Apify 배치 {i // APIFY_BATCH + 1} 시도 {attempt + 1} 실패: {str(e)[:120]}")
                time.sleep(10)
        if not isinstance(items, list):
            print(f"  [WARN] 배치 {i // APIFY_BATCH + 1} 미기록 (다음 실행 재시도)")
            continue
        got: dict[str, int] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            h = norm(str(it.get("username") or ""))
            fc = it.get("followersCount")
            if h and isinstance(fc, (int, float)) and fc >= 0:   # 0 = 유효 팔로워 수
                got[h] = int(fc)
        for h in batch:
            out[h] = got.get(h)
        print(f"  Apify 배치 {i // APIFY_BATCH + 1}: {len(batch)}건 중 {len(got)}건 확보")
        time.sleep(1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-apify", action="store_true")
    ap.add_argument("--retry-failed", action="store_true", help="실패(null) 기록 즉시 재시도")
    args = ap.parse_args()

    peers = reachout_peers()
    if not peers:
        print("리치아웃 peer 0명 — 종료")
        return 0
    cache = load_cache()
    handles = cache["handles"]
    today = date.today()
    retry_before = (today - timedelta(days=RETRY_FAILED_DAYS)).isoformat()

    def resolved(h: str) -> bool:
        e = handles.get(h)
        if not e:
            return False
        if e.get("followers") is None:   # 실패 기록 — 30일 경과 또는 --retry-failed 면 재시도
            if args.retry_failed or (e.get("at", "") <= retry_before):
                return False
        return True

    todo = [p for p in peers if not resolved(p)]
    print(f"리치아웃 peer {len(peers)}명 / 캐시 확보 {len(peers) - len(todo)} / 조회 대상 {len(todo)}")
    if not todo:
        print("전원 캐시 확보 — 조회 생략")
        return 0

    # 표기 편차 흡수 = 앞뒤 언더스코어만 (aggregate 와 동일 규약 — WL "_musukono_kiroku_" vs
    # DM "musukono_kiroku" 류). 내부 언더스코어는 별개 계정 구분자라 제거하면 오매칭 위험.
    us = lambda s: s.strip("_")

    dk = fetch_dk_followers()
    master = fetch_master_followers()
    free_source_failed = dk is None or master is None
    dk = dk or {}
    master = master or {}
    dk_us = {us(h): f for h, f in dk.items()}
    master_us = {us(h): f for h, f in master.items()}
    print(f"소스 로드 — DK {len(dk)}핸들 / Master DB {len(master)}핸들")

    # 0 팔로워 의미: DK·Master 는 소스 자체가 0/공란=미수집이라 dict 에 0이 없음(>0 필터).
    # 실측 0 은 Apify 만 가능 (fetch_apify_batch 에서 유효값 처리). 조회는 None 체크로만 분기.
    def lookup(m1: dict, m2: dict, h: str) -> int | None:
        v = m1.get(h)
        return v if v is not None else m2.get(us(h))

    remaining = []
    for h in todo:
        f, src = lookup(dk, dk_us, h), "dk"
        if f is None:
            f, src = lookup(master, master_us, h), "master"
        if f is not None:
            handles[h] = {"followers": f, "source": src, "at": today.isoformat()}
        else:
            remaining.append(h)
    print(f"무료 소스 확보 {len(todo) - len(remaining)}건 / 잔여 {len(remaining)}건")

    if remaining and free_source_failed:
        print("  [WARN] 무료 소스 일부 실패 — 이번 실행 Apify 스킵 (무료로 채울 핸들 과금 방지, 다음 실행 재시도)")
    elif remaining and not args.no_apify:
        apify = fetch_apify_batch(remaining)
        for h, f in apify.items():
            handles[h] = {
                "followers": f,
                "source": "apify" if f is not None else "apify_fail",
                "at": today.isoformat(),
            }

    save_cache(cache)
    got = sum(1 for p in peers if (handles.get(p) or {}).get("followers") is not None)
    print(f"완료 — 캐시 {len(handles)}핸들, 리치아웃 peer 팔로워 확보 {got}/{len(peers)} ({got / len(peers):.0%})")
    print(f"캐시: {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
