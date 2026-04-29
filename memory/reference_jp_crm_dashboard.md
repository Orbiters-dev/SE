---
name: JP CRM 대시보드 URL
description: Grosmimi JP 인플루언서 파이프라인 CRM 수정은 orbitools Django 대시보드에서 수행 (2026-04-22~)
type: reference
---

**메인 URL (2026-04-22 이후 CRM 수정 공식 경로)**:
https://orbitools.orbiters.co.kr/api/onzenna/intelligence/dashboard/pipeline-crm/jp#pipeline-crm/us

- JP: `#pipeline-crm/jp`
- US: `#pipeline-crm/us`

**구 URL (참고용, CRM 수정 X)**:
https://orbiters-dev.github.io/WJ-Test1/financial-dashboard/index.html#jp/jp-pipeline

**데이터 소스 구조** (적대감사 2026-04-21 확인):
- **주 소스**: n8n staticData (workflow `ynMO08sqdUEDk4Rc`, `creators` 배열) — 대시보드 상태/DM/카운트
- **보조 소스**: Django `/api/onzenna/pipeline/creators/?region=jp` — discovery 백필 전용
- n8n에 있는 핸들이 Django보다 우선. Django는 아직 n8n에 안 들어온 신규 창작자 병합용.

**쓰기 경로**: 대시보드 `updateStatus()` → n8n webhook `update_status` → staticData만 갱신 (Django 미반영)

**주의**: CRM 관련 자동화는 반드시 **n8n staticData 기반**으로 작업. Django만 건드리면 대시보드 반영 안 됨.
