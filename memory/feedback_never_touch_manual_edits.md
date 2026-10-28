---
name: 세은 수동 편집 부분 절대 건드리지 마 — 통째 재빌드 금지
description: 노션/문서 수정 지시 시 세은이 수동으로 고쳐둔 부분은 일절 손대지 않는다. delete+recreate / 덮어쓰기 금지. 지시받은 부분에만 추가·수정
type: feedback
---

세은이 「수정해/추가해」 지시했을 때, **세은이 개인적으로 수동 편집해 둔 부분은 절대 아무것도 건드리지 않는다.**

- 통째로 delete + recreate (재빌드) 금지
- 전체 덮어쓰기 금지
- 지시받은 그 부분에만 add/edit (예: "마지막 보고 사항에만 추가" = 맨 끝에만 append)

**Why:** 2026-06-15 /장보고 노션 토글. 메타몽 정보 추가 지시에 토글 전체를 delete 후 재생성 → 세은이 수동으로 고쳐둔 Headline bullet·「1) CRM 대기 중」 등 전부 소실. 「너 디질래?? 내가 수동으로 수정해 놓은 부분 절대로 아무것도 건드리지 마」 강한 교정.

**How to apply:**
- 노션 수정 = 기존 블록 보존 + 지시 지점에만 PATCH append/update. 토글·페이지 delete/recreate X.
- 실수로 archive 했으면 즉시 `PATCH archived:false`로 복원 가능 (children 유지됨). 잘못 만든 새 블록은 archive.
- 수정 전 현재 상태 GET해서 세은 편집 흔적 확인 후 진행.

관련: [[feedback_notion_page_no_archive_only_append]] / [[feedback_daily_report_notion_toggle]].
