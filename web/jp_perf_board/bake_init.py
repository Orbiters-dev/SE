# -*- coding: utf-8 -*-
"""세은 편집 JSON(init_state.json)을 index.html의 initBoards 원본으로 베이크"""
import json, re

base = r'C:\Users\orbit\Desktop\SE\.tmp\jp_perf_board'
state = json.load(open(base + r'\init_state.json', encoding='utf-8'))

# 검증
assert all(k in state for k in ['rpp', 'amz', 'meta', 'tiktok', 'notes']), 'missing tab'
for k, v in state.items():
    assert 'pages' in v and all('shapes' in p for p in v['pages']), f'{k} bad structure'
print('state ok:', {k: sum(len(p['shapes']) for p in v['pages']) for k, v in state.items()})

html = open(base + r'\index.html', encoding='utf-8').read()
start = html.index('function initBoards(){')
end_marker = '/* ============ 상태 ============ */'
end = html.index(end_marker)

init_js = json.dumps(state, ensure_ascii=False, indent=1)
replacement = (
    '/* 원본 = 세은 편집 반영본 (2026-10-08 JSON 베이크) */\n'
    'const INIT_STATE = ' + init_js + ';\n'
    'function initBoards(){ return JSON.parse(JSON.stringify(INIT_STATE)); }\n\n'
)
html = html[:start] + replacement + html[end:]
open(base + r'\index.html', 'w', encoding='utf-8').write(html)
print('baked. html size:', len(html))
