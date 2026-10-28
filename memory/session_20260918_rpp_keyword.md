---
name: session_20260918_rpp_keyword
description: 세션 2026-09-18 (삐삐 — RPP 등록 키워드 효율 + 20슬롯 재구성. 콘솔 실측(상품10·수동77·예산¥150k·슬롯상한≥17)·3분류·US벤치·H10+라쿠텐유입 3소스 종합. 강한 교정 다발)
metadata:
  type: project
---

# 세션 2026-09-18 — RPP 키워드 효율 + 20슬롯 재구성 (삐삐)

라쿠텐 매니저 피드백 대응: 풀라인업 Branded/Competitor/Generic 3분류 성과 + 20슬롯 채우기(뭘로·근거).

## 콘솔 실측 (9/17 스냅샷 뒤집힘 — 하드룰10 케이스)
- **슬롯 상한 10 아님 → 실제 ≥17**(stainless_copy 17·ppsu_ss 15 등록). 20 채우기 구조적 가능.
- **등록 상품 10개·수동 키워드 77개**(9/17은 5활성만 셌음)·**예산 ¥150,000**(8/27 ¥110k에서 증액)·단일 캠페인 `(Manual)202608-` id 400011·라인업 **9/4 재구축**.
- 全キーワードレポート는 **활동(클릭>0)만** 나옴(45개)·노출수 미제공. 등록 전량 텍스트=`iconKeywordBidModal` 콘솔 스크래핑(10개씩 페이지네이션).

## 세은 지정 대상 = 3 리스팅 (스크린샷)
ppsu_strawcup_ss·stainless_steel_strawcup_copy·grosmimi_ppsu_onetouch_copy. (300 mains 섞지 말 것 — [[mistakes_20260918_rpp_keyword_sourcing]])

## 결과 (3상품 9/1~17)
- 3분류: Branded 소수·저비용·고ROAS / Generic 본진 / Competitor 소액. Branded spend 비중이 US(KW4.4%·ST13.4%) 사이에 이미 위치 → branded 슬롯 소수 유지가 맞음(매니저 질문 답).
- 판정: 유지·확장(전환/브랜드) / 재입찰(미노출·수요큼) / 관찰(클릭O·전환0·¥5,000미달) / 신규(수요실측·제품정합) / 삭제(수요0·부적합).
- OFF임계 ¥5,000+전환0 유지([[feedback_rpp_off_threshold_5000]]).

## 방침 (세은)
- **20 다 채워 테스트 후 안되면 끄기** (등록만으론 과금X·클릭시만). 단 수요0은 노출 자체가 안 나 테스트 불성립 → 실측 수요 있는 것만.
- (B) US 속성근거(6개월·2세·practice)는 살리고 순수 수요0(ワンタッチ 조합·保温 단독)만 제거.

## 산출물
- `s\performance marketing\Rakuten\rpp_keyword_efficiency_20260918.html`(탭·인터랙티브) + `.pdf`(전상품 펼침 A3가로). 빌더 `.tmp/rpp_eff/build_v3.py`.
- 데이터: H10(`tools/helium10_client.py`·시장 822kw)·라쿠텐유입(9월)·RPP 全리포트·US mkt_weekly(192.168.0.9:8770 data/mkt_weekly.json)·현 등록 콘솔 실측.

## 강한 교정 (→ 오답노트)
대상 임의병합·PPSU에 保冷/스텐(제품불일치)·수요 실측없이 추측삽입·소스 편협(우리 서치텀만→"20개도 안 되냐 장난하냐")·이유 질문에 고치지말고 답부터. 전부 [[mistakes_20260918_rpp_keyword_sourcing]].

## 미완
- harness report 검증 미실행(세은 지시 대기). 콘솔 등록(쓰기)은 세은 실행 지시 후.
