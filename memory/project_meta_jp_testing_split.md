---
name: Meta JP Testing 1:1 분리 운영 결정 (2026-06-15)
description: Testing 광고를 소재 1개=ad set 1개로 분리, Proven은 통합 유지. 슈퍼세일+promo 실험 종료 후 실행. ad set 기본 ₩8,000(잠정).
metadata:
  type: project
---

# Meta JP Testing 1:1 분리 운영 결정 (2026-06-15)

세은과 메타몽 세션 합의. act_4117678028561958 (통화 KRW, tz Asia/Tokyo).

> **후속 (6/16): OFF·졸업·Budget 게이트 임계 확정 → [[reference_meta_wl_testing_gate_criteria]]**

## 확정 합의사항
1. **Testing만 1:1 분리** (소재 1개 = ad set 1개), **Proven은 통합 유지**.
2. **ad set 기본 예산 ₩8,000/day (잠정)** — 슈퍼세일 후 7일 실험기간에 세은+메타몽이 재정립.
3. **졸업 기준 변경: 풀 triple share → 개별 CPLPV·VTR** (분리하면 각 소재가 자기 ad set 100% share라 share 기준 무의미).
4. **판정 시점 D+3** — ₩8,000×3 ≈ 185 LPV 자동 확보. **별도 LPV 임계(150 등) 없음** (D+3까지 가면 표본 충분).
5. **실행 시점: 슈퍼세일 + promo on/off budget 실험 종료 후 트래픽 정상화 시점** (변수 격리 + 슈퍼세일 비정상 트래픽이라 판별 왜곡 회피 + 분리=learning reset이라 깨끗한 시점에).
   - **슈퍼세일 6/4 20:00~6/11 01:59 = 150h. 동일 길이 후속 관찰 = 6/11 02:00~6/17 08:00경 종료.** → 분리 실행 목표 = **6/17 오전 이후** (트래픽 정상화 확인 후).

## 판단 근거 (객관 기준)
- **Testing 목적함수 = 효율(CPLPV)이 아니라 "판별 수율"**. 정보 사는 단계.
- 현 통합 Testing 실측 문제 (6/12~14): arara 96.2%(CPLPV 179)·aomaru 98.2% 독식 → minkoro(CPLPV 81=풀 최고효율)·iroiro(CTR 17.1=풀 최고) 표본 6으로 굶어 사장. Testing 예산 94%가 이미 아는 소재 재노출에 낭비.
- 학습 무관: 우리는 LPV 최적화(Traffic). WL 캠페인 7d LPV 15,250 / purchase 0건(Rakuten landing이라 Meta 픽셀 미추적). 분리해도 ad set당 주 546~860 = 임계(50)의 10배+. **purchase 최적화였으면 분리 시 learning limited 위험** — funnel 하단이라 이벤트 희소.
- Proven 1:1 금지 이유: Proven 목적=효율. Meta 골라주기가 효율 무기인데 1:1이면 끔 + 검증완료라 판별 불필요 = 이점 0 + 효율손실만.

## ₩8,000 산식 (잠정)
`일예산 = (D+3 목표 LPV × CPLPV) ÷ 3`. CPLPV 실측 ₩130. 목표 100 LPV(안정)=₩4,300 하한, ₩8,000=185 LPV(여유). 정답 범위 ₩5,000~10,000. Meta 정책 최소 = ₩1,499 (min_daily_budget, oCPM 과금) — 권장값이 5배+라 여유 통과.

## 슈퍼세일 후 재정립 때 볼 데이터 3개
1. 예산별 한계 CPLPV (상한 탐지) 2. D+3 실측 누적 LPV (추정 185 검증) 3. 분리 후 overlap CPM 상승폭.

## 진화 2026-06-19 (PPSU/Stainless 제품 분리 구조 확정 + 3캠페인)
6/15 "Proven 통합 유지" → **제품 분리로 진화.** 세은과 객관 컨설팅 후 확정.
- **확정 구조 = 캠페인 3개**: ① Testing(제품 통합) ② PPSU Proven ③ Stainless Proven.
- **Testing = 제품 묶음** (1 asset=1 ad set, ABO). 1:1이라 ad set당 소재 1개 → 독식/굶음 발생 불가 → 제품 분리 실익 0. **단 ad_name에 `| PPSU |`/`| Stainless |` 라벨 필수** (졸업 시 맞는 제품 Proven으로 라우팅).
- **Proven = 제품 분리** (각 제품 캠페인, 내부는 여러 소재 통합 운영). 분리 근거 = **의도적 제품별 예산/매출비중 통제** (Meta는 효율만 보지 마진·재고·전략비중 모름. 안 나누면 효율 우위 PPSU(CTR10.2/CPLPV111)가 Stainless(7.8/123) 예산 먹음). 세은: "Proven은 예산 통제해야".
- **CBO vs ABO (Proven, 1캠페인=1ad set 전제)**: 실질 **동일**. CBO/ABO 차이는 "여러 ad set 사이 예산 분배"인데 ad set 1개면 분배 대상 없음 → 캠페인 예산 전액이 그 ad set. ad set 안 에셋 간 분배는 CBO/ABO 무관 항상 Meta 자동([[feedback_meta_no_ad_level_budget]]). → **ABO 권장**(기존 JP 전부 ABO [[reference_meta_jp_all_abo]], 일관성). 단 ad set 추가하면 그때 CBO≠ABO 갈림.
- 현 실측(14d): PPSU Testing(aomaru 94.6% 독식)·Stainless Testing(kyan51%+arara44%). PPSU Proven CTR10.2/CPLPV111, Stainless Proven 7.8/123.

## 졸업 메커니즘 참고
- haru 6/11 졸업 정상 (Testing PAUSED + Proven 새 ad_id ACTIVE). 졸업=significant edit→학습 재진입, CPLPV +25~32% 악화 경향 ([reference_meta_proven_graduation_frequency.md]).
- 원래 졸업기준 = triple share (7d 풀 spend/clicks/LPV 모두 ≥50% + CTR/CPC/Freq 게이트). 본문 메모리 파일은 정리됨, MEMORY.md 인덱스 요약만 잔존.
