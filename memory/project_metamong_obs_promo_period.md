---
name: 메타몽 장기관찰 2 — Promo 기간 광고 메트릭 변화
description: Rakuten 할인 행사 등 promo 기간 전/중/후 메타 광고 메트릭(CPM/CTR/CPLPV/Freq) 변화 관찰. 행사 단위 누적.
type: project
---

# 메타몽 장기관찰 2 — Promo 기간 광고 메트릭 변화

세은 지시일: 2026-06-01. 기간 두고 누적 관찰 지시.

**Why:** 행사 기간 광고 효율 변화를 정량화해서 promo 전후 예산·소재·게이트 룰 따로 설계하기 위함. 행사 직후 carry over 피로도 검출.

**How to apply:** 행사 발생 때마다 D-14 / 행사기간 / D+7 세 윈도우 스냅샷. 누적되면 promo 시작·종료 cadence 룰화 (예: "행사 종료 D+7 동안 Freq 임계 완화").

## 측정 지표
| 메트릭 | 행사 전 (D-14~D-1) | 행사 중 | 행사 후 (D+1~D+7) | 변화율 |
|--------|---------------------|---------|--------------------|--------|
| CPM | | | | |
| CTR | | | | |
| CPLPV | | | | |
| Freq | | | | |
| 구매 (Rakuten 매출) | | | | |

## 분할 변수
- WL vs 일반 (이미지 광고)
- Testing vs Proven (졸업 풀)
- 제품 풀 (PPSU vs Stainless 별)
- 행사 종류 (お買い物マラソン / スーパーSALE / 단기 쿠폰)

## 데이터 소스
- meta_ads_daily — 일별 메트릭
- Rakuten 행사 일정 (수동 입력 또는 RMS API)
- 매출 매칭 도구 완성 전엔 매출 column 보류

## 초기 가설 (2026-06-01)
1. 행사 중 CPLPV 30~50% 개선 가능 (LP 가격 신호 → Pixel LPV 발화 ↑).
2. **단 Freq carry over** — 행사 중 노출 폭증 → 행사 직후 D+7 피로도 누적.
3. 행사 직후 CPLPV가 D-14 평소치보다 악화될 가능성. → "행사 후 D+7 Freq 휴식" 룰 후보.
4. 제품별 반응 다를 듯 — 보온/외출(Stainless) > 경량(PPSU) 행사 민감도 가설.

## Cadence
- **각 행사 종료 D+7** 마다 스냅샷.
- artifact: `.tmp/metamong_observations/YYYYMMDD_axis2_promo_{event_name}.json`

## 누적 로그
(행사 발생 시 아래에 한 줄씩 append: 행사명 / 기간 / 주요 변화율 / 시사점)

- _첫 스냅샷 대기 (다음 Rakuten 행사 시작 시)_
