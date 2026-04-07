#!/usr/bin/env python3
"""
Mistake Recorder Hook - PostToolUse hook that auto-records ALL errors to mistakes.md.
Detects any error from tool results, categorizes by agent/skill/workflow, appends new entries.
"""
import sys
import json
import re
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MISTAKES_PATH = os.path.join(PROJECT_ROOT, 'memory', 'mistakes.md')
VAULT_ERRLOG_DIR = os.path.join(PROJECT_ROOT, 'vault', 'errlog')

# Agent → vault domain mapping
AGENT_DOMAIN_MAP = {
    '아마존퍼포마': 'ads', 'ppc시뮬이': 'ads', 'Meta Ads': 'ads', 'Google Ads': 'ads',
    '파이프라이너': 'pipeline', 'n8n 매니저': 'pipeline', '쇼피파이 UI': 'pipeline',
    '그로미미 컨텐츠 트래커': 'pipeline', '차앤맘 컨텐츠 트래커': 'pipeline', 'CI 팀장': 'pipeline',
    '골만이': 'finance', 'KPI 리포트': 'finance',
    '앱스터': 'app', '쇼피파이 테스터': 'app',
    '데이터키퍼': 'infra', '커뮤니케이터': 'infra',
    '이메일 지니': 'infra',
}
DOMAIN_MOC_MAP = {
    'ads': '광고', 'pipeline': '파이프라인', 'finance': '재무',
    'app': '앱', 'infra': '인프라', 'ops': '운영',
}

