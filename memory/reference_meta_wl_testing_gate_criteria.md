---
name: Meta WL Testing 운영 3게이트 기준 (2026-06-16 확정)
description: WL 영상 Testing 1:1 분리 운영의 OFF·졸업·Budget 게이트 임계값과 산정 근거. 과거 90일 D+3/D+7 baseline 기반.
metadata:
  type: reference
---

# Meta WL Testing 운영 3게이트 기준 (2026-06-16 확정)

세은+메타몽 세션 확정. act_4117678028561958 (KRW). [[project_meta_jp_testing_split]] 후속 — 어제 분리 결정 위에 OFF/졸업/Budget 구체 임계 확정.

> **⚠️ 2026-07-27 추가 (세은 확정): Proven CPLPV OFF 게이트 신설** — 아래 「게이트 4」 참조. 동일 날짜에 Proven delivery 실패 게이트도 앱에서 D+90 임의 프록시 → 5/28 확정 룰(share<1%+zero≥7/14)로 교정됨 ([[reference_meta_delivery_failure_gate]]).

**큰 그림:** 모든 신규 인플루언서 영상 → Testing 1:1 분리(소재1=adset1) 투입 → D+3 OFF / **D+3 졸업**. Testing = 상시 깔때기 입구. 메인 판단 = CPC/CTR (세은이 평소 보는 지표), CPLPV = 크로스체크.

> **⚠️ 2026-07-09 변경 (세은):** 졸업 CPLPV **135 → 130** (PPSU/Stainless 공통). 반영 완료: `meta-constants.ts` GRAD_CPLPV_MAX=130 (Vercel 배포됨) + `meta_jp_daily.py` GRAD_CPLPV_MAX=130. 배경 = SKU별 CPLPV 티어 분석(최근30일 p50: PPSU 120 / Stainless 132) 후 세은 확정.
>
> **⚠️ 2026-07-06 변경 (세은):**
> 1. **졸업 판정 D+7 → D+3.** OFF·졸업 **둘 다 D+3**. (앱/코드 `GRAD_MIN_DAYS=3`. meta-constants.ts + meta_jp_daily.py.) 다시 D+7 언급 금지.
> 2. **Testing 은 증액 제도 없음** — Testing 광고는 (a)이대로 유지 or (b)Proven 승급 둘 중 하나. **증액 후보에 Testing 넣지 마.** 증액은 Proven 전용.
> 3. **Testing/Proven 분류 = campaign 이름 기준** (`/test/i`), 나이(D+N) 기반 X. Testing 캠페인 = "Rakuten_WL_..._Testing_2026". offRecommendations 도 campaign 기준으로 통일(이전엔 나이 기반이라 D+15+ Testing 이 Proven 으로 새어 OFF 게이트 안 탔음).

## 게이트 1 — OFF (D+3, 누적 LPV ≈185)
```
① CPC ≤₩150  그리고  CTR ≥5%        → 생존
② CPC·CTR 중 하나라도 나쁨           → CPLPV 확인
      └ CPLPV ₩190↑ → 즉시 OFF
      └ CPLPV 정상  → D+5 유예 (경계선 보호)
③ CPC·CTR 멀쩡한데 CPLPV ₩190↑      → OFF (이탈형 돈샘)
```
- 나쁨선 = 과거 90일 WL 광고 D+3 성적 **하위 15%**: CPC ₩149→**₩150**, CTR 4.8%→**5%**(깔끔하게), CPLPV ₩189→**₩190**.

## 게이트 2 — Proven 졸업 (D+3 — 2026-07-06 변경, 이전 D+7)
```
CPC ≤₩95  그리고  CTR ≥8%  그리고  CPLPV ≤₩130  → Proven 승급   (CPLPV 2026-07-09 세은: 135→130)
승급 방식 = Testing PAUSE → Proven 새 ad_id (haru 방식, learning 재진입 CPLPV +25~32% 감안)
```
- 졸업 자격선 = **실제 Testing→Proven 졸업한 영상 5개(monyuru/bebimon/haru/kina/komugiko)의 Testing 시절 성적** 중앙(CTR 7.6/CPC86/CPLPV126) vs 비졸업군(CTR5.5/CPC130/CPLPV157) 경계.
- CTR 7% vs 8% 졸업생 통과 동일(bebimon10.4·haru8.6) → 8% 채택(더 보수적, 약한 졸업 komugiko6.7·monyuru5.7 차단). 현 우수신규 kyan10.1·aomaru8.7은 8%로도 통과.

