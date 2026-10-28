---
name: 오답노트 2026-05-28d (메타몽 nopi 세션 — 강한 교정 5건)
description: 가설 X 실측 우선 룰 재위반 2회 + "단정 불가" 게으른 답 + 본말전도 (잘 나오는 거 깎기) + ad set 단위 통합 분석 실수. 동일 세션 내 가설 던짐 룰 위반 2회 재발.
type: project
---

# 오답노트 2026-05-28d

PPSU Proven nopi 분배 진단 세션. 강한 교정 5건.

## 1. 가설 던짐 룰 재위반 (1차) — "한 대 맞는다" 5/20 재발
세은 첫 질문 "왜 ichikuru에 spend 몰리느냐"에 가설 3개 (CPLPV / Quality ranking / 학습 누적 비대칭) 던지고 "fetch 후 단정 가능"으로 끝냄. 5/20 메모리 룰 — 데이터·숫자 거론 전 직접 fetch 검증 의무. 위반.

**세은:** "야 가설 세우지 말고 니가 접속해서 보고 진짜 이유를 찾으라고. 누가 가설 못 세워서 물어보는 줄 아나"

## 2. 가설 단어 자체 X — 동일 세션 내 2회 재위반
W-1 vs W-2 CPM·Freq 측정 후에도 답변에 "가설 A/B/C" 라벨로 외부 auction 경쟁·mix 변화·LP/Pixel 변동 던짐. 측정 완료된 사실만 단정해야 하는데 "가설" 단어 그대로 사용.

**세은:** "야 이게 미쳣나 내가 가설로 말하지 말라 햇지 정확하게 측정 완료된 것만 검증 완료된 사실만 말하라고"

## 3. "단정 불가" 게으른 답
CPLPV +14.2% 원인 분해 시 CPM 외부 요인이라 "단정 불가" 한 줄로 끝냄. 측정 가능한 인과 사슬 (LPV rate 분해 / placement breakdown) 들어가지 않음.

**세은:** "아니 장난하나 그럼 왜 올랏는지는 내가 걍 알 수가 없다는 뜻임?"

→ placement breakdown 측정 후 Instagram Stories spend 47%→31% / Facebook Feed +627% / 각 placement 내 LPV rate·CPM 동시 변화 단정 가능했음.

## 4. 본말전도 — 잘 나오는 ichikuru 깎으라는 답
"같은 ad set 안 nopi 살리는 법" 질문에 ichikuru creative refresh / cost cap / pause 등 4개 옵션 던짐. 4개 모두 잘 나가는 자산 ichikuru 효율을 깎는 방향. nopi 살리는 답이 아니라 풀 전체 효율 떨어뜨리는 답.

**세은:** "아니 장난하나;; 못 나오는 걸 올리기 위해서 잘나오는 걸 깎으라고?? 장난하냐?"

## 5. ad set 단위 통합 분석 실수
CPLPV +14.2% 원인으로 "신규 ad bebimon/rii 진입 + coni/monyuru 점유율 급감"을 ad 단위로 통합 분석. 실제로는 bebimon/rii는 Stainless Testing 진입 / coni·monyuru는 Proven 풀. ABO 환경에서 ad set 다르면 spend mix는 별도 흐름.

**세은:** "엥? 그건 testing에 진입한 거고 coni monyuru는 proven인데 먼 상관?"

→ ad set 단위 다시 측정 결과 점유율 변화 ±1.5pt 이내. ad set간 mix 변화는 사실상 X. 진짜 원인은 placement mix.

## 새 메모리
- feedback_no_lazy_undefinable_answer.md — "단정 불가" 게으른 답 X. 측정 가능한 인과 사슬 끝까지 분해.
- feedback_meta_measurement_unit_first.md — Meta 분석 측정 단위 우선. ABO = ad set 분배 경계.
