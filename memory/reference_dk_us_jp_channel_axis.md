---
name: DataKeeper 광고 데이터 US vs JP 축 구분 (메타 brand 키·아마존 profile_id·통화)
description: DK 광고 테이블은 US/JP가 한 테이블에 섞여 있어 브랜드키·profile_id로 반드시 필터해야 함. JP 리포트에 US 데이터 넣으면 대형 오류. 통화도 채널별 상이(메타 JP=KRW, 아마존 JP=JPY, 메타 US=USD).
metadata:
  type: reference
---

**2026-09-10 대형 오류 교정 (「너 뒤질래?」)**: JP 슈퍼세일 리포트에 메타 `brand="Grosmimi"`(=US·USD)를 JP 메타비로 넣음 → 실제 JP는 `brand="Grosmimi JP"`(KRW). 데이터도 통화도 둘 다 틀림.

## DK `meta_ads_daily` 브랜드 키
- `brand="Grosmimi JP"` → **JP**, target_countries=['JP'], **통화 KRW**, 캠페인=`Rakuten_WL_*` (WL 인플루언서 광고). JP 리포트는 이거.
- `brand="Grosmimi"` → **US**, target=['US'], **USD**, 캠페인=Amazon/Shopify US. JP에 쓰면 안 됨.
- JP 메타는 라쿠텐 픽셀 전환귀속 없음(purchase_value=0) → 메타 자체 ROAS 산출 불가, 지출만. 블렌디드 tROAS로만 평가.

## DK `amazon_ads_daily` profile_id
- `3736142261021843` = **Grosmimi JP** (JPY, ad_type SP/SB/SD, 캠페인 Stainless_Manual·PPSU_Manual + SBV). JP 리포트는 이거.
- `1094731557245186` = US Grosmimi / `1766270639560191` = 또 다른 US 계열.
- 아마존 매출=14d 귀속(최근일 저평가).
- ⚠ **JP SBV(SB) 캠페인명이 DK엔 없음**(amazon_campaigns에 profile 3736… 자체가 없음). 이름은 Amazon Ads API 직접 조회: `POST advertising-api-fe.amazon.com/sb/v4/campaigns/list` body `{}` (Accept `application/vnd.sbcampaignresource.v4+json`), 인증=`.tmp/ceo_ads_report/jp_ads_token.json` refresh + CID/CSEC(pull_amz_ads_daily_direct.py), scope profile 3736…. (9/10 실측: …4189=お手入れたんたん / …4997=目盛り / …2420=消毒)

## 환율 (Frankfurter ECB, UA헤더 필요·urllib 기본 403)
- USD→JPY, JPY→KRW 조회. `api.frankfurter.app/latest?from=JPY&to=KRW` (9/9=8.718). 메타 KRW→JPY 환산 = KRW ÷ (KRW per JPY). 교차검증=open.er-api.com.

**How to apply:** JP 광고 리포트 작성 시 DK 광고 테이블은 **무조건 brand="Grosmimi JP" / profile_id=3736142261021843로 필터 후** 통화 확인(메타 KRW·아마존 JPY). 채널 합산 전 통화 통일. [[reference-dk-read-orbitools-mcp]]
