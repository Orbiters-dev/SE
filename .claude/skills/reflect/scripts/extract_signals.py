#!/usr/bin/env python3
"""
extract_signals.py — 세션 transcript에서 학습 신호를 추출한다.
세은의 한국어 교정 패턴 + 일본어 DM 피드백을 자동 감지.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 한국어 교정 패턴 (HIGH confidence) ──
CORRECTION_PATTERNS = [
    # "~하지마", "~하지 말고"
    (r"(.{2,40}?)\s*(?:하지\s*마|하지\s*말고|쓰지\s*마|넣지\s*마|붙이지\s*마)", "prohibition"),
    # "~금지", "절대 ~"
    (r"절대\s+(.{2,40}?)(?:하지마|쓰지마|안돼|금지|넣지마)", "prohibition"),
    (r"(.{2,40}?)\s*금지", "prohibition"),
    # "~ 말고 ~ 해"
    (r"(.{2,40}?)\s*말고\s+(.{2,40}?)(?:해|해줘|써|쓰자|하자|해라)", "correction"),
    # "~ 아니고 ~"
    (r"(.{2,40}?)\s*아니고\s+(.{2,40})", "correction"),
    # "~ 대신 ~"
    (r"(.{2,40}?)\s*대신에?\s+(.{2,40}?)(?:해|써|쓰자|하자|해줘)", "correction"),
    # "템플릿대로 해", "그대로 해"
    (r"템플릿\s*대로\s*해", "template_enforcement"),
    (r"그대로\s*(?:해|써|쓰자)", "template_enforcement"),
    # "되도 않은 거 하지 말고"
    (r"되도\s*않은\s*거\s*하지\s*말고", "prohibition"),
    # "저장해", "기억해"
    (r"(?:저장해|기억해|메모해)\s*(?:이거|이걸|둬)?", "save_request"),
    # "똑바로"
    (r"똑바로\s+(.{2,30})", "correction"),
    # "~빼고 ~만"
    (r"(.{2,20}?)\s*빼고\s+(.{2,20}?)만\s*(?:제안|추천|보내|해)", "correction"),
    # "~해야지", "~적어야지"
    (r"(.{2,30}?)\s*(?:해야지|적어야지|써야지|해야돼|해야 되잖아)", "correction"),
    # "~ ㄴ다는데", "~ 인데 왜"
    (r"오늘이\s+(.{2,10}?)(?:이냐|냐|야)\s*\?*", "factcheck"),
    # "캐주얼하게 적진 말고"
    (r"(?:너무|좀)\s+(.{2,20}?)(?:적진\s*말고|하진\s*말고|쓰진\s*말고)", "correction"),
]

# ── 한국어 승인 패턴 (MEDIUM confidence) ──
APPROVAL_PATTERNS = [
    (r"^(?:웅|ㅇㅇ|맞아|그래|좋아|ㄱㄱ|오케이|굿|완벽)$", "approval"),
    (r"^(?:그거야|바로\s*그거|딱\s*좋아)$", "approval"),
]

# ── DM 관련 피드백 패턴 ──
DM_FEEDBACK_PATTERNS = [
    # DM 톤 교정
    (r"(?:톤|말투|표현)이?\s*(?:너무|좀)\s*(.{2,20})", "dm_tone"),
    # 특정 일본어 표현 교정
    (r"「(.{2,30}?)」\s*(?:말고|아니고|대신)\s*「(.{2,30}?)」", "jp_expression"),
    # 이모지/서명 관련
    (r"(?:이모지|서명|GROSMIMI)\s*(?:넣지마|빼|없이)", "dm_format"),
]


def extract_signals(transcript_path: str) -> list[dict]:
    """transcript JSONL에서 학습 신호를 추출한다."""
    signals = []

    try:
        messages = _load_transcript(transcript_path)
    except Exception as e:
        print(f"[extract] transcript 로드 실패: {e}", file=sys.stderr)
        return []

    # user 메시지만 순회
    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = _extract_text(msg)
        if not text or len(text) < 3:
            continue

        # HIGH — 교정 패턴
        for pattern, ptype in CORRECTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                signals.append({
                    "type": ptype,
                    "confidence": 0.85,
                    "text": text.strip()[:200],
                    "match": match.group(0)[:100],
                    "timestamp": datetime.now().isoformat(),
                })
                break  # 메시지당 1개만

        # MEDIUM — 승인 패턴
        for pattern, ptype in APPROVAL_PATTERNS:
            if re.match(pattern, text.strip(), re.IGNORECASE):
                signals.append({
                    "type": ptype,
                    "confidence": 0.65,
                    "text": text.strip()[:200],
                    "timestamp": datetime.now().isoformat(),
                })
                break

        # DM 피드백
        for pattern, ptype in DM_FEEDBACK_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                signals.append({
                    "type": ptype,
                    "confidence": 0.75,
                    "text": text.strip()[:200],
                    "match": match.group(0)[:100],
                    "timestamp": datetime.now().isoformat(),
                })
                break


    # 중복 제거 (같은 text)
    seen = set()
    unique = []
    for s in signals:
        if s["text"] not in seen:
            seen.add(s["text"])
            unique.append(s)

    return unique


def _load_transcript(path: str) -> list[dict]:
    """JSONL transcript를 파싱한다."""
    messages = []
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"transcript not found: {path}")

    # utf-8 먼저, 실패 시 cp949 fallback (Windows)
    raw = None
    for enc in ["utf-8", "utf-8-sig", "cp949"]:
        try:
            raw = p.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if raw is None:
        raw = p.read_text(encoding="utf-8", errors="replace")

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            messages.append(msg)
        except json.JSONDecodeError:
            continue

    return messages


def _extract_text(msg: dict) -> str:
    """메시지에서 텍스트를 추출한다."""
    content = msg.get("content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)

    return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: extract_signals.py <transcript_path>")
        sys.exit(1)

    signals = extract_signals(sys.argv[1])
    print(json.dumps(signals, ensure_ascii=False, indent=2))
    print(f"\n[extract] {len(signals)}개 신호 감지됨", file=sys.stderr)
