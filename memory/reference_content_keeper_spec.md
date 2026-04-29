---
name: Content Keeper 파이프라인 데이터 스펙
description: gk_content_posts 테이블·관련 테이블·API·slim 모드 주의사항. 다운스트림 데이터 소비 세션의 진입점
type: reference
---

원본 파이프라인: `/Users/wongi/Desktop/DEV/WONGI/COMP/pipeline/` (WJ 로컬, 원기 관리)
프로덕션 EC2: `https://orbitools.orbiters.co.kr/api/datakeeper/...`

## 주 테이블: `gk_content_posts`
Django 모델: `datakeeper.domains.content.models.ContentPosts` (post_id unique)

핵심 필드 그룹:
- 식별: post_id, url, platform(ig/tiktok), username, region(us/jp), content_source, post_date, pipeline_version=v2, creator_id
- 성과: videos_30d / views_30d / likes_30d / comments_30d / followers / engagement_rate / virality_coeff
- 텍스트: caption(500자 trunc) / transcript / hashtags / hook_caption_spoken / hook_caption_visual / top_5_comments / source_keyword
- 분석(JSONField `ci_analysis`): emotional_tone, persuasion_type, key_message, script_structure, brand_match
- 파트너: brand, content_type(partnered/non_partnered), partner_brand, is_partner, partner_status, partner_program, has_dm, sample_sent
- 미디어: media_dir, analysis_tier(slim=light), frame_count

## ⚠️ slim 모드 (현재 기본) 무시 컬럼
`scoring_version = 'slim'` 인 레코드는 다음 전부 신뢰 금지:
- composite_v2_score / content_quality_score / creator_fit_score / tier_scores_json (전부 0)
- audio_bonus, audio_tone (audio 분석 OFF)
- product_center_pct / product_first_appearance_pct / child_appearance_pct (-1 sentinel)
- scene_fit / scene_tags / brand_fit_score / subject_age / has_subtitles
- evaluation_tier / lt_passed (레거시 V1)

→ **정렬은 views_30d / engagement_rate / post_date 사용**. composite_v2_score 절대 X.

## 관련 테이블
- `gk_content_metrics_daily`: D+60 일별 추적 (post_id+date 키, views/likes/comments/shares)
- `onz_pipeline_creators`: 크리에이터 마스터 (creator_id UUID 매칭)
- `onz_influencer_orders`: Shopify 주문 (is_partner 결정)

## API
```
GET https://orbitools.orbiters.co.kr/api/datakeeper/content/contentposts/?platform=instagram&post_date__gte=2026-04-01&limit=50
헤더: X-Service-Token: <ORBITOOLS_SERVICE_TOKEN>
```
대시보드 가공 shape: `/api/onzenna/pipeline/content/?platform=instagram&region=us&views_min=10k&order=-views`

## 다운스트림 체크리스트
- [ ] scoring_version='slim' 레코드의 점수 필드 무시
- [ ] product_center/child_appearance/audio_tone 컬럼 사용 X
- [ ] creator_id NULL 대응 (username+platform fallback)
- [ ] brand 빈값 = 미매칭 (NULL 아닌 "")
- [ ] content_type='partnered' 필터로 파트너 포스트 분리

## 코드 위치 (원본 확인용)
- `pipeline/stages/analyze_post.py` — orchestration
- `pipeline/adapters/datakeeper/export.py:_map_to_db` — DB 컬럼 매핑
- `datakeeper/domains/content/models.py:ContentPosts` — 스키마
