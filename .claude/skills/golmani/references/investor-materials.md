# Investor Materials -- Templates & Guidelines

Templates for pitch decks, CIMs, teasers, process letters, and other IB deliverables.
Adapted for ORBI's DTC/e-commerce multi-brand business.

---

## 1. Pitch Deck (10-15 Slides)

### Standard IB Pitch Deck Flow

| Slide # | Title | Content | Data Source |
|---------|-------|---------|-------------|
| 1 | Cover | Company name, tagline, date, confidential | Static |
| 2 | Executive Summary | 3-5 bullet investment highlights | Synthesized |
| 3 | Company Overview | Business description, entity structure, brands | orbi-business-context.md |
| 4 | Market Opportunity | TAM/SAM/SOM, market growth, trends | industry-benchmarks.md + web research |
| 5 | Brand Portfolio | 10 brands, revenue share, GM% by brand | DataKeeper |
| 6 | Product Showcase | Hero products, pricing, unique features | Product catalog |
| 7 | Channel Strategy | D2C + Amazon + B2B, channel economics | DataKeeper + orbi-business-context.md |
| 8 | Financial Performance | Revenue trend, GM%, EBITDA (or path to) | DataKeeper + run_kpi_monthly |
| 9 | Unit Economics | CAC, LTV, payback, MER, ROAS | DataKeeper (calculated) |
| 10 | Growth Strategy | New brands, new channels, international | Management input |
| 11 | Competitive Positioning | vs key competitors, moat | industry-benchmarks.md |
| 12 | Financial Projections | 3-5 year forecast, key assumptions | Model output |
| 13 | Valuation | Football field (DCF + Comps + Precedent) | valuation-frameworks.md |
| 14 | Transaction Overview | Deal structure, timeline, use of proceeds | Deal-specific |
| 15 | Appendix | Supporting data, detailed financials | All sources |

### Slide Design Guidelines (python-pptx)

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Standard dimensions
SLIDE_WIDTH = Inches(13.333)   # Widescreen 16:9
SLIDE_HEIGHT = Inches(7.5)

# Color palette
NAVY = RGBColor(0x00, 0x2B, 0x5C)      # Headers, titles
DARK_GRAY = RGBColor(0x33, 0x33, 0x33)  # Body text
ACCENT_BLUE = RGBColor(0x00, 0x7B, 0xC0) # Highlights
ACCENT_GREEN = RGBColor(0x00, 0x96, 0x4B) # Positive metrics
ACCENT_RED = RGBColor(0xCC, 0x00, 0x00)   # Negative metrics
LIGHT_GRAY = RGBColor(0xF2, 0xF2, 0xF2)  # Table alternating

# Typography
TITLE_FONT = 'Calibri'
TITLE_SIZE = Pt(28)
SUBTITLE_SIZE = Pt(18)
BODY_SIZE = Pt(12)
FOOTNOTE_SIZE = Pt(8)
```

### Key Chart Types

| Data | Chart | Notes |
|------|-------|-------|
| Revenue trend | Stacked bar (by brand) + line (total) | Monthly or quarterly |
| Channel mix | Donut chart | D2C vs Amazon vs B2B % |
| Margin waterfall | Waterfall chart | Revenue → GM → CM → EBITDA |
| Competitive position | Bubble chart (growth vs margin) | Size = revenue |
| Valuation range | Football field (horizontal bar) | DCF, Comps, Precedent ranges |

---

## 2. CIM (Confidential Information Memorandum) -- 40-60 Pages

### Chapter Structure

| Chapter | Pages | Content |
|---------|-------|---------|
| **I. Executive Summary** | 3-5 | Investment highlights, key metrics, transaction overview |
| **II. Company Overview** | 5-8 | History, mission, entity structure, management team |
| **III. Brand Portfolio** | 8-12 | Each brand: products, pricing, GM%, growth trajectory |
| **IV. Market Analysis** | 5-8 | TAM/SAM/SOM, competitive landscape, industry trends |
| **V. Operations** | 5-8 | Supply chain (Korea→US), fulfillment (WBF), tech stack |
| **VI. Sales & Marketing** | 5-8 | Channel strategy, ad performance, customer acquisition |
| **VII. Financial Overview** | 8-12 | Historical P&L, balance sheet, cash flow, KPIs |
| **VIII. Growth Opportunities** | 3-5 | New products, new channels, international expansion |
| **IX. Financial Projections** | 5-8 | 3-5 year model, assumptions, sensitivity |
| **X. Transaction Structure** | 2-3 | Proposed terms, timeline, process |
| **Appendices** | 5-10 | Detailed financials, product catalog, org chart |

### CIM Writing Standards

- **Tone**: Professional, factual, forward-looking but grounded
- **Data citation**: Every metric must cite its source (DataKeeper, management, industry report)
- **Risk factors**: Include but frame constructively (risk → mitigation strategy)
- **Projections**: Conservative base case, upside scenario, clearly label assumptions
- **Confidentiality**: Header/footer with "CONFIDENTIAL" watermark
- **Formatting**: Consistent fonts, page numbers, table of contents, section dividers

---

## 3. Teaser (1-2 Pages)

### Anonymous Teaser Template

```
[CONFIDENTIAL]

