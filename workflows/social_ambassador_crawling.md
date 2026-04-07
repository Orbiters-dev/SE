# 소셜 대사 크롤링 (Social Ambassador Discovery Crawling)

## 목적

일본어 육아 키워드/해시태그로 IG 포스트를 검색해 **아직 grosmimi와 콜라보하지 않은 새로운 크리에이터**를 발굴한다.
발굴된 크리에이터는 Whisper CI (transcript + vision 분석) 를 거쳐 JP CRM 파이프라인(`onz_pipeline_creators`)에 자동 등록된다.

> **기존 파이프라인과의 차이**:
> - `crawler_pipeline.md` = grosmimi_japan 태그된 포스트 수집 (= 이미 콜라보한 크리에이터)
> - **이 워크플로우** = 육아 해시태그 검색으로 **새로운 후보** 발굴 (= 아웃바운드 소싱)

---

## 데이터 소스

| 소스 | 방식 | 대상 |
|------|------|------|
| IG 해시태그 검색 | Apify `apify/instagram-hashtag-scraper` | JP 육아 키워드 |
| IG 프로필 조회 | Apify `apify/instagram-profile-scraper` | 발견된 크리에이터 |
| Whisper CI | OpenAI Whisper + GPT-4o Vision | 비디오 포스트 분석 |

---

## JP 육아 검색 키워드 (해시태그)

### Tier 1 — 핵심 제품 관련 (높은 전환 가능성)
- `#ストローマグ` (straw mug)
- `#ベビーマグ` (baby mug)
- `#ストロー練習` (straw practice)
- `#ストローデビュー` (straw debut)
- `#マグデビュー` (mug debut)
- `#赤ちゃんマグ` (baby mug)
- `#ベビーストロー` (baby straw)

### Tier 2 — 이유식/육아 카테고리 (넓은 풀)
- `#離乳食` (baby food/weaning)
- `#離乳食初期` (early weaning)
- `#離乳食中期` (mid weaning)
- `#離乳食後期` (late weaning)
- `#離乳食レシピ` (weaning recipe)
- `#育児グッズ` (parenting goods)
- `#ベビー用品` (baby products)
- `#ベビーグッズ` (baby goods)

### Tier 3 — 라이프스타일/맘 카테고리 (볼륨)
- `#育児ママ` (parenting mom)
- `#新米ママ` (new mom)
- `#ママライフ` (mom life)
- `#子育て` (child rearing)
- `#赤ちゃんのいる生活` (life with baby)
- `#生後6ヶ月` (6 months old) ~ `#生後12ヶ月` (12 months old)

### 제외 키워드 (이미 콜라보한 경우)
- `grosmimi`, `グロスミミ`, `grosmimi_japan`, `onzenna`

---

## 실행 흐름

```
1. Apify 해시태그 검색
   ├── Tier 1 키워드 우선 실행 (제품 관련 = 높은 의도)
   ├── 각 해시태그별 최근 50-100개 포스트 수집
   ├── 비디오 포스트만 필터 (Reels)
   └── 중복 제거 (같은 크리에이터의 여러 포스트)

2. 기존 크리에이터 제외
   ├── onz_pipeline_creators.ig_handle 매칭
   ├── gk_content_posts.username 매칭 (이미 grosmimi 포스팅한 사람)
   └── EXCLUDE 리스트 (브랜드 계정)

3. 크리에이터 프로필 조회
   ├── 팔로워 수 필터 (MIN 1,000 ~ MAX 500,000)
   ├── 프로필 바이오 분석 (ママ, 育児, 子育て 등)
   └── 최근 포스트 engagement rate 계산

4. Whisper CI 분석 (상위 후보)
   ├── 비디오 transcript 추출 (일본어)
   ├── Vision 분석 (육아 씬 감지, 제품 노출 가능성)
   └── 스코어링: relevance_score (0-100)

5. CRM 파이프라인 등록
   ├── gk_content_posts에 포스트 저장 (region=jp, source=discovery_hashtag)
   ├── onz_pipeline_creators에 크리에이터 등록 (region=jp, source=ambassador_discovery)
   └── transcript + vision 결과 동기화

6. Google Sheet 업데이트 (Apify 시트 JP Discovery 탭)
   └── 발견 크리에이터 리스트 + 스코어 + 프로필 링크
```

