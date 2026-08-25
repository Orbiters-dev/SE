"""IG DM 수집기 — @grosmimi_japan 전 스레드를 메시지 원장(JSON)으로 적재.

Instagram API with Instagram Login (claude connection-IG 앱, 2026-08-25 개통).
- 대화 목록 → 스레드별 최근 20개 메시지(발신자/시각/본문) 수집
  ※ 20개 = Meta API 하드 제약 (공식 문서: 스레드당 최근 20개만 상세 조회 가능,
    더 오래된 메시지는 조회 시 에러). 페이지네이션으로 못 넘음.
- 원장 data/ig_dm_ledger.json 에 증분 머지 (메시지 id 기준 union —
  매일 돌리면 20개 창이 굴러가며 신규 메시지가 누적 보존됨.
  첫 백필 시점에 이미 20개를 넘긴 스레드의 과거분만 미확보)
- 아웃바운드(우리 발신) 본문만 저장 (템플릿 분류용). 인바운드 본문은 저장 안 함.

Usage:
    python tools/ig_dm_collector.py            # 증분 (updated_time 기준)
    python tools/ig_dm_collector.py --full     # 전 스레드 재수집 (백필)
    python tools/ig_dm_collector.py --refresh-token-only
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "ig_dm_ledger.json"
# 호스트 주의: 이 도구는 "Instagram API with Instagram Login" 루트 (IGAA… 토큰) —
# 정식 호스트가 graph.instagram.com 이다. graph.facebook.com 은 별개인 구형
# Messenger Platform(페이지 토큰) 루트. 2026-08-25 실측: 이 호스트로 760 스레드
# / 4,292 메시지 수집 성공. 20개 제한 근거 = 공식 문서
# developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/conversations-api
# ("you can only get details about the 20 most recent messages... older → deleted error" — 실측 일치)
GRAPH = "https://graph.instagram.com/v21.0"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

TOKEN = os.environ.get("IG_DM_ACCESS_TOKEN", "")


def api_get(url: str, retries: int = 3) -> dict:
    last_err = ""
    for i in range(retries):
        try:
            raw = urllib.request.urlopen(url, timeout=60).read()
            try:
                return json.loads(raw)
            except ValueError:
                last_err = f"non-JSON response: {raw[:200]!r}"
                time.sleep(5 * (i + 1))
                continue
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            # rate limit (code 4/17/613) → 백오프 후 재시도
            if e.code in (400, 403, 429) and ('"code":4' in body or '"code":17' in body or '"code":613' in body):
                wait = 60 * (i + 1)
                print(f"  rate limited — {wait}s 대기 후 재시도")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = f"network: {e}"
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"API 재시도 소진 ({last_err})")


def refresh_token_if_needed() -> None:
    """60일 토큰 연장. 새 토큰이 오면 .env 갱신."""
    url = (f"https://graph.instagram.com/refresh_access_token"
           f"?grant_type=ig_refresh_token&access_token={urllib.parse.quote(TOKEN)}")
    d = api_get(url)
    days = d.get("expires_in", 0) // 86400
    new_tok = d.get("access_token", "")
    print(f"token refresh OK — {days}일 남음")
    active = new_tok if new_tok else TOKEN
    # 활성 토큰을 .tmp 에 기록 — GH Actions 가 시크릿 자가 갱신에 사용 (gitignored)
    tmp_tok = ROOT / ".tmp" / "ig_token_current.txt"
    tmp_tok.parent.mkdir(parents=True, exist_ok=True)
    tmp_tok.write_text(active, encoding="utf-8")
    if new_tok and new_tok != TOKEN:
        import re
        env_path = ROOT / ".env"
        if env_path.exists():  # GH Actions 러너엔 .env 없음 — 로컬에서만 갱신
            text = env_path.read_text(encoding="utf-8")
            new_text, n = re.subn(r"(?m)^IG_DM_ACCESS_TOKEN=.*$", f"IG_DM_ACCESS_TOKEN={new_tok}", text)
            if n == 0:  # 라인이 없으면 append (치환 실패로 만료 토큰이 남는 것 방지)
                new_text = text.rstrip("\n") + f"\nIG_DM_ACCESS_TOKEN={new_tok}\n"
            env_path.write_text(new_text, encoding="utf-8")
            print(f"새 토큰으로 .env 갱신됨 (치환 {n}건)")
        else:
            print("새 토큰 발급됨 — .env 없음 (Actions), .tmp/ig_token_current.txt 만 기록")


def load_ledger() -> dict:
    if LEDGER.exists():
        d = json.loads(LEDGER.read_text(encoding="utf-8"))  # 손상 시 여기서 즉사 — 침묵 유실 금지
        if not isinstance(d.get("threads"), dict):
            raise RuntimeError(f"원장 스키마 손상: threads 키 없음 ({LEDGER})")
        for cid, t in d["threads"].items():
            if not isinstance(t.get("messages"), list):
                raise RuntimeError(f"원장 스키마 손상: {cid} messages 가 list 아님")
        return d
    return {"ig_user_id": "", "generated_at": "", "threads": {}}


def save_ledger(ledger: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(LEDGER)


def fetch_conversations() -> list[dict]:
    out = []
    seen_urls = set()
    url = (f"{GRAPH}/me/conversations?platform=instagram&limit=50"
           f"&fields=id,updated_time,participants&access_token={urllib.parse.quote(TOKEN)}")
    pages = 0
    while url and pages < 500:  # 무한 루프 가드 (500p × 50 = 25,000 스레드 상한)
        if url in seen_urls:
            print("  경고: 페이지네이션 커서 반복 감지 — 중단")
            break
        seen_urls.add(url)
        d = api_get(url)
        out.extend(d.get("data") or [])
        url = (d.get("paging") or {}).get("next")
        pages += 1
        time.sleep(0.2)
    return out


def fetch_messages(cid: str) -> list[dict]:
    url = (f"{GRAPH}/{cid}?fields=messages.limit(20){{id,created_time,from,message}}"
           f"&access_token={urllib.parse.quote(TOKEN)}")
    d = api_get(url)
    return ((d.get("messages") or {}).get("data")) or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="전 스레드 재수집")
    ap.add_argument("--refresh-token-only", action="store_true")
    args = ap.parse_args()

    if not TOKEN:
        print("ERROR: IG_DM_ACCESS_TOKEN 없음 (.env)")
        return 1

    refresh_token_if_needed()
    if args.refresh_token_only:
        return 0

    ledger = load_ledger()
    threads = ledger["threads"]

    me = api_get(f"{GRAPH}/me?fields=user_id,username&access_token={urllib.parse.quote(TOKEN)}")
    my_id = str(me.get("user_id") or me.get("id"))
    ledger["ig_user_id"] = my_id
    print(f"계정: {me.get('username')} ({my_id})")

    convos = fetch_conversations()
    print(f"대화 스레드: {len(convos)}개")

    to_fetch = []
    for c in convos:
        cid = c["id"]
        parts = ((c.get("participants") or {}).get("data")) or []
        peer = next((p for p in parts if str(p.get("id")) != my_id), {})
        t = threads.setdefault(cid, {"peer": "", "peer_id": "", "updated_time": "", "messages": []})
        t["peer"] = (peer.get("username") or t["peer"] or "").lower()
        t["peer_id"] = str(peer.get("id") or t["peer_id"] or "")
        new_upd = c.get("updated_time", "")
        if args.full or new_upd != t["updated_time"] or not t["messages"]:
            to_fetch.append((cid, new_upd))

    print(f"메시지 수집 대상: {len(to_fetch)}개 스레드")
    fetched = errors = 0
    for i, (cid, new_upd) in enumerate(to_fetch, 1):
        try:
            msgs = fetch_messages(cid)
        except RuntimeError as e:
            errors += 1
            print(f"  [{i}] {cid[:20]}... FAIL: {e}")
            continue
        t = threads[cid]
        known = {m["id"] for m in t["messages"]}
        for m in msgs:
            mid = m.get("id")
            if not mid or mid in known:
                continue
            sender = str((m.get("from") or {}).get("id", ""))
            direction = "out" if sender == my_id else "in"
            rec = {"id": mid, "ts": m.get("created_time", ""), "dir": direction}
            text = m.get("message")
            if direction == "out" and isinstance(text, str) and text:
                rec["text"] = text[:500]
            t["messages"].append(rec)
        t["messages"].sort(key=lambda m: m["ts"])
        # capped: 20개 창 가득참 = 창 이전 이력 미확보 "가능성" 신호 (정확히 20건인
        # 스레드는 오탐이지만, 집계에서 보수적으로 저신뢰 처리하는 용도라 허용)
        t["capped"] = len(msgs) >= 20
        t["updated_time"] = new_upd
        fetched += 1
        if i % 50 == 0:
            save_ledger(ledger)
            print(f"  진행 {i}/{len(to_fetch)}")
        time.sleep(0.15)

    ledger["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_ledger(ledger)
    total_msgs = sum(len(t["messages"]) for t in threads.values())
    print(f"완료 — 스레드 {len(threads)}, 수집 {fetched}, 실패 {errors}, 원장 메시지 {total_msgs}건")
    print(f"원장: {LEDGER}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
