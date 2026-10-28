---
name: "단정 불가" / "외부 요인이라 알 수 없음" 게으른 답 금지
description: 직접 측정 불가능한 부분(외부 auction·시즌 등) 만나면 거기서 멈추지 말고, 측정 가능한 인접 인과 사슬을 끝까지 분해해라. "단정 불가" 한 줄은 게으른 답.
type: feedback
---

# "단정 불가" 게으른 답 금지

직접 측정 불가능한 변수(외부 auction CPM·시즌·경쟁자 입찰 등) 만나면 거기서 멈추지 말고, **측정 가능한 인접 인과 사슬을 끝까지 분해**해라. "외부 요인이라 단정 불가" 한 줄로 끝내는 답은 사용자가 알고 싶은 정보의 80%를 버리는 행위.

**Why:** 5/28 메타몽 세션 CPLPV +14.2% 원인 분해 시 CPM이 외부 요인이라 "단정 불가" 한 줄로 끝냄. 세은 "그럼 왜 올랐는지 내가 걍 알 수가 없다는 뜻임?" 강한 교정. 실제로는 placement breakdown 분해하면 Instagram Stories spend 47%→31% / Facebook Feed +627% / 각 placement 내 LPV rate·CPM 동시 변화 등 단정 가능한 인과 80%가 측정 가능했음.

**How to apply:**
1. 한 변수가 외부 요인이라 단정 불가여도, **수학적 인과 사슬의 다른 변수는 분해 가능**. 예: CPLPV = CPC / LPV rate = CPM / (LPV rate × 1000). CPM 외부면 LPV rate / CTR / placement / ad set / ad 단위로 분해.
2. **breakdown 차원 우선 시도**: placement / age / gender / region / device / hour / weekday. Meta Graph API는 거의 다 지원.
3. "단정 불가"는 사슬의 마지막 한 단계만. 그 앞 단계까지는 측정으로 단정한 다음에 한 줄로 boundary 명시.
4. 보고 형식: "X는 측정으로 단정 가능 (수치) → Y는 X의 함수, 측정 가능 → Z(외부 요인)만 단정 불가."
