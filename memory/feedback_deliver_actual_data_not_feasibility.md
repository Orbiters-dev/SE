---
name: feedback-deliver-actual-data-not-feasibility
description: "수집/조사 지시엔 '취득가능' 라벨 말고 실제로 취득해서 값까지 채워라 (2026-07-02)"
metadata:
  type: feedback
---

# 수집 지시 = 실제 취득·채움까지 (feasibility 라벨 금지)

세은이 "수집해/뽑아봐/채워" 라고 하면 컬럼별로 「O/취득가능/Keepa취득가능」 같은 **가능성 라벨만 달고 끝내지 마라.** 실제로 도구 돌려서 **값을 채워** 내놔.

**Why:** 2026-07-02 JP BSR 조사에서 필드맵에 "Keepa취득가능"이라 써서 냄 → 「취득가능이라고 쓰면 뭐하냐? 미쳤나; 취득해서 집어넣어 디질려고」 강한 교정.

**How to apply:**
- "가능/불가" 판정은 1차 답. 지시가 수집이면 그다음 **실제 스크랩/쿼리 실행 → 값 채운 산출물**이 본 답.
- 못 채우는 칸(외부 키 부재 등)만 사유 1줄로 공란 표시. 나머지는 전부 실값.
- 관련: [[reference-jp-bsr-data-availability]] · [[mistakes-20260702-premature-unavailable-claims]] · [[feedback-no-method-giveup]]
