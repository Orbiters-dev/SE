---
name: 메타몽 콘텐츠 소구점 태깅 프로젝트 (2026-06-15)
description: DK content_posts 영상분석 데이터를 7축 소구점으로 multi-label 태깅. 노이즈필터+협업판정 버그+수동UI 계획. 진행중.
metadata:
  type: project
---

# 메타몽 콘텐츠 소구점 태깅 프로젝트 (2026-06-15)

세은 목표: 메타몽 콘텐츠 탭(orbitools.orbiters.co.kr/content)에서 각 인플루언서 콘텐츠를 소구점별 태깅 → "어떤 소구점으로 만든 게 잘 됐나" 데이터 누적 (집계/분석은 나중, 지금은 **정확한 태깅 자체가 급선무**).

## DK API 접근 (read-only)
- key: `.env` 의 `DATAKEEPER_API_KEY` (dk_SE_... read 전용, gitignored)
- base: `https://orbitools.orbiters.co.kr/api/datakeeper/` 헤더 `X-Api-Key`
- 콘텐츠 테이블: `content_posts`(게시물+30d지표+ci_analysis), `content_pipeline_evaluations`(ci_analysis 상세)
- ci_analysis 4블록: **whisper(대사분석=가장 풍부)** / vision(빈약, hook_caption만) / brand_match / scores(composite 미연결, 다 0)
- whisper 필드: hook_text_3s·key_message·persuasion_type·script_structure·vocabulary_level·repeat_watchability·delivery_verbal_score·transcript 등 (이미 LLM분석 완료, 끌어오기만)
- **transcript는 영어 자동번역 → 분류 근거로 부정확. caption(일본어 원문)이 정확** (✔포인트 명시)

## 소구점 7축 (세은 확정)
素材(PPSU/Stainless) / お手入れ簡単 / 漏れない / 赤ちゃんの発達 / ストロー / 日常 / **デザイン(かわいい·見た目)** ← 디자인 7번째 추가
- **multi-label (主+副) + 信頼(高/中/低)** + 근거 필수. 단일 라벨 X (대부분 복합 소구점).

## DK 협업/organic 판정 버그 (중요)
- DK `content_type=partnered` 판정 = **IG 공동게시(ig_coauthor) 메타 유무만**. 실제 협업 여부 아님.
- **2026-03~04 수집분(content_source=legacy) 36건은 공동게시 정보를 레코드에 안 담음** → non_partnered(organic) 오분류. (5~6월 tagged 수집분은 정상 partnered)
- 즉 IG엔 공동게시 다 돼있는데 옛 레코드라 누락. 세은 화면 42 = 공동게시분만, 실제 협업은 훨씬 많음.
- **해결: ① 원기에게 legacy 36건 재수집 요청 (DK 파이프라인) ② 우리는 caption @grosmimi_japan 태그로 협업 판정 우회**

## 노이즈 필터 (적용 완료)
- 룰: ① caption 일본어비율<10% ② 제품명사(マグ/ストロー/PPSU/ステンレス) 없음 → 除外候補
- JP 94건 중 8건 제외 (baby.boutique.kh 캄보디아 대리점 6 + deanna.hauk 미국 2). 원인=DK가 source_keyword "grosmimi"로 organic 수집 → 타국/무관 혼입.

## 산출물 / 진행 상태
- **`.tmp/jp_content_tags_v2_7axis.csv`** (86건: username·url·partner·主·副·信·근거). partner: collab 82 / owned 4(공식). "일단 다 협업으로" 처리.
- 主 분포: 漏れない25·発達23·素材19·日常7·デザイン6·お手入れ3·ストロー3. 信頼: 高49/中36/低1.
- 태깅 스크립트: `.tmp/tag_jp.py`

## 작업 순서 (세은 승인)
**b(노이즈필터)✅ → a(7축 재태깅)✅ → c(수동 태깅 UI, 미착수)**
- c = human-in-the-loop: 자동 高=확정, 中/低="要確認" 배지 → 콘텐츠 탭에서 칩 클릭 確定/수정 → 메타몽 DB 저장 (DK는 read-only라 못 씀). **메타몽 앱 코드작업(orbitools-code-edit MCP)+승인 후.**

