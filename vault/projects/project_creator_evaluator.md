---
type: project
domain: pipeline
agents: [creator-evaluator, deep-crawler, social-enricher]
status: active
created: 2026-04-08
updated: 2026-04-08
tags: [creator-eval, lt-ht, keyframe, vision, scoring, pipeline]
moc: "[[MOC_파이프라인]]"
---

# project_creator_evaluator

LT/HT 2-Tier 크리에이터 품질 평가 파이프라인.

## 목표

- 주 1000명+ 크리에이터를 자동 스크리닝 + 품질 평가
- 키프레임/오디오 저장으로 재분석 시 재크롤링 불필요 ($0)
- 4-Tier 프레임워크 (T1~T4)로 표준화된 점수 산출

## 2-Tier 구조

| Tier | 키프레임 | 대상 | 비용 |
|------|---------|------|------|
| **LT (Light Touch)** | 10장 (Hook 3 + Body 7) | 1000명 전체 → ~250명 통과 | ~$20/주 |
| **HT (Heavy Touch)** | 30장 (Hook 3 + 1초 간격) | LT 상위 → ~50명 정밀 | ~$10/주 |

## 키프레임 추출 전략

```
Hook Zone (고정): 0.0s, 1.5s, 3.0s — 첫 3초가 핵심
Body Zone:
  LT: 퍼센트 기반 7장 (14%, 28%, ..., 100%)
  HT: 1초 간격 ~27장 (3.0s 이후)
Short (<3s): 0.0s, mid, end — 3장만
```

## 4-Tier 평가 프레임워크

| Tier | 항목 | 가중치 | 기준 |
|------|------|--------|------|
| **T1: Pass/Fail** | baby_present + category_fit≥60% | Gate | 불합격 → composite=0 |
| **T2: Content Specs** | duration, hook, subtitles, audio, demo | 30% | 0-100 |
| **T3A: Engagement** | ER by band + comment quality | 25% | 0-100 |
| **T3B: Audience** | follower location, age, bot_risk, growth | 20% | 0-100 |
| **T4: Performance** | frequency, UGC quality, collab history, multiplatform | 25% | 0-100 |

`framework_composite = T2(30%) + T3A(25%) + T3B(20%) + T4(25%)` (T1 FAIL이면 0)

## 파이프라인 흐름

```
① deep_crawler.py      → 프로필 + 포스트 크롤 (Apify)
② lt_screener.py        → 6-필터 자동 스크리닝
③ frame_extractor.py    → LT 10장 / HT 30장 키프레임 추출
④ vision_tagger.py      → GPT-4o Vision 분석 (LT/HT 프롬프트)
⑤ score_calculator.py   → v2 점수 + 4-Tier Framework
⑥ creator_evaluator.py  → 오케스트레이터 (전체 통합)
⑦ PG sync               → gk_content_posts + gk_creator_evaluations
```

## LT 스크리닝 6-필터

1. **Follower 범위**: 1K~500K
2. **ER by Band**: micro(≥3%), mid(≥1%), macro(≥0.5%)
3. **카테고리 적합성**: 40%+ 키워드 매칭 (baby, toddler, sippy cup 등)
4. **게시 빈도**: 30일 내 4+ 포스트
5. **영상 비율**: 30%+ 비디오/릴
6. **봇 의심**: ER > 20% → 차단

## 미디어 캐시 저장 구조

```
EC2: /home/ubuntu/export_calculator/media/ci_cache/
Local: .tmp/ci_cache/

ci_cache/{username}/{post_id}/frames/   ← 키프레임 JPG
ci_cache/{username}/{post_id}/audio.mp3 ← 오디오
ci_cache/{username}/{post_id}/meta.json ← tier, frame_count, duration
```

PG `media_dir` = `"{username}/{post_id}"` → 파일 경로와 1:1 매칭

## DB 스키마 변경 (2026-04-08)

### gk_content_posts 신규 컬럼 (8개)
`media_dir`, `media_tier`, `media_stored_at`, `frame_count`, `composite_v2_score`, `evaluation_tier`, `lt_passed`, `tier_scores_json`

### gk_creator_evaluations 신규 테이블 (24개 컬럼)
`username`(unique), `platform`, `region`, `posts_analyzed`, `avg_content_quality`, `avg_creator_fit`, `avg_composite_v2`, `max_composite_v2`, `evaluation_tier`, `lt_passed`, `lt_score`, `ht_score`, `followers`, `engagement_rate`, `category_fit_score`, `posting_frequency`, `tier1_pass`, `tier2_score`, `tier3a_score`, `tier3b_score`, `tier4_score`, `crm_pushed`, `crm_pushed_at`, `evaluated_at`

## 재분석 비용

| 변경 | 비용 | 설명 |
|------|------|------|
| score_calculator 가중치 | **$0** | PG 숫자만 재계산 |
| Vision 프롬프트 | **~$0.01/릴** | 캐시된 키프레임으로 GPT-4o 재호출 |
| 크롤링 재실행 | **~$0.005/프로필** | Apify (필요 시만) |

## CLI 명령

```bash
# LT 파이프라인
python tools/creator_evaluator.py --lt --handles "user1,user2" --region us

# HT 파이프라인 (LT 통과자 대상)
python tools/creator_evaluator.py --ht --from-lt-results --min-lt-score 60

# 재분석 (프롬프트/가중치 변경 시)
python tools/creator_evaluator.py --reanalyze --tier LT

# 상태 확인
python tools/creator_evaluator.py --status
```

## 트리거 키워드

`크리에이터 평가`, `LT 파이프라인`, `HT 파이프라인`, `creator evaluator`, `크리에이터 스크리닝`, `키프레임 분석`, `재분석`, `평가 프레임워크`

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `tools/creator_evaluator.py` | 메인 오케스트레이터 |
| `tools/ci/frame_extractor.py` | LT/HT 키프레임 추출 |
| `tools/ci/media_cache.py` | EC2/로컬 파일 캐시 관리 |
| `tools/ci/lt_screener.py` | 6-필터 자동 스크리닝 |
| `tools/ci/vision_tagger.py` | GPT-4o Vision (LT/HT 프롬프트) |
| `tools/ci/score_calculator.py` | v2 점수 + 4-Tier Framework |
| `tools/ci/downloader.py` | 비디오 다운로드 |
| `tools/deep_crawler.py` | Apify 프로필/포스트 크롤 |
| `datakeeper/models.py` | Django 모델 (ContentPosts, CreatorEvaluations) |

## 남은 작업

- [ ] `_pg_sync_results()` 구현 (creator_evaluator.py 내 TODO stub)
- [ ] 실제 핸들로 LT 테스트 실행
- [ ] HT 프로모션 테스트
- [ ] GitHub Actions 자동화 (주간 배치)

## 관련 노트

- [[pipeline_data_architecture]] — 데이터 흐름 전체
- [[MOC_파이프라인]] — 파이프라인 도메인 홈
- [[MOC_인프라]] — DataKeeper + EC2