# ─────────────────────────────────────────────────
# Tool filename → Agent mapping
# ─────────────────────────────────────────────────
TOOL_AGENT_MAP = {
    # 아마존퍼포마 (Amazon PPC)
    'amazon_ppc_executor': '아마존퍼포마',
    'amazon_ppc_tester': '아마존퍼포마',
    'amazon_ppc_simulator': 'ppc시뮬이',
    'amazon_ppc_daily': '아마존퍼포마',
    'amazon_ads_oauth': '아마존퍼포마',
    'run_amazon_ppc': '아마존퍼포마',
    'generate_naeiae_deep_proposal': '아마존퍼포마',
    '_analyze_st': '아마존퍼포마',
    'fetch_campaign_urls': '아마존퍼포마',

    # 이메일 지니 (Gmail RAG)
    'gmail_rag': '이메일 지니',
    'gmail_rag_compose': '이메일 지니',
    'send_gmail': '이메일 지니',
    'sync_gmail_contacts': '이메일 지니',
    'fetch_anthropic_billing': '이메일 지니',

    # KPI 리포트
    'run_kpi_monthly': 'KPI 리포트',
    'kpi': 'KPI 리포트',

    # 데이터키퍼
    'data_keeper': '데이터키퍼',
    'data_keeper_client': '데이터키퍼',
    'data_keeper_backfill': '데이터키퍼',
    'deploy_datakeeper': '데이터키퍼',
    'export_to_shared': '데이터키퍼',
    'sync_nas_datakeeper': '데이터키퍼',

    # 그로미미 컨텐츠 트래커
    'fetch_syncly_export': '그로미미 컨텐츠 트래커',
    'sync_syncly_to_sheets': '그로미미 컨텐츠 트래커',
    'sync_sns_tab': '그로미미 컨텐츠 트래커',
    'sync_sns_tab_chaenmom': '차앤맘 컨텐츠 트래커',
    'sync_sns_tab_grosmimi': '그로미미 컨텐츠 트래커',
    'sync_sns_tab_jp': '그로미미 컨텐츠 트래커',
    'daily_syncly_email': '그로미미 컨텐츠 트래커',
    'syncly_daily_email': '그로미미 컨텐츠 트래커',

    # CI 팀장 (크롤러/컨텐츠)
    'fetch_apify_content': 'CI 팀장',
    'fetch_instagram_metrics': 'CI 팀장',
    'check_influencer_hashtag': 'CI 팀장',
    'check_nonclassified': 'CI 팀장',
    'build_apify_report': 'CI 팀장',
    'build_ranking_dashboard': 'CI 팀장',
    'update_usa_llm': 'CI 팀장',

    # 파이프라이너
    'test_influencer_flow': '파이프라이너',
    'dual_test_runner': '파이프라이너',
    'fetch_influencer_orders': '파이프라이너',
    'process_influencer_order': '파이프라이너',
    'sync_influencer_notion': '파이프라이너',
    'create_typeform_influencer': '파이프라이너',
    'setup_n8n_gifting': '파이프라이너',
    'setup_n8n_gifting2': '파이프라이너',
    'setup_n8n_delivery_email': '파이프라이너',
    'setup_n8n_sample_request': '파이프라이너',
    'setup_n8n_creator_to_airtable': '파이프라이너',
    'update_n8n_gifting': '파이프라이너',
    'update_n8n_gifting2': '파이프라이너',
    'update_n8n_full_data_save': '파이프라이너',
    'update_n8n_metafields': '파이프라이너',
    'update_n8n_creators': '파이프라이너',
    'sync_airtable_schema': '파이프라이너',

    # n8n 매니저
    'clone_n8n_to_test': 'n8n 매니저',
    'setup_n8n_core_signup': 'n8n 매니저',
    'setup_n8n_customer': 'n8n 매니저',
    'setup_n8n_loyalty': 'n8n 매니저',
    'setup_n8n_metafield': 'n8n 매니저',
    'setup_n8n_order': 'n8n 매니저',
    'setup_n8n_signup': 'n8n 매니저',
    'setup_n8n_syncly': 'n8n 매니저',

    # 앱스터 (Shopify + ONZ APP)
    'deploy_onzenna': '앱스터',
    'shopify_tester': '쇼피파이 테스터',
    'shopify_bulk_import': '앱스터',
    'shopify_oauth': '앱스터',
    'setup_shopify_webhooks': '앱스터',
    'setup_survey_metafields': '앱스터',
    'sync_survey_to_customer': '앱스터',
    'create_missing_tables': '앱스터',
    'configure_nginx_cors': '앱스터',

    # 쇼피파이 UI
    'deploy_influencer_page': '쇼피파이 UI',
    'deploy_influencer_gifting': '쇼피파이 UI',
    'deploy_influencer_gifting2': '쇼피파이 UI',
    'deploy_chaenmom_gifting': '쇼피파이 UI',
    'deploy_naeiae_gifting': '쇼피파이 UI',
    'deploy_creator_sample_form': '쇼피파이 UI',
    'deploy_creator_profile': '쇼피파이 UI',
    'deploy_core_signup': '쇼피파이 UI',
    'deploy_loyalty_survey': '쇼피파이 UI',
    'setup_n8n_gifting_airtable': '쇼피파이 UI',
    'setup_n8n_gifting_pg': '쇼피파이 UI',

    # 커뮤니케이터
    'run_communicator': '커뮤니케이터',

    # 효율가
    'run_workflow_analyzer': '효율가',
    'run_skill_optimizer': '효율가',

    # 골만이
    'golmani': '골만이',

    # Meta Ads
    'fetch_facebook_ads': 'Meta Ads',
    'fetch_meta_ads': 'Meta Ads',

    # 자료 찾기
    'parse_export_documents': '자료 찾기',
    'autopilot': '자료 찾기',

    # 공통
    'error_logger': 'Core',
    'env_loader': 'Core',
    'mistake_recorder': 'Core',
    'mistake_checker': 'Core',
}

