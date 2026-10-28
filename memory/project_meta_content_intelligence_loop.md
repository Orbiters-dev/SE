---
name: Meta Testing 자동화 ↔ onzenna intelligence 콘텐츠 루프 (2026-07-01 착수)
description: 신규 IG 게시물 → Meta Testing 자동집행 → 성과 → 콘텐츠 유형 분석으로 닫는 루프. 절반(CT-pk 조인·MetaAdExecution·matched_groups)은 orbitools에 이미 존재. 신규 2개만 구축.
metadata:
  type: project
---

# Meta Testing 자동화 ↔ onzenna intelligence 콘텐츠 루프 (2026-07-01 착수)

세은 지시: 우리 IG에 올라오는 모든 게시물을 일단 Meta Testing(₩8,000 ACTIVE)으로 돌려 데이터로 판별(사람 눈 X) → 좋으면 Proven 승급 / 아니면 Off. **이 작업이 onzenna intelligence(orbitools.orbiters.co.kr) 콘텐츠 파이프라인과 연결**되어야 하고, 인플루언서/콘텐츠 특징 태깅을 콘텐츠별 특징 분석에 연결해 **유형화**.

## 닫힌 루프 (CT-`<pk>`가 양방향 조인키)
```
콘텐츠 파이프라인(ADR-036 scrape→AI분석→export) → gk_content_posts (신규 + matched_groups 유형chip)
  → [신규①] partnered/owned 신규 row → Meta Testing ad set+ad 생성 (ad명에 CT-<pk>, ₩8,000 ACTIVE)
  → Meta 집행(LPV/CTR/CPC)
  → [기존§23, 타이머OFF] MetaAdExecution sync (CT-<pk> 역매칭, 성과 회수)
  → [신규②] intelligence: matched_groups(유형) × 성과 조인 → "어떤 유형이 잘 되나" → Proven/Off + 기획 피드백
```

