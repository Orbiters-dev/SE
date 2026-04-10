Base directory for this skill: c:\dev\WJ-Test1\.claude\skills\social-evaluator

# Social Evaluator — Content Score Backtester & Weight Optimizer

## When to Use This Skill

- "소셜 이밸류에이터" / "social evaluator"
- "스코어링 백테스트" / "가중치 최적화"
- "뷰 예측" / "view predictor"
- "서브스코어 상관분석" / "어떤 서브스코어가 뷰 예측하냐"
- "스코어링 캘리브레이션" / "weight calibration"

## Architecture

```
gk_content_posts (35K+ rows: sub-scores + actual views/likes)
    │
    ▼
social_evaluator.py
├── [1] BACKTEST: sub-score vs actual views correlation
│     ├── Pearson r per sub-score
│     ├── Scatter plots (optional)
│     └── Feature importance ranking
│
├── [2] OPTIMIZE: regression-based weight learning
│     ├── Linear Regression (baseline)
│     ├── XGBoost / Random Forest (optional)
│     └── Output: optimized weight dict → v3 scoring
│
├── [3] PREDICT: content signals → predicted views
│     ├── Input: transcript + vision analysis (no actual metrics)
│     ├── Output: predicted_views, predicted_engagement_tier
│     └── Confidence interval
│
└── [4] REPORT: HTML summary
      ├── Correlation matrix heatmap
      ├── v1 weights vs v3 optimized weights
      ├── Prediction accuracy (MAE, R²)
      └── "If we used v3 from day 1" backtest
```

## Commands

```bash
# Step 1: Correlation analysis (needs CI-analyzed posts in PG)
python tools/social_evaluator.py --backtest

# Step 2: Weight optimization
python tools/social_evaluator.py --optimize

# Step 3: Predict views for a specific post
python tools/social_evaluator.py --predict --post-url "https://..."

# Full pipeline
python tools/social_evaluator.py --full

# Dry run (show data availability only)
python tools/social_evaluator.py --dry-run
```

## Prerequisites

- `gk_content_posts` must have rows with BOTH:
  - CI sub-scores (ci_analysis JSON with hook_score, authenticity_score, etc.)
  - Actual metrics (views_30d, likes_30d, comments_30d)
- Minimum 100 rows for correlation, 500+ for regression

## Output

- Backtest report: `.tmp/evaluator/backtest_report.html`
- Optimized weights: `.tmp/evaluator/optimized_weights.json`
- Prediction model: `.tmp/evaluator/predictor_model.pkl`

## Data Flow

```
CI Pipeline (Vision + Whisper) → sub-scores → PG
                                                ↓
Social Evaluator ← actual views/likes from PG ←┘
    ↓
Correlation Analysis → Weight Optimization → v3 score_calculator
    ↓
View Predictor: "this content style → ~50K views predicted"
```


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
