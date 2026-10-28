---
name: reference-jp-bsr-data-availability
description: "JP 경쟁사 BSR 시트 확장 — Amazon JP(Keepa)=US 완전동형, Rakuten=순위/가격/리뷰만 (2026-07-02 실측)"
metadata:
  type: reference
---

# JP BSR 데이터 수집 가능 범위 (US Top100 시트 → JP 확장)

US 시트 = `docs.google.com/spreadsheets/d/105gMV-fUEyuP2Sb3aloQffNJXiexcmmowWrfuT814E8` (Top100 BSR_Toddler Cups). 현재 탭 실제 헤더 **43열**(gviz csv 실측): Display Order·Product Details·Parent ASIN·ASIN·URL·Image URL·Brand·Price US$·Price/Unit·Pack Size·Parent Level Sales·ASIN Sales·Recent Purchases·Parent Level Revenue·ASIN Revenue·Title Char.Count·BSR·Seller Country·Fees US$·Active Sellers·Ratings·Review Count·Images·Review velocity·Buy Box·Category·Size Tier·Fulfillment·Dimensions·Weight·ABA Most Clicked·Creation Date·Sponsored·Best Seller·Seller Age·Seller·Material·Drinking Mechanism·Age Range·Volume Tier·Price Tier·Notes(Claude)·Notes(Jiah).

## ⚠️ 시트 출처 = Helium 10 Xray extension (7/6 세은 확인 — Keepa/DK 아님)
**이 시트는 Helium 10 Xray Chrome 확장으로 뽑은 것.** 기존 "Keepa product API / orbiters DK 산출물" 추정은 **틀림**. Sales·Revenue·Parent·Active Sellers·Fees·Creation Date·Dimensions·Weight·BSR = 전부 Xray 컬럼세트(추정치). → **JP도 Helium 10 Xray로 뽑아야 US와 같은 추정엔진·비교 성립**.
- Helium 10 = amazon.co.jp(JP 마켓) 지원. GROSMIMI JAPAN 셀러 연결됨(A1A01CME113JSP, 근데 **Xray엔 셀러 연결 무관** — 확장 유료로그인만 필요).
- **확장 로그인 ≠ 웹 대시보드 로그인**(별개). Sales/Revenue 블러 = 확장이 무료/미로그인 → 확장 로그아웃→유료 재로그인→Ctrl+Shift+R. 확장 팝업 우하단 플랜(Free/Platinum) 표시로 확인.
- 방법: 확장 설치·유료로그인 → amazon.co.jp 카테고리(`gp/bestsellers/baby/{node}`) 또는 검색결과 페이지 → 확장 팝업 **Xray — Amazon Product Research** → 테이블 → **Export CSV**. 검색결과 페이지가 Xray 더 잘 뜸(베스트셀러는 Niche Summary 위젯이 더 잠김). 무료=Sales/Revenue 잠김.

## Keepa (orbiters — 참고, US 시트 소스 아님)

