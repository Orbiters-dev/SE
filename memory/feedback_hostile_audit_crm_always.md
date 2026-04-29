---
name: CRM 건들면 무조건 적대감사
description: CRM 관련 스크립트/자동화는 작성 후 무조건 적대감사 필수. 진실 소스 확인 없이 작업 금지.
type: feedback
---

CRM 관련 작업(스크립트 수정·생성, 자동화, 대시보드 연동)은 **무조건 적대감사**로 검증.

**Why:** 2026-04-21 세션에서 세은이 "너 적대감사 하고 있냐? crm 고치는 건 무조건 적대감사해. 너 지금 n8n 기반으로 고치고 있어 뭐야"라고 지적. 내가 `update_crm_status.py`가 n8n staticData 수정하는 걸 보고 "이게 CRM"이라 단정 → 대시보드 실제 소스 확인 없이 작업. 적대감사 2차 시도 후에야 `loadCreators()`가 n8n+Django 하이브리드임을 확인. 두 번 헛짓거리 보고.

**How to apply:**
- CRM 스크립트 쓰기/수정 전: 대시보드 코드에서 `loadCreators` / `updateStatus` 등 데이터 소스 경로 먼저 Grep
- 작업 완료 직후: 적대감사(codex_evaluator 또는 수동) 반드시 실행
- workflow exit 0만 보고 "성공" 보고 금지 → 로그 전체 읽고 실제 기능 확인
- 방향 오판 의심 시: 섣불리 "전면 재작업" 선언 전에 한 번 더 감사
