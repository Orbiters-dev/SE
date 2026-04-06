---
type: errlog
domain: pipeline
agents: [pipeliner, n8n-manager]
severity: critical
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [email, auto-send, incident, n8n]
moc: "[[MOC_파이프라인]]"
---

# errlog_auto_email_send_incident

## 증상
n8n 워크플로우가 321건의 이메일을 자동 발송. 의도하지 않은 대량 발송 사고.

## 원인
자동 발송 트리거 조건이 너무 느슨함. 테스트 중 실제 발송이 실행됨.

## 해결
- `is_auto_sent` 플래그 추가 (PipelineConversation 모델)
- 발송 전 Human-in-the-Loop(HiL) 확인 단계 필수
- `testEmailOverride` 설정 후 테스트, 반드시 빈값으로 초기화

## 교훈
자동 발송 = 항상 HiL 게이트 필수. 테스트 후 override 반드시 초기화.

## 관련
- [[feedback_propose_execute_ux]]
