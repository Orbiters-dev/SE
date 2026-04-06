---
type: errlog
domain: pipeline
agents: [pipeliner, n8n-manager]
severity: critical
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [api, pipeline, filter, param]
moc: "[[MOC_파이프라인]]"
---

# errlog_conversations_api_filter

## 증상
API 필터링이 작동 안 함. 특정 이메일로 조회해도 전체 결과 반환.

## 원인
API 파라미터 이름 불일치:
- 잘못된 것: `?email=`
- 올바른 것: `?creator_email=`

## 해결
`/api/onzenna/pipeline/conversations/` 호출 시 `creator_email=` 사용.

## 교훈
API param 이름은 반드시 실제 엔드포인트 코드에서 확인. 추측 금지.
