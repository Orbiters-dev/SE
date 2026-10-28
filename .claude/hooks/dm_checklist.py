#!/usr/bin/env python3
"""
DM Auto-Lookup + Rule Guard Hook — UserPromptSubmit
1. Detects Japanese names (○○様) or IG handles (@xxx) in user message
2. Searches memory/influencers/ for matching files
3. Injects found influencer summary + STRONG-CORRECTION RULE LIST into context

Why this exists
---------------
2026-05-21 ゆっち様(@yucchi_mamababy) 사고: 강한 교정 룰 여러 건이 메모리에 박혀
있는데도 작업 시작 시점에 능동 체크 안 되어 재위반. 세은 「뜯어고쳐 미친놈아」.
룰 "저장" 만으로 부족 — 작업 트리거 시점에 강제 컨텍스트 주입으로 능동 체크.
"""
import sys
import json
import re
import os
import glob
import threading

# Windows stdin/stdout 인코딩 (cp949 기본) → utf-8 강제. reconfigure 실패해도 진행.
for stream_name in ('stdin', 'stdout'):
    try:
        getattr(sys, stream_name).reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _read_stdin_with_timeout(timeout_sec: float = 5.0) -> str:
    """stdin 을 별도 thread 로 읽음. timeout 넘기면 빈 문자열 반환 (hang 방지).

    Claude Code subprocess 가 Windows 에서 stdin pipe 를 안 닫는 케이스 회피.
    """
    result = {'data': ''}

    def _read():
        try:
            raw = sys.stdin.buffer.read()
            result['data'] = raw.decode('utf-8', errors='replace')
        except Exception:
            try:
                result['data'] = sys.stdin.read()
            except Exception:
                pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    return result['data']

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
INFLUENCER_DIR = os.path.join(PROJECT_ROOT, 'memory', 'influencers')

# ── Base checklist (always injected on influencer-related prompt) ──
BASE_CHECKLIST = (
    "DM_CHECKLIST (인플루언서 작업 트리거 — 능동 체크 의무):\n"
    "0) [호칭] 본명(풀네임) 수령됐으면 즉시 「{성}様」 로 호칭 변경. SNS 닉네임(○○ちゃんママ, ゆっち 등) 그대로 유지 X. "
    "본명 적힌 메시지가 이번 또는 직전 턴에 보이면 그 자리에서 호칭 바꿔.\n"
    "1) [메모리] 해당 인플루언서 memory/influencers/influencer_*.md Read로 열어 진행 단계·제품·보수 확인.\n"
    "2) [계약서 SOP] 정보(풀네임+메일) 수령하면 그 턴에 **자동으로** (묻지 말고): [1] DOCX 생성 → [2] DocuSeal --no-send 업로드 → "
    "**서명 URL(링크)을 세은에게 제시** → 세은 검수 OK → resend 본 발송. "
    "⛔ 검수는 반드시 DocuSeal URL 링크로. 로컬 DOCX/PDF 경로·「확인해주세요」 말 약속 = 강한 교정(2026-06-12). "
    "--no-send 는 인플루언서에게 메일이 안 나가는 검수용 업로드(sent_at=None 검증됨) → **세은 승인·마커 없이 그 턴에 자동 실행**해 URL까지 내놔. "
    "「생성하겠습니다」·「업로드할까요?」·「발송할까요?」로 미루면 강한 교정. resend 본 발송(인플루언서 메일 실제 발송)만 세은 「발송해」 승인 필요.\n"
    "3) [검증] 도구 출력 텍스트 그대로 신뢰 X. 「발송 X」 라고 도구가 찍어도 실제 동작·외부 시스템 응답 검증 후 보고. "
    "검증 안 한 정보는 답변 본문에 단정으로 X — 「확인 못 함」 한 줄로.\n"
    "4) [외부 발송] DocuSeal/이메일/DM 본 발송 = 세은 명시 「발송해」 승인 후. dry-run / preview / --no-send 도 "
    "외부 시스템 액션이면 사전 보고 + 진행 여부 확인.\n"
    "5) [DM 포맷] 코드블록(```) + 호칭 + GROSMIMI JAPAN 서명 + 한국어 번역 코드블록 필수.\n"
    "6) [유상 마무리] 유상 인플루언서 STEP 12 마무리 DM 末尾에 입금 안내 통합 (2026-10-21 세은 확정: "
    "「今週中にお振込み」 + 착금까지 시간 소요 가능 안내 + 입금 확인 시 연락 요청 — 「本日中」 금지. "
    "정본 문구=workflows/grosmimi_japan_influencer_dm.md STEP 12 DM②). 별도 DM X.\n"
    "7) [자료 송부 알림] 인플루언서가 원본/광고코드/캡션 송부 알림 보내면 「확인하겠습니다」 ack 분리 X. "
    "세은이 침묵=확인 OK 가정 → 全完了 마무리 + (유상시) 입금 약속 한 번에 통합 DM. "
    "세은이 정정 지시 보낼 때만 별도 답신.\n"
    "8) [송금 정보] 송금/입금 정보 전달 요청 = 산출 전 memory/reference_remittance_info_format.md Read 필수. "
    "표준 2블록 표(송금 정보+주소·연락처) 고정 — 수취인 한자/カナ/영문 3중·은행코드+지점코드(없으면 웹 조회)·주소 JP/EN 병기. "
    "임의 표 금지 (2026-09-09 교정·2026-10-21 재발).\n"
    "DM 아닌 상황이면 이 checklist 무시."
)


