---
name: Meta Proven 졸업 시 frequency 반영 + 효율 유지 여부 (2026-05-29 검증)
description: Testing→Proven 졸업 시 frequency는 ad set별 별도 계산 → Off Rule freq≥2.5 게이트에 Testing 누적 노출 안 잡힘. 효율도 떨어지는 경향 (komugiko 7d/14d CPLPV +24.9~+31.6%).
type: reference
---

## Q1 (frequency 반영 여부)

- Frequency = Impressions ÷ Reach. **Campaign / Ad Set / Ad 각 레벨별 별도 계산** (Meta 공식 + Jon Loomer 검증).
- Testing adset에서 본 사용자는 새 Proven adset에서 freq=0부터 시작 → **Off Rule freq≥2.5 게이트에 Testing 누적 노출은 안 잡힘**. Campaign 레벨에서만 합산.
- Meta에는 **"이미 본 사람 자동 제외" 기능 없음**. 같은 사용자에게 Proven adset이 다시 노출됨.
- 제외하려면 **Custom Audience 기반 exclude** (Testing engagement / Pixel 시청자) 수동 추가 必.

## Q2 (Proven 옮긴 후 효율 유지 여부)

- **같은 효율 보장 X, 떨어지는 경향**.
- 졸업 = 새 adset 생성·새 ad 추가 = **significant edit으로 학습 재진입** 가능.
- 풀 실측 4건 중 가장 명확한 케이스 (komugiko 7d/14d):
  - CTR: -7.6 ~ -13.5%
  - CPC: +6.7 ~ +17.8%
  - **CPLPV: +24.9 ~ +31.6% (Proven 측이 더 안 좋음)**
- bebimon stable 비교: CTR -17.2% / CPC +8.9% / CPLPV +18.0%.
- 첫날만 보면 거의 동일(노이즈)이라 단기 단정 X — **표본 추가 필요**.

## 코드/룰 변경

- **합의된 변경 없음**. 진단 단계까지만 완료.
- 후속 검토 = Custom Audience exclude 도입 여부 + Proven 졸업 표본 N건 추가 누적 후 룰화.

## How to apply

- Off Rule 적용 시 freq≥2.5 트리거는 **ad set 단위 frequency** 기준임을 명심. Campaign 단위로 보면 다름.
- 졸업 후 Proven 광고를 같은 효율로 가정하지 X — 옮긴 후 7d/14d 추적 의무.
- 일일 보고에서 졸업 권고 시 「효율 하락 가능성」 라벨 동반.
