---
name: session-20260904-pipi-supersale
description: 삐삐 — 라쿠텐 슈퍼세일 RPP 키워드 확장 (US+JP 승자 → 세은 세팅분 제외 → 미등록 리스팅), 슬롯 만석이 바인딩 제약
metadata:
  type: project
---

# 세션 2026-09-04 삐삐 슈퍼세일 RPP 키워드 확장

세은 지시: 오늘부터 라쿠텐 슈퍼세일. 슈퍼세일용 URL에 세팅해 둔 RPP 키워드 읽고, **거기 있는 건 제외**하고 없는 것 위주로 US 대시보드 승자 + JP 승자 찾아 리스팅.

## 실측 3축

1. **세은 슈퍼세일 세팅분(제외 대상)** — RPP 콘솔 내부 API `/rpp/api/keyword?itemId=` 직접 조회(로그인 재사용 `rms_review_playwright.do_login`). 덤프 스크립트 `.tmp/pipi_ss/rpp_dump.py` → `rpp_all_keywords.json`. 슈퍼세일 상품 = `_copy`/`_ss` 접미사 복사본 5개.
2. **US 승자** — Data Keeper `amazon_ads_keywords`/`amazon_ads_search_terms`, US 그로미미 profile_id=1094731557245186(≠Grosmimi JP 3736…). 30d. 원자료 `.tmp/pipi_us_probe/`.
3. **JP 승자** — `.tmp/ceo_ads_report/inflow_keywords_monthly.json` (라쿠텐 유입 검색어 실측, months 딕셔너리 2026-05~09).

## ⚠️ 바인딩 제약 = 슬롯 만석 (핵심 발견)

RPP 상품당 키워드 슬롯 10개(8/11 룰). 슈퍼세일 5상품 슬롯:
- stainless_steel_strawcup_copy (스텐 히어로) **10/10 만석**
- grosmimi_ppsu_strawcup_ss (PPSU 히어로) **10/10 만석**
- grosmimi_ppsu_onetouch_copy (원터치) 8/10 → **2칸 여유**
- grosmimi_srawnipple_2set_copy / _4p_copy (파츠) 각 2/10

→ "미등록 추가"가 물리적으로 **교체(스왑) 또는 신규 슈퍼세일 상품 URL 등록**을 요구. 히어로에 그냥 못 넣음.

## 산출 (세은 콘솔 페이스트용, 하드룰 11대로 나는 쓰기 실행 X)

- **블록 A (원터치 2빈칸 즉시)**: `食洗機対応 ストローマグ`(JP유입 13v·상품명 食洗機OK인데 미등록), `ワンタッチ ストローマグ`
- **블록 B (JP 실측 근거, 교체/신규용)**: 保冷マグ 赤ちゃん · ベビーマグ 保冷 · ステンレスマグ ベビー · ストローマグ 魔法瓶 · 透明 ストローマグ(PPSU 투명 전용) · ストローマグ 2way · ストローマグ 逆流防止 · ミルク ストローマグ(US toddler milk ROAS5.26 + JP5v 양축)
- **블록 C (US 이식 가설, D+14 노출0 퇴출)**: ベビー 水筒 · ステンレス 水筒 ベビー(US baby water bottle ROAS8.9) · トレーニングマグ(US sippy cup 대응)

제외 소거는 **어순·띄어쓰기 변형=동일**(8/11 룰) 적용해 24종 union 대비.

## 대기 (세은 결정)

슈퍼세일 상품 URL을 **더 늘릴지**(자리 확보) vs 만석 히어로에서 **스왑**할지 — 방향 주면 상품별 최종 페이스트본 확정. 스왑 후보로 히어로의 `ストローマグ 1歳/2歳`(US 월령 이식 실패 이력·JP유입 근거 약) 눈에 띄나 세은 의도면 유지, 임의 삭제 X.

## 교정

강한 교정 1: 「개소리여 다시 진행해」 — 도구 경로 SKILL에 다 있는데 `.tmp` 인벤토리 스캔 두 라운드 → [[feedback-no-inventory-dump-when-task-concrete]].