## 실측 검증 (2026-07-01, orbitools-code-edit MCP)
- **조인키 100% 일치(라이브)**: content_posts id=57350 nee_and_twins ↔ ad CT-57350 / 57349 rii_mama_ikuji / 57352 arara_norarara / 34815 komugiko_126. **CT번호 = content_posts 정수 PK.**
- **이미 있는 것**: ① 콘텐츠 파이프라인이 신규 게시물 자동 적재(별도 IG폴링 불요) ② Keyword Groups v3 = `ContentPosts.matched_groups`[{name,label,kind}], kind=brand/topic/competitor/trend/**custom** (키워드 마스터 UI로 편집, 유형태깅 인프라) [[09 §2b]] ③ §23 `MetaAdExecution`(gk_meta_ad_execution) = ad명 CT-pk 매칭→첫집행일·impr·spend·신호등. `sync_meta_ad_execution` 타이머(06:15 UTC) **비활성(활성=운영자 승인)**.
- **없는 것 = 신규 2개**: ① 신규 게시물→Testing 광고 자동생성기 ② 유형×성과 조인 분석면(intelligence). 내 cap에 `code:edit:dashboard:intelligence.*` 있음.

## 자동생성 피드 (신규①)
- 대상 = `content_posts WHERE content_type='partnered' AND brand='grosmimi' AND region='jp' AND MetaAdExecution 없음`. ⚠️ 경쟁사 PR(ピジョン/リッチェル/bbox/アラウ, brand="")는 제외 — brand='grosmimi' 필수.
- 명명 = `Y26M{MM}D{DD}_Grosmimi_RKT_WL-{P/G}_{핸들}_{ASIN}_CT-{pk}` (라이브 템플릿). ad set: daily ₩8,000·goal LANDING_PAGE_VIEWS·billing IMPRESSIONS·bid LOWEST_COST_WITHOUT_CAP·1소재=1adset·캠페인 `Rakuten_WL_PPSU&Stainless_Testing_2026`(ABO). creative=use-existing-post(object_story_id/source_instagram_media_id).
- 토큰 META_JP_ACCESS_TOKEN = ads_management 쓰기 O.

## 세은 결정 (2026-07-01)
- 대상 = **앞으로 올라오는 것만(룰/도구)**, 40개 legacy 일괄생성 X. 상태 = **ACTIVE 즉시, 각 ₩8,000**. 생성범위 = **ad까지 전부 자동(WL 포함)** — 단 세은이 WL **파트너십 코드(branded content) 접근 경로** 제공 예정(블로커).
- 유형 택소노미 축 = **훅/도입3초 · 소구점/메시지 · 영상포맷/구성**. **세은이 유형화 작업 따로 해서 자료 전달 예정** (메타몽이 만들지 말 것).

## 접근 확인 (2026-07-01) — WL코드 읽기 권한 블로커
- wl_code·sponsorship_type = `gk_partner_content_classification`(orbitools), 제품=`gk_docuseal_contract`. **셋 다 DK 게이트웨이 미등록** → SE read토큰으로 못 읽음(basic 401 / bearer 403 "admin tier or tab access required" / /query unknown_table, 3경로 확인). 엔드포인트 `/api/datakeeper/admin/partner-content/list/` 존재하나 SE 토큰=read-tier라 403. SE 토큰=`DK_SE_READ_TOKEN`. 대시보드 계정 `ORBITOOLS_DASHBOARD_ID/PW`(basic 미수용, 세션로그인 엔드포인트 tools에 없음).
- **해소책 = request_cap #7 `code:edit:datakeeper:*` (2026-07-01 pending, 원기 승인 대기, expires 7/8)**. 승인 시: register.py에 wl_code·sponsorship_type 비-PII 노출 → SE가 dk_query_table로 읽기 → 커넥터 완성. (대안: 원기가 SE토큰에 partner-content 탭/admin tier 부여)
- dry-run 1차(권한 전): grosmimi·partnered·jp 미집행 **22건 superset**(라이브 CT 17개 제외). 명명 채워진필드=날짜·핸들(username)·CT-pk. 대기필드=WL-P/G(sponsorship_type)·ASIN(제품→SSOT)·wl_code. 실제대상=wl_code 있는 것만(22보다 적음).

## 진행 (착수)
1. 메타몽 즉시: 자동생성기 **dry-run(피드+명명 리스트, 실생성·creative X)** 부터. → 파트너십 코드 경로 받으면 "실제 생성" 부착.
2. 콘텐츠↔성과 연결 스위치(§23 타이머 ON) = orbitools 운영변경 → 세은 "켜" 승인 시.
3. 유형 태깅(kind=custom 그룹) = 세은 자료 수령 후.

## 명명 블로커 해소경로 확정 (2026-07-06) — cap #7 대체
7/1 요청한 무거운 `code:edit:datakeeper:*`(cap #7) **불필요**. 7/3 신설 게이트로 훨씬 가볍게 뚫림:
- **토큰4 WL-G/P (gifted/paid) + WL코드**: 세은이 `/report/partner-content` 미니 스프레드시트(`content_url`+`wl_code`+`sponsorship_type`+WL기간)에 **수동 등록** → `PartnerContentClassification.sponsorship_type`(`gk_partner_content_classification`, CT-키 1:1). Claude는 `admin/partner-content/list|export`로 읽음.
- **토큰6 ASIN**: `ProductSSOT-TEST_0612_임시Filled.xlsx`(`s\パポマ\META ADS 관리용\`)에 `(Parent/Child)ASIN`+`Amazon SKU`+`Shopify SKU88` 완비 → **SKU→ASIN 확정**. 콘텐츠별 제품 = partner-content에서 pin된 오더의 **발송상품 SKU**로 물림(별도 수기 X).
- **읽기 권한 = 2026-07-03 `tabs.read` 위임.** `_TAB_DELEGATION_ALLOWLIST=frozenset({"report/partner-content"})`(`views/admin/__init__.py`). SE키(`DK_SE_READ_TOKEN`)에 `admin/api_keys/<id>/update/`로 `tabs.read:["report/partner-content"]` 부여. **실측(7/6): 현재 SE토큰 partner-content 호출 403 "admin tier or tab access required"** — 권한 미부여 상태 확인. MCP `code:read:datakeeper`는 6테이블 allowlist뿐(partner_content_classification=unknown table)이라 별개.

## 원기 요청 완료 (2026-07-06, ETA ~7/7)
세은이 원기에게 2건 전달, **기능 수정 중, 내일쯤 반영 예정**:
1. `report/partner-content` list·export serializer에 **발송상품 SKU** 필드 노출 추가 (코드변경).
2. SE키에 **`tabs.read:["report/partner-content"]`** 위임 (읽기전용·그 탭만).
→ 반영되면 Claude가 list 긁어 gifted/paid·WL코드·SKU→ASIN 검증 후 제목 7토큰 전자동 확정 → 자동생성기 dry-run 붙임.

## 자체해소 (2026-07-07) — partner-content 읽기는 CRM토큰으로 이미 뚫림 (원기 대기 불필요)
7/6 "SE read토큰 403 → 원기 tabs.read 위임 대기" 결론은 **부분 오판**. `DK_SE_CRM_TOKEN`(dk_SE_bd10...) Bearer 로 `admin/partner-content/list/` **200 통과** (read토큰 dk_SE_240e...만 403). → sponsorship_type·wl_code·content_advertisable·content_ad_crosscheck·wl_code_status 전부 읽힘. **읽기 블로커 해소, 원기 안 기다려도 됨.**
- **content_advertisable = Meta `branded_content_advertisable_medias` 실권한** (09 §20.17, WL코드/핸들 무관, shortcode 직접조회 삼상태 T/F/None, 양쪽 광고주계정 병합). **이게 광고집행 가능 여부의 SoT.** verdict(agree_advertisable/conflict_code_dead/opportunity)=content True계열 → 광고가능 / agree_denied=content False → 불가 / content_unverified=None.
- **여전히 막힌 것 (7/7)**: ① 크리에이티브 `source_instagram_media_id` resolve = grosmimi_japan IG(`17841473805016400`)에 branded_content_advertisable_medias 조회 필요 → **JP토큰 IG권한X(code1) / 글로벌 META_ACCESS_TOKEN 죽음(code190) / AWS SSM creds 로컬X / 레포에 WL토큰 없음.** WL토큰은 서버 SSM `/orbiters/meta_jp_wl/access_token`. → 광고 실물 생성은 이거 없이는 불가(과거처럼 Ads Manager UI 수동). ② ASIN(발송SKU) 필드 원기 미노출. ③ opportunity건 sponsorship_type 미등록(gifted/paid 미정).
- 7/7 시점 신규 advertisable(True)+미집행 = minkoro_kosodate(62157, opportunity) · an_3mama_baby(61550, conflict_code_dead). Testing 캠페 id=120248267687980223, ad set 클론템플릿=₩8000/IMPRESSIONS/LANDING_PAGE_VIEWS/LOWEST_COST_WITHOUT_CAP/JP18-65/advantage_audience.

관련: [[project_meta_jp_testing_split]] · [[reference_meta_wl_testing_gate_criteria]] · [[reference_meta_lpv_ceiling]] · [[feedback_self_reliance_exhaust_own_paths]]
