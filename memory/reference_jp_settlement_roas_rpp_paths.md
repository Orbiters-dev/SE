---
name: reference-jp-settlement-roas-rpp-paths
description: JP 메타 결산 데이터 경로 — 블렌디드 ROAS(Meta+RPP), RPP 취득법, 라쿠텐 매출 RMS config client
metadata:
  type: reference
---

# JP 메타 결산 데이터 경로 (2026-07-01 확립)

## ROAS 정의 (세은 확정)
- **블렌디드(Total) ROAS = 라쿠텐 총매출 ÷ (Meta 스펜드 + RPP 광고비)**. RPP(라쿠텐 프로모션) 비용도 분모에 포함해야 함 — 안 넣으면 과대계상.
- 통화 = **원(₩) 통일**, JPY→KRW는 **당일 환율**(2026-07-01 기준 1엔=9.58). Meta JP 스펜드는 이미 KRW.
- Total ROAS = 블렌디드 MER(오가닉 포함)이지 incremental 아님. Meta LPV→라쿠텐 픽셀 추적 불가 → 방향성 지표.

## 데이터 취득
1. **Meta JP 6월**: `META_JP_ACCESS_TOKEN` + act_4117678028561958, Graph v21.0 `/insights` (`.tmp/meta_daily_windows_*.py` 패턴 재사용). fetch_meta_ads.py는 글로벌계정용(JP 아님).
2. **라쿠텐 매출**: ✅ **일별 자동 수집 (2026-07-21 프로덕션화)** — `tools/collect_rakuten_sales_daily.py` → `data/rakuten_sales_daily.json` (searchOrder→getOrder `priceTaxIncl×units`, 취소 제외, 청크 스로틀+403 백오프). 백필 2025-11-01~. 401 뜨면 licenseKey 만료 = [[reference-rms-licensekey-rotation]](reference_rms_licensekey_rotation.md).
   **Total ROAS 는 meta-app 에 상시 표기**: 홈(어제/7일 KPI) + 예산 탭 기간 뷰 카드 + 월별 표 (매출·Total ROAS 컬럼). 시드 rakuten-sales-seed.json / rpp-daily-seed.json, Task Scheduler `RakutenRPP_Daily_Spend` 09:20 매출→RPP 체인 후 재배포.
3. **RPP 광고비**: ✅ **일별 자동 수집 가능 (2026-07-21 실측)** — 콘솔 내부 API `downloadPerfFile` + `periodType:2`(日ごとに集計)로 일별 row CSV, 기간 자유(백필 가능). 상세 = [[Rakuten RPP 데이터 한계 + 実績額 = spend 매칭]](reference_rakuten_rpp_data_limits.md). 공식 RMS API는 여전히 미노출.
