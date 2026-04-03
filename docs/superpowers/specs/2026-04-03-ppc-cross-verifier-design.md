# PPC Cross-Verification Agent — Design Spec

**Date:** 2026-04-03
**Status:** Approved with conditions (제갈량 APPROVE_WITH_CONDITIONS)
**Owner:** WJ
**Priority:** Critical (real money pipeline — $150~$3,000/day)

---

## 1. Problem Statement

ORBI의 Amazon PPC 파이프라인은 3개 브랜드(Naeiae $150/day, Grosmimi $3,000/day, CHA&MOM $150/day)의 입찰/예산을 매일 자동 조정한다. 현재 문제:

1. **데이터 정합성 미검증** — DataKeeper, PPC Dashboard, Financial Dashboard 3곳의 숫자가 불일치할 수 있으나 감지 메커니즘 없음
2. **AOV 하드코딩 버그** — $20 AOV 가정으로 저가 상품(Rice Pop $3~5) harvest/negative 미작동 (수정 완료)
3. **예산 정체** — Naeiae Manual ROAS 7.38x인데 budget ceiling($100)에 막혀 성장 불가. 자동 예산 추천 메커니즘 부재
4. **CFO 브리핑 시 숫자 신뢰도** — Financial Dashboard KPI와 PPC 숫자 교차 확인 불가

---

## 2. Architecture — Hybrid: Python Verifier + Codex Analyst

```
              3 Gates × 3 Loops
              ==================

 GATE 1 (Pre-Propose)          GATE 2 (Pre-Execute)         GATE 3 (Post-Execute)
 "데이터 믿을 수 있나?"         "이 액션 안전한가?"           "뭘 배웠나?"
 ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
 │ L1: DK ↔ Fin    │          │ L1: Freshness   │          │ L1: Result vs   │
 │ L2: DK ↔ PPC    │          │     + Drift     │          │     Expectation │
 │ L3: 3-way       │          │ L2: Ceiling     │          │ L2: Codex Root  │
 │     + Insights   │          │     + Rate Limit│          │     Cause       │
 │     + Budget Rec │          │ L3: Fin ROAS    │          │ L3: Insight Gen │
 └────────┬────────┘          │     + TACOS     │          │     + Budget Rec│
          │                   │     + Budget Rec│          └────────┬────────┘
     FAIL → Block             └────────┬────────┘                   │
     PASS → Propose                    │                    → ppc_xv_insights.json
                               FAIL → Block                 → 다음날 Gate 1 참조
                               PASS → Execute
```

### Tool Separation

| Component | Type | Purpose |
|-----------|------|---------|
| `ppc_cross_verifier.py` | NEW Python tool | Gates 1 & 2: 결정론적 숫자 검증 |
| `codex_auditor.py --domain ppc` | EXTEND existing | Gate 3: 원인 분석 + 인사이트 |
| `amazon_ppc_executor.py` | MODIFY existing | Gate hook 연결 + 예산 추천 로직 |
| `amazon_ppc_pipeline.yml` | MODIFY existing | CI에 Gate 단계 삽입 |

---

## 3. Data Sources & Timezone Alignment

### 3 Sources

| Source | Location | Refresh | Timezone |
|--------|----------|---------|----------|
| DataKeeper (PG) | `orbitools.orbiters.co.kr/api/datakeeper` | 2x daily | UTC stored, PST queried |
| PPC Dashboard | `docs/ppc-dashboard/data.js` | Per proposal | PST (generated_pst field) |
| Financial Dashboard | `docs/financial-dashboard/fin_data.js` | 2x daily | PST (generated_pst field) |

### Timezone Protocol (제갈량 필수조건 #1)

모든 비교는 **PST (America/Los_Angeles) 기준 date window**로 정렬:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PST = ZoneInfo("America/Los_Angeles")

def aligned_date_range(days_back: int = 7) -> tuple[str, str]:
    """Return PST-aligned date range for all source queries."""
    now_pst = datetime.now(PST)
    end = now_pst.date()
    start = end - timedelta(days=days_back)
    return start.isoformat(), end.isoformat()

