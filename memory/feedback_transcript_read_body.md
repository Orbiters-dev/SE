---
name: 트랜스크립트 분석은 본문 펴서 읽기 — hit 카운트 dismiss 금지
description: 일일 보고·세션 정리 시 트랜스크립트에서 키워드 hit 카운트로 "작업 없음" 단정 X. user/assistant 메시지 본문 펴서 읽어야 실제 작업 잡힘.
type: feedback
---

키워드 hit 카운트만 보고 "SKILL 본문 매칭" / "boilerplate" 로 dismiss 하지 마. 실제 작업이 그 hit 안에 섞여있을 수 있다. **반드시 user/assistant 메시지 본문을 펴서 읽어라.**

**Why:** 2026-05-18 /장보고 작업. 트랜스크립트에서 "인플루언서 56 hits / 시딩 7 hits / 리치아웃 3 hits" 잡혔는데, 전부 SKILL 본문 매칭이라 자체 판단하고 세은에게 "오늘 인플루언서 작업 뭐 있어?" 떠넘김. → "지랄하지 말고 오늘 클로드로 했던 일 분석해" 강한 교정. 본문 펴서 보니 새벽 0:10~6:02 DM 8건 (星野/おと/上林/神保/nina/牛込/岡田) 작업 다 잡힘.

**How to apply:**
1. 트랜스크립트 분석 시 카운트는 1차 필터만. 0이 아니면 본문 펴서 읽기 의무.
2. `role=assistant` text 블록을 시간순으로 dump → 본문에서 핸들·STEP 번호·작업 종류 추출.
3. SKILL 본문/boilerplate 필터링은 본문 펴고 나서 (예: `##` 3개 이상이면 skip 등 휴리스틱).
4. /장보고 호출 시 인플루언서·CRM·박람회·시딩 본문 깊이 스캔이 디폴트.
5. 자체 탐색 0건이 진짜인지 본문 확인 후에야 "세은에게 묻기" 결정 가능.

본문 dump 의무는 [feedback_self_first_no_wongi_default.md](feedback_self_first_no_wongi_default.md) + [feedback_investigate_first.md](feedback_investigate_first.md) 연장. "자체 탐색" = 카운트가 아니라 **본문 읽기**.
