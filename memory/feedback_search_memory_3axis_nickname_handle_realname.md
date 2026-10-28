---
name: 인플루언서 메모리 검색은 3축 (호칭/핸들/본명) + .tmp 보조 인덱스 — 1축 grep 단정 X
description: 닉네임 호칭으로 저장된 인플루언서 메모리는 본명이 안 박혀있을 수 있음. 호칭/핸들/본명 3축 + .tmp/build_daily_*.py + DocuSeal submission_*.json 까지 확장 후에만 「없음」 단정 가능. 5/28 玉木様 = pon_bebe 사고
type: feedback
---

인플루언서 메모리 검색 시 한 축(본명만 / 핸들만 / 호칭만) grep 결과 0건 = 「메모리 없음」 단정 X.

**Why:**
2026-05-28 玉木様(本명 玉木もなみ) 메모리 검색 시 `grep "玉木|もなみ|tamaki|monami"` 0건 → 「신규 인플루언서」 단정 → 「있는데 왜 없다구 자꾸 해」 강한 교정. 실제로는 `influencer_pon_bebe.md` 가 호칭 「pon様」 + 핸들 「@pon__bebe」 로 저장되어 있고, STEP 6 본명 수령 (5/22) 후 본명 박기 갱신이 안 되어 stale. ls 출력에서 파일명 자체는 봤지만 「pon」을 玉木와 매칭 못 함. 5/12·5/21·5/27 grep 1회 단정 X 룰 4번째 누적 재발.

**How to apply:**

1. **닉네임/핸들/본명 3축 다 시도**:
   - `grep "{본명}|{히라가나}|{로마자}"`
   - `grep "{닉네임}|{핸들}|{nick의 변형}"`
   - `grep "{호칭}様|{호칭}ちゃん"`
   - 한 축 0건이어도 다른 축 시도. 3축 다 0건일 때만 「없음」 후보

2. **`.tmp/` 보조 인덱스 확장**:
   - `.tmp/build_daily_*.py` — 일일 보고 문맥에 「호칭(핸들)」 매핑 박혀있음
   - `.tmp/docuseal_submissions/submission_*.json` — 본명·이메일·계약일 박혀있음
   - `.tmp/notion_daily_*.py` — 일일 보고 nested 데이터
   - 3축 grep 미스 후에도 「없음」 단정 전 `.tmp/` 전체 grep 의무

3. **닉네임 호칭 디폴트 인플루언서 = 본명 누락 위험군 표시**:
   - pon様 / yucchi様 / のぴ様 / おとちゃんママ様 등 닉네임 디폴트 호칭 케이스 = STEP 6 본명 수령 시 즉시 메모리 본명 박기
   - 위반 시 stale 누적 → 다음 검색 매칭 0건

4. **메모리 발견 시 본문 stale 검증**:
   - 마지막 진행 이력 날짜가 오늘 - 7일 이상이면 stale 의심
   - DocuSeal Submission 번호 / 송장 / STEP 진행 vs 외부 사실 대조

**관련 메모리:**
- `mistakes_20260528c.md` 사고 ① (이 룰의 발원 사고)
- `feedback_no_method_giveup.md` (5/21)
- `feedback_dm_identify_recipient_first.md` (5/12)
- `feedback_verify_data_values_before_discussing.md` (5/20)
- `mistakes_20260527.md` 사고 ② (직전 동일 패턴)
