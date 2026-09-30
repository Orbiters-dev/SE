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
    (r"(.{2,40}?)\s*(?:하지\s*마|하지\s*말고|쓰지\s*마|넣지\s*마|붙이지\s*마|적지\s*마|적지\s*말고)", "prohibition"),
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
    # "저장해/기억해" save_request 패턴은 8/11 오탐 판정으로 제거 (단순 지시 ≠ 교정) — 재추가 금지
    # "똑바로"
    (r"똑바로\s+(.{2,30})", "correction"),
    # "장난하나/장난하냐 + 지시" — 강한 교정 상용구 (7/3 표, 6/4 제목, 7/10 표 재위반 등)
    (r"장난\s*하(?:나|냐)\s*[.?]?\s*(.{0,40})", "correction"),
    # "~빼고 ~만"
    (r"(.{2,20}?)\s*빼고\s+(.{2,20}?)만\s*(?:제안|추천|보내|해)", "correction"),
    # "~해야지", "~적어야지"
    (r"(.{2,30}?)\s*(?:해야지|적어야지|써야지|해야돼|해야 되잖아)", "correction"),
    # "~ ㄴ다는데", "~ 인데 왜"
    (r"오늘이\s+(.{2,10}?)(?:이냐|냐|야)\s*\?*", "factcheck"),
    # "캐주얼하게 적진 말고"
    (r"(?:너무|좀)\s+(.{2,20}?)(?:적진\s*말고|하진\s*말고|쓰진\s*말고)", "correction"),
    # 중단 지시 — "걍 그만해", "그만하고 ~해" (8/7 추가: 탐색 오래 끌기 교정)
    (r"(?:야\s*)?(?:걍\s*)?그만\s*(?:해|하고|해라)", "stop_order"),
    # 진행 방식 불만 — "언제까지 하나", "너무 정신사나워" (8/7 추가)
    (r"언제까지\s*하[나냐]", "process_complaint"),
    (r"정신\s*사납", "process_complaint"),
    (r"정신\s*사나워", "process_complaint"),
    # 판정 반박 — "~가 아니잖아" (8/7 추가: 형식 오판 교정)
    (r"(.{2,40}?)\s*(?:가|이)?\s*아니잖아", "correction"),
    # "나대다" 계열 — 시키지 않은 선제 실행 질책 (8/12 「왤케 나대는 거삼」)
    (r"나대(?:는|지|냐|삼|네)", "correction"),
    # "이자석아/이 자식아" — 강한 교정 호격 (8/12 「PPC라고 표기하면 안되지요 ^^ 이자석아」)
    (r"이\s*자[석식](?:아)?", "correction"),
    # "~하면 안되지(요)" — 금지 지적, 존대형 포함 (8/12 추가)
    (r"(.{2,40}?)\s*(?:하면|표기하면|쓰면|넣으면)\s*안\s*되(?:지요|지|죠|잖아)", "prohibition"),
    # 강한 교정 상용구 (8/20 추가: 「죽을래?」·「뭔 개소리야」·「미쳤나」·「쌰갈」 — 7/28·8/3·8/20 반복 실증)
    (r"죽을래", "strong_rebuke"),
    (r"(?:뭔\s*)?개소리", "strong_rebuke"),
    (r"미쳤(?:나|냐|어)", "strong_rebuke"),
    (r"쌰갈", "strong_rebuke"),
    # 떠넘김 질책 — "스스로 생각을 해", "나한테 묻고" (8/20 추가)
    (r"스스로\s*생각(?:을)?\s*해", "offload_complaint"),
    (r"나한테\s*묻고", "offload_complaint"),
    # 강한 교정 호격 — "미친놈아", "이새끼야", "정신나간색히야" (8/27 무단 실행 사고 · 8/24 색히 — 커버 공백 수리)
    (r"미친\s*놈|이\s*새끼|색히", "strong_rebuke"),
    # 무단 실행 질책 — "내가 언제 ~하라고 했냐" (8/27 추가)
    (r"언제\s*.{0,24}?(?:하라고|시켰다고|실행하라고)\s*했[냐어]", "correction"),
    # 확인 태만 질책 — "왜 제대로 확인을 안 해서", "내가 꼭 한 번 더 물어보게" (8/26·8/27 반복 실증)
    (r"제대로\s*확인(?:을)?\s*안\s*하", "correction"),
    (r"내가\s*꼭\s*.{0,24}?(?:물어보게|지적을\s*해야)", "process_complaint"),
    # 불요 지적 — "넣을 필요 없어", "다 아는 사실" (8/27 추가)
    (r"넣을\s*필요\s*없|(?:이미\s*)?다\s*아는\s*사실", "correction"),
    # 중단 지시 — "야 멈춰" (8/28 실증: weekly deck 오독 정지 지시가 0건 미감지)
    (r"(?:야\s*)?멈춰", "stop_order"),
    # 강한 교정 호격 — "임마" (8/28 「여기 쓰는 거 쓰라고 임마」)
    (r"임마", "strong_rebuke"),
    # 오독 정정 — "~말한 거 아니야" (8/28 「weekly deck 말한 거 아니야」)
    (r"(.{2,40}?)\s*말한\s*거\s*아니[야냐]", "correction"),
    # 문미 단독 "~말고" — 뒤 동사 없이 끊는 정정 (8/28 「weekly deck 말고」)
    (r"(.{2,40}?)\s*말고\s*$", "correction"),
    # 품질 질책 — "이따구" (9/1 「왜 또 이따구로 처나오냐」 0건 미감지 수리)
    (r"이따구", "strong_rebuke"),
    # 재발 질책 — "왜 또", "맨날 (처) 하" (9/1 「니 이 실수를 맨날 처 하는데」)
    (r"왜\s*또\s+(.{0,40})", "recurrence_complaint"),
    (r"맨날\s*(?:처\s*)?(?:하|그러)", "recurrence_complaint"),
    # 사전 조치 요구 — "~해 놔야지 / 박아 놔야지" (9/1 「기록을 해 놔야지」)
    (r"(.{2,40}?)\s*(?:해|적어|박아|기록해)\s*놔야지", "correction"),
    # 위협형 강한 교정 — "죽는다", "죽여", "뒤진다" (9/29 「왜 다 지웟어 죽는다」 0건 미감지 수리; 기존 "죽을래"만 커버)
    (r"죽는다|죽여|뒤진다|뒤질래", "strong_rebuke"),
    # 질책형 의문 — "왜 (다) ~했어/지웠어/뺐어/바꿨어" (9/29 「왜 다 지웟어」)
    (r"왜\s*(?:다\s*)?(.{0,30}?)(?:했어|했냐|했니|지웠어|지웟어|지웠냐|뺐어|바꿨어|만들었어|건드렸어)", "correction"),
    # 지시 미이행 지적 — "(분명히) ~하라고 했을 텐데/했잖아" (9/29 「내가 분명히 ~하라고 했을 텐데」)
    (r"(?:분명히\s*)?(.{2,40}?)\s*(?:하라고|하랬|시켰|말했)\s*(?:했을\s*텐데|텐데|했잖아|했는데|잖아)", "correction"),
    # 결과 불신·재확인 요구 — "~한 거 맞아?", "제대로 한 거 맞아?" (9/29 「복원한 거 맞아?」)
    (r"(.{2,30}?)\s*(?:한\s*거|했는지)\s*맞(?:아|지)\s*\?", "verify_distrust"),
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
    # Claude Code transcript 라인 = {"type":"user","message":{"role":"user","content":...}}
    # (구 포맷 {"role":...,"content":...} 도 호환)
    # 작업 중 끼어든 세은 메시지 = {"type":"attachment","attachment":{"prompt":[{"text":...}]}}
    for msg in messages:
        if msg.get("type") == "attachment":
            att = msg.get("attachment") or {}
            prompt = att.get("prompt")
            if not isinstance(prompt, list):
                continue
            text = " ".join(b.get("text", "") for b in prompt if isinstance(b, dict))
        else:
            inner = msg.get("message") if isinstance(msg.get("message"), dict) else msg
            if inner.get("role") != "user":
                continue
            text = _extract_text(inner)

        if not text or len(text) < 3:
            continue
        # 스킬 호출 본문·커맨드 래퍼·백그라운드 태스크 알림은 세은 발화 아님 — 제외
        # (훅 컨텍스트·system-reminder는 _extract_text에서 블록 단위 제거 — 메시지 통째 스킵 금지)
        if any(m in text for m in ("Base directory for this skill",
                                   "<command-message>", "<command-name>",
                                   "<task-notification", "<local-command",
                                   "스킬을 발동시킨다")):
            continue
        # 마크다운 헤딩으로 시작하는 문서 붙여넣기(스킬 본문 등)는 세은 발화 아님 (8/13: reel-translator SKILL 본문 오탐)
        if text.lstrip().startswith("#"):
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

    # transcript JSONL은 항상 UTF-8. cp949 전체 fallback은 utf-8 strict가 한 바이트라도
    # 실패하는 순간 파일 전체를 mojibake로 디코드할 위험이 있어 제거 (8/13).
    # 깨진 바이트만 치환하고 나머지 라인은 살린다.
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
        # 하네스 주입 블록(훅 컨텍스트·system-reminder)은 블록 단위로만 제거 —
        # 메시지 전체를 버리면 같은 메시지에 실린 세은 발화까지 유실 (8/7 수리:
        # UserPromptSubmit 훅이 매 메시지에 DM_CHECKLIST를 붙이면서 전 세션 신호 0건이 됨)
        parts = [p for p in parts
                 if "<system-reminder" not in p and "DM_CHECKLIST" not in p
                 and "hook additional context" not in p]
        return " ".join(parts)

    return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: extract_signals.py <transcript_path>")
        sys.exit(1)

    signals = extract_signals(sys.argv[1])
    print(json.dumps(signals, ensure_ascii=False, indent=2))
    print(f"\n[extract] {len(signals)}개 신호 감지됨", file=sys.stderr)
