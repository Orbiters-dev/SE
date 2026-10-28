---
name: Notion API numbered_list_item batch 묶임 사고
description: 큰 batch (100 children)에 numbered_list_item 여러 개 보내면 일부 누락/묶임. 작은 chunk 분할로 회피.
type: project
---

# Notion API: numbered_list_item batch에서 일부 누락 사고

**Fact:** 2026-05-07 W18 OKR 페이지(`35986c6d-c046-804d-8748-ff18d2d14a6a`) 작성 시 PATCH `/blocks/{page_id}/children` 100 blocks chunk에 ol(numbered_list_item) 4개 연속 삽입 → 첫 번째 ol 1개만 살아남고 2-4번 누락. 두 번째 chunk (after 파라미터) 호출 시 응답 results=20개로 비정상 (실제 입력 3개).

**Why:** Notion API의 numbered_list_item이 batch 안에서 "리스트 그룹" 으로 묶임 처리되는 듯. 한 children 배열에 여러 ol이 있으면 첫 번째 ol에 children으로 nesting되거나, 일부가 silently drop되는 패턴.

**How to apply:**
- numbered_list_item 추가 시 작은 chunk (5-10개씩) 또는 ol 사이에 다른 type 블록 끼워넣기
- 큰 batch 후에는 페이지 fetch로 실제 child 수 검증 필수
- `after` 파라미터로 insert 시 응답 results는 신뢰하지 말고 페이지 children 다시 fetch
- 더 안전한 패턴: ol 대신 ul (bulleted_list_item) 사용 — 이번 사고에서 ul은 모두 정상 삽입됨