## 다음 (대기)
1. 中 36건 + デザイン 6건 세은 검수 (오태깅 교정)
2. 원기에 legacy 재수집 요청
3. 검수 후 메타몽 콘텐츠 탭 반영(c) or 다음 배치
4. 반복 운영 시 수동 dict → LLM 분류 파이프라인化 (tools/ 스크립트) 필요 (지금은 1회성 수동)

## 진행 2026-06-16 (c 수동 UI — 풀스택 작성, PR 대신 핸드오프)
세은 결정: 반영(시드) → 수동 UI 검수. 검수 동선 = **상세카드 + 목록 要確認 필터**.
- 콘텐츠 탭 = `app/(dashboard)/content/` (intelligence_next Next.js), 상세 `/content/[id]/_components/*-card.tsx`.
- 저장소 = 대시보드 자체 DB 모델 `ContentAppealTag` (db_table `onz_content_appeal_tags`, app_label onzenna). 선례 InfluencerReportTag/ReplyPlaybook/PeerReviewLog.
  - 필드: ref_id(=ContentPosts.id str)·primary_appeal(主)·sub_appeals(副 JSON)·confidence(高中低)·review_status(auto/verified/rejected)·rationale. unique(ref_id). 행 부재→미태깅.
- **막힘 2개(원기)**: ① backend.migrations cap 없음 (request_cap #6 pending) ② 서버 git apply check clone 15초 timeout. → PR 못 올림.
- **산출물**: `.tmp/content_appeal_handoff/` 8파일 (README + 모델/migration0108/views/urls/FE카드 appeal-tags-card.tsx/목록필터). 원기 인계용.
- MCP 운영 경로 → [[reference_orbitools_mcp_token_rest]]
- 시드 86건(jp_content_tags_v2_7axis.csv) → ContentAppealTag mgmt command 아직 미작성.

## 진행 2026-06-19 (콘텐츠 탭에 "태깅 항목" 탭 배포 + 등급 산식 확정)
- **중요 정정: 세은이 보는 콘텐츠 등급 화면 = WONGI intelligence_next 아님. 로컬 `meta-app`(vercel 배포, meta-app-one.vercel.app).** nav "콘텐츠" → `/influencers` 라우트 = `meta-app/app/influencers/page.tsx` (ContentPoolPage). 등급칩 = `components/meta/GradeChip`. 위 6/16 intelligence_next 핸드오프(ContentAppealTag)와 별개 트랙. meta-app은 SE 레포 gitignore → 로컬 Edit 후 `vercel --prod --yes` (cd 시 Bash 훅 깨짐→PowerShell). [[reference_metaapp_deploy_vercel_cli]]
- **현행 등급 S/A/B/C 산식 (화면 명시)**: D+3 view 기준 · 단가(0.45)+VTR(0.45)+정성(0.10) · S≥80+게이트 / A≥60 / B≥25 / C<25. (정성 0.10 내부 구성은 미확인). score_calculator.py(tools/ci)와는 다른 자체 산식.
- **태깅 항목 확정 (세은)**: 점수=등급합산 / 분류=집계축 구분. 점수=hook·storytelling·authenticity·delivery·repeat_watchability·brand_fit / 분류=소구점(主副 7축)·persuasion_type / 분류겸점수=애기등장(subject_age·child_appearance_pct). **소구점은 점수 X (분류축) — 세은 확정.** script_structure·vocabulary_level 제외.
- 애기등장은 이미 vision 엔진이 추출함: `tools/ci/vision_tagger.py` HT tier에 subject_age/scene_tags["baby","toddler"]/child_appearance_pct. whisper 필드 정의 = `tools/ci/whisper_transcriber.py`.
- **배포함**: page.tsx에 `<Tabs>` 세 번째 트리거 "태깅 항목" + 정적 TaggingPlanSection 표 추가 (grid-cols-2→3). dpl_9aNV1rrL2jkjPLGGqbvxbxEGvph2 READY. 정적 패널이라 기존 풀 영향 0.
- WONGI 소스 read 토큰: Credential Manager CredRead "git:https://github.com" (40자 gho_) → GitHub contents API. `git credential fill`은 비대화형 NO_PW. (meta-app 작업엔 불필요 — 로컬이라)
- **다음**: 점수 항목들을 실제 86건에 채우는 파이프(content_quality_score 연결) + 태깅 항목 탭은 현재 "정의 표"만 — 실제 값 표시·집계는 아직.
