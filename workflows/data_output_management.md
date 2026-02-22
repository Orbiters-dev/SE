# Data Output Management

## Folder Structure

```
Data Storage/
  polar/           Polar Financial Model, Dashboard, Ads Classification
  cs/              Gorgias CS Templates
  influencer/      Affiliate FAQ, Notion Sync Reports
  marketing/       Klaviyo Dashboard, Keyword Volume
  export/          Export Document Summary + reference/FLT/
  misc/            Job Listings etc.
  _archive/        Old files (pre-reorganization)

.tmp/              Intermediate/disposable data (NOT final outputs)
  polar_data/      JSON feeds (q1-q13, kl1-kl2) for Polar tools
  facebook_ads.xlsx   Intermediate data for classify_polar_ads
```

## Naming Convention

All final Excel outputs follow this pattern:

```
{base_name}_{YYYY-MM-DD}_v{N}.xlsx
```

Examples:
- `cs_templates_2026-02-22_v1.xlsx` (first run today)
- `cs_templates_2026-02-22_v2.xlsx` (second run today)
- `financial_model_2026-02-23_v1.xlsx` (first run tomorrow)

Version auto-increments per day. No manual numbering needed.

## Tool → Output Mapping

| Tool | Workflow | Output |
|------|----------|--------|
| gorgias_cs_template_builder.py | cs | cs_templates_{date}_v{N}.xlsx |
| gmail_affiliate_faq_builder.py | influencer | affiliate_faq_{date}_v{N}.xlsx |
| sync_influencer_notion.py | influencer | sync_report_{date}_v{N}.xlsx |
| klaviyo_email_dashboard.py | marketing | klaviyo_dashboard_{date}_v{N}.xlsx |
| fetch_keyword_volume.py | marketing | keyword_volume_{date}_v{N}.xlsx |
| scrape_job_listings.py | misc | job_listings_{date}_v{N}.xlsx |
| polar_financial_model.py | polar | financial_model_{date}_v{N}.xlsx |
| polar_dashboard_builder.py | polar | dashboard_{date}_v{N}.xlsx |
| classify_polar_ads.py | polar | ads_classification_{date}_v{N}.xlsx |
| parse_export_documents.py | export | export_summary_{date}_v{N}.xlsx |
| apply_row_grouping.py | polar | financial_model_{date}_v{N}.xlsx |
| update_search_volume_model.py | polar | financial_model_{date}_v{N}.xlsx |

## Using output_utils.py

All tools import from `tools/output_utils.py`:

```python
# Versioned output (most tools)
from output_utils import get_output_path
path = get_output_path("cs", "cs_templates")
# → Data Storage/cs/cs_templates_2026-02-22_v1.xlsx

# Find latest existing file (for tools that read previous output)
from output_utils import get_latest_file
path = get_latest_file("polar", "financial_model")
# → Data Storage/polar/financial_model_2026-02-22_v3.xlsx (latest)

# Intermediate data (stays in .tmp/)
from output_utils import get_intermediate_path
path = get_intermediate_path("polar_data", "q10_influencer_orders.json")
# → .tmp/polar_data/q10_influencer_orders.json
```

## Rules

1. **Final Excel → Data Storage/{workflow}/**. Never save final outputs to `.tmp/`.
2. **Intermediate JSON → .tmp/**. Regenerable feeds stay in `.tmp/polar_data/`.
3. **Always use output_utils.py** when creating new tools. Never hardcode paths.
4. **Version increments per day**. Running a tool twice on the same day produces v1, v2.
