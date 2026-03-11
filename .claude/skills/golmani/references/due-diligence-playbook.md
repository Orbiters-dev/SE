# Due Diligence Playbook

DD checklists, IC memo templates, PE returns analysis, deal screening, and value creation frameworks.
Adapted for DTC/e-commerce consumer brands and ORBI's specific context.

---

## 1. Due Diligence Checklist

### Commercial DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | Revenue by channel (D2C/Amazon/B2B) trailing 24M | DataKeeper | Critical |
| 2 | Revenue by brand trailing 24M | DataKeeper | Critical |
| 3 | Customer acquisition cost (CAC) by channel | DataKeeper (calculated) | Critical |
| 4 | Customer lifetime value (LTV) and cohort retention | shopify_orders_daily (repeat analysis) | Critical |
| 5 | Amazon BSR trends, review velocity, star ratings | Amazon SP-API / Jungle Scout | High |
| 6 | Organic vs paid traffic split | ga4_daily | High |
| 7 | Brand distribution agreements / exclusivity | Legal documents | Critical |
| 8 | Competitive positioning and market share estimate | Web research + industry-benchmarks.md | High |
| 9 | Customer concentration (top 10 customers % of B2B) | shopify_orders_daily (B2B) | Medium |
| 10 | Promo calendar and discount rate trends | run_kpi_monthly (KPI_할인율) | High |
| 11 | Product return rate by brand/channel | Shopify refunds / Amazon returns | High |
| 12 | Net Promoter Score or customer satisfaction | Klaviyo surveys / reviews | Medium |

### Financial DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | Monthly P&L (IS) trailing 24M | DataKeeper + manual | Critical |
| 2 | Balance sheet (quarterly) | Manual from accounting | Critical |
| 3 | Cash flow statement | Derived from IS + BS | Critical |
| 4 | COGS breakdown by SKU | run_kpi_monthly (685 SKU map) | Critical |
| 5 | Ad spend by platform (monthly detail) | DataKeeper (meta/google/amazon_ads) | Critical |
| 6 | Seeding/influencer cost detail | run_kpi_monthly (KPI_시딩비용) | High |
| 7 | Working capital analysis (inventory, AR, AP) | Manual | High |
| 8 | Tax returns (3 years) for all entities | ORBI, LFU, FLT | Critical |
| 9 | Bank statements (12M) | Banks | High |
| 10 | Debt schedule (all obligations) | Manual | Critical |
| 11 | FX exposure analysis (KRW/USD) | Accounting records | High |
| 12 | Quality of earnings adjustments | Addbacks, one-time items | Critical |