# Assertion in every comparison function
def assert_tz_aligned(dk_dates, fin_dates, ppc_dates):
    """All dates must align to same PST day boundaries."""
    assert dk_dates == fin_dates == ppc_dates, \
        f"TZ mismatch: DK={dk_dates}, Fin={fin_dates}, PPC={ppc_dates}"
```

---

## 4. Gate 1: Pre-Propose Cross-Check

**Purpose:** 데이터 소스 신뢰성 확인. 숫자 안 맞으면 PROPOSE 차단.

### Loop 1: DataKeeper vs Financial Dashboard

| Check | Method | Tolerance | Fail Action |
|-------|--------|-----------|-------------|
| 7D Ad Spend (Amazon) | DK `amazon_ads_daily` SUM vs `fin_data.js` ad_performance.amazon.spend | ±1% | BLOCK |
| 7D Ad Sales (Amazon) | DK SUM vs fin_data.js | ±1% | BLOCK |
| Through-date alignment | DK freshness vs fin_data generated_pst | ≤24h gap | BLOCK |
| fin_data.js freshness | `generated_pst` timestamp | ≤24h old | BLOCK (제갈량 #3) |

### Loop 2: DataKeeper vs PPC Dashboard

| Check | Method | Tolerance | Fail Action |
|-------|--------|-----------|-------------|
| Campaign-level 7D spend | DK per-campaign vs data.js proposals | ±1% | BLOCK |
| ACOS direct calc vs display | spend/sales 직접계산 vs data.js ACOS 표시값 | ±0.5pp | WARN |
| Budget config consistency | executor BRAND_CONFIGS vs dashboard_config_override.json | exact match | BLOCK |
| data.js freshness | data.js generation timestamp | ≤24h old | BLOCK (제갈량 #3) |

### Loop 3: 3-Way Reconciliation + Budget Recommendation

| Check | Method | Tolerance | Fail Action |
|-------|--------|-----------|-------------|
| 3-way spend/sales match | DK vs Fin vs PPC 불일치 카운트 | 0 mismatches | BLOCK |
| AOV sanity check | Search term AOV vs Shopify AOV | ±50% | WARN |
| Yesterday's insights applied | `ppc_xv_insights.json` action items vs today proposal | 적용 여부 | WARN |
| **Budget scaling recommendation** | See Section 7 | - | INFO (advisory) |

### DataKeeper Fallback Mode (제갈량 필수조건 #2)

```python
def gate1_with_fallback():
    dk_available = test_datakeeper_connection()
    if dk_available:
        return run_gate1_3way()  # Normal 3-way
    else:
        # Degraded: 2-way only (fin_data vs data.js)
        result = run_gate1_2way()
        result.warnings.append("DataKeeper DOWN — 2-way verification only")
        result.budget_override = 0.70  # 70% budget cap
        notify_slack("#ppc-emergency", "DataKeeper down, PPC running at 70%")
        return result
