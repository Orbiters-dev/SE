---
name: Rakuten RPP 데이터 한계 + 実績額 = spend 매칭
description: RPP 일별 spend = 콘솔 내부 API downloadPerfFile periodType=2(日ごとに集計)로 프로그래밍 수집 가능 (2026-07-21 실측). RMS 공식 API는 여전히 미지원. 「実績額(合計)」 = 실 청구 spend 추정.
type: reference
---

## ✅ 일별 수집 해결 (2026-07-21 실측 — 아래 구 한계 항목 2·3·4 무효화)

- **`POST ad.rms.rakuten.co.jp/rpp/api/reports/downloadPerfFile` + `periodType: 2` = 日ごとに集計** → 지정 기간의 **일별 row CSV**가 한 요청에 떨어짐 (기간 자유 지정 → 과거 백필도 가능).
- payload: `{page:1, selectionType:1(전체)/2(캠페인)/3(상품)/4(키워드), periodType:2, startDate, endDate, reportFilter:1, campaignType:"1", rankType:1, ...}` — periodType 0=全期間합계 1row, 1·3=에러.
- 실행로: `rms_review_playwright.do_login` (헤드리스 검증) → `/rpp/reports` 페이지에서 「この条件でダウンロード」 1클릭으로 x-xsrf-token 헤더 캡처 → **페이지 컨텍스트 fetch 리플레이** (ctx.request는 403).
- **프로덕션: `tools/collect_rpp_daily.py`** (하네스 PASS) → `data/rpp_daily.json` 일별 upsert. Task Scheduler `RakutenRPP_Daily_Spend` 매일 09:20 `--update-app` (meta-app `lib/rpp-daily-seed.json` 복사 + vercel 재배포). 백필 2025-11-01~ 완료(262일), **6월 합계 ¥106,902 = 세은 제공값 정확 일치** 검증. 월별 TROAS = 이 store 월 합산 ÷ 분모 결합으로 계산(세은 방침 7/21: 일일 수집만, TROAS는 월별).
- **앱 표기 자리: meta-app 예산 탭 → 월별 뷰 「월별 총 광고비 (Meta + RPP)」 카드** (`app/budget/page.tsx` TotalAdSpendCard + `lib/rpp.ts`). RPP ¥→₩ = open.er-api.com 실시간(12h 캐시, fallback 9.11). prod 렌더 실측 완료 7/21.
- 교차검증: 단일일 요청(7/20) 実績額 ¥4,497 = 일별집계(7/14~20) 7/20 row ¥4,497 일치. CSV는 cp932.
- 주의: ① 720時間(D+30) 매출 귀속은 소급 갱신 → 최근 30일 창 재수집 필요 ② 실적 0에 가까운 날은 row 자체가 생략될 수 있음 (7/19 부재, 7/18은 0 row 존재 — 결측일 0 처리) ③ 키워드별(sel 4)은 実績額 TOP10 필터.

## RPP 데이터 한계 (2026-06-08 확인 — 상당 부분 위 7/21 발견으로 대체됨)

1. **RMS API 2.0 RPP 미지원** — `import_rakuten_rpp.py` docstring 명시. 공식 API 경로는 여전히 없음 (수집은 위 콘솔 내부 API로)
2. ~~CSV export 期間 합계 1 row만~~ → periodType=2로 일별 분해 가능
3. ~~当月暫定 누적값만~~ → 동일
4. ~~차분 기반 일별 추적 path~~ → 불필요

## 「実績額(合計)」 ≈ spend 매칭 검증

- CSV 4일(6/4~6/7) row: 클릭 296 × CPC ¥37 = ¥10,952 ≈ 「実績額(合計)」 ¥10,909
- CSV 7일(6/1~6/7) row: 「実績額(合計)」 ¥31,898 ≈ 当月暫定 6/8 「前日まで」 ¥31,481 (오차 ¥417 = 시점 차)
- 「割引後実績額」 컬럼 "-" (할인 미적용)
- **결론(매칭 근거):** 「実績額(合計)」 = 실 청구 spend. 단 Rakuten RMS 공식문서로 단정 검증은 미완료

## 도구 한계 

`tools/import_rakuten_rpp.py` 의 COLUMN_MAP 은 「広告費」「広告費用」 → cost 로 기대. 실제 CSV 컬럼은 「実績額(合計)」 → 매핑 mismatch. import 도구 사용 시 컬럼 매핑 수정 필요.

## 6/8 검증된 RPP 데이터

| 기간 | spend (¥) | clicks | CPC | 매출 12h (¥) | 매출 720h (¥) |
|---|---:|---:|---:|---:|---:|
| 6/1~6/7 (7일) | 31,898 | 509 | 63 | 98,810 | 133,690 |
| 6/4~6/7 (4일, 슈퍼세일 후) | 10,909 | 296 | 37 | 83,220 | 101,360 |
| 6/1~6/3 (3일, 차분) | 20,989 | 213 | 99 | — | — |

**관찰:** 슈퍼세일 기간 RPP 일평균 spend −61% (¥6,996 → ¥2,727). CPC −63% (¥99 → ¥37). 원인 미확인 (cap hit / 입찰 경쟁 변동 / organic 흡수 후보).
