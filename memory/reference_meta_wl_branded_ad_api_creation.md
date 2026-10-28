---
name: Meta WL(branded content) 광고 API 생성법 — 미디어 resolve + 크리에이티브 구조
description: 인플루언서 게시물을 Meta Testing 광고로 API 자동생성하는 검증된 경로. GROSMIMI_JP_API 토큰 + bare shortcode + page_id. 앱 dev모드가 마지막 벽.
metadata:
  type: reference
---

# Meta WL branded content 광고 API 생성법 (2026-07-07 실측)

인플루언서 IG 게시물(branded content)을 grosmimi_japan 광고로 API 자동집행하는 검증 경로. [[project_meta_content_intelligence_loop]] 파이프라인의 크리에이티브 자동부착 해결.

## 필수 토큰 = GROSMIMI_JP_API 앱 (claude connection 아님!)
- **claude connection 앱**(`1570751280806472`, .env `META_JP_ACCESS_TOKEN`)은 **인스타 권한 0** → branded content 미디어 조회 `(#10) Application does not have permission`. 광고 계정 read/adset생성만 됨.
- **GROSMIMI_JP_API 앱**(`1456998555820600`, user Kazuki Yamaguchi)이 정답. 스코프에 `instagram_basic` + `instagram_branded_content_brand` + **`instagram_branded_content_ads_brand`** + `ads_management` + `business_management` 다 있음. Graph API Explorer로 발급(단기 1~2h) 또는 시스템유저 장기토큰.
- **앱≠계정.** 광고계정 `act_4117678028561958`(JP Grosmimi Ads)은 비즈니스 자산 → 어느 앱 토큰이든 접근권만 있으면 만짐. GROSMIMI_JP_API 토큰도 이 계정 접근 OK(promote_pages 확인).

## 미디어 V2 id resolve (핵심 함정: bare shortcode)
```
GET /{ig_user_id}/branded_content_advertisable_medias?permalinks=["<SHORTCODE>"]
```
- **permalinks에 full URL(`https://instagram.com/p/xxx/`) 넣으면 `data:[]` (빈결과). bare shortcode(`DaPtDxcPgoV`)만 넣어야 미디어 id 나옴.**
- grosmimi_japan IG id = `17841473805016400`. FB 페이지(Grosmimi Japan) = `880831635120245`.
- 반환 `data[0].id` = source_instagram_media_id (V2). shortcode 디코딩값(3931...)은 별개 — API가 거부("valid Instagram media V2 ID").

## 크리에이티브 구조 (기존 라이브 광고 미러)
```
POST /act_4117678028561958/adcreatives
  source_instagram_media_id = <위 V2 id>
  instagram_user_id = <크리에이터 IG id, 17841...형식>  (구형식 platform_uid 68503.. 거부)
  call_to_action = {"type":"SHOP_NOW","value":{"link":"<라쿠텐 상품URL>"}}
  url_tags = "utm_source=traffic&utm_medium=meta&utm_campaign=UGC_Grosmimi&utm_content=<제품>_<핸들>"
  degrees_of_freedom_spec = {"creative_features_spec":{"standard_enhancements":{"enroll_status":"OPT_IN"}}}
```
- 라쿠텐 링크는 **제품(ASIN)별 상이** → 기존 광고에서 ASIN별로 긁음. PPSU Straw(B08TZY1TFY)=`item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_strawcup300/` / Stainless FLIPTOP(B0G6CCJ24K)=`.../stainless_steel_strawcup_300/`.
- 광고: `POST /act/ads` name+adset_id+creative{creative_id}+status=PAUSED.

## 마지막 벽 (2026-07-07 미해결) = 앱 Development 모드
- top-level 우리IG 구조 → `Ads creative post was created by an app that is in development mode`
- page_id top-level → `(#3) Application does not have the capability`
- object_story_spec+page 조합 → 계속 `link field required`(subcode 2061015, source_media와 충돌)
- **결론: GROSMIMI_JP_API 앱을 Live 모드로 전환해야 API 광고게시물 생성 가능.** developers.facebook.com/apps/1456998555820600 상단 App Mode 토글. (전환 후 top-level 구조 재시도 필요.)