# Workflow file → Agent mapping
WORKFLOW_AGENT_MAP = {
    'amazon_ppc': '아마존퍼포마',
    'amazon_ppc_executor': '아마존퍼포마',
    'amazon_ppc_tester': '아마존퍼포마',
    'amazon_ppc_daily': '아마존퍼포마',
    'meta_ads': 'Meta Ads',
    'meta_tester': 'Meta Ads',
    'google_ads': 'Google Ads',
    'crawler_pipeline': 'CI 팀장',
    'gmail_rag': '이메일 지니',
    'gmail_affiliate': '이메일 지니',
    'influencer_flow': '파이프라이너',
    'influencer_inbound': '파이프라이너',
    'influencer_typeform': '파이프라이너',
    'process_influencer': '파이프라이너',
    'shopify_tester': '쇼피파이 테스터',
    'shopify_customer': '앱스터',
    'onzenna_survey': '앱스터',
    'deploy_influencer': '쇼피파이 UI',
    'n8n': 'n8n 매니저',
    'export_document': '자료 찾기',
    'find_resources': '자료 찾기',
    'weekly_performance': '효율가',
    'no_polar_financial': 'KPI 리포트',
    'data_output': '데이터키퍼',
    'teams_notifications': '커뮤니케이터',
    'gorgias': 'CS (Gorgias)',
    'grosmimi': '그로미미 컨텐츠 트래커',
    'sync_influencer_notion': '파이프라이너',
}

# Skill dir → Agent mapping
SKILL_AGENT_MAP = {
    'amazon-ppc-agent': '아마존퍼포마',
    'appster': '앱스터',
    'communicator': '커뮤니케이터',
    'content-intelligence': 'CI 팀장',
    'data-keeper': '데이터키퍼',
    'data-modeler': '분석이',
    'firecrawl': 'Firecrawl',
    'gmail-rag': '이메일 지니',
    'golmani': '골만이',
    'golmani-formatter': '골만이',
    'golmani-validator': '골만이',
    'kpi-monthly': 'KPI 리포트',
    'meta-ads-agent': 'Meta Ads',
    'n8n-manager': 'n8n 매니저',
    'pipeliner': '파이프라이너',
    'resource-finder': '자료 찾기',
    'shopify-ui-expert': '쇼피파이 UI',
    'syncly-crawler': '그로미미 컨텐츠 트래커',
}

