---
type: project
domain: pipeline
agents: [social-evaluator]
status: active
created: 2026-04-08
updated: 2026-04-08
tags: [evaluator, backtest, weight-optimization, view-prediction, correlation]
moc: "[[MOC_파이프라인]]"
---

# project_social_evaluator

소셜 이밸류에이터 — CI 서브스코어 백테스트 + 가중치 최적화 + 뷰 예측.

## 목표

score_calculator의 가중치가 **실제 퍼포먼스(views/engagement)를 예측하는지** 검증하고,
데이터 기반으로 최적 가중치를 학습한다.

## 3가지 모드

### 1. BACKTEST — 서브스코어 vs 실제 뷰 상관분석
```bash
python tools/social_evaluator.py --backtest
```
- Pearson r per sub-score (어떤 점수가 뷰와 상관 높은지)
- Feature importance ranking
- 최소 100 rows 필요

### 2. OPTIMIZE — 회귀 기반 가중치 학습
```bash
python tools/social_evaluator.py --optimize
```
- Linear Regression (baseline)
- XGBoost / Random Forest (optional)
- 출력: `optimized_weights.json` → score_calculator v3에 적용
- 최소 500+ rows 권장

### 3. PREDICT — 콘텐츠 시그널 → 뷰 예측
```bash
python tools/social_evaluator.py --predict --post-url "https://..."
```
- 입력: transcript + vision analysis (실제 뷰 없이)
- 출력: predicted_views, predicted_engagement_tier, confidence interval

### Full Pipeline
```bash
python tools/social_evaluator.py --full     # 1→2→3 전체
python tools/social_evaluator.py --dry-run  # 데이터 가용성만 확인
```

## Feature 목록

### Vision Features (GPT-4o)
`hook_score`, `storytelling_score`, `authenticity_score`, `delivery_score`, `brand_fit_score`

### Whisper Features (오디오)
`delivery_verbal_score`, `repeat_watchability`

### Binary Features
`has_subtitles`, `demo_present`, `cta_present`, `product_mention`

### Categorical Features (bonus mapping)
`emotional_tone`, `hook_type`, `script_structure`, `persuasion_type`, `subject_age`, `scene_fit`

## 전제 조건

- `gk_content_posts` 에 CI sub-scores + 실제 메트릭(views_30d, likes_30d) 둘 다 있어야 함
- CI 파이프라인 500+ 포스트 실행 필요 (~$50, 유저 승인 대기)

## 출력 파일

| 파일 | 내용 |
|------|------|
| `.tmp/evaluator/backtest_report.html` | 상관분석 리포트 |
| `.tmp/evaluator/optimized_weights.json` | 학습된 최적 가중치 |
| `.tmp/evaluator/predictor_model.pkl` | 뷰 예측 모델 |

## 데이터 흐름

```
CI Pipeline (Vision + Whisper) → sub-scores → PG (gk_content_posts)
                                                ↓
Social Evaluator ← actual views/likes from PG ←┘
    ↓
Correlation Analysis → Weight Optimization → v3 score_calculator
    ↓
View Predictor: "이 콘텐츠 스타일 → ~50K 뷰 예측"
```

## 활용 시나리오

1. **"hook_score가 진짜 중요한가?"** → backtest로 Pearson r 확인
2. **"가중치 바꿔야 하나?"** → optimize로 데이터 기반 최적 가중치 학습
3. **"이 크리에이터 영상 뷰 얼마나 나올까?"** → predict로 사전 예측
4. **"v1 가중치 vs v3 최적화 비교"** → backtest report에 side-by-side

## 트리거 키워드

`소셜 이밸류에이터`, `social evaluator`, `스코어링 백테스트`, `가중치 최적화`, `뷰 예측`, `서브스코어 상관분석`, `weight calibration`

## 남은 작업

- [ ] CI 파이프라인 500+ 포스트 실행 (~$50, 유저 승인 대기)
- [ ] CLAUDE.md에 소셜이밸류에이터 트리거 등록

## 관련 노트

- [[project_social_deep_crawler]] — 데이터 소스 (크롤러 + enricher)
- [[project_creator_evaluator]] — 평가 파이프라인 (이 가중치의 소비자)
- [[MOC_파이프라인]] — 파이프라인 도메인 홈
