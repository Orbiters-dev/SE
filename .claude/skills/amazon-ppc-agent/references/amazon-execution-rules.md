# Amazon PPC Execution Rules

## Bid Adjustment Engine

### Presets by Campaign Type

#### Manual Campaigns (Exact/Phrase Match)
| Parameter | Value | Notes |
|-----------|-------|-------|
| desired_acos | 0.25 (25%) | Target ACOS for profitability |
| increase_by | 0.20 (20%) | Bid increase for outperformers |
| decrease_by | 0.20 (20%) | Bid decrease for underperformers |
| max_bid | $3.00 | Hard ceiling per keyword |
| min_bid | $0.10 | Floor to maintain visibility |
| high_acos | 0.30 (30%) | Above = aggressive cut |
| mid_acos | 0.25 (25%) | Between mid and high = moderate cut |
| click_limit | 10 | Min clicks for statistical significance |
| impression_limit | 200 | Min impressions before acting |
| step_up | $0.05 | Incremental bump for low-visibility keywords |

#### Auto Campaigns (Discovery)
| Parameter | Value | Notes |
|-----------|-------|-------|
| desired_acos | 0.35 (35%) | Looser for keyword discovery |
| max_bid | $2.00 | Lower ceiling (less control) |
| min_bid | $0.05 | Minimal floor |
| click_limit | 15 | Higher bar (noisier data) |
| impression_limit | 300 | Need more signal |
| step_up | $0.03 | Smaller bumps |

### Bid Decision Logic (Per Keyword, 7-Day Window)

```
FUNCTION adjust_bid(keyword, presets):

  # Case 1: Strong performer - scale up
  IF keyword.acos < presets.mid_acos
  AND keyword.clicks >= presets.click_limit
  AND keyword.sales >= 1:
    new_bid = keyword.bid * (1 + presets.increase_by)
    RETURN min(new_bid, presets.max_bid)

  # Case 2: Moderate zone - hold
  IF keyword.acos >= presets.mid_acos
  AND keyword.acos <= presets.high_acos:
    RETURN keyword.bid  # No change

  # Case 3: Inefficient - cut
  IF keyword.acos > presets.high_acos
  AND keyword.clicks >= presets.click_limit:
    new_bid = keyword.bid * (1 - presets.decrease_by)
    RETURN max(new_bid, presets.min_bid)

  # Case 4: Spending, no sales - aggressive cut
  IF keyword.clicks >= presets.click_limit
  AND keyword.sales == 0:
    new_bid = keyword.bid * 0.70  # -30%
    RETURN max(new_bid, presets.min_bid)

  # Case 5: Low visibility - gentle bump
  IF keyword.impressions < presets.impression_limit
  AND keyword.clicks < 3:
    new_bid = keyword.bid + presets.step_up
    RETURN min(new_bid, presets.max_bid)

  # Case 6: Zero impressions for 7 days - pause
  IF keyword.impressions_7d == 0:
    RETURN "PAUSE"

  # Default: no action
  RETURN keyword.bid
```

### Batch Processing Rules

- Process max 50 keyword changes per cycle (API rate limit safety)
- Group changes by campaign (one API call per campaign batch)
- Log every change with: keyword_id, old_bid, new_bid, reason, timestamp
- Never change more than 30% of a campaign's keywords in one cycle

---

## Search Term Optimization

### Harvesting Flow (Profitable -> Exact Match)

```
INPUT: Search Term Report (14-day window)

FILTER profitable_terms:
  - acos < desired_acos (e.g., < 25%)
  - clicks >= click_limit (e.g., >= 10)
  - sales >= 1
  - NOT already in an exact match campaign

FOR EACH profitable_term:
  1. CREATE keyword in exact match campaign:
     - match_type: EXACT
     - bid: profitable_term.cpc * 1.10 (10% above current CPC)
     - state: ENABLED
  2. CREATE negative keyword in source campaign:
     - match_type: NEGATIVE_EXACT
     - Prevents source auto/broad from competing
  3. LOG: term, source_campaign, target_campaign, bid, timestamp
```

### Negative Keyword Flow (Unprofitable -> Block)

