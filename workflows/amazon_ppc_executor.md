# Amazon PPC Executor Workflow (Mazone)

## Overview
Automated PPC optimization for **Fleeters Inc (Naeiae)** with human-in-the-loop approval.
Analyzes campaigns every 6 hours, emails proposals, executes only approved changes.

## Budget Rules
- **Total daily cap**: $120/day (scalable to $150 if performing well)
- **Manual campaigns**: 60% ($72/day) - exact/phrase keywords, tighter ACOS target (25%)
- **Auto campaigns**: 40% ($48/day) - keyword discovery, looser ACOS target (35%)
- **Per-campaign max**: $50
- **Max bid**: $3.00

## ROAS Decision Framework

| 7d ROAS | Action | Bid Change | Budget Change | Priority |
|---------|--------|------------|---------------|----------|
| < 1.0 | pause | - | - | urgent |
| 1.0~1.5 | reduce_bid | -30% | - | urgent |
| 1.5~2.0 | reduce_bid | -15% | - | high |
| 2.0~3.0 | monitor | - | - | medium |
| 3.0~5.0 | increase_budget | - | +20% | medium |
| > 5.0 | increase_budget | +10% | +30% | high |

Additional: Yesterday ROAS drops 30%+ vs 7d avg -> extra -20% bid reduction.

## Commands

### Analyze & Email Proposal
```bash
python tools/amazon_ppc_executor.py --propose
python tools/amazon_ppc_executor.py --propose --to wj.choi@orbiters.co.kr
python tools/amazon_ppc_executor.py --propose --skip-keywords   # Campaign-level only (faster)
```
- Collects 30d campaign data + 14d search term/keyword data from Amazon Ads API
- Generates campaign-level proposals (bid/budget/pause) based on ROAS framework
- Generates keyword-level proposals: harvesting, negative keywords, bid adjustments
- Emails HTML proposal for review
- Saves JSON to `.tmp/ppc_proposal_YYYYMMDD.json`

### Review & Approve
1. Check email or open `.tmp/ppc_proposal_YYYYMMDD.json`
2. Set `"approved": true` for items to execute
3. Or reply to email with approved items

### Execute Approved Changes
```bash
python tools/amazon_ppc_executor.py --execute
```
- Reads latest proposal JSON
- Executes only `"approved": true` items
- Logs all changes to Google Sheets (`PPC_CHANGELOG_SHEET_ID`)
- Emails execution confirmation

### 6-Hour Cycle (Background)
```bash
python tools/amazon_ppc_executor.py --cycle
```
- Runs --propose every 6 hours automatically
- Emails proposal each cycle
- Never auto-executes (always waits for approval)

### Check Status
```bash
python tools/amazon_ppc_executor.py --status
```

## Safety Guards
- **Approval required**: Nothing executes without explicit `"approved": true`
- **Budget caps**: $120/day total, $50/campaign max, $3 bid max
- **Change log**: Every action logged to Google Sheets with timestamp
- **Email trail**: Proposal + execution confirmation emails
- **Fleeters Inc only**: Hardcoded to only touch Naeiae campaigns

## Required Environment Variables
- `AMZ_ADS_CLIENT_ID` - Amazon Ads API
- `AMZ_ADS_CLIENT_SECRET` - Amazon Ads API
- `AMZ_ADS_REFRESH_TOKEN` - Amazon Ads API
- `PPC_CHANGELOG_SHEET_ID` - Google Sheets for change log (optional)

## Keyword-Level Proposals (NEW)

The `--propose` command now also generates keyword-level proposals:

### Keyword Harvesting
- Pulls 14d search term report
- Finds profitable terms (ACOS < target, 1+ sales, 10+ clicks)
- Proposes adding to exact match campaign + negating in source campaign

### Negative Keywords
- **Tier 1 (urgent)**: spend > 3x target CPA with 0 sales -> negative exact
- **Tier 2 (high)**: ACOS > 2x target with sufficient clicks -> negative exact or bid cut

### Keyword Bid Adjustments
- Uses preset-based rules per campaign type (Manual vs Auto)
- Increases bids on strong performers (ACOS < mid threshold)
- Decreases bids on underperformers (ACOS > high threshold)
- Steps up bids on low-visibility keywords
- Pauses keywords with 0 impressions

Max 50 keyword changes per cycle (API safety limit).

## File Outputs
- `.tmp/ppc_proposal_YYYYMMDD.json` - Proposal data (campaigns + keyword_proposals)
- `.tmp/ppc_proposal_YYYYMMDD_HHMM.html` - Proposal email HTML
- `.tmp/ppc_executed_YYYYMMDD.json` - Execution log
- `.tmp/ppc_executed_YYYYMMDD_HHMM.html` - Execution email HTML
