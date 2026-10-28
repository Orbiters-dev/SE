---
name: Meta WL Off 후보 — Delivery 실패 정량 게이트 (share<1% AND zero days≥7/14)
description: 5/28 신설. WL Proven 풀 algorithm 몰빵 분배로 dormant 된 광고 자동 식별. tools/meta_jp_daily.py 의 delivery_failure_candidates 함수 + render_delivery_failure_box 박스. 메모리 룰 reference_meta_wl_lifecycle_3to6months.md 의 「delivery 실패 hit 시 Off」 정량화 버전.
type: reference
---

# Delivery 실패 정량 게이트 (5/28 신설)

WL Proven 풀에서 algorithm 분배 몰빵으로 dormant 되는 광고를 자동 식별. nopi_ikuji 5/28 진단 → 정량 룰화 합의.

## 트리거 (둘 다 hit)

| 축 | 임계 |
|---|---|
| (a) adset 내 spend share | < 1% (14d 누적) |
| (b) zero delivery days | ≥ 7 일 (14d 윈도우 중) |
| 조건 | D+14+ (학습 단계 통과) |

## 배경

- WL Proven 풀은 ad 단위 예산 X — adset 예산을 algorithm 이 풀 내 분배
- 풀 winner(예: ichikuru_fufu 84% 점유) Off 안 하면 부진 광고 살아날 path 없음
- 시간 단독 sunset(D+60/D+90)은 폐지됨 (memory: reference_meta_wl_lifecycle_3to6months.md 의 WL 3~6개월 운용 룰)
- 정량 룰 없을 때 nopi_ikuji 처럼 표면 KPI(CTR 60% / CPLPV ₩52)에 속아 winner 로 오분류

## 액션 라인

- **자동 식별**: meta_jp_daily 1d 이메일에 「Off 후보 — Delivery 실패」 박스 매일 표시 (주황 배경)
- **수동 toggle**: 세은이 Ads Manager 에서 직접 Off
- **자동 Off X**: false positive 회복 비용 큼 (memory: feedback_check_automation_necessity.md)

## 코드 위치

- `tools/meta_jp_daily.py`:
  - `delivery_failure_candidates(ad_rows_14d, ad_rows_14d_daily, ref_date, share_threshold=0.01, min_zero_days=7, window_days=14, min_age_days=14)`
  - `render_delivery_failure_box(candidates)`
- `analyze_1d()` 에서 14d ad-level aggregated + daily fetch 후 호출
- `render_1d()` 에서 `render_off_recommend_box` 다음에 박스 렌더

## 5/28 첫 실행 결과 (참고)

6건 자동 식별:
1. AD F | Fliptop | coni | PAID (D+42) — share 0.02%, zero 9/14
2. AD E | PPSU 300ml | nopi_ikuji | GIFT (D+49) — share 0.04%, zero 9/14 ← 진단 발단
3. AD C | Daino | emachi | PAID (D+113) — share 0.06%, zero 10/14
4. AD D | Stainless 300ml | Erimama | PAID (D+96) — share 0.11%, zero 9/14
5. AD M | Stainless 300ml | kina | GIFT (D+42) — share 0.18%, zero 9/14
6. AD I | Stainless 200ml | shiro | GIFT (D+71) — share 0.47%, zero 8/14

임계 추후 조정 가능:
- share 1% 가 느슨하면 0.5% 로
- zero days 7/14 가 느슨하면 9/14 로

## 관련 메모리

- reference_meta_wl_lifecycle_3to6months.md (WL 3~6개월 운용 룰)
- feedback_meta_no_ad_level_budget.md (ad 단위 예산 X)
- feedback_check_automation_necessity.md (자동 Off X)
- feedback_sync_code_when_memory_rule_changes.md (메모리·코드 동기화 한 묶음)
