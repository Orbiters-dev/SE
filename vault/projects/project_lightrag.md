---
type: project
domain: infra
agents: [data-keeper]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [lightrag, rag, knowledge-graph, vector-db]
moc: "[[MOC_인프라]]"
---

# project_lightrag

LightRAG — 프로젝트 전체 knowledge graph + vector DB.
memory, skill, workflow, error log 인덱싱.

## 서버
- URL: `http://localhost:9621`
- 시작: `bash lightrag/start_server.sh`

## 사용법
```bash
python tools/rag_query.py "query" --mode hybrid  # 검색
python tools/rag_index.py                         # 재인덱싱
python tools/rag_index.py --list                  # 인덱싱 상태
```

## 검색 모드
- `hybrid` (기본) — local + global 결합
- `local` — 특정 엔티티 주변
- `naive` — 단순 벡터 (빠르지만 그래프 맥락 없음)

## 언제 쿼리
1. API 호출 전 — known quirks 확인
2. 새 작업 시작 시 — 관련 과거 이슈
3. 에러 발생 시 — 동일 에러 해결 방법