```

---

## 5. Gate 2: Pre-Execute Cross-Check

**Purpose:** 실행 직전 안전장치. 실제 돈 쓰기 전 마지막 확인.

### Loop 1: Proposal Freshness + Data Drift

| Check | Method | Threshold | Fail Action |
|-------|--------|-----------|-------------|
| Proposal age | proposal generated_at vs now | ≤3h (제갈량 조정: 6h→3h) | BLOCK |
| Proposal age (high-spend) | $1000+/day brands | ≤2h | BLOCK |
| Real-time data drift | Current DK spend vs proposal basis | ±5% (제갈량 조정: 10%→5%) | BLOCK |
| Partial execution check | Previous exec_log for incomplete runs | any partial | WARN (제갈량 #5) |

### Loop 2: Ceiling + Rate Limit Enforcement

| Check | Method | Threshold | Fail Action |
|-------|--------|-----------|-------------|
| Campaign budget ceiling | proposed budget vs max_single_campaign_budget | exceed → BLOCK | BLOCK |
| Bid ceiling | proposed bid vs brand max_bid | exceed → BLOCK | BLOCK |
| Brand daily budget cap | sum(proposed budgets) vs total_daily_budget × 2.2 | exceed → BLOCK | BLOCK |
| **Daily budget change rate** | new budget vs yesterday's / brand config | ±30%/day max | BLOCK (제갈량 #4) |
| **Daily bid change rate** | new bid vs current bid | ±20%/day max | BLOCK (제갈량 #4) |
| **Cross-brand total cap** | sum(all brands) vs COMPANY_DAILY_PPC_CAP | exceed → BLOCK | BLOCK |

```python
COMPANY_DAILY_PPC_CAP = 4000.0  # Naeiae $150 + Grosmimi $3000 + CHA&MOM $150 + headroom
MAX_DAILY_BUDGET_CHANGE_RATE = 0.30  # ±30% per day
MAX_DAILY_BID_CHANGE_RATE = 0.20     # ±20% per day
```

### Loop 3: Financial Cross-Check + TACOS Impact

| Check | Method | Threshold | Fail Action |
|-------|--------|-----------|-------------|
| ROAS cross-check | Proposal expected ROAS vs fin_data 30d ROAS | >3x divergence | WARN |
| TACOS impact | (current spend + proposed delta) / total_sales | >15% predicted TACOS | WARN |
| Contribution margin impact | projected spend change vs fin_data CM% | CM% drops >5pp | WARN |
| **Budget scaling recommendation** | See Section 7 | - | INFO (advisory) |

### Human Override Policy (제갈량 추가 제안)

```yaml
gate_override_policy:
  approval_channel: "#ppc-emergency"
  approval_timeout_hours: 4
  fallback_if_no_response: "EXECUTE_WITH_SAFE_DEFAULTS"
  safe_defaults:
    budget_multiplier: 0.8     # 80% of normal
    bid_change_max_pct: 0      # freeze bids
    notify: ["wjcho"]
```

---

## 6. Gate 3: Post-Execute Analysis

**Purpose:** 실행 결과 분석 + 인사이트 축적 + 다음 날 반영.

### Loop 1: Execution Result vs Expectation (Python)

| Check | Method |
|-------|--------|
| Applied changes count | exec_log entries vs approved proposals |
| Partial execution detection | any throttled/failed API calls (제갈량 #5) |
| Budget actually changed | verify via API callback / next DK refresh |
| Bid actually changed | same verification |

```python
def detect_partial_execution(exec_log: list, proposals: list) -> dict:
    """Flag if not all approved proposals were executed."""
    approved = [p for p in proposals if p.get("approved")]
    executed = [e for e in exec_log if e.get("status") == "success"]
    failed = [e for e in exec_log if e.get("status") in ("throttled", "error")]
    return {
        "total_approved": len(approved),
        "total_executed": len(executed),
        "total_failed": len(failed),
        "partial": len(failed) > 0,
        "failed_items": failed,
    }
```

### Loop 2: Codex Root Cause Analysis

```bash
python tools/codex_auditor.py --domain ppc \
  --audit \
  --context ".tmp/ppc_xv_gate1_result.json .tmp/ppc_xv_gate2_result.json"
