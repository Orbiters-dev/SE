---
name: reference_rakuten_rpp_demand_signals_api
description: 라쿠텐 RPP 키워드 수요 신호 API 정본 — 몰 전체 검색량은 비공개지만 RMS RPP가 recommendationRankedKeywords(검색량랭크)와 recommendationCpc(目安, POST+XSRF)로 라쿠텐 네이티브 신호를 준다. 임의 신규 키워드 目安 전수 조회 가능.
metadata:
  type: reference
---

RPP 키워드의 **라쿠텐 네이티브 수요 신호** 조회법 (2026-10-02 삐삐 재발견). 라쿠텐은 아마존 Helium10 같은 **몰 전체 검색량을 공개 안 함**(확인). 그래서 RMS RPP API가 주는 두 신호가 유일한 라쿠텐 실측이다.

## API 2종 (ad.rms.rakuten.co.jp/rpp/api, 로그인=`rms_review_playwright.do_login`)
1. **GET `/keywords/recommendationRankedKeywords?itemId=X`** → `data.keywords[{keyword, keywordHash, searchVolumeRank(1~5), competingItemBidRank}]`.
   - `searchVolumeRank` = 라쿠텐 실검색량 랭크(1~5). **가장 순수한 라쿠텐 검색량 신호지만 커버리지 낮음** — 라쿠텐이 그 상품에 "추천하는" 키워드만(stainless 29·ppsu 23·onetouch 14개). 임의 신규어는 대부분 목록에 없음(랭크 데이터 없음). 상위랭크는 전부 광의/브랜드어(出産祝い·ストローマグ·ベビー用品·赤ちゃん=랭크5).
2. **POST `/keywords/recommendationCpc`** body `{"itemId":X,"keywords":[...]}` → `data.keywords[{keyword, recommendationCpc(目安), minRecommendedPrice, maxRecommendedPrice, urbClassification}]`.
   - **임의 키워드 전수 가능**(등록 안 한 신규어도) → 신규어 목安 조회의 핵심.
   - ⚠ **`x-xsrf-token` 헤더 필수**(없으면 403). 값 = 쿠키 `XSRF-TOKEN`을 `decodeURIComponent`. page.evaluate fetch에서 `(document.cookie.match(/XSRF-TOKEN=([^;]+)/)||[])[1]`로 추출.
   - ⚠ **예전 GET `/keywords/recommendationCpc?keyword=X&itemId=Y`(8/10 `rpp_reco_refresh.py`)는 죽음** — 지금은 SPA index.html 반환(status 200). 라쿠텐 UI 개편으로 GET단일→POST배치 전환.

## itemId (판매중 3상품, 2026-10-02 실측)
- `stainless_steel_strawcup_300` = **10000008**
- `grosmimi_ppsu_strawcup300` = **10000001**
- `grosmimi_ppsu_onetouch_srawcup` = **10000002**
- items 목록: GET `/rpp/api/items?page=N` → `data.items[{itemId, manageNumber/itemUrl(slug 포함)}]`.

## 해석 (사전 지표 — 성과 아님)
- **目安CPC = 라쿠텐 내 경쟁가 = 수요 간접 신호**. 高(¥150+)=경쟁/수요 큼, ¥40 floor 근처=극소. ⚠ "검색량 직접"이 아니라 경쟁강도 프록시.
- **高目安이면 ¥40 탐침으론 노출 안 뜸**(경쟁가가 그보다 높아서) → 신규어 등록 입찰은 目安 하한(min) 근처로.
- 이 신호들은 전부 **사전(넣기 전) 수요 가설**. "잘 되는지"는 등록 후 노출→클릭→전환 실측으로만 판정([[reference_rpp_keyword_expansion_map]] 사후 판정).

툴: `.tmp/rpp_eff/fetch_rakuten_demand_v3.py`(최종 수집) · `capture_post_headers.py`(XSRF 식별) · `discover_meyasu_api.py`(네트워크 추적 발견). 관련: [[reference_rpp_replacement_3source_dsinsight]]·[[reference_rpp_keyword_efficiency_pipeline]].