## 게이트 3 — Budget
- Testing 각 ad set **₩8,000/day** · Proven 현행 유지 · **개수 캡 없음**(모든 신규 다 받음).
- 분리 시 Testing 예산 ₩131K→₩56K (**−₩75K/day, 월 ≈−₩2.25M**). 현재 Testing 2개 adset에 몰빵(76K+55K)이던 걸 7개×8K로 쪼개도 절약.
- 캡 불필요 이유: D+3 OFF·D+7 졸업이 자동 조절. **늦어도 D+7엔 모든 영상이 Testing 떠남**(OFF/졸업/Proven흡수). 중간 잔류작도 D+7 결론 → 안 쌓임.
- 총액은 막는 선 아닌 **모니터링 지표**(평소 ₩56K 대비 튀면 유입폭증/OFF미작동 신호).

## 게이트 4 — Proven CPLPV OFF (2026-07-27 세은 확정 — 지속성 판정)
```
OFF 후보   = 14d AND 30d 모두 CPLPV ≥₩150  (양 창 LPV ≥30)
모니터링   = 14d CPLPV ≥₩135              (졸업컷 130 이탈 관찰)
조건      = Proven 캠페인 · WL(PAID/GIFT)만 · 이관 D+14+ (재학습 +25~32% 보호)
```
- 190 은 Proven 에서 죽은 기준 (실분포 30d min86/p50113/max148 — 졸업 필터 통과 풀이라 타이트).
- 150 근거: 졸업컷 130 +15% = 자격 상실 / Stainless BEP ≈100 의 1.5배. Testing 190→150 하향 제안과 값 통일 (Testing 쪽은 별건·계류).
- Testing D+3 스냅샷과 달리 **이중창(14d+30d) 지속성** — 일시 스파이크는 30d 가 흡수.
- 반영: `meta-constants.ts` PROVEN_* 4종 + `meta-aggregations.ts provenCplpvCandidates` + alerts 병합 + `meta_jp_daily.py proven_cplpv_candidates` + 렌더 박스. 도입 시점 실측 = OFF 0 / 모니터링 4 (CONI 147/138·KOMUGIKO 146/148·ARARA 138/137·MUGI 137/121).
- **⚠️ 메일 쪽 게이트 입력은 Graph 직접** (`graph_ad_rows_for_gate`) — DK 과거 행 LPV 부재로 30d CPLPV 부풀림 (실측 KOMUGIKO 221 vs Graph 148). DK fallback 시 OFF 확정 신뢰 X.

## 머신러닝 안전 (세은 핵심 우려 — 검증됨)
1. **끄는 광고 본인**: D+3 누적 LPV 중앙 **321**(임계 50의 6배, 94% 통과) → 학습 완료 후 OFF, 미완 중단 아님.
2. **옆 광고**: 학습은 ad set 단위. **1:1이라 OFF=그 adset 통째 종료, 타 소재 adset 완전 독립** → 학습 영향 0. 통합 방식(한 ad 끄면 같은 adset 리셋)보다 오히려 안전.
3. **리셋 트리거 없음**: OFF=한 번 끄고 폐기(새 영상 대체), 껐다 켰다 반복 X.

## D+3 조기판정 타당성 (검증됨)
- D+3 순위 → D+7 순위 예측력: **CPC +0.97 / CTR +0.93 / CPLPV +0.96** (거의 완벽).
- D+3 멀쩡→D+7 추락 = **0건** (좋은 거 죽이는 일 없음). D+3 OFF선→D+7 회복 2건(AD C·monyuru)은 경계선 → D+5 유예가 커버.

## CPLPV vs CPC/CTR 관계 (왜 CPLPV 크로스체크)
- 공식: `CPLPV = CPC ÷ (클릭→LPV 도착률)`. CPC/CTR은 클릭까지만, CPLPV는 랜딩도착(우리가 사는 것)까지.
- 우리 풀 클릭→LPV율 44~97% 출렁. CPC vs CPLPV 순위상관 0.81 → 세은 CPC/CTR 메인 OK(80% 일치). 단 AD P(CTR6.1好·CPC130괜찮·CPLPV294꼴찌, 도착률44%)처럼 "클릭 잘되는데 랜딩 이탈"형은 CPC/CTR로 못 잡음 → CPLPV가 그것만 거름.

## 잔여·실행
- **⏳ 2026-07-08 계류:** OFF CPLPV 190→**150** 하향 제안 중 (세은 확정 대기). 배경 = Stainless BEP CPLPV ≈₩100(세은 계산), 190은 분포 하위15% 컷이라 경제성 논리 없음. 실측 근거·반영 파일 = [[project_off_gate_cplpv150_pending]]. 확정 전 판정은 현행 190.
- 표본 작음 (OFF baseline 19개 / 졸업생 4개). **6/17 정상 트래픽 후 갱신.**
- 실행 시점 = 6/17 오전 이후 (슈퍼세일 후속관찰 ~6/17 08:00 종료, 트래픽 정상화 확인 후).
- 메인 데이터 도구: `tools/meta_jp_daily.py` fetch(level=ad, with_daily) → ad별 D+3/D+7 윈도우 집계. WL 식별 = ad_name `| PAID |`/`| GIFT |` 라벨.