```

Codex analyzes:
- Why specific campaigns have high/low ACOS (e.g., "Auto ACOS 64.9% because...")
- Anomaly patterns across 7D/30D trends
- **Only for outlier campaigns** (ACOS > target ±5pp) — cost control (제갈량 추가 제안)

Verdict schema:
```json
{
  "verdict": "DEGRADED",
  "checks": [
    {"name": "naeiae_auto_acos", "result": "FAIL", "detail": "64.9% vs 35% target"},
    {"name": "naeiae_manual_roas", "result": "PASS", "detail": "7.38x exceeds 2.5x target"}
  ],
  "root_causes": ["Auto campaign targeting too broad — consider tightening match types"],
  "recommendations": ["Shift 20% of Auto budget to Manual", "Add negative keywords for non-converting terms"]
}
```

### Loop 3: Insight Generation + Budget Recommendation

Output → `.tmp/ppc_xv_insights.json`:

```json
{
  "generated_pst": "2026-04-03T08:15:00-07:00",
  "insights": [
    {
      "brand": "naeiae",
      "type": "budget_recommendation",
      "action": "increase_total_daily_budget",
      "current": 150,
      "recommended": 200,
      "reasoning": "Manual ROAS 7.38x sustained 7D. Auto needs negative keyword cleanup first.",
      "confidence": "high"
    },
    {
      "brand": "naeiae",
      "type": "structural",
      "action": "shift_budget_manual_to_auto",
      "detail": "Manual 60%→75%, Auto 40%→25% until Auto ACOS improves",
      "confidence": "medium"
    }
  ],
  "gate_failures_today": 0,
  "codex_cost_usd": 0.04
}
```

---

## 7. Budget Scaling Recommendation Engine

### Problem

Naeiae total_daily_budget = $150이 정적 값으로 고정. Manual ROAS 7.38x인데:
- `max_single_campaign_budget = $100` → Manual 캠페인 ceiling 도달
- Auto ACOS 64.9% → 전체 40% 예산 낭비
- 성과 좋아도 올릴 메커니즘 없음

### Solution: 3-Tier Budget Advisor

Gate 1 Loop 3와 Gate 3 Loop 3에서 실행. Proposal 결과에 advisory로 포함.

```python
def compute_budget_recommendation(brand: str, campaigns: list, config: dict) -> dict:
    """Recommend budget config changes based on performance."""

    manual_camps = [c for c in campaigns if classify_targeting(c["name"]) == "MANUAL"]
    auto_camps = [c for c in campaigns if classify_targeting(c["name"]) == "AUTO"]

    manual_roas = weighted_roas(manual_camps, period="7d")
    auto_roas = weighted_roas(auto_camps, period="7d")
    manual_acos = weighted_acos(manual_camps, period="7d")
    auto_acos = weighted_acos(auto_camps, period="7d")

    current_budget = config["total_daily_budget"]
    current_max_camp = config["max_single_campaign_budget"]
    target_roas = config["targeting"]["MANUAL"]["min_roas"]

    recommendations = []

    # ── Tier 1: Campaign ceiling lift ──
    # If best campaign is AT ceiling and ROAS > 2x target → lift ceiling
    best_camp = max(manual_camps, key=lambda c: c.get("roas_7d", 0), default=None)
    if best_camp:
        at_ceiling = best_camp.get("currentDailyBudget", 0) >= current_max_camp * 0.95
        strong_roas = best_camp.get("roas_7d", 0) >= target_roas * 2
        if at_ceiling and strong_roas:
            new_max = min(current_max_camp * 1.5, current_budget * 0.8)
            recommendations.append({
                "tier": 1,
                "type": "lift_campaign_ceiling",
                "field": "max_single_campaign_budget",
                "current": current_max_camp,
                "recommended": round(new_max, 2),
                "reason": f"{best_camp['name']} at ceiling (${current_max_camp}) with ROAS {best_camp.get('roas_7d', 0)}x",
                "confidence": "high",
            })

    # ── Tier 2: Budget share rebalancing ──
    # If Manual ROAS >> Auto ROAS → shift allocation
    if manual_roas > 0 and auto_roas > 0:
        ratio = manual_roas / auto_roas
        if ratio > 3.0:
            # Manual is 3x+ more efficient → shift to 75/25
            recommendations.append({
                "tier": 2,
                "type": "rebalance_targeting_share",
                "manual_share": {"current": 0.60, "recommended": 0.75},
                "auto_share": {"current": 0.40, "recommended": 0.25},
                "reason": f"Manual ROAS {manual_roas:.1f}x vs Auto {auto_roas:.1f}x ({ratio:.1f}x gap)",
                "confidence": "high" if ratio > 5.0 else "medium",
            })
        elif ratio > 2.0:
            recommendations.append({
                "tier": 2,
                "type": "rebalance_targeting_share",
                "manual_share": {"current": 0.60, "recommended": 0.70},
                "auto_share": {"current": 0.40, "recommended": 0.30},
                "reason": f"Manual ROAS {manual_roas:.1f}x vs Auto {auto_roas:.1f}x ({ratio:.1f}x gap)",
                "confidence": "medium",
            })

    # ── Tier 3: Total daily budget scaling ──
    # If overall brand ROAS > target AND budget utilization > 80% → recommend increase
    overall_roas = weighted_roas(campaigns, period="7d")
    actual_daily_spend = sum(c.get("spend_7d", 0) for c in campaigns) / 7
    utilization = actual_daily_spend / current_budget if current_budget > 0 else 0

    if overall_roas >= target_roas and utilization > 0.80:
        # Scale proportional to ROAS headroom, max +50%/recommendation
        roas_headroom = overall_roas / target_roas
        scale_factor = min(1.5, 1.0 + (roas_headroom - 1.0) * 0.3)
        new_budget = round(current_budget * scale_factor, 2)
        recommendations.append({
            "tier": 3,
            "type": "increase_total_daily_budget",
            "field": "total_daily_budget",
            "current": current_budget,
            "recommended": new_budget,
            "reason": f"ROAS {overall_roas:.1f}x (target {target_roas}x), utilization {utilization*100:.0f}%",
            "confidence": "high" if roas_headroom > 2.0 else "medium",
            "prerequisite": "Auto ACOS must be addressed first" if auto_acos and auto_acos > 50 else None,
        })
    elif manual_roas >= target_roas * 2 and utilization < 0.60:
        # Strong Manual but underspending — need structural fix first
        recommendations.append({
            "tier": 3,
            "type": "structural_fix_required",
            "reason": f"Manual ROAS {manual_roas:.1f}x is excellent but utilization {utilization*100:.0f}%",
            "actions": [
                "Fix Auto campaign (negative keywords, tighten targeting)",
                "Then shift freed budget to Manual",
                "Then consider total budget increase",
            ],
            "confidence": "high",
        })

    return {
        "brand": brand,
        "recommendations": recommendations,
        "summary": {
            "manual_roas_7d": round(manual_roas, 2),
            "auto_roas_7d": round(auto_roas, 2),
            "utilization_pct": round(utilization * 100, 1),
            "current_budget": current_budget,
        },
    }