Investment Opportunity -- [Code Name]

OVERVIEW
- Leading Korean baby products company with US market presence
- Multi-brand portfolio spanning [N] categories
- DTC (Shopify) + Amazon + B2B distribution

KEY METRICS (LTM)
- Revenue: $[X]M
- Gross Margin: [X]%
- Revenue Growth: [X]% YoY
- [N] brands, [N]+ SKUs

INVESTMENT HIGHLIGHTS
1. Premium positioning in growing baby products market
2. Multi-brand portfolio with shared infrastructure
3. Dual-channel (DTC + Amazon) reduces platform dependency
4. Proven unit economics (LTV:CAC > [X]:1)
5. Significant growth runway (new brands, channels, geographies)

TRANSACTION OVERVIEW
- Seeking: [Strategic partner / Growth equity / Full acquisition]
- Timeline: [Process timeline]

Contact: [Advisor name and email]
```

### Named Teaser Additions

- Company name: Orbiters Co., Ltd. / ORBI
- Hero brand: Grosmimi (PPSU baby cups)
- Website: zezebaebae.com (Onzenna storefront)
- Specific financial ranges (with management approval)

---

## 4. Process Letter

### Standard M&A Process Letter Template

```
[Date]
[Recipient Name]
[Recipient Company]

Re: Project [Code Name] -- Invitation to Participate

Dear [Name],

We are writing on behalf of our client, [ORBI / Code Name], to invite
[Recipient Company] to participate in a process to evaluate strategic
alternatives for the Company.

COMPANY OVERVIEW
[2-3 paragraph summary]

PROCESS TIMELINE
- Phase 1: Initial Indications of Interest (IOI) due [Date]
- Phase 2: Management presentations and site visits [Date range]
- Phase 3: Final bids due [Date]
- Phase 4: Exclusivity and closing [Date]

INFORMATION REQUEST
Interested parties should submit:
1. Preliminary valuation range
2. Proposed transaction structure
3. Financing plan
4. Key due diligence items
5. Anticipated timeline to close

NEXT STEPS
To receive the Confidential Information Memorandum, please execute
the attached Non-Disclosure Agreement and return to [contact].

Sincerely,
[Advisor]
```

---

## 5. Data Pack (Supporting Exhibits)

### Standard Exhibit List

| Exhibit | Content | Source |
|---------|---------|--------|
| A | Monthly P&L (trailing 24 months) | DataKeeper + run_kpi_monthly |
| B | Revenue by Brand (monthly) | shopify_orders_daily + amazon_sales_daily |
| C | Revenue by Channel (monthly) | DataKeeper (channel classification) |
| D | Ad Spend by Platform (monthly) | meta/google/amazon_ads_daily |
| E | Unit Economics Summary | Calculated from DataKeeper |
| F | Top 20 SKUs by Revenue | shopify_orders_daily |
| G | Customer Cohort Analysis | shopify_orders_daily (repeat purchase) |
| H | Amazon Performance Dashboard | amazon_sales_daily + amazon_ads_daily |
| I | Inventory Summary | Manual (not in DataKeeper) |
| J | Organization Chart | Manual |

---

## 6. IC Memo (Quick Reference)

See `due-diligence-playbook.md` for full IC memo template.

Quick structure:
1. **Deal Overview** (1 page): Target, price, structure, timeline
2. **Investment Thesis** (1-2 pages): Why this deal, key drivers
3. **Financial Analysis** (2-3 pages): Historical + projected, returns
4. **Risk Assessment** (1-2 pages): Key risks + mitigants
5. **Recommendation** (0.5 page): Approve / Decline / Conditional

---

## 7. Strip Profile

### Format

One-page summary per comparable company or target, used in buyer lists or comps analysis.

```
COMPANY: [Name]
TICKER/STATUS: [Public/Private]
HQ: [Location]
REVENUE: $[X]M (LTM)
EBITDA: $[X]M ([X]% margin)
GROWTH: [X]% YoY
EV: $[X]M
EV/REVENUE: [X]x
EV/EBITDA: [X]x

DESCRIPTION:
[2-3 sentences on business model, products, channels]

RELEVANCE TO ORBI:
[1-2 sentences on why this is a relevant comp or buyer]
```

---

## 8. Output Conventions

| Deliverable | Tool | Format | Location |
|-------------|------|--------|----------|
| Pitch deck | python-pptx | .pptx | `Data Storage/` |
| CIM | python-pptx or markdown→PDF | .pptx / .md | `Data Storage/` |
| Teaser | Markdown or python-pptx | .md / .pptx | `Data Storage/` |
| Process letter | Markdown | .md | `Data Storage/` |
| Data pack | openpyxl | .xlsx | `Data Storage/` |
| IC memo | Markdown | .md | `Data Storage/` |
| Strip profiles | openpyxl | .xlsx | `Data Storage/` |

**Never** save final deliverables to `.tmp/`. Use `.tmp/` only for processing intermediates.