---

## 스코어링 기준

| 항목 | 가중치 | 설명 |
|------|--------|------|
| 팔로워 수 | 15% | 1K-500K 범위. micro (1K-50K) 우선 |
| Engagement Rate | 20% | (likes+comments)/followers. 3%+ 우수 |
| 콘텐츠 관련성 | 30% | transcript에 육아/이유식/마그 키워드 빈도 |
| 비디오 품질 | 15% | Vision 분석: 조명, 구도, 전문성 |
| 포스팅 빈도 | 10% | 주 2회 이상 활성 크리에이터 |
| 기존 브랜드 콜라보 | 10% | PR 경험 유무 (바이오/캡션에서 감지) |

---

## 실행 도구

| 도구 | 역할 | 상태 |
|------|------|------|
| `tools/discover_jp_ambassadors.py` | 메인 디스커버리 스크립트 | **신규 생성 필요** |
| `tools/fetch_apify_content.py` | Apify 클라이언트 (재사용) | ✅ 기존 |
| `tools/analyze_video_content.py` | Whisper CI 오케스트레이터 | ✅ 기존 |
| `tools/ci/downloader.py` | 비디오 다운로드 | ✅ 기존 |
| `tools/ci/whisper_transcriber.py` | 음성 텍스트 변환 | ✅ 기존 |
| `tools/ci/vision_tagger.py` | 프레임 분석 | ✅ 기존 |

---

## GitHub Actions 통합

`apify_daily.yml`에 JP Discovery 스텝 추가:

```yaml
- name: JP Ambassador Discovery (hashtag crawl)
  id: jp_ambassador
  run: |
    python -u tools/discover_jp_ambassadors.py \
      --tier 1 \
      --max-per-hashtag 50 \
      --min-followers 1000 \
      --max-followers 500000
  continue-on-error: true

- name: Run Whisper CI on JP discoveries
  id: jp_discovery_ci
  run: |
    curl -s -X POST "https://orbitools.orbiters.co.kr/api/onzenna/pipeline/run-ci/" \
      -u "${{ secrets.ORBITOOLS_USER }}:${{ secrets.ORBITOOLS_PASS }}" \
      -H "Content-Type: application/json" \
      -d '{"region": "jp", "max": 20, "min_views": 0, "source": "discovery_hashtag"}'
  continue-on-error: true
```

---

## 비용 예상

| 항목 | 예상 비용 (일) |
|------|----------------|
| Apify 해시태그 크롤링 (7 hashtags x 50 posts) | ~$2-5 |
| Apify 프로필 조회 (50 크리에이터) | ~$1-2 |
| Whisper CI (20 비디오) | ~$0.10 |
| **일일 합계** | **~$3-7** |

---

## 주의사항

1. **Rate limiting**: Apify 해시태그 스크래핑은 IG 정책에 민감. 일 1회만 실행
2. **중복 방지**: `gk_content_posts.shortcode`로 이미 저장된 포스트 스킵
3. **기존 크리에이터 제외 필수**: grosmimi 태그/멘션 이력 있는 크리에이터는 discovery에서 제외
4. **Tier 우선순위**: 예산 제한 시 Tier 1만 실행 (제품 직접 관련 키워드)
5. **개인정보**: 크롤링 데이터는 PG에만 저장, 외부 공유 금지

---

## 성공 지표

| KPI | 목표 |
|-----|------|
| 주간 신규 크리에이터 발견 수 | 30+ |
| 주간 CRM 파이프라인 등록 수 | 10+ (스코어 70+) |
| 발견→아웃리치 전환율 | 20%+ |
| 발견→콜라보 전환율 | 5%+ |
