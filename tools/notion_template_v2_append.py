"""마스터 Daily Report TEMPLATE 토글에 v2 (Jiah 형식) append.
한 번만 실행. 멱등성 없음 — 재실행 전 GET으로 children 수 확인."""
import json
import urllib.request
from pathlib import Path

env = {}
for line in Path('.env').read_text(encoding='utf-8').splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k, _, v = line.partition('=')
        env[k.strip()] = v.strip()

TOKEN = env['NOTION_API_TOKEN']
TEMPLATE_ID = '35a86c6d-c046-81f1-96d4-d1fe3634baaf'
URL = f'https://api.notion.com/v1/blocks/{TEMPLATE_ID}/children'
HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json',
}


def rt(content, bold=False, italic=False):
    return {
        'type': 'text',
        'text': {'content': content},
        'annotations': {'bold': bold, 'italic': italic},
    }


def para(*runs):
    runs = [rt(r) if isinstance(r, str) else r for r in runs]
    return {'object': 'block', 'type': 'paragraph',
            'paragraph': {'rich_text': list(runs)}}


def h3(content):
    return {'object': 'block', 'type': 'heading_3',
            'heading_3': {'rich_text': [rt(content)]}}


def divider():
    return {'object': 'block', 'type': 'divider', 'divider': {}}


def bullet(*runs, children=None):
    runs = [rt(r) if isinstance(r, str) else r for r in runs]
    blk = {'object': 'block', 'type': 'bulleted_list_item',
           'bulleted_list_item': {'rich_text': list(runs)}}
    if children:
        blk['bulleted_list_item']['children'] = children
    return blk


def table(width, rows):
    """rows: list of list of strings (each row = list of cell texts)."""
    children = []
    for row in rows:
        cells = [[rt(c)] for c in row]
        children.append({'object': 'block', 'type': 'table_row',
                         'table_row': {'cells': cells}})
    return {'object': 'block', 'type': 'table',
            'table': {'table_width': width, 'has_column_header': True,
                      'has_row_header': False, 'children': children}}


