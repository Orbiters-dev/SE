#!/usr/bin/env python3
"""
DM Auto-Lookup Hook — UserPromptSubmit
1. Detects Japanese names (○○様) or IG handles (@xxx) in user message
2. Searches memory/influencers/ for matching files
3. Injects found influencer summary into Claude's context
No more "없다" — the hook finds it before Claude even starts thinking.
"""
import sys
import json
import re
import os
import glob

sys.stdin.reconfigure(encoding='utf-8', errors='replace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
INFLUENCER_DIR = os.path.join(PROJECT_ROOT, 'memory', 'influencers')

# ── Base checklist (always injected) ──────────────────────────
BASE_CHECKLIST = (
    "DM_CHECKLIST: DM 작성이 필요한 상황이면 반드시 다음을 먼저 수행할 것. "
    "1) 해당 인플루언서 메모리 파일(influencer_*.md) Read로 열어서 확인. "
    "2) DM 포맷: 코드블록(```) 필수, 이름(○○様) 필수, GROSMIMI JAPAN 서명 필수, 한국어 전문번역 코드블록 필수. "
    "3) 메모리에 없는 인플루언서면 세은에게 먼저 정보 확인. "
    "4) DM 아닌 상황이면 이 메시지 무시."
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
    if not os.path.isdir(INFLUENCER_DIR):
        return []

    matches = []
    seen_files = set()

    for inf_file in glob.glob(os.path.join(INFLUENCER_DIR, 'influencer_*.md')):
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
                # Extract key info: first 4 non-empty, non-frontmatter lines
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


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        # Fallback: just output base checklist
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": BASE_CHECKLIST
            }
        }, ensure_ascii=False))
        return

    message = hook_input.get('user_prompt', '')

    # Search for influencer mentions
    terms = extract_search_terms(message)
    matches = search_influencer_files(terms) if terms else []

    if matches:
        # Build auto-lookup result
        parts = [BASE_CHECKLIST, ""]
        parts.append("INFLUENCER_AUTO_LOOKUP: 아래 인플루언서 메모리를 자동으로 찾았음. '없다'고 하지 말 것.")
        for path, summary in matches:
            parts.append(f"  FILE: {path}")
            parts.append(f"  INFO: {summary}")
        parts.append("반드시 위 파일을 Read로 열어서 전체 내용 확인 후 응답할 것.")

        context = "\n".join(parts)
    else:
        context = BASE_CHECKLIST

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
