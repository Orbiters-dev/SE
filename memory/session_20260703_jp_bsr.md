---
name: session-20260703-jp-bsr
description: "세션 2026-07-03~06 (JP Amazon/Rakuten BSR 시트 — 대칭축·라쿠텐 dedup·100행 스크랩·Helium10 발견)"
metadata:
  type: project
---

# 세션 2026-07-03~06 (JP BSR 시트)

어제(7/2) JP BSR 수집가능성 조사 이어서, 실제 랭킹 뽑기.

## 한 일
1. **4장르 랭킹 뽑기** — Amazon 식기(2479261051)·마그(345985011) + Rakuten 식기(207750)·마그(207753). firecrawl.
2. **대칭축 교정** — 처음 Amazon 넓은축을 root로 잘못 잡음(라쿠텐 식기와 스코프 불일치). 세은 지적 → **양쪽 ベビー食器 레벨로 대칭(A안)** 확정. 산출 `JP_BSR_랭킹_4장르_대칭_20260703.xlsx`.
3. **라쿠텐 = 멀티셀러 몰** 규명 — 같은 제품(b.box 시피컵 등)을 여러 샵이 각자 리스팅 → 순위에 중복(b.box 23건, サーモス 9건). b.box 정규품 240ml가 coniconi/gekiyasu/natural-living 3샵 다 ¥2,420 실증. 제품 dedup 시도했으나 **JAN/型番/製品ID 부재로 하드 확정 불가**(제목 휴리스틱만).
4. **원본 판매량 순위 그대로 나열** — 세은 최종 요구. 라쿠텐 데일리 랭킹은 리스팅 단위(제품 단위 순위 없음).
5. **Amazon US 완전동일 43컬럼 100행** — firecrawl `browser` Playwright 스크롤 + JPY 쿠키로 lazy-load 100행·¥·일본어 확보. `AmazonJP_BSR_US완전동일_2장르_100위_20260703.xlsx`. Xray 전용 23칸은 회색.
6. **핵심 발견(7/6)**: **US 시트는 Helium 10 Xray extension으로 뽑은 것**(Keepa/파이프라인 아님). → JP도 Xray가 정답. 세은 Helium 10 Platinum + JP 셀러 연결, 확장 유료 로그인까지 진행. Xray Export CSV 대기.

