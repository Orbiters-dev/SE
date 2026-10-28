---
name: 메모리 한 번 보고 "0건" 단정 금지
description: 메모리는 한 시점 스냅샷. 샘플 발송/지출/수치 0건 단정 전에 시트·CRM·DB 등 다른 도구로 교차검증 필수.
type: feedback
---

# 메모리 한 번 = "0건" 단정 X. 무조건 시트/CRM 등 baseline 도구 교차검증

**Why:** 2026-05-07 W18 OKR 작성 시 "이번 주 샘플 발송 0건 / 협업 지출 ¥0" 단정 → 세은 "엥 ???? 아닐걸 ?????" 강한 교정. 메모리 session_*.md만 보고 단정한 게 원인. 실제로는 시트(Grosmimi tab)에 Shipping 단계 10명 + Delivered 8명 + Guideline Sent 2명 = 20건 진행 중. 메모리는 "한 시점에 적은 것"이라 모든 활동을 캡처 X.

**How to apply:**
- 샘플/지출/투고/리치아웃 등 수치 답변 시: 메모리 → **시트(인플루언서 관리 시트)** → CRM API → DB 순으로 교차검증
- 시트 = ORBI 팀의 baseline (PIC 필터 + 운영기간/Status 필터로 활성 건 추출)
- 시트 ID: `1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU` Grosmimi tab (gid=386147805)
- "0건"이라는 결론은 baseline 도구에서 0건 확인 후에만 사용. 메모리에서만 0건 → "확인 못 함"이 정답
- CLAUDE.md 절대 룰: "검증 한 번 = 도구 한 개로 끝나면 안 됨. 빈 결과/0건/오류는 '없음' 단정 근거가 아니라 '도구 실패 가능성' 신호"
