---
name: reference_rms_report_daily_by_item
description: RMS 리포트(access get-item-list · RPP 商品別)는 아이템×일 2차원 미지원 → 하루씩 startDate=endDate 루프로 일별화. 로그인 1회 후 page.request 재사용.
metadata:
  type: reference
---

RMS 데이터툴 리포트의 공통 제약 (2026-09-23 채널 CVR 실험에서 실측 규명).

## 제약: 아이템×일 2차원 동시 미지원
- **access get-item-list** (`datatool.rms.rakuten.co.jp/access/item/get-item-list/`): `period=daily` + 기간(startDate~endDate)을 줘도 **각 행이 date=None** — 기간 전체를 아이템별로 **합산**해 반환. 일별 아님.
- **RPP 商品別 리포트** (`ad.rms.rakuten.co.jp/rpp/api/reports/downloadPerfFile` `selectionType=3`): **全期間(periodType=0)만 되고 日ごと(periodType=2)는 HTTP 400**. 商品別은 일별 불가.

## 우회: 하루씩 startDate=endDate 루프
두 리포트 모두 **startDate=endDate=단일일**로 호출하면 그 날 하루의 아이템별 값을 준다. 날짜 범위를 루프 돌려 일별 시계열을 만든다. Playwright **로그인 1회**(rms_review_playwright.do_login) 후 `page.request`(access) / 페이지 fetch 리플레이(RPP, ctx.request는 403)를 재사용하면 N일도 빠름.

## selectionType (RPP downloadPerfFile)
1=すべての広告 · 2=キャンペーン · 3=商品別 · 4=キーワード別. 캠페인(2)은 日ごと 되지만 商品別(3)·キーワード별은 全期間/月ごと만.

## 아이템 식별자 = 商品管理番号 (itemId 아님)
access·RPP 商品別 둘 다 **商品管理番号**(mngNumber)으로 아이템 구분 — 동일 키라 조인 가능. fliptop=`grosmimi_ppsu_onetouch_srawcup`(+copy) · 기본컵=`grosmimi_ppsu_strawcup300`(+_ss) · Stainless=`stainless_steel_*`. ⚠️ RPP "商品連動 itemId"(10000001 등)는 리포트에 안 나옴 — 리포트 조인엔 관리번호 사용.

## 지표 컬럼
- access salesFormula: `visitAll`(アクセス人数)·`orderCountAll`(주문)·`unitsAll`(판매개수)·`cvrAll`(%).
- RPP 商品別: `クリック数(合計)`(클릭)·`売上件数(合計12時間)`/`(合計720時間)`(주문). same-day 정렬엔 12時間, RPP 캐노니컬(D+30)은 720時間.

도구: `tools/channel_cvr_daily.py`(access) · `tools/collect_rpp_item_daily.py`(RPP). 관련 [[project_meta_tiktok_channel_cvr_experiment]] · [[reference_rpp_full_keyword_report]].