# ─────────────────────────────────────────────────
# Known error patterns with auto-fix hints
# ─────────────────────────────────────────────────
KNOWN_PATTERNS = [
    (r'UnicodeEncodeError.*charmap', 'cp949 인코딩 에러',
     "스크립트 상단에 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 추가"),
    (r'UnicodeDecodeError', '파일 디코딩 에러',
     "파일 읽기를 `open(f, 'rb')` → `.decode('utf-8', errors='replace')` 로 변경"),
    (r'unexpected EOF while looking for matching', '따옴표 중첩 에러',
     "`python -c` 대신 `.tmp/script.py` 파일로 저장 후 `python .tmp/script.py` 실행"),
    (r'SSL.*revocation|schannel.*revocation', 'SSL revocation 실패',
     "curl 명령에 `-sk` 플래그 추가"),
    (r'Unable to parse range.*\\!', 'Sheets range 포맷 에러',
     "탭 이름을 작은따옴표로 감싸기: `\"'Tab Name'!A1:Z50\"` 형식"),
    (r'text-embedding-004.*404|404.*text-embedding-004', '임베딩 모델 404',
     "모델명을 `gemini-embedding-001` 로 변경"),
    (r'Insufficient Permission.*scopes?', 'OAuth 스코프 부족',
     "Gmail OAuth 재인증 필요: gmail.readonly + gmail.send + gmail.modify 스코프"),
    (r'google\.generativeai.*deprecated|ImportError.*generativeai', 'genai SDK deprecated',
     "`import google.generativeai` → `from google import genai` 로 변경"),
    (r'"active".*read.only|active.*cannot be set', 'n8n active 필드 에러',
     "POST body에서 `active` 필드 제거"),
    (r'dimension.*mismatch|expected \d+ got \d+', '벡터 차원 불일치',
     "임베딩 모델 차원 확인 (gemini-embedding-001 = 3072)"),
    (r'rate.limit|429|Too Many Requests', 'API rate limit 초과',
     "30초 대기 후 재시도. 반복 시 batch 크기 줄이기"),
    (r'TimeoutError|timed? ?out|ETIMEDOUT', 'API 타임아웃',
     "timeout 값 늘리기 (requests: timeout=60)"),
    (r'FileNotFoundError|No such file or directory', '파일 경로 오류',
     "경로 존재 여부 확인. NAS symlink 깨짐 여부 점검"),
    (r'PermissionError|Access.*denied', '권한 에러',
     "파일/폴더 권한 확인. NAS 파일이면 네트워크 연결 상태 점검"),
    (r'JSONDecodeError|Expecting value', 'JSON 파싱 실패',
     "응답 내용 확인 (HTML 에러 페이지? 빈 응답?)"),
    (r'KeyError', 'KeyError - 딕셔너리 키 없음',
     "`.get(key)` 또는 `if key in dict` 가드 추가"),
    (r'IndexError', 'IndexError - 리스트 인덱스 초과',
     "리스트 길이 확인 후 범위 체크 추가"),
    (r'ConnectionRefusedError|ECONNREFUSED', '서버 연결 거부',
     "서버 상태 확인: curl -sk https://orbitools.orbiters.co.kr/healthz"),
    (r'ModuleNotFoundError|No module named', '패키지 미설치',
     "`pip install 패키지명` 실행 후 재시도"),
    (r'AttributeError', 'AttributeError - 속성 없음',
     "객체 타입 확인. None 체크 또는 hasattr() 가드 추가"),
    (r'TypeError', 'TypeError - 타입 불일치',
     "인자 타입 확인. str/int/list 변환 필요 여부 점검"),
    (r'ValueError', 'ValueError - 값 오류',
     "입력값 범위/형식 확인"),
    (r'RecursionError', 'RecursionError - 무한 재귀',
     "재귀 종료 조건 확인. 순환 참조 점검"),
    (r'MemoryError|out of memory', '메모리 부족',
     "데이터 청크 처리로 전환. batch_size 줄이기"),
    (r'SyntaxError', 'SyntaxError - 문법 오류',
     "Python 문법 확인. 괄호/따옴표 짝 맞추기"),
    (r'IndentationError', 'IndentationError - 들여쓰기 오류',
     "탭/스페이스 혼용 확인. 일관된 들여쓰기 사용"),
    (r'ImportError', 'ImportError - 임포트 실패',
     "모듈 경로/설치 확인. PYTHONPATH 점검"),
    (r'AssertionError', 'AssertionError - 단언 실패',
     "assert 조건 확인. 데이터 검증 로직 점검"),
    (r'HTTP Error [45]\d\d|status.?code.*[45]\d\d|[45]\d\d.*status', 'HTTP 4xx/5xx 에러',
     "API 응답 내용 확인. 인증/권한/요청 형식 점검"),
    (r'certificate verify failed|SSL.*certificate', 'SSL 인증서 에러',
     "curl -sk 또는 requests verify=False 추가 (개발환경만)"),
]

# Generic error detection - catches anything not in KNOWN_PATTERNS
GENERIC_ERROR_PATTERNS = [
    r'Traceback \(most recent call last\)',
    r'Error:',
    r'Exception:',
    r'FAILED',
    r'error occurred',
    r'\[ERROR\]',
    r'exit code [1-9]',
]


def detect_agent_from_input(tool_input_str, tool_name):
    """Detect agent from file path or bash command."""
    text = tool_input_str.lower()

    # Check skill paths
    for skill_key, agent in SKILL_AGENT_MAP.items():
        if skill_key in text:
            return agent

    # Check workflow paths
    for wf_key, agent in WORKFLOW_AGENT_MAP.items():
        if wf_key in text:
            return agent

    # Check tool filenames
    for tool_key, agent in TOOL_AGENT_MAP.items():
        if tool_key in text:
            return agent

    # Fallback keyword matching
    fallback = {
        'gmail': '이메일 지니',
        'n8n': 'n8n 매니저',
        'airtable': '파이프라이너',
        'shopify': '앱스터',
        'pinecone': '이메일 지니',
        'openai|anthropic|gemini|claude': 'Core (LLM)',
        'datakeeper|data_keeper': '데이터키퍼',
        'amazon': '아마존퍼포마',
        'meta|facebook': 'Meta Ads',
        'google_ads': 'Google Ads',
        'ga4|analytics': 'Google Ads',
        'syncly': '그로미미 컨텐츠 트래커',
        'golmani|openpyxl|dcf|lbo': '골만이',
        'communicator': '커뮤니케이터',
        'deploy_': '앱스터',
        'onzenna': '앱스터',
    }
    for pattern, agent in fallback.items():
        if re.search(pattern, text):
            return agent

    return 'Core (공통)'


