#!/usr/bin/env python3
"""
Mistake Recorder Hook - PostToolUse hook that auto-records errors to mistakes.md.
Detects errors from tool results and appends new entries.
"""
import sys
import json
import re
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MISTAKES_PATH = os.path.expanduser(
    '~/.claude/projects/c--Users-wjcho-Desktop-WJ-Test1/memory/mistakes.md'
)

# Error patterns: (regex, title, default_agent, auto_fix_instruction)
ERROR_PATTERNS = [
    (r'UnicodeEncodeError.*charmap', 'cp949 인코딩 에러', 'Core (모든 에이전트 공통)',
     "FIX NOW: 해당 .py 파일 상단에 `import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 추가 후 재실행"),
    (r'UnicodeDecodeError', '파일 디코딩 에러', 'Core (모든 에이전트 공통)',
     "FIX NOW: 파일 읽기를 `open(f, 'rb')` -> `.decode('utf-8', errors='replace')` 로 변경 후 재실행"),
    (r"unexpected EOF while looking for matching", '따옴표 중첩 에러', 'Core (모든 에이전트 공통)',
     "FIX NOW: `python -c` 대신 `.tmp/script.py` 파일로 저장한 뒤 `python .tmp/script.py` 로 재실행"),
    (r'SSL.*revocation|schannel.*revocation', 'SSL revocation 실패', 'Core (모든 에이전트 공통)',
     "FIX NOW: curl 명령에 `-sk` 플래그 추가 후 재실행"),
    (r'Unable to parse range.*\\!', 'Sheets range 포맷 에러', 'Google API',
     "FIX NOW: 탭 이름을 작은따옴표로 감싸기 `\"'Tab Name'!A1:Z50\"` 형식으로 수정 후 재실행"),
    (r'text-embedding-004.*404|404.*text-embedding-004', '임베딩 모델 404', 'Google API',
     "FIX NOW: 모델명을 `gemini-embedding-001` 로 변경 후 재실행"),
    (r'Insufficient Permission.*scopes?', 'OAuth 스코프 부족', '이메일 지니',
     "FIX NOW: 토큰 재발급 필요. 유저에게 `gmail.readonly + gmail.send + gmail.modify` 스코프로 재인증 요청"),
    (r'google\.generativeai.*deprecated|ImportError.*generativeai', 'genai SDK deprecated', 'Google API',
     "FIX NOW: `import google.generativeai` -> `from google import genai` 로 변경 후 재실행"),
    (r'"active".*read.only|active.*cannot be set', 'n8n active 필드 에러', 'n8n 매니저',
     "FIX NOW: POST body에서 `active` 필드 제거 후 재전송"),
    (r'dimension.*mismatch|expected \d+ got \d+', '벡터 차원 불일치', 'Google API',
     "FIX NOW: 임베딩 모델 차원 확인 (gemini-embedding-001 = 3072). 인덱스 차원과 맞는지 확인 후 재실행"),
    (r'rate.limit|429|Too Many Requests', 'API rate limit 초과', 'Core (모든 에이전트 공통)',
     "FIX NOW: 30초 대기 후 재시도. 반복되면 batch 크기 줄이거나 exponential backoff 적용"),
    (r'TimeoutError|timed? ?out|ETIMEDOUT', 'API 타임아웃', 'Core (모든 에이전트 공통)',
     "FIX NOW: timeout 값 늘리기 (requests: timeout=60). 서버 상태 확인 후 재시도"),
    (r'FileNotFoundError|No such file', '파일 경로 오류', 'Core (모든 에이전트 공통)',
     "FIX NOW: 경로 존재 여부 확인. NAS symlink 깨졌으면 `ls -la` 로 점검"),
    (r'PermissionError|Access.*denied', '권한 에러', 'Core (모든 에이전트 공통)',
     "FIX NOW: 파일/폴더 권한 확인. NAS 파일이면 네트워크 연결 상태 점검"),
    (r'JSONDecodeError|Expecting value', 'JSON 파싱 실패', 'Core (모든 에이전트 공통)',
     "FIX NOW: 응답 내용 확인 (HTML 에러 페이지? 빈 응답?). binary read + utf-8 decode 시도"),
    (r'KeyError|IndexError', '데이터 구조 접근 에러', 'Core (모든 에이전트 공통)',
     "FIX NOW: 데이터 구조 출력해서 실제 키/인덱스 확인. `.get()` 또는 `if key in` 가드 추가"),
    (r'ConnectionRefused|ECONNREFUSED', '서버 연결 거부', 'Core (모든 에이전트 공통)',
     "FIX NOW: 서버 상태 확인 (EC2: curl -sk https://orbitools.orbiters.co.kr/healthz, n8n: curl -sk https://n8n.orbiters.co.kr/healthz)"),
    (r'ModuleNotFoundError|No module named', '패키지 미설치', 'Core (모든 에이전트 공통)',
     "FIX NOW: `pip install 패키지명` 실행 후 재시도"),
]

# Agent detection from tool input context
AGENT_KEYWORDS = {
    'n8n': 'n8n 매니저',
    'gmail': '이메일 지니',
    'oauth': '이메일 지니',
    'sheets': 'Google API',
    'genai': 'Google API',
    'embedding': 'Google API',
    'pinecone': 'Google API',
    'amazon_ppc': '아마존 퍼포마',
    'ppc': '아마존 퍼포마',
    'meta_ads': 'Meta Ads',
    'kpi': 'KPI 리포트',
    'datakeeper': '데이터 키퍼',
    'data_keeper': '데이터 키퍼',
    'shopify': '앱스터',
    'influencer': '파이프라이너',
    'pipeline': '파이프라이너',
    'airtable': '파이프라이너',
    'dual_test': '파이프라이너',
    'test_influencer': '파이프라이너',
    'apify': 'CI 팀장 (크롤러 포함)',
    'syncly': 'CI 팀장 (크롤러 포함)',
    'sns_tab': 'CI 팀장 (크롤러 포함)',
    'content': 'CI 팀장 (크롤러 포함)',
    'golmani': '골만이',
    'dcf': '골만이',
    'lbo': '골만이',
    'openpyxl': '골만이',
    'communicator': '커뮤니케이터',
    'deploy_onzenna': '앱스터',
}