blocks = [
    divider(),
    h3('📋 TEMPLATE v2 (Jiah 형식 반영, 2026-05-22~)'),
    para(rt('복제용 — 이 v2 블록 전체를 복제해서 새 날짜 보고에 사용.', italic=True)),

    # 0. Headline
    h3('0. Headline'),
    para('오늘 끝낸 것 1~2개 + 큰 결과 1개 + blocker 위치 (1단락 압축).',
         rt(' 마지막에 결정 요청 위치 굵게 — 예: 「§4 참고」.', bold=True)),

    # 1) CRM
    h3('1) CRM 개발 진척'),
    para(rt('주요 작업', bold=True)),
    para(rt('<프로젝트명>', bold=True)),
    bullet(
        rt('[진행 중/완료/검수대기] 세부 작업명', bold=True),
        children=[
            para('배경 — '),
            para('작업 — '),
            para('결과 — '),
            para('잔여 — '),
        ],
    ),
    para(rt('부수 작업', bold=True)),
    para(rt('<프로젝트명>', bold=True)),
    bullet(rt('[상태] ', bold=True), '세부 작업명 — timeline'),
    para(rt('원기님께 부탁', bold=True)),
    bullet(rt('[대기] ', bold=True), '부탁 항목 — 어떤 단계 / 누가 처리 / 마감'),

    # 2) Meta
    h3('2) 메타 광고 (JP)'),

    para(rt('◆ 성과', bold=True)),
    para(rt('■ 전체 성과', bold=True)),
    para('일 단위 비교 (어제 M-D vs 그저께 M-D)'),
    table(4, [
        ['지표', '어제', '그저께', 'Δ'],
        ['지출', '', '', ''],
        ['클릭', '', '', ''],
        ['CTR', '', '', ''],
        ['CPC', '', '', ''],
    ]),
    para('주 단위 비교 (D-7~D-13 vs D-14~D-20)'),
    table(4, [
        ['지표', '지난 7일', '직전 7일', 'Δ'],
        ['지출', '', '', ''],
        ['클릭', '', '', ''],
        ['CTR', '', '', ''],
        ['CPC', '', '', ''],
    ]),
    para(rt('■ 캠페인별 (7일 누적)', bold=True)),
    bullet('캠페인명 — 지출 / 클릭 / CTR / CPC'),

    para(rt('◆ 이번 주 신규 광고', bold=True)),
    table(5, [
        ['광고명', '게시일', '지출', '클릭', 'CTR'],
        ['', '', '', '', ''],
    ]),

    para(rt('◆ BEST 광고', bold=True)),
    para(rt('기준: CTR 상위 + CPC 하위 종합 (7일 누적, 지출 ≥₩1,000)', italic=True)),
    table(6, [
        ['광고명', '지출', '클릭', 'CTR', 'CPC', '비고'],
        ['', '', '', '', '', ''],
    ]),

    para(rt('◆ WORST 광고', bold=True)),
    para(rt('기준: 학습 완료 + 절대/상대 기준 동시 만족 (7일 누적)', italic=True)),
    table(8, [
        ['광고명', '풀 percentile', 'CTR', 'CPC', 'Freq', 'velocity', '지출', '액션'],
        ['', '', '', '', '', '', '', ''],
    ]),

    para(rt('◆ Active experiments (운영 중 가설·룰)', bold=True)),
    table(4, [
        ['실험/룰', '가설', 'Status', 'Next checkpoint'],
        ['Off Rule 2중 게이트', '풀 P20 + 절대 CTR/CPC 동시 hit = 강한 Off 신호', '운영 중 (5/18~)', '1주 후 평가'],
        ['Testing→Proven 졸업', '7일 share 모두 ≥50% + 2주 유지', '운영 중', '매주'],
    ]),

    para(rt('◆ 부가 작업', bold=True)),
    bullet('졸업 사례, 룰 변경, 공부 노트 등'),

    # 3) 기타
    h3('3) 기타 작업'),
    para(rt('◆ (단발 작업 헤더 — 예: Syncly 키워드 정비)', bold=True)),
    bullet('bullet'),

    para(rt('◆ 인플루언서 DM', bold=True)),
    table(2, [
        ['인플루언서', 'STEP / 진행'],
        ['', ''],
    ]),
    para(rt('시딩 발송 (유상)', bold=True)),
    bullet('@핸들 (성씨様) — sku · 팔로워 N만 / 평균 reach N'),
    para(rt('시딩 발송 (무상)', bold=True)),
    bullet('@핸들 (성씨様) — sku · 팔로워 N만 / 평균 reach N'),
    para(rt('신규 스케줄 조정 (업로드 예정일 순)', bold=True)),
    bullet('YYYY-MM-DD @핸들 (성씨様) — sku'),
    para(rt('이번 보고 후 캘린더 추가/변경 사항', bold=True)),
    para(rt('[이미지 삽입 필요] 세은이 캘린더 이미지에 직접 표시하여 첨부.', italic=True)),
    bullet('(변경 사항)'),

    para(rt('◆ 인스타그램 게시물 업로드 (자체 컨텐츠)', bold=True)),
    bullet(''),

    # 4) 의문 사항 / 결정 요청
    h3('4) 의문 사항 / 결정 요청'),
    table(4, [
        ['#', '항목', '사유 / 컨텍스트', '회신란'],
        ['1', '', '', ''],
        ['2', '', '', ''],
    ]),
    para(rt('Default if no response: ', bold=True),
         rt('(당일 기본 진행 방침 한 줄)', italic=True)),
]

print(f'블록 수: {len(blocks)}')
payload = {'children': blocks}
req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'),
                             headers=HEADERS, method='PATCH')
try:
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode('utf-8')
        status = resp.status
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8')
    status = e.code

print(f'HTTP {status}')
Path('.tmp/notion_template_v2_response.json').write_text(body, encoding='utf-8')
data = json.loads(body)
if 'results' in data:
    print(f'append 된 블록 수: {len(data["results"])}')
else:
    print(body[:500])