def detect_error(result_str):
    """Match result against known patterns. Returns (title, fix_hint, is_known)."""
    for pattern, title, fix in KNOWN_PATTERNS:
        if re.search(pattern, result_str, re.IGNORECASE):
            return title, fix, True

    # Generic error detection
    for gp in GENERIC_ERROR_PATTERNS:
        if re.search(gp, result_str, re.IGNORECASE):
            # Extract error type from traceback
            tb_match = re.search(r'(\w+Error|\w+Exception): (.+)', result_str)
            if tb_match:
                err_type = tb_match.group(1)
                err_msg = tb_match.group(2)[:80]
                return f'{err_type}: {err_msg}', '에러 내용 확인 후 수정 필요', False
            return '알 수 없는 에러', '에러 로그 확인 필요', False

    return None, None, None


def get_next_id(content):
    """Get next M-XXX id from mistakes.md."""
    ids = re.findall(r'M-(\d+)', content)
    if not ids:
        return 'M-011'
    return f'M-{max(int(i) for i in ids) + 1:03d}'


def is_duplicate(content, error_title):
    """Check if this error title is already in mistakes.md."""
    # Normalize for comparison
    normalized = re.sub(r'\s+', ' ', error_title.lower().strip())
    # Check title overlap
    existing_titles = re.findall(r'### M-\d+: (.+)', content)
    for t in existing_titles:
        t_norm = re.sub(r'\s+', ' ', t.lower().strip())
        # Count word overlap
        words_a = set(re.findall(r'[a-zA-Z가-힣]{2,}', normalized))
        words_b = set(re.findall(r'[a-zA-Z가-힣]{2,}', t_norm))
        if words_a and words_b and len(words_a & words_b) >= 2:
            return True
    return False


def extract_error_message(result_str):
    """Extract the most relevant error line."""
    lines = result_str.split('\n')
    # Prefer lines with Error/Exception
    for line in lines:
        if re.search(r'\w+Error|\w+Exception|FAILED|\[ERROR\]', line):
            return line.strip()[:200]
    return lines[0].strip()[:200] if lines else 'Unknown'


