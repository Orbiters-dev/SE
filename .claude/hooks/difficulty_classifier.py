#!/usr/bin/env python3
"""
Difficulty Classifier Hook — UserPromptSubmit
Every user message → LOW / MEDIUM / HIGH → guidance injected into context.

LOW:    no overhead
MEDIUM: feedback memory grep reminder
HIGH:   Plan mode + human approval required
"""
import sys
import json
import re
import os
import glob

sys.stdin.reconfigure(encoding='utf-8', errors='replace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Keyword patterns ──────────────────────────────────────────

HIGH_PATTERNS = [
    r'계약서', r'contract', r'docuseal', r'서명',
    r'배포', r'deploy', r'push\s', r'force',
    r'입찰.*변경', r'bid.*change', r'예산', r'budget',
    r'대량', r'bulk', r'全員', r'一斉',
    r'delete.*prod', r'drop\s', r'rm\s+-rf',
    r'ppc.*실행', r'ppc.*execute', r'금액.*변경',
    r'send.*contract', r'발송.*계약',
]

MEDIUM_PATTERNS = [
    r'DM\b', r'dm\b', r'様', r'さん.*메시지', r'답장',
    r'수정', r'fix\b', r'bug', r'코드.*변경',
    r'스크립트', r'script', r'리포트', r'report',
    r'대시보드', r'dashboard', r'워크플로우', r'workflow',
    r'n8n', r'인플루언서', r'influencer',
    r'기획', r'plan', r'트위터', r'twitter', r'인스타',
]

LOW_PATTERNS = [
    r'확인해', r'조회', r'읽어', r'보여', r'열어',
    r'status', r'git\s+log', r'git\s+status', r'git\s+diff',
    r'검색', r'찾아', r'몇\s', r'뭐야', r'어디',
    r'알려', r'설명', r'what\s+is', r'show\s+me',
]

# Influencer stages that escalate to HIGH
HIGH_STAGE_KEYWORDS = [
    'STEP 6', 'STEP 7', 'STEP 8', 'STEP 9', 'STEP 10',
    'contract', '계약', 'DocuSign', 'DocuSeal', '서명',
    '발송 준비', '배송', 'shipping',
]

# ── Influencer stage lookup ───────────────────────────────────

INFLUENCER_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', 'memory', 'influencers'
)


def find_influencer_stage(message):
    """If message mentions ○○様, check their memory file for current stage."""
    # Extract 様 names from message
    names = re.findall(r'([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]+様)', message)
    if not names or not os.path.isdir(INFLUENCER_DIR):
        return None

    # Search influencer files for matching name
    for inf_file in glob.glob(os.path.join(INFLUENCER_DIR, 'influencer_*.md')):
        try:
            with open(inf_file, 'r', encoding='utf-8') as f:
                header = f.read(500)  # only read top for speed
        except Exception:
            continue

        for name in names:
            name_base = name.replace('様', '')
            if name_base in header:
                # Check if high stage
                for kw in HIGH_STAGE_KEYWORDS:
                    if kw in header:
                        return 'HIGH'
                return 'MEDIUM'

    return None


# ── Classifier ────────────────────────────────────────────────

def classify(message):
    """Classify message difficulty: LOW / MEDIUM / HIGH"""

    # 1. Check HIGH keywords
    for p in HIGH_PATTERNS:
        if re.search(p, message, re.IGNORECASE):
            return 'HIGH'

    # 2. Check influencer stage escalation
    stage_level = find_influencer_stage(message)
    if stage_level == 'HIGH':
        return 'HIGH'

    # 3. Check MEDIUM keywords
    for p in MEDIUM_PATTERNS:
        if re.search(p, message, re.IGNORECASE):
            return 'MEDIUM'

    # 4. Check LOW keywords
    for p in LOW_PATTERNS:
        if re.search(p, message, re.IGNORECASE):
            return 'LOW'

    # 5. Default: MEDIUM (conservative — uncertain = check more, not less)
    return 'MEDIUM'


def get_guidance(difficulty):
    if difficulty == 'HIGH':
        return (
            "DIFFICULTY: HIGH. "
            "Plan 모드 진입 후 세은 승인 받고 실행. "
            "완료 후 harness.py 감사 필수. "
            "관련 피드백 메모리 반드시 확인."
        )
    elif difficulty == 'MEDIUM':
        return (
            "DIFFICULTY: MEDIUM. "
            "실행 전 관련 피드백 메모리 grep. "
            "인플루언서 관련이면 메모리 파일 먼저 Read."
        )
    # LOW: zero overhead
    return None


# ── Main ──────────────────────────────────────────────────────

def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    message = hook_input.get('user_prompt', '')
    if not message or len(message) < 2:
        sys.exit(0)

    difficulty = classify(message)
    guidance = get_guidance(difficulty)

    if guidance:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": guidance
            }
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