```

### Naeiae 현재 상태에 적용하면

| Tier | Recommendation | Current | Proposed |
|------|----------------|---------|----------|
| 1 | `lift_campaign_ceiling` | $100 | $120 (= $100 × 1.5, capped at $150 × 0.8) |
| 2 | `rebalance 75/25` | Manual 60% / Auto 40% | Manual 75% / Auto 25% |
| 3 | `structural_fix_required` | $150/day | "Fix Auto ACOS first, then increase to $200" |

**Budget recommendation은 advisory only** — 실제 config 변경은 human approval 필요.
Dashboard UI에서 승인하면 `dashboard_config_override.json`에 반영.

---

## 8. File Outputs

| File | Gate | Content |
|------|------|---------|
| `.tmp/ppc_xv_gate1_result.json` | Gate 1 | 3-way reconciliation + budget rec |
| `.tmp/ppc_xv_gate2_result.json` | Gate 2 | Safety checks + rate limits |
| `.tmp/ppc_xv_gate3_result.json` | Gate 3 | Execution results + Codex analysis |
| `.tmp/ppc_xv_insights.json` | Gate 3 | Accumulated insights for next day |
| `.tmp/ppc_xv_budget_rec.json` | Gate 1+3 | Budget scaling recommendations |

---

## 9. CI Integration (amazon_ppc_pipeline.yml)

```yaml
# Current flow:
#   Daily Report → Propose+Execute → Upload
#
# New flow:
#   Daily Report → GATE1 → Propose → GATE2 → Execute → GATE3 → Upload