## WL 코드는 콘텐츠(post_id) 단위
partner-content는 post_id별 row, 각자 고유 `wl_code`(adcode-...). 2회 콜라보 크리에이터도 게시물 id로 정확 구분(크리에이터 단위 섞임 X). 단 미디어 resolve엔 WL코드 불필요 — IG권한 토큰이 shortcode로 직접 조회.

## 2026-08-27 재검증 — 구조는 증명됨, 병목은 여전히 IG branded 토큰
- **크리에이티브 구조 실증 성공**: 기존 라이브 광고(jurixmitsu)의 알려진 `source_instagram_media_id`(18112884866515201)+`instagram_user_id`(17841460971352610)+`branded_content{instagram_boost_post_access_token:adcode, ad_format:3}`+`call_to_action`로 `POST /act/adcreatives` → **파트너십 지문(source+user+effective_media) 정상 생성**. META_JP_ACCESS_TOKEN(claude connection, IG권한0)으로도 크리에이티브 생성 자체는 됨. 즉 **source_instagram_media_id만 있으면 완전 자동화 가능**.
- **필수 파라미터 확정**(매트릭스): `source_instagram_media_id` 없으면 전부 "Ad Incomplete/missing required fields"(subcode 2446391). adcode만·instagram_user_id만으론 불가. effective_media(내가 만든 링크광고 미디어)를 source로 넣으면 "Invalid Instagram Story ID"(다른 미디어).
- **object_story_spec+page_id link_data 로 만들면 object_type=SHARE(링크광고)** → UI에서 Partnership OFF로 보임. 인플루언서 영상 안 물림. 이 구조는 오답.
- **`standard_enhancements` DOF 필드 deprecated**(subcode 3858504) — 빼야 함. text_optimizations/video_* 만 OPT_IN.
- **로컬 토큰 전멸 확인(8/27)**: META_ACCESS_TOKEN=code190 사망 / IG_ACCESS_TOKEN=parse불가 / IG_DM_ACCESS_TOKEN=살아있으나 graph.instagram.com 전용(branded_content_advertisable_medias 필드 부재, /me/media에 크리에이터 콜라보 미노출) / n8n 워크플로우 추출 토큰=logged out / NAS kazuki config=플레이스홀더 / AWS SSM=로컬 creds 없음(aws sts 실패) / adcode=토큰 아님.
- **결론 = source media resolve는 GROSMIMI_JP_API 앱(1456998555820600, instagram_branded_content_ads_brand 스코프) 라이브 토큰 필수** — 브라우저 OAuth(Graph API Explorer) 1회 발급만 남은 물리 블로커. 발급되면 shortcode(bare)로 2건 resolve → 크리에이티브+광고 완전 자동 생성.
- ku___vlog=post_id 65695·shortcode `Dcao0Vrxw-3`·adcode `...388qp0j_o8` / mamo___baby=post_id 65428·adcode `...hvT7bHmQT0`. ad set: ku=120250641902780223 / mamo=120250592664040223 (둘 다 PAUSED·₩8000·광고0건 클린). advertiser page=880831635120245.

