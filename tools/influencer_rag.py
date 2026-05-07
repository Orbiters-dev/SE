#!/usr/bin/env python3
"""
Influencer RAG — 인플루언서 프로필 + DM 대화 기록 관리
JSON 기반 경량 RAG. 벡터 DB 없이 이름 매칭 + 키워드 검색.

사용법:
  python tools/influencer_rag.py --status                    # 전체 현황
  python tools/influencer_rag.py --lookup ゆきな              # 프로필 조회
  python tools/influencer_rag.py --search "원터치"            # 키워드 검색
  python tools/influencer_rag.py --list                       # 전체 인플루언서 목록
  python tools/influencer_rag.py --list --stage "STEP 10.5"   # 스테이지별 필터
  python tools/influencer_rag.py --update ゆきな stage "STEP 11"  # 필드 업데이트
  python tools/influencer_rag.py --log ゆきな "DM 내용..."     # 대화 로그 저장
  python tools/influencer_rag.py --history ゆきな              # 대화 이력 조회
  python tools/influencer_rag.py --create                      # 새 프로필 생성 (interactive)
"""

import argparse
import json
import os
import sys
import io
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows cp949 인코딩 문제 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
RAG_DIR = BASE_DIR / ".tmp" / "influencer_rag"
PROFILES_DIR = RAG_DIR / "profiles"
CONVOS_DIR = RAG_DIR / "conversations"


def ensure_dirs():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    CONVOS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """이름을 파일명으로 안전하게 변환"""
    return re.sub(r'[<>:"/\\|?*]', '_', name.strip())


def now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def now_iso() -> str:
    return datetime.now(JST).isoformat()


# ── Profile CRUD ──────────────────────────────────────────

def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{sanitize_filename(name)}.json"


def load_profile(name: str) -> dict | None:
    p = profile_path(name)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # fuzzy match: 부분 매칭
    for f in PROFILES_DIR.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        if name.lower() in data.get("name", "").lower():
            return data
        if name.lower() in data.get("handle", "").lower():
            return data
    return None


def save_profile(profile: dict):
    p = profile_path(profile["name"])
    p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all_profiles() -> list[dict]:
    profiles = []
    for f in sorted(PROFILES_DIR.glob("*.json")):
        try:
            profiles.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return profiles