steps:
  - name: Run Daily Report
    run: python -u tools/run_amazon_ppc_daily.py
    continue-on-error: true

  - name: "GATE 1: Pre-Propose Cross-Check (3 loops)"
    run: |
      python -u tools/ppc_cross_verifier.py \
        --gate 1 \
        --loops 3 \
        --fail-action block

  - name: Run Propose + Auto-Execute (tier 1-2)
    run: |
      python -u tools/amazon_ppc_executor.py \
        --propose \
        --auto-execute \
        --no-email \
        --pre-execute-gate  # NEW: triggers Gate 2 internally before execute

  - name: "GATE 3: Post-Execute Analysis (3 loops)"
    if: always()
    run: |
      python -u tools/ppc_cross_verifier.py \
        --gate 3 \
        --loops 3 \
        --codex-analyze
```

Gate 2는 executor 내부에서 `--pre-execute-gate` 플래그로 호출 (execute 직전 타이밍 보장).

---

## 10. Codex Auditor Extension

`codex_auditor.py`에 `--domain ppc` 추가:

```python
DOMAIN_CONFIGS["ppc"] = {
    "label": "PPC Cross-Verification",
    "data_files": [
        ".tmp/ppc_xv_gate1_result.json",
        ".tmp/ppc_xv_gate2_result.json",
    ],
    "checks": [
        "spend_reconciliation",
        "acos_calculation_accuracy",
        "budget_utilization_analysis",
        "anomaly_root_cause",
    ],
    "prompt_template": """
    Amazon PPC 교차검증 결과를 분석해주세요:
    
    Gate 1 결과: {gate1_result}
    Gate 2 결과: {gate2_result}
    
    분석 요청:
    1. 불일치가 있다면 원인 추정
    2. ACOS/ROAS 이상치의 근본 원인
    3. 예산 배분 최적화 제안
    4. 다음 PROPOSE에 반영할 사항
    
    verdict: PASS/FAIL/DEGRADED + 상세 이유
    """,
}
```

---

## 11. Cost Control (제갈량 추가 제안)

| Component | Estimated Cost | Control |
|-----------|---------------|---------|
| Gate 1 (Python) | $0 | No LLM |
| Gate 2 (Python) | $0 | No LLM |
| Gate 3 Loop 2 (Codex) | ~$0.02-0.05/brand | Outlier campaigns only |
| Daily total (3 brands) | ~$0.06-0.15 | Monthly cap: $5 |

Codex 분석 대상 필터:
```python
def should_codex_analyze(campaign: dict) -> bool:
    """Only send outlier campaigns to Codex (cost control)."""
    acos_7d = campaign.get("acos_7d")
    target = campaign.get("target_acos")
    if acos_7d is None or target is None:
        return False
    return abs(acos_7d - target) > 5.0  # >5pp deviation from target
