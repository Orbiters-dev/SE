# JP PPC Integration Design

**Date:** 2026-04-03
**Status:** Approved
**Scope:** JP Amazon Ads collection + JP PPC dashboard + Financial Dashboard integration

---

## Context

JP (Grosmimi JP) sells on Amazon.co.jp but Ads data is not collected. The `data_keeper.py` collection pipeline hardcodes `countryCode == "US"` and uses only the NA endpoint (`advertising-api.amazon.com`). JP Ads requires the Far East endpoint (`advertising-api-fe.amazon.com`).

**Blocker:** JP Ads API access not yet authorized. The existing US Ads LWA app (`AMZ_ADS_CLIENT_ID`) needs JP marketplace authorization via Amazon Advertising Console. Code will be prepared so data flows immediately once authorized.

**Current state verified 2026-04-03:**
- CORS: already configured (`onzenna/middleware.py` + nginx)
- Credentials: SP-API JP creds in `~/.wat_secrets`, Ads API JP creds pending console auth
- Tables: no `amazon_jp_ppc_daily` table; JP data will go into existing `amazon_ads_daily` (differentiated by `profile_id`)
- US Ads profiles: `1094731557245186` (Grosmimi), `1766270639560191` (Naeiae), `2614055044199667` (CHA&MOM)
- JP Ads profiles: none yet (pending authorization)

---

## Part 1: `data_keeper.py` — JP Ads Collection

### Changes to 4 functions

All four Amazon Ads collection functions need the same pattern change:

| Function | Line | Purpose |
|----------|------|---------|
| `collect_amazon_ads()` | 465 | Campaign daily metrics |
| `collect_amazon_ads_search_terms()` | 694 | Search term reports |
| `collect_amazon_ads_keywords()` | 753 | Keyword-level reports |
| `collect_amazon_campaigns()` | 2449 | Campaign metadata |

### Pattern change

**Before (each function):**
```python
resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                    headers=headers, timeout=30)
profiles = [p for p in resp.json()
            if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
```

**After:**
```python
profiles = _fetch_ads_profiles(headers)
```

### New shared helper

```python
ADS_ENDPOINTS = {
    "NA": "https://advertising-api.amazon.com",       # US, CA, MX, BR
    "FE": "https://advertising-api-fe.amazon.com",     # JP, AU, SG
}

COLLECT_COUNTRIES = {"US", "JP"}  # Easy to extend later

def _fetch_ads_profiles(headers, countries=None):
    """Fetch Amazon Ads profiles from all regional endpoints, filtered by country."""
    if countries is None:
        countries = COLLECT_COUNTRIES
    all_profiles = []
    for region, base_url in ADS_ENDPOINTS.items():
        try:
            resp = requests.get(f"{base_url}/v2/profiles", headers=headers, timeout=30)
            resp.raise_for_status()
            for p in resp.json():
                if (p.get("countryCode") in countries
                        and p.get("accountInfo", {}).get("type") == "seller"):
                    p["_ads_base_url"] = base_url  # Tag for report fetching
                    all_profiles.append(p)
        except Exception as e:
            print(f"  [WARN] Ads profiles from {region}: {e}")
    return all_profiles
```

### Report fetching: regional endpoint awareness

`_fetch_amz_ads_report()` and `_fetch_amz_ads_report_generic()` currently hardcode `advertising-api.amazon.com`. After the change, they must use the profile's `_ads_base_url`.

**Change:** Pass `base_url` parameter (default `advertising-api.amazon.com` for backward compat) and use it for report submission + polling URLs.

### Brand mapping update

```python
PROFILE_BRAND_MAP = {
    "GROSMIMI USA": "Grosmimi",
    "Fleeters Inc": "Naeiae",
    "Orbitool": "CHA&MOM",
    # JP — profile name TBD after console auth; placeholder:
    "GROSMIMI JP": "Grosmimi JP",
}
```

JP brand is `"Grosmimi JP"` (not `"Grosmimi"`) to distinguish from US in the same table.

### Currency handling

JP Ads API returns spend/sales in JPY (no decimals). No schema change needed — `spend` and `sales` fields are `DecimalField(max_digits=12, decimal_places=2)` which handles both USD and JPY values. The dashboard will handle currency display.

---

## Part 2: `jp-ppc-dashboard/` — JP PPC Dashboard

### Location

`docs/jp-ppc-dashboard/index.html` — single-file dashboard (same pattern as US).

### Cloned from US with these modifications

| Aspect | US (`ppc-dashboard/`) | JP (`jp-ppc-dashboard/`) |
|--------|----------------------|--------------------------|
| Title | Amazon PPC Intelligence | Amazon JP PPC Intelligence |
| Brands | Grosmimi, Naeiae, CHA&MOM | Grosmimi JP (single brand) |
| Currency | USD ($) | JPY (¥), no decimals |
| API filter | `brand=Grosmimi` etc. | `brand=Grosmimi+JP` |
| Computed metrics | From API fields | Client-side: `acos = spend/sales*100`, `roas = sales/spend`, `cpc = spend/clicks`, `ctr = clicks/impressions*100` |
| Color theme | Indigo (#6366f1) | Red (#ef4444) — matches existing JP styling |
| Nav links | US dashboards | JP dashboards (content-dashboard?region=jp, pipeline-dashboard-jp, financial-dashboard) |
| Tabs | 6 tabs (Architecture, Config, Exec Log, Simulator, Live Analytics, System Admin) | Same 6 tabs |
| Data files | `data.js`, `pl_data.js`, `bt_data.js` | Same structure, JP data |
| embed mode | `?embed=1` hides nav | Same |

### Single-brand simplification

Since JP has only Grosmimi JP, the brand selector tabs are removed. All views render for the single brand directly.

---

## Part 3: Financial Dashboard — JP PPC Tab

### Change in `financial-dashboard/index.html`

Add JP PPC to the existing `JP_TABS` array:

```javascript
// Before
var JP_TABS = [
  {id:'jp-amazon', label:'Amazon JP + 라쿠텐', ...},
  {id:'jp-content', label:'Content Intelligence', ...},
  {id:'jp-pipeline', label:'Pipeline CRM', ...},
  {id:'jp-fin', label:'Financial KPIs', ...}
];

// After — insert at position 1
var JP_TABS = [
  {id:'jp-amazon', label:'Amazon JP + 라쿠텐', ...},
  {id:'jp-ppc', label:'Amazon PPC', icon:'⚡', iframe:'../jp-ppc-dashboard/index.html?embed=1'},
  {id:'jp-content', label:'Content Intelligence', ...},
  {id:'jp-pipeline', label:'Pipeline CRM', ...},
  {id:'jp-fin', label:'Financial KPIs', ...}
];
```

---

## Deployment sequence

1. **Code changes** (this PR): `data_keeper.py` + `jp-ppc-dashboard/` + `financial-dashboard/`
2. **Console auth** (manual): Authorize LWA app for JP Ads in Amazon Advertising Console
3. **Deploy** `data_keeper.py` to EC2 via `deploy_ec2.yml`
4. **Verify**: Run `data_keeper.py --channels amazon_ads` and confirm JP rows appear
5. **GitHub Pages**: Push dashboard files → auto-deploy to `orbiters-dev.github.io`

---

## Out of scope

- JP-specific bid optimization rules (future — needs JP ACOS targets)
- Rakuten Ads integration
- Additional JP brands beyond Grosmimi JP
- JP Ads API console authorization (manual step, not automatable)
