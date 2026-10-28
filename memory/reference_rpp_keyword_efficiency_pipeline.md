---
name: reference_rpp_keyword_efficiency_pipeline
description: RPP 판매중 상품 키워드 효율 리포트 파이프라인 정본 (2026-09-30 삐삐) — 콘솔 등록 전량 스크래핑 × 全キーワードレポート 교차 → 탭형 HTML. 판매중 3상품 각 20키워드·is_sale_sku 제외·리포트는 클릭>0만이라 콘솔 실측 필수.
metadata:
  type: reference
---

RPP 키워드 효율 정리 요청(세은 "업뎃한 키워드 효율+시사점") 시 재사용 파이프라인 (2026-09-30 확립).

## 대상 판별 = is_sale_sku 로 슈퍼세일 제외 후 판매중만
- **판매중(대상) 3상품 슬러그**: `stainless_steel_strawcup_300`(스텐 ¥5,800) · `grosmimi_ppsu_strawcup300`(PPSU ¥3,190) · `grosmimi_ppsu_onetouch_srawcup`(원터치 ¥4,200). + 니플 `grosmimi_srawnipple_2-4`/`2-2`(브랜드어 2개씩).
- **슈퍼세일/제외**: `is_sale_sku(m)= "copy" in m.lower() or m.endswith("_ss")` (세은 지시 정본, [[reference_jp_supersale_ad_report_pipeline]]). stainless_copy·ppsu_strawcup_ss·onetouch_copy·nipple copies.
- **2026-09-30 실측**: 세은이 9/21 슈퍼세일·copy 5개 리스팅 키워드 **전량 비움**("登録済みのキーワードがありません")하고, 판매중 3상품에 **각 手動 키워드 정확히 20개** 재등록. (9/18 세션의 "세일 리스팅이 대상" 모순은 이 9/21 이동으로 해소 — 현재는 판매중이 대상.)
- **슬롯 상한 = 20 가능**(8/11 "10" 무효, 9/18 확인 ≥17).

## 데이터 소스 2개 교차 (⚠ 하나만 쓰면 반쪽)
1. **全キーワードレポート ZIP** = 효율(클릭·実績額(spend)·CPC실적·売上720h·CV·CVR·ROAS·CTR·目安CPC). 툴 `.tmp/kw_recheck/pull_rpp_kw_full.py`(로그인→/rpp/reports→rdReportTypeKeyword+cbMetricsAll→この条件で検索→#btnAllKeywordReport→/rpp/download 完了 ZIP). **집계기간 当月(9/1~어제)·当日 미제공.** CSV=cp932.
   - ⚠ **리포트는 클릭>0 키워드만 잡힘** → 등록했지만 노출0인 키워드는 안 나옴.
2. **콘솔 등록 전량**(노출0 포함) = `/rpp/items` 상품행 편집아이콘(`iconKeywordBidModal`)→登録済みキーワード 테이블(키워드·設定CPC·目安CPC), 10개/페이지 페이지네이션. 재사용 스크립트 `.tmp/rpp_eff/dump_selling_20260930.py`(판매중 대상·페이지 병합·읽기전용). 로그인=`tools/rms_review_playwright.do_login`.

## 교차·빌드
- 교차: `.tmp/rpp_eff/merge_eff_20260930.py` — 콘솔 20세트 × 리포트 (product,keyword) 매칭. 리포트 없는 키워드=클릭0=미노출.
- HTML 빌더: `.tmp/rpp_eff/build_html_20260930.py` → `s\performance marketing\Rakuten\rpp_keyword_efficiency_20260930.html`. 탭형(상품별 20개 전량)·키워드 KO병기·헤더클릭 정렬(오름/내림)·판정 배지. 세은 확정 라벨: **설정 CPC(입찰상한)·추천 CPC(目安=경쟁가)**. 렌더검증 필수(9/18 탭 미표시 버그 → verify_html.py 3탭 실측).

## 판정 기준 (세은 확정)
- **OFF = ¥5,000 소진+전환0** ([[feedback_rpp_off_threshold_5000]]). 미달 전환0=관찰보류.
- 미노출(클릭0): 目安=¥40(floor)이면 경쟁·검색 극소 신호. 입찰이 아니라 **검색빈도 극저 + 자동최적화가 관련도 높은 상품에 노출 몰아줌**(RPP 전부 자동최적화 타입). 한국계 어(韓国ストローマグ·ベビーマグ韓国)=라쿠텐 유입에 실존하나 극저빈도 → PPSU 본진엔 노출/전환, 원터치엔 0.

## 2026-09-30 핵심 결과
- 스텐 ROAS 478%(전환6) / PPSU 175%(전환7·**제네릭 ¥11,109 전액 전환0이 진범**) / 원터치 144%(전환1·상품 전환력 이슈 지속).
- **전환은 60개 중 7개 키워드가 전부·상위4(保冷·ステンレス·グロミミ×2)가 77%.** 전환축=브랜드+속성. 제네릭(ベビーマグ·ストローマグ)은 3상품 중복등록+전환0(자기잠식). 써모스 컨퀘스팅 실패. 高CTR+전환0(원터치 グロミミストローマグ CTR28%)=상품페이지 병목.

관련: [[reference_rpp_replacement_3source_dsinsight]] · [[reference_rakuten_rpp_data_limits]] · [[feedback_rpp_off_threshold_5000]] · [[mistakes_20260918_rpp_keyword_sourcing]]