```

---

## 12. Success Criteria

| Metric | Target |
|--------|--------|
| False positive gate blocks | <5% of daily runs |
| Data inconsistency detection | 100% (>1% discrepancy caught) |
| Naeiae budget utilization | >80% within 2 weeks |
| Naeiae total budget | $150 → $200+ within 1 month (if ROAS holds) |
| CFO confidence | Can answer "is this number right?" instantly |
| Codex monthly cost | <$5 |

---

## 13. Dependency: AOV Bug Fix (Already Applied)

`amazon_ppc_executor.py` line 1009-1021: dynamic AOV replaces hardcoded $20.
This fix is prerequisite for Gate 1 AOV sanity check to work correctly.

---

## 14. Social Trend Integration — 소셜 크롤링 RAG → PPC 반영

### Data Source

`gk_content_posts` (DataKeeper `content_posts`) 테이블:
- `transcript` — Whisper 영상 대사 전문 (JP/EN)
- `caption` — 포스트 캡션
- `hashtags` — 해시태그 목록
- `ci_analysis` — hook_score, key_message, persuasion_type 등
- `scene_tags` — baby, toddler, eating, outdoor 등
- `views_30d`, `likes_30d` — 참여 지표

현재 12,500+ 포스트 (US/JP), Whisper + GPT-4o Vision 분석 완료.
벡터 임베딩은 미구축 — PostgreSQL full-text + 키워드 빈도 기반으로 시작.

### Integration Points (3 경로)

#### 경로 1: 트렌드 키워드 → Search Term Harvesting 강화 (Gate 1 Loop 3)

소셜에서 뜨고 있는데 PPC에서 아직 타겟하지 않는 키워드를 발견.

```python
def get_social_trend_keywords(brand: str, days: int = 30) -> dict:
    """Extract trending keywords from content_posts transcripts/hashtags."""
    dk = DataKeeper()
    posts = dk.get("content_posts", days=days, brand=brand)

    hashtag_freq = Counter()
    keyword_freq = Counter()
    for p in posts:
        # Hashtag extraction
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag and len(tag) > 2:
                hashtag_freq[tag] += 1
        # Transcript keyword extraction (simple n-gram)
        transcript = (p.get("transcript") or "").lower()
        for word in transcript.split():
            word = word.strip(".,!?()\"'")
            if len(word) > 3 and word.isalpha():
                keyword_freq[word] += 1

    return {
        "top_hashtags": hashtag_freq.most_common(20),
        "top_transcript_keywords": keyword_freq.most_common(30),
        "post_count": len(posts),
    }


def find_untapped_social_keywords(social_keywords: list, ppc_search_terms: list) -> list:
    """Find keywords trending on social but not yet targeted in PPC."""
    ppc_terms = {t.lower().strip() for t in ppc_search_terms}
    untapped = []
    for keyword, freq in social_keywords:
        # Check if any PPC search term contains this keyword
        matched = any(keyword in term for term in ppc_terms)
        if not matched and freq >= 3:  # Minimum 3 mentions
            untapped.append({
                "keyword": keyword,
                "social_frequency": freq,
                "source": "transcript+hashtag",
                "recommendation": "Consider adding as Manual exact-match keyword",
            })
    return untapped
```

**예시:** 인플루언서들이 "baby melt snack"을 자주 쓰는데 PPC는 "rice puff"만 타겟 중
→ Gate 1에서 `untapped_social_keywords` 리스트를 harvest 추천에 포함

#### 경로 2: 고성과 콘텐츠 패턴 → Campaign 인사이트 (Gate 3 Loop 2)

```python
def get_high_performance_patterns(brand: str, days: int = 60) -> dict:
    """Analyze top-performing content for keyword/hook patterns."""
    dk = DataKeeper()
    posts = dk.get("content_posts", days=days, brand=brand)

    # Filter to video posts with views data
    video_posts = [p for p in posts if p.get("views_30d", 0) > 0]
    if not video_posts:
        return {"patterns": [], "post_count": 0}

    # Sort by engagement (views × engagement_rate proxy)
    for p in video_posts:
        views = p.get("views_30d", 0)
        likes = p.get("likes_30d", 0)
        p["_engagement_score"] = likes / max(views, 1) * views

    top_posts = sorted(video_posts, key=lambda x: x["_engagement_score"], reverse=True)[:20]
    bottom_posts = sorted(video_posts, key=lambda x: x["_engagement_score"])[:20]

    # Extract patterns from top vs bottom
    top_hashtags = Counter()
    top_keywords = Counter()
    for p in top_posts:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                top_hashtags[tag] += 1
        for word in (p.get("transcript") or "").lower().split():
            word = word.strip(".,!?()\"'")
            if len(word) > 3:
                top_keywords[word] += 1

    bottom_hashtags = Counter()
    for p in bottom_posts:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                bottom_hashtags[tag] += 1

    # Keywords that appear in top but NOT bottom = differentiators
    differentiators = []
    for kw, count in top_keywords.most_common(30):
        if count >= 3 and kw not in bottom_hashtags:
            differentiators.append({"keyword": kw, "top_freq": count})

    return {
        "top_hashtags": top_hashtags.most_common(10),
        "differentiator_keywords": differentiators[:15],
        "top_post_count": len(top_posts),
        "avg_top_views": sum(p.get("views_30d", 0) for p in top_posts) // max(len(top_posts), 1),
    }