## 7/8 업데이트 — ベビーマグ 완성 (식기는 세은 결정으로 제외)
- 세은 Xray CSV(마그) 도착 → `AmazonJP_BSR_TOP100.xlsx` (META ADS 관리용 루트) 에 머지 완료 상태 확인. Sales 100/Revenue 99/CreationDate 99.
- **PDP 100건 스펙 스크랩** (firecrawl browser, 세션당 5 ASIN 배치 — 10개는 execute 타임아웃): 商品情報 kv (素材·容量·対象年齢·商品種別·入り数) → `.tmp/usa_ref/pdp_kv_0708.json`.
- 태그 컬럼 빈 칸 채움 (파란 배경 = PDP 스펙 출처): Material 30→86 / Mech 83→100 / Age Range 13→76 (스펙 최저월령 "6M+" 형식) / Volume Tier 44→77 / Pack Size 0→92.
- **색 체계 (세은 지시)**: 파랑=PDP 스펙 확정(신규+기존값 PDP일치 교차검증 137건), 노랑=추정·세은 확인 필요 27셀(불일치 23+PDP스펙없음 4). b.box Straw→**Weighted Straw 6건은 세은 확인 후 반영**. A1 타이틀에 범례 추가.
- 영구 공란: Parent 4컬럼+Price/Unit+Pack(Xray JP export에 컬럼 없음 — Xray 테이블 컬럼 설정에서 추가 후 재export하면 가능할 수도), ABA(US도 N/A), Sponsored(export 전부 빈값).
- **US v0_FINAL 형식 이관 (7/8, gid=173600900 실측)**: US 주간 트래커 23컬럼 구조로 재구성 — 시트 `v0_FINAL`(메인) + `raw_41col_20260703`(보존). Update DATE=2026-07-03·New Entry=New·드롭다운 5개(S~W 3:102, US formula1 그대로)·헤더 서식/열너비/freeze A2 복제. 값 매핑: Stainless→Stainless Steel/Plastic→Other/부품→Accessories(제목+商品種別 한정, パーツ少ない·スペア～付き 오탐 제외)/Cup→Open·ミラクルカップ→360º rim/월령버킷(<6M=">6M")/PriceTier Low→Budget·High→Premium·Premium→Luxury. BSR in Baby/Toddler = PDP 売れ筋ランキング 파싱 100/100. US Price Tier는 단가(USD) 수식 — JP는 ¥임계 미정이라 값 매핑(수식화하려면 세은 ¥임계 필요). 파랑312/노랑27 carry. 빌더 `.tmp/usa_ref/build_us_format_0708.py`.
- **chip 드롭다운 = 구글시트 전용**. ⚠️US 시트에 JP탭 붙였다가 「JP는 아예 새로 만들어야지」 교정 → 세은이 새 시트 생성. **최종 산출물 = 「TOP 100 BSR _ JP」 시트** `1Sq2EpVkCtcbChCOX3bVjAYbgMufk9oYTlchh4ZHRRGc` `v0_FINAL` 탭(gid=1437430340): US v0_FINAL copy_to(chip·옵션색 상속)→값 클리어→JP 100행+¥포맷(H/I/L/M)+노랑27셀. US 시트는 원상복구(세은이 JP탭 삭제, 4탭 확인). SA influence-sync@ editor. xlsx·시트 태그 전수대조 diff 0. **다른 팀/브랜드 시트에 우리 탭 만들지 말 것 — 산출물은 항상 별도 시트.**
- 세은이 탭명 `v0_FINAL`→`ベビーマグ` 변경. Tag Reference 탭 복사(섹션5=JP ¥기준으로 갱신) + **Price Tier = US 동일구조 ARRAYFORMULA 자동화** (W3, 단가 I열 기준, SS별도: 일반 810/1300/2430·스텐 1620/2430/3240, USD→¥@162.1 7/8환산, 세은 지시 「알아서 판단말고 수식으로」). 분포 Premium38/Budget24/Luxury19/Mid16/공란3(가격N/A). I열(단가)도 ARRAYFORMULA(H÷J) 자동화 → **H·J·태그만 수기, I·W는 수식 영역(직접입력=#REF)**. H=판매가/I=개당단가 구분 설명 완료. 세은 노랑 셀 직접 교정 진행 중(b.box PP, EDISONmama Accessories 확인).
- **가격 기준 = 판매가(수집시점 buybox) 확정 (7/8 세은 합의)**: 「정가로 해야 객관적 아니냐」 질문 → ①순위는 판매가로 만들어진 결과 ②参考価格=셀러 주장(부풀림·부재 다수) ③상시할인 왜곡 ④Revenue 정합 논리로 판매가 유지 설득, 세은 「이해했어 판매가로 가자」. 세일 눌림은 주차 스냅샷 누적으로 해소. 정가는 필요 시 별도 컬럼 병기(미실행).
- 라쿠텐 쪽은 판매량 순위 원본(중복 포함)으로 확정.

## 7/8b~7/9 업데이트 — JP vs US 비교 보고서 + 시트 정리
- **JP vs US 비교 HTML 보고서** 생성: `Desktop\s\パポマ\META ADS 관리용\JP_US_BSR_TOP100_비교보고_20260708.html` (Playwright 렌더 실측 완료). 핵심: US 매출 6.4배·분산 vs JP 과점(TOP5 브랜드 84.7%, b.box+Thermos 2강)·Luxury 매출 1위(41.9%)·Straw 계열 85.6%·리뷰 중앙값 68 vs 3,645. GROSMIMI = US 브랜드 6위(3.9%, 5 SKU 전부 Luxury) / JP TOP100 부재 → JP Amazon 미개척 시사점. 비교는 양쪽 다 M열 ASIN Revenue 기준(환율 162.1 고정). 스냅샷 시차 US 6/1 vs JP 7/3 주석.
- **카테고리 대칭 실증**: JP 345985011 영문 페이지 제목 = "Best Sellers in **Toddler Cups**" — US 166801011과 Amazon 공식 동일 노드(Baby>Feeding>Solid Feeding>Cups, 형제 Dishes/Utensils 대칭). "더 toddler스러운 JP 노드"는 Baby 트리에 없음(컵 노드 단일).
- **O열 뒤섞임 원인+수리**: 행순서=7/3 Xray CSV 순서, O열=7/8 PDP 파싱 순위 → 5일 BSR drift. O열 오름차순 재정렬(값 A-H/J-V만, I/W ARRAYFORMULA 불가침, 배경색 행따라 이동, 무결성 튜플집합 검증). 이후 세은 지시로 **O열 1~100 연번화** + **브랜드 33표기→20개 영문 통일**(Richell 26/Combi 21/b.box 9/…, あにま~るマグ→EDISONmama, プラキラ→Plakira 공식확인). 백업 `.tmp/usa_ref/presort_backup_0709.json`.
- **K/L(Parent Level Sales/Revenue) 공란 원인 확정**: Helium 10 자체 추정값이라 Xray export가 유일 소스인데 JP CSV에 컬럼 자체가 없음(실측). H10 크레덴셜 전무(.env/.wat_secrets 확인)라 SE가 못 뽑음. US 데이터로 의미 실증(96/100 ASIN rev < Parent rev = 변형 패밀리 합산).
- **미완료**: ① 세은 Xray Column Settings에 Parent Level 항목 있는지 확인 → 재export 시 K/L 머지 + 진짜 현재시점 1~100 갱신(기존 ASIN 태그 carry-over) ② JP 시트의 O열은 이제 "리스트 내 연번"(진짜 BSR 아님) — 재export 갱신 때 정리.

## 강한 교정 (다수) → [[mistakes_20260703_jp_bsr]], [[mistakes_20260709_cause_question_direct_answer]]
소스 미확인 삽질(Keepa 단정) / 선택지 남발 / 휴리스틱 단정 / 메커니즘 과장 / K·L 원인 재질문 받음(결론 흐림). 관련 [[reference_jp_bsr_data_availability]].
