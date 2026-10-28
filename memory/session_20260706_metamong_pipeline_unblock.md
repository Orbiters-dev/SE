---
name: session-20260706-metamong-pipeline-unblock
description: 메타몽 — 콘텐츠→메타 Testing 자동세팅 명명 블로커(WL-G/P·ASIN) 해소경로 7/3 tabs.read 게이트로 확정 + 원기 요청 완료
metadata:
  node_type: memory
  type: project
---

2026-07-06 메타몽 세션 (강한 교정 0건, 협업 진단):

**주제:** 콘텐츠 자동 메타 세팅 파이프라인에서 광고 제목(AdName 7토큰) 중 자동 파악 불가였던 2필드 해소경로 확정.

- **못 뽑던 2토큰 = 토큰4 WL-G/P(gifted/paid) + 토큰6 제품(ASIN).** 나머지 5토큰(날짜·브랜드·채널·핸들·CT코드)은 content_posts+고정값으로 이미 자동.
- **7/1 stale 판단 교정:** 무거운 `code:edit:datakeeper:*`(cap #7) 불필요. **7/3 신설 `tabs.read` 위임 게이트**(`_TAB_DELEGATION_ALLOWLIST=frozenset({"report/partner-content"})`)로 그 탭만 읽기전용 열면 됨.
- **실측:** SE토큰(`DK_SE_READ_TOKEN`) partner-content 호출 → **403 "admin tier or tab access required"** (권한 미부여 확인). MCP `code:read:datakeeper`는 6테이블 allowlist뿐(`partner_content_classification`=unknown table)이라 별개.
- **데이터 흐름 확정:** gifted/paid+WL코드 = 세은이 `/report/partner-content` 미니 스프레드시트 수동등록 → `PartnerContentClassification`(CT-키). 제품 = pin된 오더의 발송상품 SKU → `ProductSSOT-TEST_0612_임시Filled.xlsx`(Amazon SKU·SKU88 열)로 SKU→ASIN.
- **원기 요청 완료(7/6, ETA ~7/7):** ① list·export serializer에 발송상품 SKU 노출 ② SE키에 `tabs.read:["report/partner-content"]` 위임. 원기 기능 수정 중, 내일 반영 예정.
- **내일 첫 액션:** list 열리면 pin된 오더가 어느 SKU(Amazon/SKU88/KR)를 실어주는지부터 확인 → 조인키 확정 → 제목 7토큰 dry-run.

상세: [[project_meta_content_intelligence_loop]] · [[reference_adname_framework_v1]]
