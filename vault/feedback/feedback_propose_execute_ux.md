---
type: feedback
domain: pipeline
agents: [pipeliner, syncly-crawler]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [ux, email, syncly, auto-send]
moc: "[[MOC_파이프라인]]"
---

# feedback_propose_execute_ux

## 핵심 규칙
- **Syncly 메트릭 필수**: 이메일 생성 전 콘텐츠 메트릭 확인
- **자동발송 금지**: 항상 Human-in-the-Loop 확인 후 발송
- Propose → 유저 확인 → Execute 순서 준수

## 관련
- [[errlog_auto_email_send_incident]]