def get_next_id(content):
    """Get next M-XXX id from mistakes.md."""
    ids = re.findall(r'M-(\d+)', content)
    if not ids:
        return 'M-014'
    max_id = max(int(i) for i in ids)
    return f'M-{max_id + 1:03d}'


def detect_agent(tool_input_str):
    """Guess which agent is active from tool input context."""
    lower = tool_input_str.lower()
    for keyword, agent in AGENT_KEYWORDS.items():
        if keyword in lower:
            return agent
    return '공통'


def is_duplicate(content, error_title, error_pattern_regex):
    """Check if this error type is already recorded."""
    # Check exact title
    if error_title.lower() in content.lower():
        return True
    # Check if the regex pattern itself matches any existing entry
    if re.search(error_pattern_regex, content, re.IGNORECASE):
        return True
    # Check key phrases overlap
    keywords = set(re.findall(r'[a-zA-Z가-힣]{3,}', error_title.lower()))
    for line in content.split('\n'):
        if line.startswith('### M-'):
            existing_kw = set(re.findall(r'[a-zA-Z가-힣]{3,}', line.lower()))
            overlap = keywords & existing_kw
            if len(overlap) >= 2:
                return True
    return False


def detect_error(tool_result_str):
    """Match tool result against known error patterns."""
    for pattern, title, default_agent, fix in ERROR_PATTERNS:
        if re.search(pattern, tool_result_str, re.IGNORECASE):
            return title, default_agent, pattern, fix
    return None, None, None, None


def record_mistake(mid, title, agent, situation, error_msg):
    """Append a new mistake entry to mistakes.md."""
    today = datetime.now().strftime('%Y-%m-%d')

    entry = f"""
### {mid}: {title}
- **에이전트**: {agent}
- **날짜**: {today}
- **상황**: {situation}
- **에러**: `{error_msg[:200]}`
- **수정**: (자동 기록 - 수정 방법 확인 필요)
- **예방**: (자동 기록 - 예방 방법 확인 필요)
"""

    with open(MISTAKES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the agent's section and insert before the next ---
    agent_section = f'## {agent}'
    if agent_section in content:
        # Find position after the agent header
        idx = content.index(agent_section)
        # Find the next --- after this section
        next_divider = content.find('\n---', idx + len(agent_section))
        if next_divider != -1:
            # Remove placeholder if present
            section_content = content[idx:next_divider]
            placeholder = '(아직 기록된 실수 없음 — 발생 시 추가)'
            if placeholder in section_content:
                content = content[:idx] + section_content.replace(placeholder, '') + content[next_divider:]
                # Recalculate position
                idx = content.index(agent_section)
                next_divider = content.find('\n---', idx + len(agent_section))

            content = content[:next_divider] + entry + content[next_divider:]
        else:
            content += entry
    else:
        # Agent section not found, append before Template
        template_idx = content.find('## Template')
        if template_idx != -1:
            content = content[:template_idx] + f'## {agent}\n{entry}\n---\n\n' + content[template_idx:]
        else:
            content += f'\n## {agent}\n{entry}\n'

    with open(MISTAKES_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    return mid


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get('tool_name', '')
    tool_input = hook_input.get('tool_input', {})
    tool_result = hook_input.get('tool_result', '')

    if tool_name not in ('Write', 'Edit', 'Bash'):
        sys.exit(0)

    # Only process errors (non-zero exit or error content)
    result_str = str(tool_result) if tool_result else ''
    if not result_str:
        sys.exit(0)

    # Detect error pattern
    error_title, default_agent, matched_pattern, fix_instruction = detect_error(result_str)
    if not error_title:
        sys.exit(0)

    # Read current mistakes to check duplicates and get next ID
    if not os.path.exists(MISTAKES_PATH):
        sys.exit(0)

    with open(MISTAKES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # If already recorded, still send fix instruction (don't re-record)
    if is_duplicate(content, error_title, matched_pattern):
        if fix_instruction:
            output = {"systemMessage": f"KNOWN MISTAKE: {error_title}\n{fix_instruction}"}
            print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)

    # Detect agent
    input_str = json.dumps(tool_input, default=str)
    agent = detect_agent(input_str)
    if agent == '공통':
        agent = default_agent

    # Build situation description
    if tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        situation = f'`{cmd[:100]}` 실행 중 발생'
    else:
        fp = tool_input.get('file_path', '')
        situation = f'`{os.path.basename(fp)}` 파일 작업 중 발생'

    # Extract error message (first matching line)
    error_lines = result_str.split('\n')
    error_msg = next(
        (line.strip() for line in error_lines
         if any(re.search(p, line, re.IGNORECASE) for p, _, _, _ in ERROR_PATTERNS)),
        error_lines[0][:200] if error_lines else 'Unknown error'
    )

    # Record it
    mid = get_next_id(content)
    record_mistake(mid, error_title, agent, situation, error_msg)

    # Build message with auto-fix instruction
    msg = f"MISTAKE RECORDED: [{mid}] {error_title} ({agent})"
    if fix_instruction:
        msg += f"\n{fix_instruction}"

    output = {"systemMessage": msg}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
