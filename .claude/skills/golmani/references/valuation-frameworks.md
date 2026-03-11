# Valuation Frameworks

Core methodologies for DCF, Trading Comps, Precedent Transactions, LBO, and Merger Models.
Adapted for DTC/e-commerce consumer brands.

---

## 1. DCF (Discounted Cash Flow)

### Steps

1. **Project Free Cash Flow (5 years)**
   - Revenue forecast: bottom-up (units x ASP by brand/channel) or top-down (growth rate)
   - COGS: SKU-level from DataKeeper or % of revenue
   - OpEx: fixed (rent, salaries) + variable (ad spend, fulfillment)
   - CapEx: minimal for asset-light DTC (inventory is working capital)
   - FCF = EBIT x (1-t) + D&A - CapEx - Change in NWC

2. **Determine Discount Rate (WACC)**
   - Cost of equity: CAPM or build-up method
   - For private companies: add size premium + company-specific risk
   - ORBI range: 15-20% (early-stage, Korea-to-US, multi-brand complexity)

3. **Calculate Terminal Value**
   - Perpetuity growth: FCF_n+1 / (WACC - g), g = 2-3%
   - Exit multiple: Terminal EBITDA x multiple (preferred for DTC)
   - Use both, show range

4. **Sensitivity Table (MANDATORY)**

   ```
               WACC
            14%   16%   18%   20%
   g=2.0%   $Xm   ...   ...   ...
   g=2.5%   ...   ...   ...   ...
   g=3.0%   ...   ...   ...   ...
   ```

### DTC/E-commerce Adjustments

- Use **Revenue multiples** if EBITDA negative or volatile
- **SDE (Seller's Discretionary Earnings)** for sub-$5M businesses: Net Income + owner comp + one-time expenses
- **Inventory = working capital**, not CapEx: model inventory turns (typically 4-6x for baby products)
- **Customer acquisition cost** as a "quasi-capex": amortize over customer lifetime

---

## 2. Trading Comps (Comparable Company Analysis)

### Steps

1. **Select comparable universe** (see industry-benchmarks.md for ORBI comps)
2. **Gather financial data**: Revenue, EBITDA, Net Income, growth rates
3. **Calculate multiples**: EV/Revenue, EV/EBITDA, P/E, EV/Gross Profit
4. **Apply appropriate multiple to ORBI metrics**

### Multiple Selection for DTC Brands

| Metric | When to Use | Typical Range (Baby/Consumer) |
|--------|-------------|-------------------------------|
| EV/Revenue | Pre-profit or high growth | 1.0-3.0x (mature), 3-8x (high growth) |
| EV/EBITDA | Profitable, stable | 8-15x |
| EV/Gross Profit | Variable OpEx, scaling | 2-5x |
| SDE Multiple | Small business (<$5M rev) | 3-5x |
| P/S (Price/Sales) | Public comp proxy | 1-4x |

### Adjustments

- **Growth adjustment**: Higher growth = higher multiple. Use PEG-like ratio.
- **Profitability adjustment**: Negative EBITDA -> use revenue or gross profit multiples only
- **Size discount**: ORBI is small vs public comps -> apply 20-40% size discount
- **Multi-brand premium**: Portfolio of 10 brands -> add 10-20% diversification premium

---

## 3. Precedent Transactions

### Steps

1. **Build transaction database** from industry-benchmarks.md
2. **Note deal context**: strategic vs financial buyer, auction vs bilateral
3. **Calculate implied multiples**: EV/Revenue, EV/EBITDA at transaction
4. **Apply control premium** (typically 20-40% over trading multiples)

### Key Adjustments

- **Timing**: Adjust for market conditions at time of deal
- **Synergies**: Strategic buyers pay more (synergy value)
- **Amazon aggregator multiples**: Different from traditional M&A (Thrasio era 3-5x SDE, post-correction 2-3x)

---

## 4. LBO Model

### Structure

```
Sources & Uses
  Sources: Senior Debt + Mezzanine + Equity
  Uses: Purchase Price + Fees + Working Capital

Operating Model (5 year)
  Revenue -> EBITDA -> Free Cash Flow -> Debt Paydown

Debt Schedule
  Senior: amortizing, SOFR + spread
  Mezzanine: PIK or cash pay
  Revolver: working capital facility

Returns Analysis
  IRR = f(entry multiple, exit multiple, hold period, debt paydown)
  MOIC = Exit Equity / Entry Equity
  Cash-on-Cash = Distributions / Invested
```

### ORBI-Specific LBO Considerations

- **Leverage capacity**: ORBI's asset-light model limits senior debt (no hard assets). Max 2-3x EBITDA.
- **Working capital**: Inventory-heavy (Korean imports), 60-90 day lead times
- **Growth CapEx**: Primarily marketing spend (treat as OpEx, not CapEx)
- **Exit options**: Strategic sale to larger consumer brand, Amazon aggregator, or IPO (unlikely at current scale)

### Returns Sensitivity

```
           Exit Multiple
         8x    10x   12x   15x
Entry
  8x    15%   22%   28%   35%   <- IRR
 10x    10%   17%   23%   30%
 12x     5%   12%   18%   25%
```

---

## 5. Merger Model (Accretion/Dilution)

### When ORBI is the Acquirer

1. Model standalone financials for both ORBI and target
2. Estimate synergies (cost savings, revenue upside, cross-sell)
3. Determine purchase price and financing (cash, stock, debt)
4. Pro-forma combined P&L
5. EPS accretion/dilution analysis

### When ORBI is the Target

1. Standalone valuation (from DCF + Comps above)
2. Synergy value to potential acquirers
3. Walk-away price vs deal price negotiation range
4. Fairness opinion range

### Synergy Categories for DTC Brand Acquisitions

| Type | Example | Confidence |
|------|---------|------------|
| Fulfillment consolidation | Share WBF warehouse, reduce per-unit shipping | High |
| Marketing efficiency | Shared Meta/Google ad accounts, audience overlap | Medium |
| Cross-sell | Grosmimi customers -> Naeiae products | Medium |
| Amazon account consolidation | Single seller account, better terms | Medium |
| Supply chain | Combined Korea sourcing, volume discounts | Low-Medium |

---

## Model Audit Checklist (check-model)

- [ ] All inputs colored blue, formulas black
- [ ] No hardcoded numbers in formula cells
- [ ] Balance sheet balances (Assets = L + E)
- [ ] Cash flow ties to balance sheet cash change
- [ ] Circular references resolved or flagged
- [ ] Sensitivity tables use DATA TABLE or manual inputs
- [ ] Terminal value is reasonable (% of total EV < 75%)
- [ ] Growth rates decelerate to terminal rate smoothly
- [ ] Tax rate applied correctly
- [ ] Discount rate applied to mid-year convention