def record_mistake(mid, title, agent, situation, error_msg, fix_hint, is_known):
    """Append a new mistake entry to mistakes.md under the correct agent section."""
    today = datetime.now().strftime('%Y-%m-%d')

    fix_text = fix_hint if fix_hint else '(수동 확인 필요)'
    known_tag = '' if is_known else ' ⚠️ 신규'

    entry = f"""
### {mid}: {title}{known_tag}
- **에이전트**: {agent}
- **날짜**: {today}
- **상황**: {situation}
- **에러**: `{error_msg}`
- **수정**: {fix_text}
- **예방**: (확인 후 추가)
"""

    with open(MISTAKES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    agent_section = f'## {agent}'
    placeholder = '(아직 추가 기록 없음)'
    placeholder_old = '(아직 기록된 실수 없음 — 발생 시 추가)'

    if agent_section in content:
        idx = content.index(agent_section)
        next_divider = content.find('\n---', idx + len(agent_section))

        # Remove placeholder if present
        if next_divider != -1:
            section_content = content[idx:next_divider]
            for ph in [placeholder, placeholder_old]:
                if ph in section_content:
                    section_content = section_content.replace(ph, '')
            content = content[:idx] + section_content + content[next_divider:]
            idx = content.index(agent_section)
            next_divider = content.find('\n---', idx + len(agent_section))

        if next_divider != -1:
            content = content[:next_divider] + entry + content[next_divider:]
        else:
            content += entry
    else:
        # New agent section - insert before Template
        template_idx = content.find('## Template')
        new_section = f'\n## {agent}\n{entry}\n---\n'
        if template_idx != -1:
            content = content[:template_idx] + new_section + content[template_idx:]
        else:
            content += new_section

    with open(MISTAKES_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    return mid


def create_vault_errlog(mid, title, agent, situation, error_msg, fix_hint):
    """Create a vault errlog note for the new mistake. Returns filepath or None."""
    try:
        os.makedirs(VAULT_ERRLOG_DIR, exist_ok=True)
        slug = re.sub(r'[^a-z0-9]+', '_', title.lower())[:50].strip('_')
        filepath = os.path.join(VAULT_ERRLOG_DIR, f'errlog_{slug}.md')
        if os.path.exists(filepath):
            return None

        domain = AGENT_DOMAIN_MAP.get(agent, 'ops')
        moc_name = DOMAIN_MOC_MAP.get(domain, '운영')
        today = datetime.now().strftime('%Y-%m-%d')

        # Extract tags from title and error
        tag_words = set(re.findall(r'[a-zA-Z]{3,}', f'{title} {error_msg}'.lower()))
        tags = ', '.join(sorted(list(tag_words)[:5]))

        content = f"""---
type: errlog
domain: {domain}
agents: [{agent}]
severity: medium
status: open
created: {today}
tags: [{tags}]
moc: "[[MOC_{moc_name}]]"
---

# {mid}: {title}

## Situation
{situation}

## Error
`{error_msg[:300]}`

## Fix
{fix_hint or '(수동 확인 필요)'}

## Prevention
(TBD)
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath
    except Exception:
        return None


def index_vault_note(filepath):
    """Index a vault note into LightRAG. Fire-and-forget."""
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tools'))
        from rag_client import index_file, enqueue_for_index
        if not index_file(filepath, timeout=5):
            enqueue_for_index(filepath)
    except Exception:
        pass


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get('tool_name', '')
    tool_input = hook_input.get('tool_input', {})
    tool_result = hook_input.get('tool_result', '')

    if tool_name not in ('Bash', 'Write', 'Edit'):
        sys.exit(0)

    result_str = str(tool_result) if tool_result else ''
    if not result_str or len(result_str) < 10:
        sys.exit(0)

    # Detect error
    error_title, fix_hint, is_known = detect_error(result_str)
    if not error_title:
        sys.exit(0)

    # Check mistakes.md exists
    if not os.path.exists(MISTAKES_PATH):
        sys.exit(0)

    with open(MISTAKES_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Skip duplicates (known errors already documented)
    if is_known and is_duplicate(content, error_title):
        output = {"systemMessage": f"KNOWN: {error_title} — {fix_hint}"}
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)

    # Detect agent
    input_str = json.dumps(tool_input, default=str)
    agent = detect_agent_from_input(input_str, tool_name)

    # Build situation
    if tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        situation = f'`{cmd[:120]}` 실행 중'
    else:
        fp = tool_input.get('file_path', '')
        situation = f'`{os.path.basename(fp)}` 파일 작업 중'

    error_msg = extract_error_message(result_str)
    mid = get_next_id(content)
    record_mistake(mid, error_title, agent, situation, error_msg, fix_hint, is_known)

    # Auto-create vault errlog note + RAG index (fire-and-forget)
    vault_path = create_vault_errlog(mid, error_title, agent, situation, error_msg, fix_hint)
    if vault_path:
        index_vault_note(vault_path)

    # Auto pull → commit → push (실패해도 메인 흐름 영향 없음)
    try:
        import subprocess
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # pull 먼저 — union merge로 기존 내용 보존
        subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'],
                       cwd=project_root, capture_output=True, timeout=20)
        subprocess.run(['git', 'add', 'memory/mistakes.md', 'vault/errlog/'],
                       cwd=project_root, capture_output=True, timeout=10)
        subprocess.run(['git', 'commit', '-m', f'auto: mistakes [{mid}] {error_title[:50]}'],
                       cwd=project_root, capture_output=True, timeout=10)
        subprocess.run(['git', 'push', 'origin', 'main'],
                       cwd=project_root, capture_output=True, timeout=20)
    except Exception:
        pass

    msg = f"MISTAKE RECORDED [{mid}] {error_title} → {agent}"
    if fix_hint:
        msg += f"\n→ {fix_hint}"

    print(json.dumps({"systemMessage": msg}, ensure_ascii=False))


if __name__ == '__main__':
    main()
