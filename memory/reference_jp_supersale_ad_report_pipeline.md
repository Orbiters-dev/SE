---
name: JP 슈퍼세일/아마존 광고 리포트 빌더 + 데이터 소스 (탭형 HTML)
description: 라쿠텐 슈퍼세일 + 아마존 SP/SBV 광고 리포트(탭형)의 빌더 경로·데이터 소스·정본 위치. 9/11 완결본 재실행법 포함.
metadata:
  type: reference
---

**2026-09-10 신규**: 탭형 광고 리포트 (탭1 라쿠텐 슈퍼세일 / 탭2 아마존 & 위클리 진척).

## 빌더·산출
- 빌더 `.tmp/weekly_report/build_supersale_0910.py` → `operations/rakuten_supersale_ad_report_20260910.html`.
- 정본 = **`C:\Users\orbit\Desktop\s\performance marketing\META ADS 관리용\operations\`** (기존 주간 덱들 있는 폴더. "S 폴더"=Desktop\s, "s\..."의 s는 Shared 아님 Desktop\s). 로컬 SE/operations + 이 정본 둘 다 복사.
- 별도 아마존 진단 리포트 빌더 `.tmp/weekly_report/build_amz_diag_0910.py` → `operations/amazon_jp_ad_efficiency_diag_20260910.html` (레드 테마).

## 데이터 소스 (전부 read-only, 콘솔 조작 없음)
- **RPP 일별** `data/rpp_daily.json` (계정 총계·JPY). **스토어 매출** `data/rakuten_sales_daily.json`.
- **RPP 키워드×상품** = 全キーワードレポート ZIP. ⚠ 기본 날짜피커가 월초(9/1)부터 → 시작일을 세일창(9/4)으로 세팅해야 정합. 미리보기/직접 API(downloadPerfFile)는 403 or TOP10캡 → **async 全キーワードレポート만 전량**. 집계 최소 단위=日別(시각 분리 불가, 20:00 시작 못 자름). 키워드리포트=키워드연동만.
- **RPP 상품별(자동+키워드 통합)** = 全商品レポート (rdReportTypeItem + #btnAllItemReport). 주문 합계가 계정과 일치 → 商品連動(자동) 포함 진짜 상품 총계. 키워드뷰선 누수 보이던 상품이 상품뷰선 자동채널 전환으로 승자일 수 있음(9월 스텐 실증).
- **스토어 제품별 매출/주문** = RMS `datatool.rms.rakuten.co.jp/access/item/get-item-list/?period=daily&startDate=YYYYMMDD&endDate=` → salesFormula(salesAll·orderCountAll·unitsAll·visitAll·cvrAll). 商品管理番号로 버킷.
- **메타/아마존** = DK ([[reference-dk-us-jp-channel-axis]] — JP 필터 필수). SBV명=Ads API.
- **6월 비교** = 동일 파이프라인 6/4~6/9 + 노션 6월 공식 성과 리포트.

## 상품 3갈래 버킷 (mngNumber/ASIN)
PPSU=*ppsu*strawcup* (ASIN B08TZY1TFY·B0B9GLVWYN) / fliptop(원터치)=*onetouch* (B0DJNXD66N) / stainless=*stainless* (B0G6CCJ24K·B0FR4FGBPP) / 기타=srawnipple·brush. tROAS=스토어매출÷(메타+RPP광고비).

## 9/11 완결본 (2026-09-11 세션 — build_supersale_0911.py · 정본 rakuten_supersale_ad_report_20260911.html)
puller들(pull_ss_daily_kw·pull_ss_item·pull_ss_store_item) 종료일 변경 후 재수집 → 빌더 재실행. 출력 to0910 파일 유지(내부).

### ⚠ 라쿠텐 당일 광고데이터 전면 미제공 (9/11 실측 확정)
"지금 현시간까지" 요청 시: 라쿠텐 RPP/상품 리포트는 **당일치를 일절 안 준다**. RPP downloadPerfFile(당일 포함)=HTTP 400 "集計期間 오류" · 全商品レポート 다운로드 버튼=disabled · get-item-list(endDate=당일)=전일까지만 반환 · 全キーワード=당일 리포트 미생성(폴링 실패). **주문 API(searchOrder/getOrder)만 당일 조회 가능.** collect_rpp_daily/collect_rakuten_sales_daily도 yesterday까지만 저장 설계. → **세일 상품 매출은 주문 API로 9/11 당일까지 집계**: getOrder ItemModel.**manageNumber**(=상품관리번호)로 세일용 SKU(_copy/_ss)별 매출·판매건수 필터 집계(.tmp/weekly_report/sale_sku_orders.py). orderDatetime으로 세일 실기간(4일20:00~11일01:59) 시간정밀도 가능. 판매건수 3종 구분 필수: 주문 건수(order_set) < 상품 라인 수(=팀원 「판매 건수」·평단=매출÷수량) < 판매 수량(units). → 광고 ROAS 리포트는 전일까지가 모든 축 정합 최신. 당일 스토어매출은 참고 note로만.

### 메타는 hourly breakdown으로 세일 실기간·당일 가능 (9/11 실측)
`api_get(f"{ACCT}/insights", {level:account, fields:spend, time_range:{since,until}, breakdowns:"hourly_stats_aggregated_by_advertiser_time_zone"})` → 하루 24시간대 spend. 토큰=env META_JP_ACCESS_TOKEN·ACCT=META_JP_AD_ACCOUNT_ID(meta_jp_daily.py 재사용). **당일치도 시간별로 지금까지 나옴**(라쿠텐과 다름). 슈퍼세일 실기간=**4일 20:00~11일 01:59** 시간정밀 합산(.tmp/weekly_report/meta_sale_hourly.py). ⚠ DK meta_ads_daily의 최근일(9/10)은 집계지연 부분치일 수 있음 — hourly가 정확(9/10 daily ₩130K vs hourly ₩274,979). 단 hourly=기간 정밀도지 세일용/평시 상품 구분 아님(메타 landing_url DK 미기록·ASIN만).

### 세일용 SKU 필터 (세은 지시 — 세일 성과=세일용 상품 URL만)
슈퍼세일 상품은 평시와 별도 SKU(상품관리번호 `_copy`/`_ss` 접미사). `is_sale_sku(m)= "copy" in m.lower() or m.endswith("_ss")` 로 스토어(get-item-list)·RPP(全商品) 세일용만 순수 집계. 평시(`_300`·`_200`·onetouch_srawcup·brush·2-4/2-2) 제외. ⚠ PPSU 세일용 SKU가 6월 `_copy`→9월 `_ss`로 바뀜(둘 다 세일용). 메타만 상품 구분 불가(전체·참고치).

### 리포트 슬라이드 순서 (탭1, Total ROAS 슬라이드 제거됨 — 메타 픽셀귀속 없어 블렌디드 부정확)
6월 비교 → 스테인리스 급감 분석 → 한눈에 RPP → 상품3갈래 → 채널2분해 → 전환키워드 → 클릭TOP5.

### 6월 대비 9월 부진 원인 규명 (9/11)
세일 상품 매출 6월 ¥602,820 → 9월 ¥180,240(-70%). **감소분 전체가 스테인리스 단독**(¥538K→¥99K·-82%), PPSU·원터치는 오히려 성장. **트래픽 아니라 전환 붕괴**: 스테인리스 방문 11,000→16,067(+46%)인데 CVR 0.85%→0.11%(1/8). 유입 증가 주원인=메타 클릭 +57%(20,984→32,905·노출 비슷·지출 -14%=CPC 개선). 해석(추론): 6월 스테인리스 신제품 런칭 슈퍼세일 첫구매 폭발 vs 9월 3개월차 초기수요 소진. 가격/할인율 차이는 미확인.
