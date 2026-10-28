---
name: reference-ih-video-source-drive-naming
description: "IH(자사 grosmimi_japan 계정) 영상 광고 소스 = 지정 Google Drive 폴더. ad set·ad 제목 = 매칭 영상 파일 제목 그대로, 현재 형식 유지. 제품은 세은이 제목에 붙임"
metadata:
  type: reference
---

# IH 영상 광고 — 소스 폴더 + 네이밍 규칙 (2026-09-18 세은 지시)

`@grosmimi_japan` **자사 계정** 게시물(=IH, In-House)을 IH 캠페인(`120250841109750223`)에 광고로 올릴 때:

## 영상 소스 = 고정 Google Drive 폴더
- **폴더**: https://drive.google.com/drive/folders/1E5vKZQ5zUTNo4U8zTBibA1ebCbR-N-QO (folder id `1E5vKZQ5zUTNo4U8zTBibA1ebCbR-N-QO`)
- 여기에 올릴 영상은 **항상** 이 폴더에 저장돼 있음. IH 업로드 착수 시 이 폴더에서 매칭 영상 찾기.

## ad set · ad 제목 = 매칭 영상 제목 그대로
- Drive 영상 **파일 제목과 매칭**해서 ad set 및 ad 제목을 만든다. **ad set 이름 = ad 이름 (동일)**.
- **확정 형식 (9/18 IH 캠페인 실물 확인)**: `{YYMMDD}_{제품}_{테마}`
  - 예: `260911_PPSU_回転ハンドル` · `260911_stainless_話題のマグ` · `260910_stainless_理想のマグ` · `260918_モニター募集`(제품 없는 예외=모집)
  - 제품 토큰 = `PPSU` / `stainless` (소문자). 테마 = 영상 제목의 핵심(날짜접두 뺀 부분).
- 예산 = **₩8,000/day · LANDING_PAGE_VIEWS** (WL Testing과 동일).
- **앞으로는 세은이 영상 제목에 제품도 같이 붙여줌** → 제품 추측 매핑 불필요, 제목 표기 그대로 사용. (현재 폴더 영상들은 아직 제품 미포함 → 이 배치는 세은에게 제품 확인 필요.)

## IH 광고 생성 레시피 (2026-09-18 실측·생성 성공)
자사 게시물(REELS) → IH 광고. WL과 달리 **branded content sponsor 없음**. 기존 IH 크리에이티브 해부로 확정:
1. **자사 미디어 id** = `GET /{GROS_IG}/media?fields=id,permalink` 에서 permalink에 shortcode 매칭(예 DdTREOfSPmw=`17987326458061157`).
2. **FB 복사본**(REELS 필수) = `POST /act/advideos {source_instagram_media_id:<media>}` (SYS 토큰).
3. **크리에이티브**(LIVE 토큰) = `POST /act/adcreatives {source_instagram_media_id, instagram_user_id:GROS_IG(=자사, sponsor 없음), call_to_action:{LEARN_MORE, link:제품LP}, url_tags:utm_campaign=IHV_Grosmimi&utm_content=제품_테마, degrees_of_freedom_spec, contextual_multi_ads:OPT_IN}`.
   - ⚠️ `standard_enhancements` DOF는 Meta 거부(subcode 3858504·deprecated) → **제외**. 나머지 text_optimizations/video_auto_crop/video_filtering/video_uncrop 4종 OPT_IN.
4. **ad set**(LIVE) = campaign_id=IH · daily_budget=8000 · IMPRESSIONS · LANDING_PAGE_VIEWS · LOWEST_COST_WITHOUT_CAP · targeting(JP 18~65·advantage_audience:1·brand_safety RELAXED) · **status=ACTIVE**(세은 in-session 지시분).
5. **ad**(LIVE) = adset_id + creative{creative_id} + status=ACTIVE. 생성 직후 effective=IN_PROCESS(심사중 정상).
- 생성 스크립트 정본 = `.tmp/ih_create_0918.py` (단계 로깅 + adset 실패 시 고아 크리에이티브 DELETE).
- PPSU 기본컵 LP = `item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_strawcup300/`.
- 첫 생성(9/18): DdTREOfSPmw → `260915_PPSU_韓国製ストローマグ` (ad 120250958068310223 · adset 120250958067280223).

## IH 캠페인 실물 (2026-09-18)
- 캠페인 = `Rakuten_IH_PPSU&Stainless_Testing` (id `120250841109750223`, ACTIVE).
- 현재 ad set/ad 11쌍 (260910~260918). 대부분 260911 배치(PPSU 6 + stainless 3) + 260910 stainless + 260918 モニター募集(예산 ₩20,000).
- Drive 영상 5개(전부 0915, 자체제작): `話題のマグ` / `韓国製ストローマグ` / `デザイン１` / `オススメマグ` / `グロミミ開要`(概要 오타 추정). ⚠️ `話題のマグ`는 이미 `260911_stainless_話題のマグ`로 존재 → 중복/재편집본 여부 확인 필요.

관련: [[reference_metamong_app_5tab_ih_dashboard]] · [[reference_meta_wl_branded_ad_api_creation]] · [[feedback_wl_ad_create_then_on]]
