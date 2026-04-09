---
type: project
domain: pipeline
agents: [deep-crawler, social-enricher]
status: active
created: 2026-04-08
updated: 2026-04-08
tags: [crawler, apify, ig, tiktok, enrichment, profile, posts]
moc: "[[MOC_파이프라인]]"
---

# project_social_deep_crawler

소셜 딥크롤러 — Apify 기반 IG/TikTok 프로필 + 포스트 스크래퍼 + 메트릭 enrichment.

## 구성 요소

| 도구 | 역할 |
|------|------|
| `tools/deep_crawler.py` | 프로필 + 최신 포스트 크롤 (Apify) → Excel → PG |
| `tools/ci/enricher.py` | 댓글 스크래핑 + GPT 품질분류, 메타데이터, 콜라보 감지, 멀티플랫폼 |
| `tools/ci/score_calculator.py` | v2 점수 계산 (7 new sub-scores) |

## deep_crawler.py 기능

### 입력 방식
```bash
# 핸들 직접 입력
python tools/deep_crawler.py --handles "user1,user2,user3"

# 파일에서 (한 줄에 핸들 하나)
python tools/deep_crawler.py --handles-file creators.txt

# Syncly 캐시에서
python tools/deep_crawler.py --from-syncly --min-views 5000

# 플랫폼 필터
python tools/deep_crawler.py --handles "user1" --platform tiktok
```

### 주요 옵션
| 옵션 | 설명 |
|------|------|
| `--max-posts N` | 크리에이터당 최대 포스트 수 |
| `--min-post-views N` | 최소 뷰 필터 |
| `--pg-sync` | PG `gk_content_posts`에 동기화 |
| `--dry-run` | API 호출 없이 확인만 |
| `--raw-json` | Apify 원본 JSON 캐시 저장 (재분석용) |
| `--output "file.xlsx"` | 커스텀 출력 경로 |

### Raw JSON 캐시
`--raw-json` 옵션으로 Apify 원본 응답을 저장 → 재크롤링 없이 재분석 가능
- 경로: `.tmp/deep_crawler/raw/{username}_{platform}.json`

## enricher.py 기능

| 기능 | 소스 | 데이터 |
|------|------|--------|
| 댓글 품질 분류 | Apify `instagram-comment-scraper` + GPT-4o | genuine/spam/bot 분류 |
| 프로필 메타데이터 | Apify `instagram-profile-scraper` | followers, bio, posts count |
| 게시 빈도 분석 | 최근 포스트 날짜들 | posts_per_month |
| 콜라보 감지 | 캡션 regex | #ad, #sponsored, #gifted, #PR 등 |
| 멀티플랫폼 | bio 내 링크 | TikTok/YouTube 크로스 존재 여부 |

### 콜라보 패턴
```
#ad, #sponsored, #gifted, #collab, #partnership, #paid, #ambassador,
#brandpartner, #供給, #PR, "paid partner", "sponsored by", "gifted by"
```

### 캐시
`enrichment_cache.json` — `.tmp/ci_enrichment_cache.json`
- 이미 enrichment된 크리에이터는 스킵 (Apify 비용 절감)

## score_calculator v2 sub-scores (7개 신규)

| Sub-score | 소스 | 설명 |
|-----------|------|------|
| `duration_score` | 비디오 길이 | 15-60초 최적, <5초/> 180초 감점 |
| `comment_quality_score` | enricher GPT | genuine 댓글 비율 |
| `posting_frequency_score` | enricher | 월 4~12회 최적 |
| `collab_history_score` | enricher regex | 1~3회 최적 (0=경험없음, 5+=과다) |
| `bot_risk_score` | enricher | ER>20% 또는 spam>30% → 감점 |
| `content_consistency_score` | vision tags | 카테고리 일관성 |
| `multi_platform_score` | enricher bio | 2+ 플랫폼 보너스 |

## 데이터 흐름

```
Apify IG/TikTok Scraper
    ↓
deep_crawler.py → profile + posts → Excel + raw JSON cache
    ↓
enricher.py → comments + metadata + collab + multiplatform
    ↓
score_calculator.py v2 → 7 new sub-scores
    ↓
creator_evaluator.py → 4-Tier Framework (T1~T4)
    ↓
PG: gk_content_posts + gk_creator_evaluations
```

## 관련 노트

- [[project_creator_evaluator]] — LT/HT 2-Tier 평가 (이 크롤러의 소비자)
- [[project_social_evaluator]] — 백테스트/가중치 최적화 (이 데이터 기반)
- [[MOC_파이프라인]] — 파이프라인 도메인 홈