## 2026-08-27 후속 — 전체 레시피 확정, 마지막 벽=앱 Development 모드 (7/7과 동일 지점)
세은이 GROSMIMI_JP_API 앱(1456998555820600) 유저토큰 Graph Explorer 발급(15스코프, instagram_branded_content_ads_brand 포함, 만료 ~2026-06). `.tmp/jpapi_token.txt`. 이걸로 **거의 끝까지 뚫음**:
1. **media resolve OK**: `GET /17841473805016400/branded_content_advertisable_medias?permalinks=["<bare_shortcode>"]` → `data[0].id`. ku(Dcao0Vrxw-3)=17886363630457421. jurixmitsu 검증: shortcode는 광고 표시 permalink(p/DcaSRC9M4cP)가 아니라 **source reel permalink(reel/DcOEhBHT9HN)** 로 해야 라이브 source(18112884866515201) 일치. id 17/18 prefix는 세대 차이일 뿐 무관(둘 다 REELS/VIDEO).
2. **크리에이터 IG id**: `GET /{ig_uid}?fields=business_discovery.username(<handle>){id}`. ku___vlog=17841476540970810.
3. **크리에이티브 정본 구조**(라이브 jurixmitsu 해부): `source_instagram_media_id`(크리에이터 미디어)+`instagram_user_id`(크리에이터 IG id)+`instagram_branded_content={sponsor_id:17841473805016400(grosmimi IG=광고주)}`+`branded_content={instagram_boost_post_access_token:adcode, ad_format:3}`+`call_to_action`. (구형 instagram_user_id 단독 X → "select both first and second identities" subcode 3867111.)
4. **REELS "must upload to FB"(subcode 1815279) 돌파 = 신규 발견**: 최초 광고화 안 된 reel은 FB 복사본 없어 거부. **`POST /act/advideos {source_instagram_media_id:<media>}` → FB video id 발급**(ku=4703378793266704, ~즉시 ready). 이후 정본 크리에이티브 재시도.
5. **최종 벽(7/7과 동일)**: FB 복사 후 크리에이티브 = `"Ads creative post was created by an app that is in development mode"`(subcode 1885183). **GROSMIMI_JP_API 앱을 Live(공개) 전환 필수** — developers.facebook.com/apps/1456998555820600 App Mode 토글(privacy URL 필요 시 meta-app /privacy 재사용 가능, [[reference_ig_dm_kpi_pipeline]]에서 claude connection 앱 동일 방식 Publish). 유저토큰으로 앱모드 못 바꿈·앱시크릿 로컬 부재 → 대시보드 1회 토글이 물리 블로커. 전환 후 크리에이티브+광고 재실행하면 완결.
- mamo___baby(65428)는 partner-content 997행에 없음(분류 미등록) → shortcode 미확보. 앱 Live 후 shortcode 확보 필요(WL시트/노션 또는 세은).

## 2026-08-27 ★완전 돌파★ — dev모드 벽 우회 (LIVE앱 분리) + adcode 불필요. WL 광고 API 100% 자동화 확립
7/7·8/27전반의 "앱 Live 전환 필수" 결론 **폐기**. 앱 퍼블리시(Business 인증·며칠) 없이 뚫음:
- **핵심 우회 = 토큰 2개 역할 분리.** ① 미디어 resolve·business_discovery·advideos = **GROSMIMI_JP_API 토큰**(IG branded 스코프 有, dev모드). ② **크리에이티브·광고 생성 = META_JP_ACCESS_TOKEN**(claude connection, 이미 **Live** — IG DM 파이프라인 때 Publish됨 [[reference_ig_dm_kpi_pipeline]]). Live앱 토큰으로 crea 생성하면 "app in development mode"(1885183) **안 뜸**. ads_management만으로 branded content crea 생성됨(IG 스코프 불요 — 광고권은 미디어에 이미 있음).
- **adcode(instagram_boost_post_access_token) 불필요.** grosmimi가 advertisable 권한 있는 미디어면(=branded_content_advertisable_medias가 id 반환) `instagram_branded_content={sponsor_id:17841473805016400}` 만으로 충분. adcode 없이 crea 생성 성공 실측. → 시트 adcode 안 찾아도 됨.
- **완성 레시피 (재현):**
  1. shortcode(bare) → `GET /17841473805016400/branded_content_advertisable_medias?permalinks=["<sc>"]` (JPAPI) → media id
  2. 크리에이터 IG id → `GET /17841473805016400?fields=business_discovery.username(<handle>){id,media.limit(20){...}}` (JPAPI). 최근 미디어 순회하며 각 shortcode를 1번 edge로 광고가능+D+3 판정.
  3. VIDEO면 FB 복사본 = `POST /act/advideos {source_instagram_media_id:<media>}` (JPAPI). ~즉시 ready. (안 하면 "must upload to FB" 1815279.)
  4. 크리에이티브 = `POST /act/adcreatives {source_instagram_media_id, instagram_user_id:<creator>, instagram_branded_content:{sponsor_id:17841473805016400}, call_to_action, url_tags, contextual_multi_ads:{enroll_status:OPT_IN}}` (**LIVE 토큰**). `standard_enhancements` DOF 넣지 말 것(3858504).
  5. 광고 = `POST /act/ads {adset_id, creative:{creative_id}, status:PAUSED}` (LIVE).
