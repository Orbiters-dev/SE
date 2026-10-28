---
name: 메타몽 대시보드 팝업 룰 (경고 미표시 + 가시화 + KRW)
description: meta-app 팝업/공지 영구 룰 — issues_info 경고 표시 금지, 줄글 X 카드·게이지 가시화, 금액 KRW 통일, 통합 지표는 Total ROAS 표기.
metadata:
  type: feedback
---

meta-app (메타몽 대시보드) 팝업·공지 작성 영구 룰. 2026-06-11 세션에서 세은 지시 누적.

1. **issues_info 경고 표시 금지 (영구)** — "경고 검토는 지우고, 앞으로도 하지마". 팝업·공지에 Meta API issues_info 경고문 노출 X. 데이터 수집에서도 제외.
2. **줄글 금지 — 가시화** — "구구절절 적지 말고 읽는 사람이 한 눈에 파악할 수 있도록". 카드/타일/게이지(기준선 포함)/배지로. 예: 졸업 = 점유율 게이지 3개 + 50% 기준선 + 충족 배지.
3. **금액 KRW 통일** — ¥ 혼용 X. 환산 환율은 해당 윈도우 평균 (Frankfurter).
4. **RPP 등 타채널 합산 ROAS = "Total ROAS" 표기** — Meta 단독은 sub로 병기. 기간 불일치 시 빨간 경고 1줄.
5. **명시적 줄바꿈** — 카드 sub 등 좁은 영역에서 자동 wrap에 맡기지 말고 의미 단위 \n (예: "Meta ₩…" / "+ RPP ₩…").

**Why:** 6/11 팝업 작업에서 경고 노출·줄글·¥ 혼용·어중간한 줄바꿈 4건 연속 교정.
**How to apply:** meta-app 팝업/공지 신규·수정 시 위 5개 체크 후 배포. 관련: [[reference_metamong_operating_persona]]
