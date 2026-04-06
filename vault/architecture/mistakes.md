---
type: architecture
domain: ops
agents: [제갈량]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [mistakes, lessons, agents]
moc: "[[MOC_운영]]"
---

# mistakes — 에이전트별 실수 기록

## M-001 ~ M-014 (상세 내용은 각 errlog 참조)

| ID | 에이전트 | 실수 | 참조 |
|----|---------|------|------|
| M-001 | amazon-ppc-agent | config field 매핑 누락 | [[errlog_ppc_config_override]] |
| M-002 | amazon-ppc-agent | search term timeout silent fail | [[errlog_search_term_timeout]] |
| M-003 | amazon-ppc-agent | 메트릭 정의 미확인 | [[errlog_autocomplete_wrong_metric]] |
| M-004 | pipeliner | API param 이름 불일치 | [[errlog_conversations_api_filter]] |
| M-005 | n8n-manager | 321건 자동발송 사고 | [[errlog_auto_email_send_incident]] |
| M-006 | syncly-crawler | hashtag 항등식 분류 버그 | [[errlog_hashtag_classification_tautology]] |
| M-007~014 | 미기록 | — | — |

## 패턴 분석
- config 변경 시 매핑 함수 업데이트 잊음
- silent fail (빈 배열) 처리 미흡
- API 파라미터 추측 (문서 미확인)
- 자동화 트리거 조건 미검증
