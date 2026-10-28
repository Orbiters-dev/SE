---
name: reference_rpp_replacement_3source_dsinsight
description: RPP 대체 키워드 발굴 = 라쿠텐 유입 + Amazon JP 서치텀(전환실측) + Google Trends 3소스 교차. 큰 검색량 ≠ 전환. Yahoo Insight=DS.INSIGHT(RPP엔 부적합·반려됨).
metadata:
  type: reference
---

RPP 대체 키워드 발굴 방법론 (2026-09-17 확립).

## 3소스 교차검증 (라쿠텐 몰 내 검색량 직접 데이터 부재 → 프록시 조합)
1. **라쿠텐 점포 유입 검색어** `.tmp/ceo_ads_report/inflow_keywords_monthly.json` (searchWord/visit/ratio). "이미 우리를 찾은 수요"라 discovery엔 좁음(생존편향)·규모 작음(top 80~256 visit).
2. **Amazon JP 서치텀·Brand Analytics** — `DataKeeper.get("amazon_ads_search_terms"/"amazon_brand_analytics")` brand="Grosmimi JP". 실제 노출+클릭+**전환**까지 있는 1차 데이터(Helium10보다 우위 — H10엔 전환 없음). SFR=검색빈도순위.
3. **Google Trends** `pytrends` — 상대 수요(절대량 아님)+연관쿼리. ⚠️ `TrendReq(retries=..)` 인자 = urllib3 2.x와 충돌(method_whitelist) → `TrendReq(hl="ja-JP",tz=540)`만.

## 핵심 결론: 큰 검색량 ≠ 전환
- **子供 水筒**(GTrends 55≈ストローマグ급·Amazon 14,036노출)·赤ちゃん マグ·保冷マグ 등 **대형 제네릭어는 3소스 모두 전환 0~2%** (라쿠텐 ベビーマグ 동일 패턴). 세은 「야후 검색량으로 큰 수요 찾자」 가설의 실측 답 = 큰 수요는 있으나 전환 안 됨.
- **전환축 = 브랜드어(グロミミ/グロミミ ストローマグ) + 속성조합(保冷·漏れない·ステンレス).** 대체어 등급: 전환검증(우리 실적) > 수요검증(수요 큼·전환미검증→¥40 실험) > 상품정합(가설). 수요·정합 등급은 반드시 저가 실험만.

## 2026-09-18 확립: 시장수요 소스 = Helium10 + 라쿠텐 유입 (우리 서치텀만 = 좁음)
- **소스 편협 오판 주의**: `amz_agg`(우리 아마존 계정 서치텀)는 **우리 광고 걸린 것만**이라 시장 전체 아님. 이걸로 "수요 키워드 부족" 결론=오판(세은 "20개도 안 되냐 장난하냐"). 
- **주 소스 = Helium10 시장 검색량**: `tools/helium10_client.py` (Magnet `get_keywords_by_keyword` 시드확장·Cerebro `analyze_keywords` 배치SV·marketplace=JP·refresh token 무인). 시드 10개 확장=822 시장키워드→제품관련 필터(`.tmp/rpp_eff/h10_filter.py`) 93개. ストローマグ SV 9338.
- **+ 라쿠텐 점포 유입**(`inflow_keywords_monthly.json`) = **라쿠텐 몰 직접 실수요**(플랫폼 일치·아마존 프록시보다 직접적). H10엔 없는 ストローマグ 漏れない 保冷·マグ ベビー 등 라쿠텐 실수요 포착. 保冷·漏れない·ステンレス 축 강함.
- **종합 판정**: 신규/재입찰 = H10 검색량 OR 라쿠텐 유입 있는 것만(수요0=삭제). 정렬=라쿠텐 유입(직접) 우선→H10 SV. **제품정합 필터 필수**(PPSU≠保冷/스텐). 빌더 `.tmp/rpp_eff/build_v3.py`(3소스+US 종합·상태그룹).
- **Google 검색량 절대값 = `tools/fetch_keyword_volume.py`** (DataForSEO). ⚠️ 잔액 마이너스→402 결제필요(보조 소스·H10로 대체 가능).
- 산출물: `s\performance marketing\Rakuten\rpp_keyword_efficiency_20260917.html`(상품별 탭)+`.pdf`. 빌더 `.tmp/rpp_eff/build_tabs.py`·`aggregate.py`·`gtrends.py`·`amz_agg.py`.

## Yahoo Insight = DS.INSIGHT (LINEヤフー)
- 라쿠텐 매니저 추천 "Yahoo Insight"의 실체 = **DS.INSIGHT**(ヤフー・データソリューション). 검색볼륨·연관어·디모그래픽·계절성. 무료 없음(엔트리 2만엔/월·다운로드 불가), 7일 트라이얼 https://ds.yahoo-net.jp/trial/dsinsight (신청목적=市場調査/무엇 골라도 기능동일).
- **RPP 대체어 소스로는 부적합**: ①야후 웹검색(라쿠텐 몰 내 아님·점유 ~10%) ②단위=유니크 유저(검색횟수 아님) ③롱테일 임계컷(니치 안잡힘). 규모 발굴엔 **Google(DataForSEO/KP)이 우위**.
- **2026-09-17 littlefingerusa 명의 트라이얼 신청→당일 반려**(審査理由 비공개). 유료 구독도 같은 심사면 어려울 수 있음.

관련: [[feedback_rpp_off_threshold_5000]], [[reference_rakuten_rpp_data_limits]].
