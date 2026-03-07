# Amazon PPC Query Patterns Guide

## Scoping Your Queries

### By Brand (Profile)
| Brand | Profile Name | When to Use |
|-------|-------------|-------------|
| CHA&MOM | Orbitool | Primary brand analysis |
| Grosmimi | GROSMIMI USA | Established brand monitoring |
| Naeiae | Fleeters Inc | Executor target, optimization focus |
| All | (no filter) | Cross-brand comparison |

### By Time Window
| Window | Use Case |
|--------|----------|
| Yesterday | Spot anomalies, daily health check |
| 7 days | Short-term trend, bid decisions |
| 14 days | Keyword harvesting (attribution window) |
| 30 days | Baseline, budget planning |

---

## Performance Analysis Queries

### Overall Health
```
"Show overall ROAS, ACOS, spend, sales, impressions, clicks for yesterday, 7d, and 30d.
Break down by brand. Highlight any brand with ROAS < 2.0."
```

### Campaign Ranking
```
"Top 10 campaigns by ROAS in the last 14 days.
Include: campaign name, brand, spend, sales, ROAS, ACOS, impressions.
Sort by ROAS descending."
```

### Worst Performers
```
"Show campaigns with 7d spend > $20 and ROAS < 1.5.
Include: campaign name, brand, spend, sales, ROAS, ACOS.
Sort by spend descending. These are bid reduction candidates."
```

### Zero Sales Audit
```
"Which campaigns have spent > $0 in the last 7 days but generated zero sales?
Include: campaign name, brand, total spend, impressions, clicks, CTR.
Sort by spend descending. These are pause candidates."
```

### Trend Analysis
```
"Show daily ROAS and spend for the last 30 days for [brand].
Is ROAS improving, declining, or stable?
Flag any day where ROAS dropped >30% vs the 7-day moving average."
```

---

## Keyword & Search Term Queries

### Top Keywords
```
"Top 20 keywords by sales in the last 14 days for [brand].
Include: keyword text, match type, campaign, bid, CPC, impressions, clicks, sales, ACOS.
Sort by sales descending."
```

### Wasted Keywords
```
"Keywords with 14d spend > $10 but zero sales for [brand].
Include: keyword text, match type, campaign, impressions, clicks, CPC, spend.
Sort by spend descending. These need bid reduction or pause."
```

### Harvesting Candidates
```
"Search terms with ACOS < 20% and 2+ sales in the last 14 days.
Check if they already exist as exact match keywords.
If not, these are harvesting candidates.
Include: search term, source campaign, source ad group, clicks, sales, ACOS, CPC."
```

### Negative Keyword Candidates
```
"Search terms with 15+ clicks but zero sales in the last 14 days.
Include: search term, campaign, ad group, impressions, clicks, spend.
Sort by spend descending.
These are negative keyword candidates."
```

### High-Spend Low-Return
```
"Search terms where spend > $20 and ACOS > 50% in the last 14 days.
Include: search term, campaign, spend, sales, ACOS, clicks.
These need bid reduction or negative keyword treatment."
```

---

## Budget & Spend Queries

### Budget Utilization
```
"For each campaign, show daily budget vs actual yesterday spend.
Calculate utilization rate (spend / budget * 100).
Flag campaigns >80% utilized (may be leaving money on table).
Flag campaigns <30% utilized (may need bid increases or better keywords)."
```

### Spend Distribution
```
"Show total 7d spend by campaign type (auto vs manual).
Is the 60/40 split being maintained?
Show top 5 campaigns by spend share."
```

### Budget Depletion Forecast
```
"Based on last 7 days average daily spend, which campaigns will exhaust
their daily budget before 6PM? Estimate depletion hour."
```

---

## Competitive & Market Queries

### Impression Share
```
"For top 10 keywords by spend, what is the impression share?
If available, show lost impression share due to budget vs rank."
```

### CPC Trends
```
"Show average CPC trend over the last 30 days for [brand].
Is CPC increasing (more competition) or decreasing?
Break down by match type (exact, broad, auto)."
```

---

## Execution Queries

### Propose Changes
```
"Run analysis for Fleeters Inc and generate bid/budget proposals.
Apply the ROAS Decision Framework.
Email the proposal to the default recipient."
```

### Review Proposals
```
"Show current pending proposals. For each, show:
- Campaign name
- Current bid/budget
- Proposed change
- Reason (which ROAS band triggered it)
- Expected impact"
```

### Post-Execution Review
```
"Show all changes executed in the last 7 days.
For each change, show the before/after metrics.
Did the changes improve ROAS? Calculate net impact."
```

---

## Query Best Practices

1. **Always specify time window** - "last 7 days" or "2026-02-28 to 2026-03-06"
2. **Specify metrics you want** - Don't just say "performance", list spend, sales, ROAS, etc.
3. **Specify sorting and limits** - "Top 20, sorted by spend descending"
4. **Name the entity type** - "campaigns" vs "keywords" vs "search terms" vs "ad groups"
5. **Include the brand** - Unless you want cross-brand comparison
6. **State your intent** - "These are pause candidates" helps the agent frame recommendations

## Attribution Reminder

Amazon Ads uses 14-day attribution:
- Data from the last 2-3 days may be incomplete (attribution lag)
- Always compare apples to apples: if using 14d data, compare to same window
- Yesterday's numbers will be revised upward as more conversions attribute
- For decision-making, prefer 7d window (balances recency vs completeness)