```

Gate 3 Codex prompt에 추가:
```
소셜 크롤링 트렌드 (최근 30일, {post_count}개 포스트):
- 인기 해시태그: {top_hashtags}
- 고성과 콘텐츠 차별화 키워드: {differentiators}
- PPC에서 미타겟 소셜 트렌드: {untapped_keywords}
→ 이 트렌드를 PPC 키워드 전략에 어떻게 반영할지 분석해주세요
```

#### 경로 3: 해시태그 급등 감지 → Bid 전략 선제 조정 (Gate 1 Loop 3)

```python
def detect_hashtag_surge(brand: str) -> list:
    """Detect hashtags with week-over-week frequency surge."""
    dk = DataKeeper()
    posts_7d = dk.get("content_posts", days=7, brand=brand)
    posts_30d = dk.get("content_posts", days=30, brand=brand)

    freq_7d = Counter()
    freq_30d = Counter()
    for p in posts_7d:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                freq_7d[tag] += 1
    for p in posts_30d:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                freq_30d[tag] += 1

    surges = []
    for tag, count_7d in freq_7d.items():
        count_30d = freq_30d.get(tag, 0)
        # Normalize: 7d rate vs 30d rate
        rate_7d = count_7d / 7
        rate_30d = count_30d / 30 if count_30d > 0 else 0.01
        surge_ratio = rate_7d / rate_30d

        if surge_ratio > 2.0 and count_7d >= 3:  # 2x+ surge, minimum 3 mentions
            surges.append({
                "hashtag": tag,
                "count_7d": count_7d,
                "count_30d": count_30d,
                "surge_ratio": round(surge_ratio, 1),
                "recommendation": "Consider preemptive bid increase for related PPC keywords",
            })

    return sorted(surges, key=lambda x: x["surge_ratio"], reverse=True)[:10]
```

**예시:** `#babyledweaning` 7D 빈도가 30D 평균 대비 3x 급등
→ Gate 1에서 "baby led weaning" 관련 PPC 키워드 bid를 선제적으로 +10% 추천

### Output Integration

Gate 결과 JSON에 추가 필드:

```json
// .tmp/ppc_xv_gate1_result.json
{
  "gate": 1,
  "loops": [...],
  "social_trends": {
    "brand": "naeiae",
    "untapped_keywords": [
      {"keyword": "baby melt snack", "social_frequency": 12, "source": "transcript"}
    ],
    "hashtag_surges": [
      {"hashtag": "babyledweaning", "surge_ratio": 3.2, "count_7d": 8}
    ],
    "high_performance_patterns": {
      "differentiator_keywords": ["melt", "organic", "first-food"]
    }
  },
  "budget_recommendations": [...]
}
```

### Cost & Performance

| Component | Cost | Frequency |
|-----------|------|-----------|
| `content_posts` DataKeeper query | $0 | Daily (Gate 1) |
| Keyword frequency analysis | $0 (Python) | Daily |
| Pattern analysis (top/bottom) | $0 (Python) | Daily |
| Codex trend → PPC mapping | ~$0.01/brand | Daily (Gate 3 only) |

벡터 임베딩 없이도 키워드 빈도 + 급등 감지로 80%의 가치를 뽑을 수 있음.
향후 pgvector 추가 시 의미 유사도 기반 매칭으로 업그레이드 가능.

### Success Criteria (Section 12 추가)

| Metric | Target |
|--------|--------|
| Untapped social keywords discovered | 5+ per brand per week |
| Social trend → PPC keyword adoption rate | 30%+ within 7 days |
| Hashtag surge early detection | 48h+ ahead of PPC search volume spike |
