#!/usr/bin/env python3
"""PreToolUse Bash hook — block DocuSeal 본 발송(인플루언서 메일 실제 발송) without seeun approval.

Target scripts:
  - tools/send_docuseal_contract.py
  - tools/send_docusign_contract.py
  - tools/send_influencer_contract_docuseal.py

BLOCK (인플루언서에게 메일 발송) unless command has approval marker:
  # seeun-approved: <YYYY-MM-DD> <영속인플 또는 사유>
  - 기본 send (mode 플래그 없음) — submission 생성 + 인플루언서 메일 발송
  - --resend SUBMITTER_ID       — 기존 submitter 에게 메일 재발송

PASS without marker (인플루언서에게 메일 안 나감):
  - --dry-run / --check / --status  — read-only, no submission
  - --no-send                       — submission 생성하되 메일 발송 X (검수용 서명 URL 만 반환)
    · 단, --resend 와 조합되면 tool 이 resend(메일)을 우선 실행하므로 PASS 하지 않는다.

Why --no-send is auto-pass (세은 「하라고」 지시)
------------------------------------------------
STEP 6 정보(풀네임+메일) 수령 시 SOP 는 [1] DOCX 생성 → [2] --no-send 업로드 →
[3] 서명 URL 세은 검수 → [4] resend 본 발송. [2] 는 검수 URL 을 만드는 단계일 뿐
인플루언서에게 메일이 나가지 않는다. 검증 근거:
  · tool 코드 `send_email_flag = not args.no_send`
  · Submission 74 API `sent_at=None` (인플루언서 메일 미발송)
매번 --no-send 를 세은 승인 뒤로 미루다 「하라고」 강한 교정 → 검수 URL 단계는
자동, 실제 메일 발송([4])만 승인 게이트로 재설계.
(날짜·경위 상세: memory/feedback_docuseal_nosend_autopass.md)

Why this hook exists (원래 사고)
--------------------------------
2026-05-21 ゆっち様(@yucchi_mamababy) 사고. [2] 세은 검토·승인 스킵 + 자동 본 발송.
그 뒤로 박힌 가드. 이제 게이트 대상은 「메일 실제 발송」 액션으로 한정.
룰: 「feedback_docuseal_upload_also_requires_approval.md」 / reference_contract_sop.md.
"""
from __future__ import annotations

import json
import os
import re
import sys


# Match ONLY actual python execution of the target scripts.
# Avoids false positive on echo / Read / grep / cat where the script name appears as a string.
EXEC_PATTERN = re.compile(
    r"(?:^|[\s;&|`(])"                                  # boundary before `python` invocation
    r"(?:python[\w.\-\\/]*|py)\s+"                      # python interpreter
    r"(?:[^\s|;&]+\s+)*"                                # any options/positionals before the path
    r"tools[\\/]"                                       # tools/ or tools\
    r"(?:send_docuseal_contract|send_docusign_contract|send_influencer_contract_docuseal)"
    r"\.py\b",
    re.IGNORECASE,
)


# Genuinely read-only flags — no submission, no email.
READ_ONLY_FLAGS = ("--check", "--status", "--dry-run")


APPROVAL_MARKER = re.compile(
    r"#\s*seeun-approved\s*:\s*\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _is_target_script(cmd: str) -> bool:
    return bool(EXEC_PATTERN.search(cmd))


def _is_read_only(cmd: str) -> bool:
    """Return True if command uses only read-only flags (no new submission creation)."""
    return any(flag in cmd for flag in READ_ONLY_FLAGS)


def _is_review_upload(cmd: str) -> bool:
    """--no-send review upload: creates a submission but emails nobody → auto-pass.

    Guard against the tool's precedence bug: `--resend` runs the resend branch
    FIRST and IGNORES --no-send, so `--resend N --no-send` DOES email. Only treat
    --no-send as review-only when it is NOT combined with --resend.
    """
    return "--no-send" in cmd and "--resend" not in cmd


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool != "Bash":
        return 0

    cmd = (data.get("tool_input") or {}).get("command", "")
    if not _is_target_script(cmd):
        return 0

    # Read-only (--dry-run/--check/--status) passes through silently
    if _is_read_only(cmd):
        return 0

    # --no-send review upload (submission only, no influencer email) — auto-pass
    if _is_review_upload(cmd):
        return 0

    # 본 발송 (기본 send / --resend) — block unless explicit seeun-approval marker
    if not APPROVAL_MARKER.search(cmd):
        _emit({
            "decision": "block",
            "reason": (
                "🛑 DocuSeal 본 발송(인플루언서 메일 실제 발송) 차단.\n"
                "SOP: [1] DOCX 생성(자동) → [2] --no-send 업로드(자동) → [3] 서명 URL 세은 검수 → [4] resend 본 발송\n"
                "이 커맨드는 인플루언서에게 메일이 나가는 액션(기본 send / --resend)이라 세은 승인이 필요.\n"
                "\n"
                "통과 조건 — 세은이 「발송해/보내」 명시 OK 한 후, Bash 커맨드에 마커 박기:\n"
                "  # seeun-approved: YYYY-MM-DD <사유>\n"
                "\n"
                "예시:\n"
                "  python tools/send_docuseal_contract.py --resend 74 \\\n"
                "    # seeun-approved: 2026-07-02 ムスコラブ 계약서 세은 OK 본 발송\n"
                "\n"
                "관련 룰:\n"
                "  - memory/feedback_docuseal_upload_also_requires_approval.md\n"
                "  - memory/reference_contract_sop.md [4] 단계\n"
                "  - memory/feedback_external_send_requires_approval.md\n"
                "\n"
                "마커 없이 통과: --dry-run / --check / --status / --no-send(검수 URL, 메일 미발송)."
            ),
            "systemMessage": "🛑 DocuSeal 본 발송 차단 — `# seeun-approved:` 마커 필요 (--no-send 는 자동 통과)",
        })
        return 0

    # Marker present — pass through with audit message
    marker = APPROVAL_MARKER.search(cmd)
    _emit({
        "systemMessage": f"✅ DocuSeal 발송 허가 (marker: {marker.group(0)[:80]})",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