## Keepa (핵심)
- **orbiters EC2(SSM)에 실재·유효** (guide §3514 dry-run #3251 "keepa=실조회 valid"). SE 로컬 .env엔 없음.
- DK 테이블 `seo.amazon_keepa_bsr_daily` (MCP dk_query 가능) — **ASIN별 일별 BSR 시계열**(Toddler Cups+Baby), 실측 우리 ASIN B08TZY1TFY 6/5~7/2 26일치. **현재 domain=1(US)만 가동**, JP=domain 5 추가하면 동일. Keepa는 과거 이력 소급도 됨.
- 시트 units/판매량 1차소스 = 아마존 SERP "X+ bought in past month" 배지(Keepa monthlySold는 fallback). JP도 배지 뜸 실측(`100+ bought in past month`, B0GL2SQ3RL).

## Amazon JP = US 41열 중 40열 취득 가능 (ABA Most Clicked만 X, US도 N/A)
- 스크랩 즉시: title·ASIN·URL·Brand·Price·**BSR Baby/Toddler**(PDP `#35 in Baby`)·Ratings·Review·Weight·Best Seller·Images수·Fulfillment·태그(Material/Mech/Age/Volume/Price Tier)
- **Keepa 필수(스크랩 0/60)**: Parent ASIN·Parent Sales/Revenue·Creation Date·Fees·Dimensions·Active Sellers
- Toddler Cups 노드 = **345985011** (US와 동명 카테고리)

## Rakuten = 순위/가격/리뷰/태그만, 판매량·매출·Parent·등록일 불가
- 카테고리 랭킹 O: `トレーニングカップ・マグ`=**genre 207753**(=Toddler Cups 대응), 상위 `ベビー食器`=207750. daily/weekly/realtime. 순위·가격·리뷰건수·평점 실측.
- **영구 불가 5칸**: Parent ASIN(D)·Parent Sales(K)·Revenue(L/M)·Creation Date(R). 라쿠텐 "売上高·売上個数 내부만 쓰고 비공개" 명시. 추정툴(Keepa류) 라쿠텐 비대상.
- 상품 ID = URL의 `shopCode/itemNumber`(itemCode) 전상품 추출됨. 단 **리스팅 단위**(같은 상품 샵별 별도 ID) → cross-seller parent 롤업 불가.
- 랭킹 추이는 forward-only(과거 소급 X).

## 산출물
- (7/2) `참고자료(USA)\JP_BSR_US형식_20260702_v2.xlsx` (Amazon 60행+Rakuten 50행). 60 PDP raw = `.tmp/usa_ref/pdp_parsed.json`.
- (7/3) `참고자료(USA)\JP_BSR_랭킹_4장르_대칭_20260703.xlsx` — 넓은(식기)+세부(마그) 2×2 대칭 4시트. 빌더 `.tmp/usa_ref/build_bsr_rankings_0703.py`.
- (7/3) `참고자료(USA)\AmazonJP_BSR_US완전동일_2장르_100위_20260703.xlsx` — **US 43컬럼 완전동일, 각 장르 100위(누락0)**. 빌더 `.tmp/usa_ref/build_amz_us100_0703.py`. Xray 전용 23칸(Sales/Revenue/Parent/치수 등)은 회색 공란 — **이 칸들이 Helium 10 Xray가 채우는 것**. 카드칸 18개(제목·순위·가격·평점·리뷰·태그)만 스크랩분.

## firecrawl 기법 (아마존 베스트셀러 100행 + JP locale + ¥)
- 정적 `scrape --country JP`는 **lazy-load로 페이지당 ~30개만**(31~50·81~100 누락). → **`firecrawl browser` Playwright 스크롤**로 해결: `launch-session` → `execute --python` 에서 goto+`page.mouse.wheel` 반복(`.zg-bdg-text` 개수≥50까지)+카드 추출. 페이지당 50개 확보.
- **일본어**: `page.set_extra_http_headers({'Accept-Language':'ja-JP...'})` + URL `?language=ja_JP`. **¥ 가격**: `page.context.add_cookies([{name:'i18n-prefs',value:'JPY',domain:'.amazon.co.jp'}])` (안 하면 세션 US-geo라 USD로 나옴).
- ⚠️ PowerShell→node 인자로 `"` 먹힘 → Playwright 코드는 **double-quote 없이**(single quote + unquoted CSS attr). firecrawl `-o`는 파일 안 씀 → stdout을 `Out-File`로 캡처. 스크립트 `.tmp/usa_ref/bs_scroll_extract.py`.

## Xray 회색칸을 orbiters 파이프라인으로? = 막힘 (7/6 검증)
US top100 파이프라인(`amazon_keyword_top100` collector→`top100_bsr_builder`)에 JP 추가 = 내 편집 cap 밖(`code:edit:datakeeper/ingestion:*` 없음, validate 확인). ingestion은 MCP 편집 자체 불가(admin git). Keepa 키도 EC2만. → **JP 회색칸은 Helium 10 Xray로 뽑는 게 정답**(파이프라인 확장 불필요).

## 랭킹 뽑을 때 축(넓은=식기 / 세부=마그, 플랫폼 대칭 A안 — 세은 7/3 승인)
계층 실측: `Amazon: ベビー&マタニティ > 授乳・食事 > ベビー食器(2479261051) > ベビーマグ(345985011)` ↔ `Rakuten: キッズ·ベビー·マタニティ(100533) > … > ベビー食器(207750) > トレーニングカップ·マグ(207753)`. **넓은축은 root 아님 — 반드시 ベビー食器 레벨로 대칭**(root은 기저귀·분유 범벅이라 컵 분석 무의미). US는 root 썼지만 JP는 A안 채택, B안(root 미러) 폐기.
- Amazon JP: 넓은=ベビー食器 **2479261051** + 세부=ベビーマグ **345985011**(=US Toddler Cups). firecrawl `gp/bestsellers/baby/{node}`(?pg=2). 파싱: `NN. #RANK`→`/dp/ASIN`→`5つ星のうちX_ 리뷰수`→`￥가격`. 타이틀 `\[…\]` 이스케이프 대괄호·ポイント배지 링크 주의(가장 긴 후보 채택). lazy-load라 URL당 ~30개(top~60/80, 갭 있음).
- Rakuten: 세부=トレーニングカップ・マグ **207753** + 넓은=ベビー食器 **207750**(`ranking.rakuten.co.jp/daily/{genre}/`, p=2로 81~). **랭킹 페이지엔 평점 평균 없음**(레ビュー 건수만) → 평점 N/A. 마커 `![N位]`(top3)/`N位`(4+).
- 우리 제품: 7/3 4장르 캡처분 전부 0건. Keepa 추적 ASIN(B08TZY1TFY 등)은 **domain=1 US** 기준이라 Amazon JP 리스팅과 별개. Rakuten littlefingerusa 샵도 카테고리 daily top~90 밖.

관련: [[reference-dk-read-orbitools-mcp]] · [[feedback-deliver-actual-data-not-feasibility]] · [[mistakes-20260702-premature-unavailable-claims]]
