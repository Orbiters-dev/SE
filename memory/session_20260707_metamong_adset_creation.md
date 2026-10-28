---
name: session-20260707-metamong-adset-creation
description: 메타몽 — 신규콘텐츠 DK읽기→Testing ad set 2개 API 자동생성(PAUSED). CRM토큰으로 partner-content read 자체해소. 크리에이티브는 앱 IG권한 없어 UI.
metadata:
  type: project
---

2026-07-07 메타몽 세션 (강한 교정: WL토큰≠WL코드 혼동 1건 "이 미친놈아", 결국 env내 해결):

**지시:** 새로 올라온 콘텐츠 전부 DK 읽어서 Meta ads 세팅. **ON은 세은이 함 → PAUSED로 세팅만.** 방법 끝까지 찾고 안 되는 것만 물어봐.

**한 것 = Testing ad set 2개 API 자동생성(PAUSED, 검증완료):**
- an_3mama_baby(CT-61550): adset `120249455846060223`, `Y26M07D07_Grosmimi_RKT_WL-G_AN_3MAMA_BABY_B0G6CCJ24K_CT-61550` (무상, Stainless FLIPTOP Olive)
- minkoro_kosodate(CT-62157): adset `120249456229390223`, `...WL-P_MINKORO_KOSODATE_B0G6CCJ24K_CT-62157` (유상, Stainless FLIPTOP Cherry)
- 공통 config: ₩8,000/day · LANDING_PAGE_VIEWS · IMPRESSIONS · LOWEST_COST_WITHOUT_CAP · JP18-65 advantage_audience · brand_safety FACEBOOK_RELAXED/AN_RELAXED · 캠페 Rakuten_WL_PPSU&Stainless_Testing_2026(120248267687980223, ABO).
- 생성법: `POST /act_4117678028561958/adsets` (META_JP_ACCESS_TOKEN, ads_management). 기존 Testing adset config 클론.

**핵심 해소/발견:**
1. **partner-content read = `DK_SE_CRM_TOKEN` Bearer 로 200** (read토큰 403). 원기 tabs.read 안 기다려도 됨(7/6 오판 정정). → sponsorship_type·wl_code·content_advertisable 다 읽힘. [[project_meta_content_intelligence_loop]]
2. **content_advertisable = Meta branded_content_advertisable_medias 실권한(SoT).** True=광고가능(agree_advertisable/conflict_code_dead/opportunity 다 포함) / False=agree_denied 제외 / None=무관. 신규 advertisable+미집행 = an_3mama·minkoro 2건.
3. **ASIN = 부모ASIN.** Stainless FLIPTOP 부모 = B0G6CCJ24K (variant는 child). ProductSSOT `s\パポマ\META ADS 관리용\ProductSSOT-TEST_0612_임시Filled.xlsx`. 발송제품은 세은이 구두 확정(olive/cherry) — DK 발송SKU 필드 여전히 미노출.

**남은 블로커 = 크리에이티브(인플루언서 영상) 자동부착 불가:**
- `source_instagram_media_id` 를 grosmimi_japan IG(`17841473805016400`)에서 branded_content_advertisable_medias 로 뽑아야 하는데 — META_JP_ACCESS_TOKEN 앱(1570751280806472)에 IG권한 없음(`/media`=code10 "Application does not have permission", branded edge=code1). 글로벌 META_ACCESS_TOKEN 죽음(code190). WL토큰은 서버 SSM `/orbiters/meta_jp_wl/access_token`(로컬X, AWS creds도 로컬X).
- → **세은이 Ads Manager UI에서 크리에이티브 붙이고 ON** (첫케이스 佐藤/oto62도 동일 이유로 UI). 완전자동엔 앱 IG권한 추가 필요.

**세팅 제외:** nee_and_twins/oto62/yucchi/ohana=advertisable False(agree_denied) / zundamon_pokemon=무관노이즈 / rhythmical_mama=이미 ACTIVE.

## 추가 진행 (같은 세션 후반) — nee 추가 + 크리에이티브 API 경로 돌파
- 세은이 nee_and_twins도 지시(코드 당일 수령) → ad set 4번째 생성: `120249456927950223` `...WL-G_NEE_AND_TWINS_B08TZY1TFY_CT-61568` (PPSU Straw 10oz). **이 세션 ad set 총 3개(an_3mama/minkoro/nee)** PAUSED.
- 세은 강력 요구 「ad set만 X, ad까지」「다른 팀 분은 API로 잘만 함, 될 때까지 찾아」 → 크리에이티브 자동부착 재도전.
- **GROSMIMI_JP_API 앱 토큰**(세은 발급, instagram_branded_content_ads_brand 등)으로 **branded content 미디어 resolve 성공**(bare shortcode): nee=`18069650129390125` / an_3mama=`18104023172115924` / minkoro=`18095365382206286`. 방법 전체 → [[reference_meta_wl_branded_ad_api_creation]].
- 광고주 페이지 Grosmimi Japan=`880831635120245`, 제품별 라쿠텐 링크 확보.
- **미해결 벽 = GROSMIMI_JP_API 앱 Development 모드** → API 광고게시물 생성 차단. Live 전환 대기(세은). 전환되면 광고 3개 생성 재시도.
- DK_SE_CRM_TOKEN(bd10) 세션 중 401 사망(새 토큰 dk_SE_7de6 발급으로 로테이션 추정). 새 토큰은 partner-content 403(tabs.read 미위임). env DK토큰 3곳 7de6로 교체.
- 강한 교정 다발 → [[mistakes_20260707_metamong_wl_ad]] (외부떠넘김 재발·조기포기·느림·남폴더뒤짐).

관련: [[project_meta_content_intelligence_loop]] · [[reference_adname_framework_v1]] · [[reference_meta_wl_testing_gate_criteria]] · [[reference_meta_wl_branded_ad_api_creation]] · [[mistakes_20260707_metamong_wl_ad]]
