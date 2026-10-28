---
name: Meta ad-level 노출 몰빵 (학습단계 정상)
description: 같은 ad set 안에 ad 여러 개일 때 한쪽만 노출되고 다른 쪽 CPC/CTR 공란 — 망가진 게 아니라 학습단계 자동 베팅. 진단/처방 체크리스트.
type: reference
originSessionId: 4abd8430-2804-42d5-921a-b3c796dc2c11
---
# Meta 광고 "한 쪽만 노출 / CPC·CTR 공란" 진단 체크리스트

같은 ad set 안에 ad 여러 개 동시 등록했는데 한쪽만 노출 받고 나머지는 거의 0이면, 우선 **학습단계(Learning) 노출 몰빵**을 의심한다. 망가진 게 아니다.

## 1. CPC/CTR "안 뜬다"는 표현의 실체

- **클릭=0이면 분자 0** → CTR/CPC 계산 불가일 뿐. 광고 자체는 정상 송출 중일 수 있음.
- 진단 첫 단추: `clicks`, `impressions`, `spend`를 각각 본다. CTR 칼럼만 보고 "안 돈다" 판정 X.

## 2. ad-level 진단 순서 (read-only)

1. `ad` detail: `effective_status`, `configured_status`, `issues_info`, `recommendations` — 검수 거절·이슈 없는지 먼저
2. ad set 동일성 확인: 두 ad의 `adset_id`가 같은지
3. creative diff: `creative.object_type`, `effective_object_story_id`, 카피, CTA — 어디만 다른지
4. `/insights` ad-level: impressions / reach / clicks / spend 직접
5. `breakdowns=publisher_platform,platform_position` — 어느 placement에서 죽었는지

## 3. 같은 ad set + 같은 카피 + 이미지만 다름 → 학습단계 몰빵 패턴

- 24~48h 동안 알고리즘이 초기 신호 보고 한쪽에 노출 97% 이상 몰빵 = 정상 동작
- 등록 후 22h쯤이면 **그냥 더 기다리는 게 1순위**

## 4. 처방 우선순위

| 순위 | 액션 | 적용 시점 |
|---|---|---|
| ① | 24~48h 더 대기 | 등록 직후 ~ 48h |
| ② | 약한 ad만 별도 ad set로 복제 / Advantage+ Creative 전환 | 48h 지나도 spend 1% 미만 |
| ③ | 약한 ad 종료 + 썸네일/카피 교체 | ②에도 노출 못 받으면 |

## 5. JP만 분석 (US는 제외)

본 진단 패턴은 `act_4117678028561958` (Grosmimi JP)만 적용. 미국 멀티브랜드는 다른 담당자 영역.

## 6. 케이스 (참고)

- 2026-05-06 18:04/18:08 동시 등록 AD E vs AD F (Stainless 머그, Rakuten | Traffic | Creative(test) | image ad set)
- AD E: imp 1,800 / spend ¥6,689 / CTR 3.11%
- AD F: imp 41 / clicks 0 / CTR 공란
- 카피·CTA·ad set 동일, creative_id(이미지)만 다름 → 학습단계 몰빵으로 결론
