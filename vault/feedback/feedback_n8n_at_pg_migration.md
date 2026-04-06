---
type: feedback
domain: pipeline
agents: [n8n-manager]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [n8n, airtable, postgresql, migration]
moc: "[[MOC_파이프라인]]"
---

# feedback_n8n_at_pg_migration

## 핵심 규칙
- Airtable → PostgreSQL 마이그레이션은 **전체 한번에**
- 37개 규칙 모두 적용 후 커밋
- 부분 마이그레이션 금지 (중간 상태에서 운영하면 데이터 불일치)
