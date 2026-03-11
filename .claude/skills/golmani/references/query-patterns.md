# Query Patterns -- Natural Language Routing Guide

Maps common user questions to the correct analytical approach, data sources, and reference documents.

---

## Valuation Queries

| User Says | Approach | Data Sources | Reference |
|-----------|----------|-------------|-----------|
| "ORBI 밸류에이션 해줘" | Revenue multiples + DCF | DataKeeper (revenue), industry-benchmarks (multiples) | valuation-frameworks.md |
| "DCF 모델 만들어줘" | 5yr DCF with terminal value | DataKeeper (historical), user (growth assumptions) | valuation-frameworks.md |
| "LBO 모델 돌려봐" | Leveraged buyout returns | DataKeeper (EBITDA proxy), user (debt terms) | valuation-frameworks.md |
| "Comps 테이블 만들어줘" | Trading comps + precedent | Web search (public data), industry-benchmarks | valuation-frameworks.md + industry-benchmarks.md |
| "기업가치가 얼마야?" | Football field (multi-method) | All of the above | valuation-frameworks.md |
| "멀티플 몇 배 적용해야해?" | EV/Revenue or EV/EBITDA range | industry-benchmarks (comps) | industry-benchmarks.md |

---

## Financial Analysis Queries

| User Says | Approach | Data Sources | Reference |
|-----------|----------|-------------|-----------|
| "그로미미 유닛이코노믹스" | CAC, LTV, payback, GM per unit | DataKeeper (COGS, ad spend, orders) | financial-statements.md |
| "P&L 만들어줘" | Income Statement by brand/channel | DataKeeper (all tables) | financial-statements.md |
| "공헌이익 분석" | CM1, CM2, CM3 waterfall | DataKeeper + run_kpi_monthly output | financial-statements.md |
| "매출 트렌드 분석" | Monthly revenue by brand/channel | shopify_orders_daily + amazon_sales_daily | financial-statements.md |
| "CAC 얼마야?" | Total ad spend / new customers | meta_ads + google_ads + amazon_ads + orders | financial-statements.md |
| "LTV 계산해줘" | Cohort-based or simplified | shopify_orders_daily (repeat purchase) | financial-statements.md |
| "COGS 구조 분석" | SKU-level cost breakdown | run_kpi_monthly (685 SKU map) | financial-statements.md |
| "마진 분석해줘" | GM%, CM%, Net margin by layer | All DataKeeper tables | financial-statements.md |

---

## Investor Materials Queries

| User Says | Approach | Data Sources | Reference |
|-----------|----------|-------------|-----------|
| "피치덱 만들어줘" | 12-slide IB pitch deck | All ORBI data + market research | investor-materials.md |
| "CIM 만들어줘" | 40-60 page confidential info memo | All ORBI data + competitive analysis | investor-materials.md |
| "티저 만들어줘" | 1-2 page investment teaser | Summary financials + highlights | investor-materials.md |
| "IR 자료 만들어줘" | Investor Relations deck | DataKeeper + financial model | investor-materials.md |
| "데이터팩 정리해줘" | Supporting exhibits package | All available data organized | investor-materials.md |
| "프로세스 레터 작성" | M&A process letter to buyers | Deal terms + timeline | investor-materials.md |
| "덱 검토해줘" | Review existing pitch deck | User-provided file | investor-materials.md |

---

## Due Diligence & PE Queries

| User Says | Approach | Data Sources | Reference |
|-----------|----------|-------------|-----------|
| "실사 체크리스트 만들어줘" | DD checklist (6 categories) | ORBI context + standard DD | due-diligence-playbook.md |
| "IC 메모 작성해줘" | Investment committee memo | All financials + thesis | due-diligence-playbook.md |
| "IRR 계산해줘" | Returns analysis (IRR/MOIC/CoC) | Cash flow projections | valuation-frameworks.md |
| "딜 스크리닝 해줘" | Evaluate acquisition target | Target data + criteria | due-diligence-playbook.md |
| "바이어 리스트 만들어줘" | Potential acquirers list | Industry research | industry-benchmarks.md |
| "가치 창출 계획" | Value creation bridge | Operational KPIs + projections | due-diligence-playbook.md |

---

## Market & Competitive Queries

| User Says | Approach | Data Sources | Reference |
|-----------|----------|-------------|-----------|
| "경쟁사 분석해줘" | Competitive positioning map | Web research + benchmarks | industry-benchmarks.md |
| "시장 규모 알려줘" | TAM/SAM/SOM analysis | Industry reports, web search | industry-benchmarks.md |
| "벤치마크 비교" | ORBI vs industry averages | DataKeeper + benchmarks | industry-benchmarks.md |
| "섹터 오버뷰" | Industry overview deck | Market research | industry-benchmarks.md |

---

## Query Scoping Rules

1. **Always clarify scope first:** brand-level vs company-level? Which time period?
2. **Default time range:** Latest 12 months (LTM) unless user specifies
3. **Default currency:** USD
4. **When data is missing:** State it explicitly, provide range estimate, never fabricate
5. **Sensitivity analysis:** Include by default for any valuation or projection
6. **Source citation:** Every number must reference its source (DataKeeper table, user input, web research, or assumption)