def create_profile(name: str, **kwargs) -> dict:
    """새 인플루언서 프로필 생성"""
    profile = {
        "name": name,
        "handle": kwargs.get("handle", ""),
        "followers": kwargs.get("followers", 0),
        "stage": kwargs.get("stage", "STEP 1"),
        "product": kwargs.get("product", ""),
        "color": kwargs.get("color", ""),
        "volume": kwargs.get("volume", ""),
        "compensation": kwargs.get("compensation", "gifting"),
        "compensation_amount": kwargs.get("compensation_amount", ""),
        "posting_date": kwargs.get("posting_date", ""),
        "contract_signed": kwargs.get("contract_signed", False),
        "shipped": kwargs.get("shipped", False),
        "tracking_number": kwargs.get("tracking_number", ""),
        "address": kwargs.get("address", ""),
        "phone": kwargs.get("phone", ""),
        "email": kwargs.get("email", ""),
        "full_name": kwargs.get("full_name", ""),
        "child_age_months": kwargs.get("child_age_months", ""),
        "notes": kwargs.get("notes", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "last_dm_date": now_jst(),
    }
    save_profile(profile)
    return profile


def update_profile(name: str, field: str, value) -> dict | None:
    """프로필 필드 업데이트"""
    profile = load_profile(name)
    if not profile:
        return None
    # boolean 변환
    if field in ("contract_signed", "shipped"):
        value = str(value).lower() in ("true", "1", "yes")
    # int 변환
    if field == "followers":
        try:
            value = int(value)
        except ValueError:
            pass
    profile[field] = value
    profile["updated_at"] = now_iso()
    save_profile(profile)
    return profile


# ── Conversation Log ──────────────────────────────────────

def convo_path(name: str) -> Path:
    return CONVOS_DIR / f"{sanitize_filename(name)}_log.jsonl"


def log_dm(name: str, message: str, direction: str = "received", summary: str = ""):
    """DM 대화 로그 저장 (append)"""
    entry = {
        "timestamp": now_iso(),
        "direction": direction,  # "received" = 인플루언서→우리, "sent" = 우리→인플루언서
        "message": message.strip(),
        "summary": summary,
    }
    p = convo_path(name)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # last_dm_date 업데이트
    profile = load_profile(name)
    if profile:
        profile["last_dm_date"] = now_jst()
        profile["updated_at"] = now_iso()
        save_profile(profile)


def load_conversation(name: str) -> list[dict]:
    """대화 이력 로드"""
    p = convo_path(name)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return entries


# ── Search ────────────────────────────────────────────────

def search_profiles(keyword: str) -> list[dict]:
    """키워드로 프로필 검색 (모든 필드 대상)"""
    keyword_lower = keyword.lower()
    results = []
    for profile in load_all_profiles():
        text = json.dumps(profile, ensure_ascii=False).lower()
        if keyword_lower in text:
            results.append(profile)
    return results


def extract_name_from_dm(dm_text: str) -> str | None:
    """DM 텍스트에서 인플루언서 이름 자동 추출"""
    # 패턴: 서명 (마지막 줄에 이름만 있는 경우)
    lines = [l.strip() for l in dm_text.strip().split("\n") if l.strip()]
    if lines:
        last_line = lines[-1]
        # 짧은 마지막 줄 = 서명일 가능성
        if len(last_line) <= 20 and not any(c in last_line for c in ["。", "、", "！", "？", "http"]):
            return last_line
    return None


# ── Display ───────────────────────────────────────────────

def format_profile(p: dict) -> str:
    """프로필을 보기 좋게 포맷"""
    lines = [
        f"━━━ {p['name']} ━━━",
        f"  IG: {p.get('handle', '-')}",
        f"  팔로워: {p.get('followers', '-')}",
        f"  스테이지: {p.get('stage', '-')}",
        f"  제품: {p.get('product', '-')} {p.get('volume', '')} ({p.get('color', '-')})",
        f"  보수: {p.get('compensation', '-')} {p.get('compensation_amount', '')}".rstrip(),
        f"  투고일: {p.get('posting_date', '-')}",
        f"  계약: {'✓' if p.get('contract_signed') else '✗'}  발송: {'✓' if p.get('shipped') else '✗'}",
        f"  마지막 DM: {p.get('last_dm_date', '-')}",
    ]
    if p.get("full_name"):
        lines.append(f"  성명: {p['full_name']}")
    if p.get("email"):
        lines.append(f"  이메일: {p['email']}")
    if p.get("child_age_months"):
        lines.append(f"  아이 월령: {p['child_age_months']}개월")
    if p.get("notes"):
        lines.append(f"  메모: {p['notes']}")
    return "\n".join(lines)


def format_conversation(entries: list[dict], limit: int = 20) -> str:
    """대화 이력 포맷"""
    if not entries:
        return "  (대화 기록 없음)"
    lines = []
    for e in entries[-limit:]:
        arrow = "← 수신" if e["direction"] == "received" else "→ 발신"
        ts = e["timestamp"][:16]
        msg_preview = e["message"][:80].replace("\n", " ")
        if len(e["message"]) > 80:
            msg_preview += "..."
        lines.append(f"  [{ts}] {arrow} {msg_preview}")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────

def main():
    ensure_dirs()

    parser = argparse.ArgumentParser(description="Influencer RAG")
    parser.add_argument("--status", action="store_true", help="전체 현황")
    parser.add_argument("--lookup", type=str, help="이름으로 프로필 조회")
    parser.add_argument("--search", type=str, help="키워드 검색")
    parser.add_argument("--list", action="store_true", help="전체 목록")
    parser.add_argument("--stage", type=str, help="스테이지 필터 (--list와 함께)")
    parser.add_argument("--update", nargs=3, metavar=("NAME", "FIELD", "VALUE"), help="프로필 업데이트")
    parser.add_argument("--log", nargs=2, metavar=("NAME", "MESSAGE"), help="DM 로그 저장")
    parser.add_argument("--direction", default="received", help="DM 방향: received/sent")
    parser.add_argument("--history", type=str, help="대화 이력 조회")
    parser.add_argument("--create", action="store_true", help="새 프로필 생성")
    parser.add_argument("--name", type=str, help="프로필 이름 (--create와 함께)")
    parser.add_argument("--handle", type=str, default="", help="IG 핸들")
    parser.add_argument("--followers", type=int, default=0)
    parser.add_argument("--product", type=str, default="")
    parser.add_argument("--color", type=str, default="")
    parser.add_argument("--volume", type=str, default="")
    parser.add_argument("--compensation", type=str, default="gifting")
    parser.add_argument("--posting-date", type=str, default="")
    parser.add_argument("--stage-init", type=str, default="STEP 1", help="초기 스테이지")
    parser.add_argument("--detect-name", type=str, help="DM 텍스트에서 이름 자동 추출")

    args = parser.parse_args()

    if args.status:
        profiles = load_all_profiles()
        print(f"\n📊 인플루언서 RAG 현황")
        print(f"  프로필 수: {len(profiles)}")
        convos = list(CONVOS_DIR.glob("*.jsonl"))
        print(f"  대화 로그: {len(convos)}개")
        if profiles:
            stages = {}
            for p in profiles:
                s = p.get("stage", "unknown")
                stages[s] = stages.get(s, 0) + 1
            print(f"\n  스테이지별:")
            for s, c in sorted(stages.items()):
                print(f"    {s}: {c}명")
        return

    if args.lookup:
        profile = load_profile(args.lookup)
        if profile:
            print(format_profile(profile))
            entries = load_conversation(profile["name"])
            if entries:
                print(f"\n  최근 대화 ({len(entries)}건):")
                print(format_conversation(entries, limit=5))
        else:
            print(f"  '{args.lookup}' 프로필을 찾을 수 없습니다.")
        return

    if args.search:
        results = search_profiles(args.search)
        if results:
            print(f"\n🔍 '{args.search}' 검색 결과: {len(results)}건\n")
            for p in results:
                print(format_profile(p))
                print()
        else:
            print(f"  '{args.search}' 검색 결과 없음")
        return

    if args.list:
        profiles = load_all_profiles()
        if args.stage:
            profiles = [p for p in profiles if args.stage.lower() in p.get("stage", "").lower()]
        if profiles:
            print(f"\n📋 인플루언서 목록 ({len(profiles)}명)\n")
            for p in profiles:
                status = f"{'✓계약' if p.get('contract_signed') else ''} {'✓발송' if p.get('shipped') else ''}".strip()
                print(f"  {p['name']:12s} | {p.get('stage', '-'):12s} | {p.get('product', '-'):20s} | {p.get('compensation', '-'):8s} | {status}")
        else:
            print("  등록된 인플루언서가 없습니다.")
        return

    if args.update:
        name, field, value = args.update
        profile = update_profile(name, field, value)
        if profile:
            print(f"  ✓ {name} → {field} = {value}")
        else:
            print(f"  '{name}' 프로필을 찾을 수 없습니다.")
        return

    if args.log:
        name, message = args.log
        log_dm(name, message, direction=args.direction)
        print(f"  ✓ {name} DM 로그 저장 ({args.direction})")
        return

    if args.history:
        profile = load_profile(args.history)
        if profile:
            entries = load_conversation(profile["name"])
            print(f"\n💬 {profile['name']} 대화 이력 ({len(entries)}건)\n")
            print(format_conversation(entries))
        else:
            print(f"  '{args.history}' 프로필을 찾을 수 없습니다.")
        return

    if args.create:
        if not args.name:
            print("  --name 필수")
            return
        profile = create_profile(
            name=args.name,
            handle=args.handle,
            followers=args.followers,
            product=args.product,
            color=args.color,
            volume=args.volume,
            compensation=args.compensation,
            posting_date=args.posting_date,
            stage=args.stage_init,
        )
        print(f"  ✓ {args.name} 프로필 생성 완료")
        print(format_profile(profile))
        return

    if args.detect_name:
        name = extract_name_from_dm(args.detect_name)
        if name:
            print(f"  감지된 이름: {name}")
            profile = load_profile(name)
            if profile:
                print(format_profile(profile))
        else:
            print("  이름을 감지할 수 없습니다.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