### Legal DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | Entity formation documents (ORBI, LFU, FLT) | Legal files | Critical |
| 2 | Brand trademark registrations (US, Korea) | USPTO / KIPO | Critical |
| 3 | Distribution/licensing agreements | Contracts | Critical |
| 4 | Amazon seller account compliance history | Seller Central | High |
| 5 | FDA compliance (baby products, food) | Regulatory filings | Critical |
| 6 | CPSC compliance (children's products) | Test reports | Critical |
| 7 | Outstanding litigation | Legal counsel | High |
| 8 | Employment agreements | HR files | Medium |
| 9 | Insurance policies | Insurance broker | Medium |
| 10 | IP assignment/ownership chain | Legal documents | High |

### Operational DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | Supply chain map (Korea → US end-to-end) | Operations team | Critical |
| 2 | Inventory management (turns, aging, locations) | WBF + Amazon FBA | Critical |
| 3 | Fulfillment cost per order (WBF, FBA) | WBF invoices, Amazon reports | High |
| 4 | Supplier concentration (top 5 suppliers % of COGS) | Procurement data | High |
| 5 | Lead time analysis (order to delivery) | Operations data | Medium |
| 6 | Technology stack (Shopify, DataKeeper, tools) | Tech team | Medium |
| 7 | Headcount and org chart | HR | Medium |
| 8 | Key person dependencies | Management assessment | High |
| 9 | FBA inventory health (stranded, excess, aged) | Amazon reports | High |
| 10 | Returns processing workflow | Operations | Medium |

### Tax DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | Korea corporate tax filings (ORBI) | Korean CPA | High |
| 2 | US federal/state tax filings (LFU, FLT) | US CPA | High |
| 3 | Transfer pricing documentation (ORBI ↔ LFU ↔ FLT) | Tax counsel | Critical |
| 4 | Sales tax nexus and compliance | Tax software / CPA | High |
| 5 | Customs duties and tariff classification | Customs broker | High |
| 6 | Korea-US tax treaty positions | Tax counsel | Medium |

### IT & Data DD

| # | Item | Source | Priority |
|---|------|--------|----------|
| 1 | DataKeeper architecture and data freshness | data_keeper_client.py | Medium |
| 2 | Shopify store configuration and apps | Shopify Admin | Medium |
| 3 | Amazon seller account health | Seller Central | High |
| 4 | PII handling and privacy compliance | Tech team | Medium |
| 5 | Automation/tool inventory (WAT framework) | tools/ directory | Low |

---

## 2. IC Memo Template (Investment Committee)

### Section 1: Deal Overview (1 page)

```
DEAL OVERVIEW

Target:           Orbiters Co., Ltd. ("ORBI")
Sector:           Consumer Products / Baby & Kids / DTC + Amazon
Headquarters:     Seoul, Korea (US operations via LFU/FLT)
Revenue (LTM):    $[X]M
EBITDA (LTM):     $[X]M ([X]% margin)
Proposed Price:   $[X]M ([X]x EV/Revenue, [X]x EV/EBITDA)
Structure:        [100% equity / majority stake / growth equity]
Timeline:         [Expected close date]
Sponsor/Lead:     [Name]
```

### Section 2: Investment Thesis (1-2 pages)

**Core Thesis:** [1-2 sentence summary of why this is an attractive investment]

**Key Drivers:**

1. **Premium positioning in growing niche**
   - US baby products market ~$12B, growing 5-7% CAGR
   - ORBI owns premium segment (PPSU cups, $25-37 ASP vs $8-15 competitors)
   - "K-baby" trend tailwind (similar to K-beauty penetration)

2. **Multi-brand portfolio with shared infrastructure**
   - 10 brands across baby cups, snacks, skincare, carriers, tableware
   - Shared fulfillment (WBF), shared marketing team, shared tech (DataKeeper/WAT)
   - Portfolio valued at premium to sum-of-parts

3. **Dual-channel diversification**
   - D2C (zezebaebae.com/Shopify) + Amazon (3 seller accounts) + B2B (Faire)
   - Reduces single-platform dependency risk
   - Each channel has different unit economics (D2C higher margin, Amazon higher volume)

4. **Proven unit economics**
   - GM ~70% (Grosmimi), CAC $25-50, LTV:CAC >3:1
   - Path to EBITDA profitability with scale

5. **Growth runway**
   - New brands in pipeline
   - Amazon expansion (TargetPlus, TikTok Shop, Walmart)
   - International (Japan in progress)

### Section 3: Financial Analysis (2-3 pages)

Include:
- Historical P&L summary (trailing 12-24 months)
- Key KPI trends (revenue, GM%, CAC, LTV, MER)
- Revenue bridge (volume vs price vs mix)
- Projected P&L (3-5 year base case)
- Returns analysis (IRR, MOIC) — see Section 4 below
- Sensitivity table (entry multiple × exit multiple × growth)

### Section 4: Risk Assessment (1-2 pages)

| Risk | Severity | Probability | Mitigant |
|------|----------|-------------|----------|
| Grosmimi concentration (~60% rev) | High | Medium | Multi-brand expansion, new launches |
| Amazon policy/fee changes | High | Medium | DTC growth, channel diversification |
| Korea supply chain disruption | High | Low | Diversify suppliers, US inventory buffer |
| FX risk (KRW/USD) | Medium | High | Natural hedge (costs KRW, revenue USD) |
| Key person risk | Medium | Medium | Document processes, build team |
| Tariff/trade policy changes | High | Low-Medium | Monitor, adjust pricing |
| Brand/IP ownership clarity | High | Low | Legal DD confirmation |
| Customer acquisition cost inflation | Medium | Medium | Organic growth, email marketing |

### Section 5: Recommendation (0.5 page)

```
RECOMMENDATION: [APPROVE / CONDITIONAL APPROVE / DECLINE]

Conditions (if applicable):
1. [Condition 1]
2. [Condition 2]

Proposed Terms:
- Valuation: $[X]M
- Structure: [Details]
- Key protections: [Reps & warranties, escrow, etc.]
```

---

## 3. Returns Analysis Framework

### IRR Calculation

```
IRR = Rate at which NPV of cash flows = 0

Cash Flow Timeline:
  Year 0: -(Entry Equity)
  Year 1-N: +Dividends / distributions (if any)
  Year N: +Exit Equity (from sale/IPO)

Entry Equity = Purchase Price - Debt Raised
Exit Equity = Exit EV - Net Debt at Exit

Exit EV = Exit Year EBITDA × Exit Multiple
```

### MOIC (Multiple on Invested Capital)

```
MOIC = Total Distributions / Total Invested

Components:
  Invested = Equity check at entry
  Distributions = Cumulative dividends + exit proceeds
```

### Returns Sensitivity Template

```
         Exit Multiple
       8x    10x   12x   15x
Entry
  8x   15%   22%   28%   35%   <- IRR
 10x   10%   17%   23%   30%
 12x    5%   12%   18%   25%

         Hold Period
       3yr   4yr   5yr   7yr
MOIC
 2.0x  26%   19%   15%   10%   <- IRR
 2.5x  36%   26%   20%   14%
 3.0x  44%   32%   25%   17%
```

### ORBI Returns Scenario

```
Base Case Assumptions:
  Entry Revenue: $[X]M
  Revenue Growth: 20% Y1, 18% Y2, 15% Y3-5
  Exit EBITDA Margin: 12%
  Entry Multiple: 2.0x Revenue
  Exit Multiple: 10x EBITDA (or 2.5x Revenue)
  Hold Period: 5 years
  Leverage: 0-1x EBITDA (asset-light limits debt)

Returns:
  Entry EV: $[X]M
  Exit EV: $[X]M
  IRR: [X]%
  MOIC: [X]x
```

---

## 4. Value Creation Bridge

### Framework

```
ENTRY VALUE
  + Revenue growth
  + Margin expansion
  + Multiple expansion
  + Debt paydown
  - Dilution (if applicable)
= EXIT VALUE

Value Creation Breakdown (% of total):
  Organic growth:    [X]%
  Operational:       [X]%
  Multiple arbitrage: [X]%
  Financial engineering: [X]%
```

### ORBI Value Creation Levers

| Lever | Initiative | Value Impact | Timeline |
|-------|-----------|-------------|----------|
| **Revenue** | Amazon expansion (new categories) | +$2-5M/yr | 12-24 months |
| **Revenue** | New brand launches | +$1-3M/yr | 18-36 months |
| **Revenue** | International (Japan, EU) | +$1-5M/yr | 24-48 months |
| **Revenue** | B2B/wholesale growth (Faire, Target) | +$0.5-2M/yr | 6-18 months |
| **Margin** | COGS negotiation (volume discounts) | +2-5% GM | 12-24 months |
| **Margin** | Fulfillment optimization | +1-3% margin | 6-12 months |
| **Margin** | Marketing efficiency (lower CAC) | +2-5% margin | 6-18 months |
| **Margin** | Reduce platform fees (D2C mix shift) | +1-2% margin | 12-24 months |
| **Multiple** | Profitability demonstration | +1-2x multiple | 12-24 months |
| **Multiple** | Scale to $20M+ revenue | +0.5-1x | 24-36 months |

---

## 5. Deal Screening Framework

### Criteria Matrix

| Criterion | Must Have | Nice to Have |
|-----------|----------|-------------|
| Revenue | >$5M LTM | >$10M LTM |
| Growth | >10% YoY | >20% YoY |
| Gross Margin | >40% | >60% |
| EBITDA | Breakeven path | >10% margin |
| Category | Baby/kids/consumer | Adjacent wellness |
| Distribution | Amazon + DTC | Multi-channel |
| Brand | Registered TM | Strong reviews (4.5+) |
| IP/Moat | Unique product | Patent protection |
| Geography | US market | Multi-country |
| Team | Operational founder | Experienced management |

### Scoring Template

```
Target: [Company Name]
Date: [Screening Date]

| Category (Weight) | Score 1-5 | Weighted |
|-------------------|-----------|----------|
| Revenue Quality (20%) | [X] | [X] |
| Growth Profile (20%) | [X] | [X] |
| Margin Structure (15%) | [X] | [X] |
| Brand Strength (15%) | [X] | [X] |
| Competitive Position (10%) | [X] | [X] |
| Synergy Potential (10%) | [X] | [X] |
| Risk Profile (10%) | [X] | [X] |
| TOTAL | | [X]/5.0 |

Verdict: PASS (>3.5) / REVIEW (2.5-3.5) / DECLINE (<2.5)
```

---

## 6. Portfolio Monitoring KPIs

### Monthly Dashboard

| KPI | Frequency | Source | Alert Threshold |
|-----|-----------|--------|----------------|
| Revenue | Monthly | DataKeeper | <80% of plan |
| Gross Margin | Monthly | DataKeeper | <-5pp vs prior month |
| EBITDA | Monthly | Calculated | <plan or negative |
| CAC | Monthly | DataKeeper | >2x prior quarter avg |
| MER | Monthly | DataKeeper | >25% |
| LTV:CAC | Quarterly | Calculated | <2:1 |
| Cash Balance | Monthly | Bank statements | <3 months runway |
| Inventory Turns | Monthly | Manual | <3x annualized |
| Amazon BSR | Weekly | SP-API | >2x normal |
| Customer NPS | Quarterly | Surveys | <30 |

### Quarterly Board Deck (5 slides)

1. **Executive Summary**: Key metrics vs plan, highlights/lowlights
2. **Financial Performance**: P&L vs budget, revenue bridge
3. **Operational KPIs**: CAC, LTV, inventory, fulfillment
4. **Strategic Update**: Initiatives progress, pipeline
5. **Outlook & Risks**: Next quarter forecast, key concerns