def extract_search_terms(message):
    """Extract Japanese names and IG handles from message."""
    terms = []

    # ○○様 patterns (hiragana, katakana, kanji, special unicode)
    sama_names = re.findall(
        r'([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF\u0080-\u024F]+様)',
        message
    )
    for name in sama_names:
        terms.append(name.replace('様', ''))

    # @handle patterns
    handles = re.findall(r'@([\w.]+)', message)
    for h in handles:
        if len(h) > 3 and h not in ('gmail', 'yahoo', 'icloud'):
            terms.append(h)

    return terms


def search_influencer_files(terms):
    """Search influencer files for matching names/handles. Returns list of (filepath, summary)."""
    try:
        inf_files = sorted(glob.glob(os.path.join(INFLUENCER_DIR, 'influencer_*.md')))
    except OSError:
        return []

    matches = []
    seen_files = set()

    for inf_file in inf_files:
        if '_dm_log' in inf_file:
            continue
        if inf_file in seen_files:
            continue

        try:
            with open(inf_file, 'r', encoding='utf-8') as f:
                content = f.read(800)
        except Exception:
            continue

        for term in terms:
            if term.lower() in content.lower():
                seen_files.add(inf_file)
                # Extract key info: first 5 non-empty, non-frontmatter lines
                lines = []
                in_frontmatter = False
                for line in content.split('\n'):
                    if line.strip() == '---':
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        continue
                    if line.strip() and not line.startswith('#'):
                        lines.append(line.strip())
                    if len(lines) >= 5:
                        break

                rel_path = os.path.relpath(inf_file, PROJECT_ROOT).replace('\\', '/')
                summary = ' | '.join(lines[:5])
                matches.append((rel_path, summary))
                break

    return matches


# ── Contract-stage detection ────────────────────────────────────
CONTRACT_TRIGGERS = (
    "契約書", "계약서", "풀네임", "フルネーム", "메일주소", "メールアドレス",
    "DocuSeal", "DocuSign", "署名", "서명", "계약",
)


def detect_contract_stage(message):
    """Return True if message looks like contract-stage info delivery."""
    if not message:
        return False
    return any(trig in message for trig in CONTRACT_TRIGGERS)


# ── Real-name detection ────────────────────────────────────────
def detect_real_name_handover(message):
    """Detect if user message includes a real-name handover (full name + email-ish pattern)."""
    if not message:
        return False
    # 풀네임/フルネーム label + email pattern in same message
    has_fullname_label = ("フルネーム" in message or "풀네임" in message or "本名" in message)
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", message))
    return has_fullname_label and has_email


def _emit_base_only():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": BASE_CHECKLIST
        }
    }, ensure_ascii=False))


def main():
    raw = _read_stdin_with_timeout(timeout_sec=5.0)
    if not raw:
        _emit_base_only()
        return
    try:
        hook_input = json.loads(raw)
    except Exception:
        _emit_base_only()
        return

    message = hook_input.get('user_prompt', '')

    # Search for influencer mentions
    terms = extract_search_terms(message)
    matches = search_influencer_files(terms) if terms else []

    parts = []

    # Stage-specific HARD warnings (prepended above base checklist)
    if detect_real_name_handover(message):
        parts.append(
            "⚠️ REAL_NAME_HANDOVER 감지: 본명(풀네임 + 메일) 수령 패턴. "
            "다음 DM·답신 작성 시 호칭을 SNS 닉네임에서 「{성}様」 로 즉시 전환. "
            "이전 컨텍스트 호칭 carry-over X. (feedback_call_by_real_name.md)"
        )

    if detect_contract_stage(message):
        parts.append(
            "⚠️ CONTRACT_STAGE 감지: 계약서 관련 메시지. "
            "진행 시 SOP 엄수 — [1] DOCX 생성 → [2] DocuSeal **--no-send 업로드(세은 승인·마커 없이 그 턴에 자동 실행, 인플루언서 메일 안 나감)** → "
            "[3] 서명 URL 세은에게 제시 → 세은 검수 OK → [4] resend 본 발송. "
            "묻지 말고 --no-send 로 URL까지 바로 내놔. **resend 본 발송(인플루언서 메일 실제 발송)만** 세은 「발송해」 명시 OK 필요. "
            "⛔ 업로드 파일은 **반드시 .docx 경로** (인자명이 --pdf여도 .docx를 넘겨야 DOCX 루트). "
            ".pdf를 넘기면 {{氏名}} 태그 글자 노출 사고(2026-09-01 Submission 208 「왜 또 이따구로」). "
            "출력의 「업로드 : DOCX (text tag 자동 제거)」 라인 확인이 완료 조건. "
            "(feedback_docuseal_upload_also_requires_approval.md / reference_contract_sop.md / mistakes_20260901_docuseal_pdf_route_tag_exposure.md)"
        )

    parts.append(BASE_CHECKLIST)

    if matches:
        parts.append("")
        parts.append("INFLUENCER_AUTO_LOOKUP: 아래 인플루언서 메모리 자동 발견. '없다' 단정 X.")
        for path, summary in matches:
            parts.append(f"  FILE: {path}")
            parts.append(f"  INFO: {summary}")
        parts.append("반드시 위 파일을 Read로 열어 전체 내용 확인 후 응답.")

    context = "\n".join(parts)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
