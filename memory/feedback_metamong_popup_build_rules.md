---
name: feedback-metamong-popup-build-rules
description: 메타몽 앱 팝업 제작 규칙 (2026-07-01 세은 반복 정정 누적)
metadata:
  type: feedback
---

# 메타몽 앱 팝업 제작 규칙 (2026-07-01)

meta-app 팝업 = `meta-app/components/meta/*Announcement.tsx` (컴포넌트 + `*_SHOW_UNTIL_UTC` + `*_DISMISS_KEY`), `AnnouncementStack.tsx` 체인에 우선순위로 연결. 배포 `vercel --prod --yes`(cd meta-app, PowerShell). 24h = `Date.UTC(...)` 만료. **다음 팝업으로 넣기 = 체인에서 A.onClose→B stageOrNext**.

**Why:** 2026-07-01 결산·신규광고 팝업 만들며 세은 반복 정정. 팝업은 한 번에 완성해야 함(반복 왕복 싫어함).

**How to apply (콘텐츠 규칙):**
- 콘텐츠 태그 표기 = **subject / focus 순서만**. hook·angle(앵글) 표기 X.
- 태그 없는 항목에 **"태깅 없음" 라벨 붙이지 마** — 그냥 지표만.
- 광고 리스트 = **Testing/Proven 단계 표기** 필수 + **운영중 vs OFF(정지) 섹션 분리**(OFF는 "OFF" 명시).
- 효율은 **CTR만 X → CPC도 같이**. CPLPV는 색뱃지(초록≤110/노랑≤140/빨강>140, 풀평균 124).
- 액션/방향 = **현재 날짜 기준** — 오늘이 이미 그 달이면 "다음 달"이 아니라 "이번 달". 이벤트 없는 달엔 "이벤트기 증액" 류 액션 넣지 마.
- 기존 룰 유지: 카드/게이지형(줄글 X)·KRW 통일·합산은 "Total ROAS"·경고 표시 금지.
