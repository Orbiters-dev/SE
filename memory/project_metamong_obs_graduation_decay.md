---
name: 메타몽 장기관찰 3 — 졸업 풀 꺾임 시점
description: Testing → Proven 졸업 후 광고가 꺾이기 시작하는 시점 관찰. (a) 누적 spend (b) 누적 노출 기간 (c) Freq 도달치 세 축.
type: project
---

# 메타몽 장기관찰 3 — 졸업 풀 꺾임 시점

세은 지시일: 2026-06-01. 기간 두고 누적 관찰 지시.

**Why:** 졸업 후 광고 수명 정량화. "어느 시점에 꺾이기 시작하는가" 데이터 누적해야 Proven Off Rule 임계 (시점·Freq) 정교화 가능. 5/29 komugiko 실측 ([reference_meta_jp_graduation_mechanism.md](reference_meta_jp_graduation_mechanism.md))에서 졸업 직후 CPLPV 악화 신호 이미 1건.

**How to apply:** 졸업 1호부터 모든 졸업 광고에 대해 매주 메트릭 트래킹. 꺾임 검출 시 (a)(b)(c) 동시 기록. 누적되면 임계 룰 update (현재 reference_meta_wl_lifecycle_3to6months.md / triple share 게이트 위).

## 꺾임 정의
**CPLPV가 풀 P50 × 1.3 이상 7일 연속 지속.** (단발 튐 제외)

## 측정 축
| 축 | 의미 | 단위 |
|----|------|------|
| **a. 누적 spend** | 졸업일 ~ 꺾임 검출일 합산 spend | ¥ |
| **b. 노출 기간** | 졸업일 ~ 꺾임 검출일 일수 | days |
| **c. Freq 도달치** | 꺾임 직전 7일 평균 Frequency | 회 |

## 데이터 소스
- meta_jp_daily.py 일간 artifact + 졸업 후보 박스
- meta_ads_daily — ad_id 별 일별 메트릭

## 초기 가설 (2026-06-01)
1. **노출 기간·Freq dominant** > spend. spend는 풀별 예산 차이로 노이즈 큼.
2. 졸업 후 **2주 내** 꺾임 신호 가능성 (5/29 komugiko 실측 가설 연장).
3. Freq 5.0 부근에서 꺾임 (현재 Off Rule 임계 2.5보다 한참 위) — 졸업 풀은 이미 Proven이라 도달 빠름.
4. **재진입 path** (Testing pause + Proven 새 ad_id) vs **carry path** (adset rename)에 따라 시점 다를 듯. 재진입 = 학습 비용 추가지만 수명 ↑. carry = 즉시 출고지만 빨리 꺾임.

## Cadence
- **주 1회** (졸업 풀 변동 시).
- artifact: `.tmp/metamong_observations/YYYYWW_axis3_graduation_decay.json`

## 누적 로그
(꺾임 검출 시 아래에 한 행씩 append: ad_id / 인플루언서 / 졸업일 / 꺾임일 / 누적spend / 노출일수 / Freq)

| ad_id | 인플 | 졸업일 | 꺾임일 | spend | days | Freq | 비고 |
|-------|------|--------|--------|-------|------|------|------|
| _첫 1건 대기_ | | | | | | | |
