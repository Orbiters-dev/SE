# Fetch Keyword Volume Workflow

## Objective
Retrieve keyword search volume data from Google and Amazon using DataForSEO API.

## Tool
`tools/fetch_keyword_volume.py`

## Required Environment
```
DATAFORSEO_LOGIN=<email>
DATAFORSEO_PASSWORD=<api_password>
```

## Commands

### Test Connection
```bash
python tools/fetch_keyword_volume.py --test
```

### Fetch Keyword Volume
```bash
# Both channels (default)
python tools/fetch_keyword_volume.py --keywords "keyword1,keyword2,keyword3"

# Google only
python tools/fetch_keyword_volume.py --keywords "keyword1,keyword2" --channel google

# Amazon only
python tools/fetch_keyword_volume.py --keywords "keyword1,keyword2" --channel amazon

# From file (one keyword per line)
python tools/fetch_keyword_volume.py --keywords-file keywords.txt

# JSON output (stdout)
python tools/fetch_keyword_volume.py --keywords "keyword1" --json

# Custom output path
python tools/fetch_keyword_volume.py --keywords "keyword1" --output .tmp/custom_path.xlsx
```

## Parameters
| Flag | Default | Description |
|------|---------|-------------|
| `--keywords` | - | Comma-separated keywords (max 1000) |
| `--keywords-file` | - | File with one keyword per line |
| `--channel` | `both` | `google`, `amazon`, or `both` |
| `--location` | `US` | Country code (US, UK, DE, FR, CA, AU, etc.) |
| `--output` | `.tmp/fetch_keyword_volume/keyword_volume_YYYY-MM-DD.xlsx` | Output Excel path |
| `--json` | false | Output raw JSON to stdout |
| `--test` | false | Test API connection only |

## Output Format (Excel)
- **Summary** sheet: Keyword | Google Volume | Amazon Volume | Google CPC | Google Competition
- **Google Detail** sheet: Full Google Ads data including monthly breakdown
- **Amazon Detail** sheet: Amazon search volume

## API Details

### Google Ads Search Volume (Live)
- Endpoint: `POST /v3/keywords_data/google_ads/search_volume/live`
- Rate limit: 12 requests/min
- Max keywords per request: 1,000
- Returns: search_volume, CPC, competition, monthly_searches (24 months)
- Cost: $0.075 per task

### Amazon Bulk Search Volume
- Endpoint: `POST /v3/dataforseo_labs/amazon/bulk_search_volume/live`
- Max keywords per request: 1,000
- Returns: search_volume (monthly average)
- Cost: $0.01/task + $0.0001/item
- Supported locations: US, UK, DE, FR, CA, AU, IN, IT, ES, MX, NL, SG

## Cost Estimate
- 100 keywords, both channels: ~$0.09
- 1,000 keywords, both channels: ~$0.19
- Account balance: Pay-as-you-go, starts with $1 free credit

## Notes
- Google may return null for very niche/new brand keywords
- Amazon has data even for small brands (e.g., "zezebaebae" = 74 searches)
- Keywords are auto-lowercased by the API
- Google returns 12 months of monthly search data by default
