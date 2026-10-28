---
name: Meta 분석 측정 단위 우선 결정 — ABO 환경은 ad set이 분배 경계
description: Meta 광고 변화 원인 분석 시 측정 단위(account/campaign/ad set/ad/placement)를 질문 성격에 맞게 먼저 정해야 한다. ABO 환경에서 ad 단위 통합 분석은 ad set 간 별도 분배를 합쳐서 mix 변화를 잘못 진단.
type: feedback
---

# Meta 분석 측정 단위 우선 결정

Meta 광고 변화·이상치 분석 시 **측정 단위를 질문 성격에 맞게 먼저 정해라**. account → campaign → ad set → ad → placement 단위 중 어디가 분배 경계인지 확인 후 측정. 한 단위에서 답이 안 나오면 다음 단위로 분해.

**Why:** 5/28 메타몽 세션 CPLPV +14.2% 원인 분해 시 ad 단위 통합으로 "신규 ad bebimon/rii 진입 + coni/monyuru 점유율 급감"을 mix 변화 원인으로 단정. 그런데 bebimon/rii는 Stainless Testing 진입 / coni·monyuru는 Proven 풀이라 ABO 환경에서 별도 ad set = 별도 예산 = 별도 분배 흐름. 세은 "그건 testing에 진입한 거고 coni monyuru는 proven인데 먼 상관?" 강한 교정. ad set 단위로 다시 측정한 결과 점유율 변화 ±1.5pt 이내로 실제 mix 변화 X. 진짜 원인은 placement mix였음.

**How to apply:**
1. **첫 측정은 분배 경계 단위로**. JP Grosmimi는 전 캠페인 ABO ([reference_meta_jp_all_abo.md](reference_meta_jp_all_abo.md)) → 분배 경계 = ad set. ad set 단위 spend 점유율·CPLPV·CPM 변화 먼저.
2. **ad 단위 통합 분석은 함정**. 다른 ad set의 ad들을 한 줄에 늘어놓으면 ad set간 별도 분배 흐름이 합쳐져 mix 변화를 잘못 진단함.
3. **ad set 단위에서 답이 안 나오면 다음 단계 분해**: placement breakdown (publisher_platform × platform_position) → audience breakdown (age/gender) → device. Graph API `breakdowns` 파라미터로 즉시 가능.
4. **인과 사슬을 단위별로 분해**: CPLPV ↑ 원인이 ad set 단위에서 안 보이면 → placement 단위로. placement 단위에서 LPV rate ↓ 보이면 → ad 단위로. 한 단위에 머물면 진단 못함.
5. **단위 결정 가이드**:
   - "어느 ad가 더 좋아?" → ad 단위 (단, 같은 ad set 내에서만)
   - "spend mix가 바뀌었나?" → ad set 단위 (ABO 환경)
   - "placement 효율 변화?" → placement breakdown
   - "audience saturation?" → reach·freq + age/gender breakdown
