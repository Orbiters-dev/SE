---
name: weekly report 효율 집계 기간 = 전 주 목 00:00 ~ 그 주 수 23:59
description: JP Weekly Report에서 메타 광고 등 효율·성과 지표 기간은 전 주 목요일 00:00 ~ 그 주 수요일 23:59 (목→수 7일). 월~일 달력주 아님.
metadata:
  type: feedback
---

세은 지시 (2026-06-18): "앞으로 weekly report 쓸 때 메타 광고나 이런 저런 거 효율 있잖아, 그 전 주 목요일 00:00~그 주 수요일 23:59 로 기간 정해서 하면 돼."

**Why:** weekly report는 목요일에 작성하며, 직전 목요일~수요일 한 주를 커버한다. 효율/성과 지표(메타 광고 spend/CTR/CPC/CPLPV 등)의 비교·집계 윈도우를 이 목→수 기준으로 통일.

**How to apply:**
- weekly report 메타·효율 지표 기간 = **전 주 목요일 00:00 ~ 그 주 수요일 23:59** (정확히 7일).
- weekly는 목요일에 작성. 그 주 수요일(작성 전날)까지 마감.
- 예: **6/18(목) 작성 weekly → `time_range {since: 2026-06-11, until: 2026-06-17}`** (전 주 목 6/11 ~ 그 주 수 6/17). 직전 비교 = 6/4~6/10.
- **달력주(월~일) 윈도우 X**, 7일 rolling(D-1~D-7) X. 항상 목 00:00 시작 → 수 23:59 종료.

**범위 구분 (혼동 금지):**
- 이 룰 = **weekly report** 효율 집계 전용.
- 일일 보고(/장보고)의 "이번 주 신규 광고" = 월요일 시작 (별개, [[feedback_this_week_means_monday_start]]).
- weekly 양식·OKR carry 등은 [[reference_jp_weekly_report_workflow]] / [[feedback_reference_previous_notion_for_okr]].
