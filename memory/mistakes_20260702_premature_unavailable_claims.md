---
name: mistakes-20260702-premature-unavailable-claims
description: "오답노트 2026-07-02 (단일 probe로 '없음/불가' 단정 반복 → 재확인서 뒤집힘 4건)"
metadata:
  type: feedback
---

# 오답노트 2026-07-02 (JP BSR 조사 — 성급한 '불가' 단정)

한 번의 실패/한 각도만 보고 "없다/안 된다" 단정 → 세은이 되물으면 다시 파보니 다 있었음. 4연속 사고.

1. **Parent ASIN "일본 미제공"** 오판 — Amazon JP도 US와 동일 제공(Keepa parentAsin, domain 무관)인데 내 SERP 스크랩에 안 떠서 N/A 회색처리. 「미국은 주는데 일본은 안 줄 이유가 없지」 교정.
2. **라쿠텐 "Toddler Cups 카테고리 없음"** 오판 — 엉뚱한 장르(100541, 댄스의상) 하나 찍고 단정. 실제 `トレーニングカップ・マグ`(genre 207753) 랭킹 존재(daily/weekly/realtime). 「카테고리 있을 거 아니야」 교정.
3. **US 시트 컬럼 22개** 과소보고 — 실제 v0_FINAL 23열·26W23 41열. F~R이 **숨김열(hiddenByUser)** 인데 "미제공"처럼 설명 → 알고보니 값 100% 채워져 있고 숨겨둔 것뿐.
4. "취득가능" 라벨로 끝냄 → [[feedback-deliver-actual-data-not-feasibility]].

**교훈:** 빈 결과·0건·한 각도 실패 = "없음" 근거 아니라 "도구/각도 실패" 신호. **두 번째 각도(다른 genre id·Keepa·hidden 여부·다른 도메인)로 교차검증 후에만 판정.** CLAUDE.md "검증 못 한 건 말하지 마라" 재위반. 관련 [[reference-jp-bsr-data-availability]].
