# Social Deep Crawling (소셜딥크롤링)

JP/US 크리에이터 콘텐츠를 주간 단위로 수집 → 분석 → 스코어링하는 자동화 파이프라인.

## Pipeline Architecture

```
CRAWL (weekly)          STORE           CI (daily)              SCORE
─────────────          ─────           ──────────              ─────
IG Reel Scraper    →   gk_content_   → Whisper Transcript  → Content Quality (0-100)
  (profile-based)       posts (PG)     GPT-4o Vision (HVA)   Creator-Brand Fit (0-100)
TikTok Hashtag     →                 → Script Analysis      → Engagement Metrics
  (JP parenting)                       Product Detection       Virality Coefficient
```

## Tools

| Tool | Path | Purpose |
|------|------|---------|
| Weekly Reels Scraper | `tools/weekly_reels_scraper.py` | IG+TikTok reels 수집 |
| CI Orchestrator | `tools/analyze_video_content.py` | Whisper+Vision+Script+Score 실행 |
| Vision Tagger | `tools/ci/vision_tagger.py` | GPT-4o 키프레임 분석 (HVA) |
| Whisper Transcriber | `tools/ci/whisper_transcriber.py` | 음성→텍스트, 제품 키워드 감지 |
| Score Calculator | `tools/ci/score_calculator.py` | Composite scoring engine v1.0 |
| JP Ambassador Discovery | `tools/discover_jp_ambassadors.py` | 해시태그 기반 크리에이터 발굴 |

## Scoring Framework (v1.0)

Baby product niche (Grosmimi/Onzenna) 최적화.

### Content Quality Score (0-100)

| Dimension | Weight | Signals |
|-----------|--------|---------|
| Authenticity & Tone | 35% | authenticity_score, emotional_tone |
| Storytelling | 25% | storytelling_score, script_structure |
| Hook Power | 20% | hook_score, has_subtitles |
| Delivery | 20% | delivery_score, delivery_verbal_score |

### Creator-Brand Fit Score (0-100)

| Dimension | Weight | Signals |
|-----------|--------|---------|
| Brand Relevance | 30% | brand_fit_score, product_mention |
| Demo & Proof | 25% | demo_present, subject_age |
| Audience Match | 25% | follower_band (nano/micro preferred) |
| Content Virality | 20% | engagement_rate, virality_coeff |

### Why these weights?

- **Authenticity > Hook**: Mom audience skips ad-like content instantly
- **Demo & Proof**: Straw cups are functional products. Baby using it = strongest signal
- **Nano/micro preferred**: 1-100K followers = higher engagement, better seeding ROI
- **Virality downweighted**: High views does not equal high conversion for baby products

## Automation Schedule

| What | When | Trigger |
|------|------|---------|
| Weekly Reels Scraper | Mondays | `apify_daily.yml` (DOW check) |
| JP Ambassador Discovery | Daily | `apify_daily.yml` |
| CI Pipeline (Whisper+Vision) | Daily | `run-ci/` endpoint |
| Transcript Sync | Daily | `sync-transcripts/` endpoint |

## Manual Execution

```bash
# Weekly scraper (IG + TikTok combined)
python tools/weekly_reels_scraper.py --min-views 5000
python tools/weekly_reels_scraper.py --platform ig --dry-run
python tools/weekly_reels_scraper.py --platform tiktok --min-views 10000

# CI pipeline with scoring
python tools/analyze_video_content.py --region jp --max 20 --min-views 5000
python tools/analyze_video_content.py --region jp --vision-only  # re-score existing
python tools/analyze_video_content.py --region jp --dry-run      # test without DB write
```

## DB Schema (gk_content_posts)

### Core columns
`post_id`, `url`, `platform`, `username`, `caption`, `transcript`, `views_30d`, `likes_30d`, `comments_30d`, `region`, `source`

### CI raw signal columns
`scene_fit` (HIGH/MED/LOW), `brand_fit_score` (0-10), `scene_tags`, `subject_age`, `product_mention`, `has_subtitles`, `ci_analysis` (JSON)

### Composite score columns
`content_quality_score` (0-100), `creator_fit_score` (0-100), `engagement_rate`, `virality_coeff`, `scoring_version`, `scored_at`

## Cost Estimates

| Component | Per Post | Weekly (200 posts) | Monthly |
|-----------|----------|-------------------|---------|
| Apify (IG+TikTok) | ~$0.0015 | ~$0.30 | ~$1.20 |
| Whisper API | ~$0.0006 | ~$0.12 | ~$0.48 |
| GPT-4o Vision | ~$0.0003 | ~$0.05 | ~$0.20 |
| GPT-4o-mini Script | ~$0.0002 | ~$0.04 | ~$0.16 |
| Score Calculation | $0 | $0 | $0 |
| **Total** | **~$0.003** | **~$0.51** | **~$2.04** |

## Data Flow

```
1. CRAWL: Apify scrapes IG reels (profile-based) + TikTok hashtags
2. STORE: Deduplicate by URL → INSERT into gk_content_posts
3. CI: For each post with empty transcript:
   a. Download video → extract audio + 3 keyframes
   b. Whisper: audio → transcript + product keyword detection
   c. Vision: keyframes → HVA scores + brand fit + scene tags
   d. Script: transcript → delivery, persuasion, watchability
   e. Score: raw signals → Content Quality + Creator-Brand Fit
   f. Upsert: all results back to PG
4. SYNC: Join gk_content_posts → onz_pipeline_creators (best transcript per creator)
5. PIPELINE: Creators sorted by creator_fit_score → gifting candidates
```

## Hashtags Monitored (TikTok)

育児, 赤ちゃん, 子育て, 離乳食, 育児ママ, ベビー用品, 1歳, 2歳, 育児グッズ, ベビーグッズ, 新米ママ, ママライフ

## Excluded Accounts

Brand/store accounts auto-filtered: onzenna.official, grosmimi_usa, grosmimi_japan, grosmimi_official, grosmimi_korea, onzenna, grosmimi, zezebaebae, grosmimithailand, grosmimi_thailand
