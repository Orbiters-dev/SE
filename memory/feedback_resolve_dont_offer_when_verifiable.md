---
name: feedback-resolve-dont-offer-when-verifiable
description: 「확인 못 함」 caveat 달고 「파볼까요?」로 끝내지 마라 — 내 도구로 그 턴에 해소 가능하면 결론까지 내고 보고
metadata:
  type: feedback
---

보고 말미에 「~는 확인 못 했습니다. 파볼까요?」 식으로 물으면 강한 교정. 세은 「어쩌라고 그러면?」 (2026-09-11, KPI 시트 반영 여부 확인 건).

**Why:** 「확인 못 함」은 **내 도구로 해소 불가능할 때만** 쓰는 한 줄이다. 도구·자격증명·스크립트가 손에 있는데 caveat만 달고 "파볼까요?"로 되물으면 = 떠넘김. 세은은 결론을 받으려고 보고를 요청한 거지, 다음 액션을 승인해주려고 받는 게 아니다. CLAUDE.md 절대 룰(직접 파악 가능한 건 묻지 마) 위반.

**How to apply:**
1. 보고 직전, 남긴 caveat 각각에 대해 "이걸 내 손의 도구로 지금 해소할 수 있나?" 자문.
2. 가능하면 **그 턴에 해소**하고 결론까지 내라. (예: gh 인증 막힘 → 앱이 읽는 구글시트를 직접 gspread로 읽어 실제 값 확인)
3. 하나의 검증 도구가 막혀도(gh auth 실패 등) "확인 못 함"으로 끝내지 말고 **두 번째 경로**로 교차검증 — 빈 결과/막힘 = 도구 실패 신호지 "없음/모름"이 아니다.
4. 진짜로 도구가 없어 못 하는 것만 "확인 못 함" 한 줄. 「파볼까요?」 금지 — 할 수 있으면 그냥 판다.

관련: [[feedback-no-speculation-verify-first]] · [[feedback-surface-interim-during-slow-ops]] · [[mistakes-20260907-partial-data-repeated-assertion]]