```
INPUT: Search Term Report (14-day window)

TIER 1 - URGENT (Zero Sales Wasters):
  FILTER: spend > 3x target_CPA AND sales == 0
  ACTION: Add as NEGATIVE_EXACT in campaign
  PRIORITY: Execute immediately

TIER 2 - HIGH (High ACOS Terms):
  FILTER: acos > 2x desired_acos AND clicks >= click_limit
  ACTION: Add as NEGATIVE_EXACT OR reduce bid to min_bid
  PRIORITY: Execute within 24 hours

TIER 3 - MEDIUM (Irrelevant Terms):
  FILTER: Manual review - terms clearly irrelevant to product
  ACTION: Add as NEGATIVE_PHRASE (blocks variations too)
  PRIORITY: Weekly review batch
```

### Campaign Exclusion Lists

Exclude from bid optimization (handle manually):
- Brand defense campaigns (always-on, not ROAS-optimized)
- Competitor targeting campaigns (different success metrics)
- Launch campaigns (< 14 days old, insufficient data)
- Seasonal/event campaigns (temporary, different targets)

---

## Budget Execution Rules

### Daily Budget Caps (Fleeters Inc / Naeiae)

| Parameter | Value |
|-----------|-------|
| Total daily cap | $120/day |
| Manual campaigns share | 60% ($72/day) |
| Auto campaigns share | 40% ($48/day) |
| Per-campaign maximum | $50 |
| Scale-up threshold | Overall ROAS > 3.0 for 7 consecutive days |
| Scale-up cap | $150/day |

### Budget Change Rules

```
# Never change budget more than 30% in one day
max_budget_change_pct = 0.30

# Minimum 3 days between budget changes on same campaign
min_days_between_changes = 3

# Budget increase requires
IF campaign.roas_7d >= 3.0 AND campaign.spend_7d > 0:
  new_budget = min(campaign.budget * 1.20, per_campaign_max)

# Budget decrease requires
IF campaign.roas_7d < 1.5 AND campaign.spend_7d > campaign.budget * 3:
  new_budget = max(campaign.budget * 0.70, min_daily_budget)
```

---

## API Execution Reference

### Update Campaign Budget
```
PUT /sp/campaigns
Headers: Amazon-Advertising-API-ClientId, Amazon-Advertising-API-Scope
Body: [{"campaignId": "...", "budget": {"budget": 50.0, "budgetType": "DAILY"}}]
```

### Update Keyword Bid
```
PUT /sp/keywords
Body: [{"keywordId": "...", "bid": 1.50}]
```

### Add Negative Keywords
```
POST /sp/negativeKeywords
Body: [{"campaignId": "...", "adGroupId": "...", "keywordText": "...", "matchType": "NEGATIVE_EXACT"}]
```

### Add New Keywords
```
POST /sp/keywords
Body: [{"campaignId": "...", "adGroupId": "...", "keywordText": "...", "matchType": "EXACT", "bid": 1.50}]
```

### Pause Campaign
```
PUT /sp/campaigns
Body: [{"campaignId": "...", "state": "PAUSED"}]
```

### Rate Limits
- Reporting v3: 100 concurrent reports
- Campaign/keyword updates: 10 TPS (throttle to 5 for safety)
- Bulk operations: batch up to 100 items per request

---

## Approval & Safety

### Pre-Execution Checklist
1. All proposed changes saved to `.tmp/ppc_proposal_YYYYMMDD.json`
2. HTML proposal email sent to reviewer
3. Each change item has `"approved": false` by default
4. Only `"approved": true` items will execute
5. Post-execution: confirmation email + Google Sheets log

### Rollback Plan
- Keep previous bid/budget values in proposal JSON (`old_bid`, `old_budget`)
- If execution causes ROAS drop >50% next day, flag for immediate rollback
- Rollback = re-apply old values from the proposal JSON

### Forbidden Actions (Hard Stops)
- Never pause ALL campaigns simultaneously
- Never set any bid above $3.00
- Never set total daily budget above $150
- Never create new campaigns (only modify existing)
- Never touch Orbitool or GROSMIMI USA campaigns from executor