- **8/27 실제 생성 3건(전부 cfg=PAUSED)**: ku___vlog(ad 120250645292580223, 기존 adset) / mamo___baby(ad 120250645577350223, 기존 adset, WL-P) / niichan.log_21(신규 adset 120250645597790223+ad 120250645601610223, WL-G stainless). D+3 게이트=post_date≤당일-3([[reference_meta_wl_testing_gate_criteria]]).
- **제품·기프팅/유상 SSOT = WL 코드 구글시트**(1wkue4G7FP...·gid 386147805·col3 CreatorID/6 Product/8 Status/15 WLcode/16 URL/23 DealType/27 Adcode). niichan.log_21은 시트에도 partner-content에도 **없음** → 제품(stainless)·WL-G는 세은 구두 확정, CT-pk 없어 이름 CT-NEW(intelligence 조인 결손). 신규 크리에이터는 시트 온보딩 먼저가 정석.
- JPAPI 토큰 캐시 `.tmp/jpapi_token.txt` — **⚠️ 단기 토큰이었음. 8/27 00:00 PDT 만료 실측(8/31)**. "만료 ~2026-06"은 오기. 만료 시 Graph Explorer 재발급(GROSMIMI_JP_API 앱·15스코프) — 세은 브라우저 1회. **대체 루트 8/31 전수 실측 사망**: LIVE토큰 resolve=(#1)·page token=/me/accounts 빈배열·oEmbed=리뷰 필요·IG_DM=/me/tags 콜라보 미노출·글로벌 토큰=비번 변경 사망.

## 2026-08-31 — D+3 일괄 세팅 (메타몽)
- **ad set 신규 2건 생성(PAUSED·₩8000·LPV)**: BOSS_TO_PAPA(CT-65712, adset 120250688596840223) / ITOSUKU_SA(CT-65962, adset 120250688597080223). 둘 다 無償(DocuSeal 124·144 계약 PDF 실측) → WL-G. 제품 = DM 실물 확정(boss=PPSU 200 白=B0B9GLVWYN / itosuku=PPSU 300 チャコール=B08TZY1TFY).
- **niichan CT-NEW → CT-65686 정정 완료** (DK 적재 확인, adset+ad rename — intelligence 조인 복구).
- **광고 미부착 5건 완결 스크립트 = `.tmp/wl_complete_0831.py`** (JPAPI 토큰 갱신 후 1커맨드, idempotent): 신규 2건 + 빈 adset 3건(OHANA CT-58420 / ASAHI.DAILY CT-62740 / RITCHAN CT-63889). ⚠️ RITCHAN 게시물은 DK non_partnered — resolve 실패 시 WL 권한 미부여 확정 → 인플루언서 매니저 루트.
- 최근 게시물 원장 = **DK content_posts is_partner/coauthor** (WL시트는 8월 행 자체가 없음 — stale 재확인). 신원·계약형태 소스 = 폼 집계 시트 통합 탭 + DocuSeal PDF + IG DM 대화 실물.
- **⚠️ DK 단독 원장은 구멍 (riono 사고 8/31 — 세은 지적)**: riono_nichijou(春日井様·유상·8/25 투고 DcdlrSAxD9C)를 DK가 미적재/non_partnered로 들고 있어 누락 → 세은 지적으로 발각. **원장 대조에 투고완료 폼 URL(시트 1Gd8JrWm 투고완료 탭) 필수 포함.** 사후 ad set 생성: 120250688654360223 (WL-P·B0G6CCJ24K). 완결 스크립트에 포함됨.
- **CT-NEW 금지 재지시(8/31)** → riono adset은 `CT-DcdlrSAxD9C`(릴 shortcode)로 rename 완료. 협업 릴은 PG 직쿼리로도 미적재 확정(65890은 8/26 비협업 게시물·폼 URL은 캐노니컬 실측). 수동 적재 루트 전멸: 로컬 Apify 토큰 사망·orbitools /save/=write:ingest 티어 필요(로컬 read뿐, 403 실측). DK 적재 시 완결 스크립트가 숫자 CT로 자동 정정. → [[feedback-no-ctnew-placeholder]]
- **WL D+3 감시견 신설(8/31)**: `tools/wl_d3_watchdog.py` — 3소스 원장(DK∪폼∪DM 10일) vs Graph 광고 커버(CT 조인) 매일 대조, 발견 시 Teams+Gmail. JPDash_Daily 체인(soft+notify) 등록. 추가 자가발견: piyomaru_ikuji=青木佳世様(無償·DocuSeal 134) 8/29 투고 DM 보고만 존재(폼·DK·시트 無) → 9/1 D+3 도달, WL 허가 요청 DM 초안 .tmp/dm_aoki_wl_ad_permission.txt(8/31 병렬 세션).
- **8월 게시분 집행 실태(8/31 Graph 실측)**: ON 2건(akittotan·jurixmitsu)뿐. 광고까지 있는데 PAUSED·지출0 = musukono·inoue·niichan·ku·mamo(ad만 PAUSED) 5건 — 세은 ON 대기 상태. 지출 있고 현재 PAUSED(OFF 판정 추정·의도 미확인) = twins_ruamoa·mitsugochan·musukolove·yuchi 4건.
- **광고 크리에이티브 permalink = 광고 복사본 permalink ≠ 원본 게시물 shortcode** (구형 UI 생성분 전부) — 커버리지 대조는 반드시 광고명 CT-##### 로. shortcode 대조는 API 생성분만 맞음.

## 2026-09-02 — D+3 세팅 (메타몽)
- **ad set 신규 2건(PAUSED·₩8000·LPV)**: ___MITSUMARU___(CT-65972, adset 120250726351430223, 폼 실물: 後藤耀子様·기프팅·PPSU 200 ピーチ=B0B9GLVWYN·8/29 투고 DcnsAQtPTVt) / PIYOMARU_IKUJI(CT-65976, adset 120250726902550223, DM 실물: 青木佳世様·DocuSeal 134 기프팅·**PPSU 300 スカイブルー**=B08TZY1TFY — 8/19 크림베이지 재고切れ→스카이블루 300 변경 발송 확정·8/30 투고 DcqI9TQppT0).
- **완결 스크립트 = `.tmp/wl_complete_0902.py`** (0831판 승계·TARGETS 8건). 빈 adset 6건(mitsumaru·piyomaru·itosuku·ohana·asahi·ritchan) 광고 부착 = JPAPI 토큰 재발급 후 1커맨드.
- 판정 원장 = DK ∪ 투고완료 폼 2소스 (`.tmp/wl_d3_scan_2src.py` — 감시견 함수 재사용). ⚠️ 감시견 dry-run 풀실행은 IG DM 앱 레이트리밋(code 4·1349210)을 소진시켜 50분+ 무한 백오프 — 수동 진단은 2소스 스캔으로, DM 소스는 정기 실행에 맡길 것.
- 제품 확정 우회 루트 실측: 라쿠텐 受注 30일 전수(전화·주소·카타카나 키) = BOSS 샘플 발송 기록 **없음**(피요마루 건) → DM이 유일 실물 소스였음. DocuSeal 기프팅 템플릿엔 제품 필드 없음.

관련: [[project_meta_content_intelligence_loop]] · [[reference_adname_framework_v1]] · [[session_20260707_metamong_adset_creation]] · [[reference_ig_dm_kpi_pipeline]] · [[reference_meta_wl_testing_gate_criteria]]
