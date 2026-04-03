# JP PPC Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JP Amazon Ads data collection to `data_keeper.py`, create a JP PPC dashboard, and wire it into the Financial Dashboard.

**Architecture:** Extract a shared `_fetch_ads_profiles()` helper that queries both NA and FE Ads API endpoints, then thread `base_url` through report functions. Clone US PPC dashboard with JP-specific modifications (single brand, JPY, red theme). Add iframe tab to Financial Dashboard.

**Tech Stack:** Python (data_keeper.py), vanilla HTML/JS/CSS (dashboard), Amazon Ads Reporting API v3

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `tools/data_keeper.py` | Add `_fetch_ads_profiles()`, update 4 collectors + 2 report functions for JP |
| Create | `docs/jp-ppc-dashboard/index.html` | JP PPC dashboard (clone of US, single brand, JPY) |
| Modify | `docs/financial-dashboard/index.html` | Add JP PPC tab to `JP_TABS` + section div + iframe |

---

### Task 1: Add `_fetch_ads_profiles()` helper and constants

**Files:**
- Modify: `tools/data_keeper.py:227-231` (after PROFILE_BRAND_MAP)
- Modify: `tools/data_keeper.py:227` (extend PROFILE_BRAND_MAP)

- [ ] **Step 1: Add JP profile to PROFILE_BRAND_MAP**

In `tools/data_keeper.py`, replace the existing `PROFILE_BRAND_MAP` at line 227:

```python
PROFILE_BRAND_MAP = {
    "GROSMIMI USA": "Grosmimi",
    "Fleeters Inc": "Naeiae",
    "Orbitool": "CHA&MOM",
}
```

with:

```python
PROFILE_BRAND_MAP = {
    "GROSMIMI USA": "Grosmimi",
    "Fleeters Inc": "Naeiae",
    "Orbitool": "CHA&MOM",
    # JP — profile name may differ; add alias after console auth
    "GROSMIMI JP": "Grosmimi JP",
    "Grosmimi JP": "Grosmimi JP",
}
```

- [ ] **Step 2: Add regional endpoint constants and `_fetch_ads_profiles()` helper**

Insert after the updated `PROFILE_BRAND_MAP` block (after line ~233), before the DataForSEO section:

```python
# Amazon Ads API regional endpoints
ADS_ENDPOINTS = {
    "NA": "https://advertising-api.amazon.com",        # US, CA, MX, BR
    "FE": "https://advertising-api-fe.amazon.com",     # JP, AU, SG
}

# Countries to collect Ads data for
ADS_COLLECT_COUNTRIES = {"US", "JP"}


def _fetch_ads_profiles(headers, countries=None):
    """Fetch Amazon Ads profiles from all regional endpoints, filtered by country.

    Each returned profile dict gets an extra '_ads_base_url' key so callers
    know which regional endpoint to use for reports and campaign listing.
    """
    if countries is None:
        countries = ADS_COLLECT_COUNTRIES
    all_profiles = []
    for region, base_url in ADS_ENDPOINTS.items():
        try:
            resp = requests.get(f"{base_url}/v2/profiles",
                                headers=headers, timeout=30)
            resp.raise_for_status()
            for p in resp.json():
                if (p.get("countryCode") in countries
                        and p.get("accountInfo", {}).get("type") == "seller"):
                    p["_ads_base_url"] = base_url
                    all_profiles.append(p)
        except Exception as e:
            print(f"  [WARN] Ads profiles from {region} ({base_url}): {e}")
    return all_profiles
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tools/data_keeper.py
git commit -m "feat(datakeeper): add _fetch_ads_profiles helper with JP/FE endpoint support"
```

---

### Task 2: Thread `base_url` through report functions

**Files:**
- Modify: `tools/data_keeper.py:567-620` (`_fetch_amz_ads_report`)
- Modify: `tools/data_keeper.py:623-691` (`_fetch_amz_ads_report_generic`)

Both functions hardcode `advertising-api.amazon.com`. They need a `base_url` parameter.

- [ ] **Step 1: Update `_fetch_amz_ads_report` signature and URLs**

In `tools/data_keeper.py`, change the function at line 567.

Old signature:
```python
def _fetch_amz_ads_report(headers, profile_id, start, end,
                          ad_product="SPONSORED_PRODUCTS",
                          report_type_id="spCampaigns",
                          columns=None):
```

New signature:
```python
def _fetch_amz_ads_report(headers, profile_id, start, end,
                          ad_product="SPONSORED_PRODUCTS",
                          report_type_id="spCampaigns",
                          columns=None,
                          base_url="https://advertising-api.amazon.com"):
```

Replace the hardcoded URL on line 590:
```python
        r = requests.post(
            "https://advertising-api.amazon.com/reporting/reports",
```
with:
```python
        r = requests.post(
            f"{base_url}/reporting/reports",
```

Replace the hardcoded URL on line 602:
```python
            r2 = requests.get(
                f"https://advertising-api.amazon.com/reporting/reports/{report_id}",
```
with:
```python
            r2 = requests.get(
                f"{base_url}/reporting/reports/{report_id}",
```

- [ ] **Step 2: Update `_fetch_amz_ads_report_generic` signature and URLs**

Same pattern for function at line 623.

Old signature:
```python
def _fetch_amz_ads_report_generic(headers, profile_id, start, end,
                                   report_type_id, group_by, columns,
                                   time_unit="DAILY"):
```

New signature:
```python
def _fetch_amz_ads_report_generic(headers, profile_id, start, end,
                                   report_type_id, group_by, columns,
                                   time_unit="DAILY",
                                   base_url="https://advertising-api.amazon.com"):
```

Replace the hardcoded URL on line 651:
```python
                r = requests.post(
                    "https://advertising-api.amazon.com/reporting/reports",
```
with:
```python
                r = requests.post(
                    f"{base_url}/reporting/reports",
```

Replace the hardcoded URL on line 667:
```python
            r2 = requests.get(
                f"https://advertising-api.amazon.com/reporting/reports/{report_id}",
```
with:
```python
            r2 = requests.get(
                f"{base_url}/reporting/reports/{report_id}",
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tools/data_keeper.py
git commit -m "refactor(datakeeper): thread base_url through Ads report functions"
```

---

### Task 3: Update `collect_amazon_ads()` to use shared helper

**Files:**
- Modify: `tools/data_keeper.py:465-564` (`collect_amazon_ads`)

- [ ] **Step 1: Replace profile fetching with shared helper**

In `collect_amazon_ads()` at line 465, replace lines 468-476:

Old code:
```python
    headers = _fresh_amz_ads_headers()

    # 1. Get profiles
    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
    print(f"  Profiles: {len(profiles)}")
```

New code:
```python
    headers = _fresh_amz_ads_headers()

    # 1. Get profiles (US + JP)
    profiles = _fetch_ads_profiles(headers)
    print(f"  Profiles: {len(profiles)} (US+JP)")
```

- [ ] **Step 2: Update campaign name fetching to use regional endpoint**

In the campaign name loop (line ~480-498), the `requests.post` to `advertising-api.amazon.com/sp/campaigns/list` must use the profile's base_url. Replace:

```python
            r = requests.post(
                "https://advertising-api.amazon.com/sp/campaigns/list",
                headers=h, json={"maxResults": 5000}, timeout=20,
            )
```

with:

```python
            ads_base = p.get("_ads_base_url", "https://advertising-api.amazon.com")
            r = requests.post(
                f"{ads_base}/sp/campaigns/list",
                headers=h, json={"maxResults": 5000}, timeout=20,
            )
```

- [ ] **Step 3: Pass `base_url` to `_fetch_amz_ads_report` in the report loop**

In the report fetching loop (line ~535), the call to `_fetch_amz_ads_report` must pass `base_url`. Replace:

```python
                report_rows = _fetch_amz_ads_report(
                    h, pid, cur.isoformat(), chunk_end.isoformat(),
                    ad_product=ad_product, report_type_id=report_type_id,
                    columns=cols,
                )
```

with:

```python
                ads_base = p.get("_ads_base_url", "https://advertising-api.amazon.com")
                report_rows = _fetch_amz_ads_report(
                    h, pid, cur.isoformat(), chunk_end.isoformat(),
                    ad_product=ad_product, report_type_id=report_type_id,
                    columns=cols,
                    base_url=ads_base,
                )
```

- [ ] **Step 4: Verify syntax**

Run:
```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add tools/data_keeper.py
git commit -m "feat(datakeeper): collect_amazon_ads now fetches US + JP profiles"
```

---

### Task 4: Update `collect_amazon_ads_search_terms()` for JP

**Files:**
- Modify: `tools/data_keeper.py:694-750`

- [ ] **Step 1: Replace profile fetching**

Replace lines 697-703:

Old:
```python
    headers = _fresh_amz_ads_headers()

    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
```

New:
```python
    headers = _fresh_amz_ads_headers()
    profiles = _fetch_ads_profiles(headers)
```

- [ ] **Step 2: Pass `base_url` to `_fetch_amz_ads_report_generic`**

In the report loop (line ~720), replace:

```python
            rows = _fetch_amz_ads_report_generic(
                h, pid, cur.isoformat(), chunk_end.isoformat(),
                report_type_id="spSearchTerm",
                group_by=["searchTerm"],
                columns=["campaignId", "adGroupId", "keywordId",
                         "searchTerm", "impressions", "clicks", "cost",
                         "sales14d", "purchases14d"],
                time_unit="DAILY",
            )
```

with:

```python
            ads_base = p.get("_ads_base_url", "https://advertising-api.amazon.com")
            rows = _fetch_amz_ads_report_generic(
                h, pid, cur.isoformat(), chunk_end.isoformat(),
                report_type_id="spSearchTerm",
                group_by=["searchTerm"],
                columns=["campaignId", "adGroupId", "keywordId",
                         "searchTerm", "impressions", "clicks", "cost",
                         "sales14d", "purchases14d"],
                time_unit="DAILY",
                base_url=ads_base,
            )
```

- [ ] **Step 3: Verify syntax and commit**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
git add tools/data_keeper.py
git commit -m "feat(datakeeper): collect_amazon_ads_search_terms now includes JP"
```

---

### Task 5: Update `collect_amazon_ads_keywords()` for JP

**Files:**
- Modify: `tools/data_keeper.py:753-810`

- [ ] **Step 1: Replace profile fetching**

Replace lines 756-762:

Old:
```python
    headers = _fresh_amz_ads_headers()

    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
```

New:
```python
    headers = _fresh_amz_ads_headers()
    profiles = _fetch_ads_profiles(headers)
```

- [ ] **Step 2: Pass `base_url` to `_fetch_amz_ads_report_generic`**

In the report loop (line ~779), replace:

```python
            rows = _fetch_amz_ads_report_generic(
                h, pid, cur.isoformat(), chunk_end.isoformat(),
                report_type_id="spKeywords",
                group_by=["adGroup"],
                columns=["campaignId", "adGroupId", "keywordId",
                         "keywordText", "matchType",
                         "impressions", "clicks", "cost",
                         "sales14d", "purchases14d"],
                time_unit="DAILY",
            )
```

with:

```python
            ads_base = p.get("_ads_base_url", "https://advertising-api.amazon.com")
            rows = _fetch_amz_ads_report_generic(
                h, pid, cur.isoformat(), chunk_end.isoformat(),
                report_type_id="spKeywords",
                group_by=["adGroup"],
                columns=["campaignId", "adGroupId", "keywordId",
                         "keywordText", "matchType",
                         "impressions", "clicks", "cost",
                         "sales14d", "purchases14d"],
                time_unit="DAILY",
                base_url=ads_base,
            )
```

- [ ] **Step 3: Verify syntax and commit**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
git add tools/data_keeper.py
git commit -m "feat(datakeeper): collect_amazon_ads_keywords now includes JP"
```

---

### Task 6: Update `collect_amazon_campaigns()` for JP

**Files:**
- Modify: `tools/data_keeper.py:2449-2578`

This function is more complex — it uses separate headers per ad type (SP, SB, SD) and each has hardcoded URLs.

- [ ] **Step 1: Replace profile fetching**

Replace lines 2460-2470:

Old:
```python
    # Get profiles (needs standard content-type)
    profile_headers = {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.get("https://advertising-api.amazon.com/v2/profiles",
                        headers=profile_headers, timeout=30)
    resp.raise_for_status()
    profiles = [p for p in resp.json()
                if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller"]
```

New:
```python
    # Get profiles (US + JP)
    profile_headers = {
        "Amazon-Advertising-API-ClientId": AMZ_ADS_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    profiles = _fetch_ads_profiles(profile_headers)
```

- [ ] **Step 2: Add `ads_base` variable at start of profile loop**

After line `brand = PROFILE_BRAND_MAP.get(pname, pname)` (line ~2476), add:

```python
        ads_base = p.get("_ads_base_url", "https://advertising-api.amazon.com")
```

- [ ] **Step 3: Update SP campaigns URL**

Replace (line ~2488):
```python
                r = requests.post(
                    "https://advertising-api.amazon.com/sp/campaigns/list",
                    headers=h_sp, json=body, timeout=30,
                )
```

with:
```python
                r = requests.post(
                    f"{ads_base}/sp/campaigns/list",
                    headers=h_sp, json=body, timeout=30,
                )
```

- [ ] **Step 4: Update SB campaigns URL**

Replace (line ~2527):
```python
            r = requests.post(
                "https://advertising-api.amazon.com/sb/v4/campaigns/list",
                headers=h_sb, json={"maxResults": 100}, timeout=20,
            )
```

with:
```python
            r = requests.post(
                f"{ads_base}/sb/v4/campaigns/list",
                headers=h_sb, json={"maxResults": 100}, timeout=20,
            )
```

- [ ] **Step 5: Update SD campaigns URL**

Replace (line ~2561):
```python
            r = requests.get(
                "https://advertising-api.amazon.com/sd/campaigns",
                headers=h_sd, timeout=20,
            )
```

with:
```python
            r = requests.get(
                f"{ads_base}/sd/campaigns",
                headers=h_sd, timeout=20,
            )
```

- [ ] **Step 6: Verify syntax and commit**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "import ast; ast.parse(open('tools/data_keeper.py').read()); print('OK')"
git add tools/data_keeper.py
git commit -m "feat(datakeeper): collect_amazon_campaigns now includes JP"
```

---

### Task 7: Create JP PPC Dashboard

**Files:**
- Create: `docs/jp-ppc-dashboard/index.html`

This is a clone of `docs/ppc-dashboard/index.html` with JP modifications. The dashboard is 3,674 lines — we copy and modify key sections.

- [ ] **Step 1: Copy US PPC dashboard as base**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1"
mkdir -p docs/jp-ppc-dashboard
cp docs/ppc-dashboard/index.html docs/jp-ppc-dashboard/index.html
cp docs/ppc-dashboard/data.js docs/jp-ppc-dashboard/data.js
cp docs/ppc-dashboard/pl_data.js docs/jp-ppc-dashboard/pl_data.js
cp docs/ppc-dashboard/bt_data.js docs/jp-ppc-dashboard/bt_data.js
cp docs/ppc-dashboard/exec_log.json docs/jp-ppc-dashboard/exec_log.json
```

- [ ] **Step 2: Update title and branding**

In `docs/jp-ppc-dashboard/index.html`:

Replace:
```html
<title>Amazon PPC Intelligence Dashboard</title>
```
with:
```html
<title>Amazon JP PPC Intelligence Dashboard</title>
```

Replace (hero section, around line 218):
```html
  <h1>Amazon PPC <span>Intelligence</span></h1>
  <div class="sub">Data Pipeline, Backtest Engine & Optimization Output</div>
```
with:
```html
  <h1>Amazon JP PPC <span>Intelligence</span></h1>
  <div class="sub">🇯🇵 Japan Marketplace — Data Pipeline, Backtest Engine & Optimization Output</div>
```

Replace (login gate, around line 197):
```html
    <h2>Amazon PPC <span ...>Intelligence</span></h2>
```
with:
```html
    <h2>Amazon JP PPC <span style="background:linear-gradient(135deg,#ef4444,#f59e0b);-webkit-background-clip:text;-webkit-text-fill-color:transparent">Intelligence</span></h2>
```

- [ ] **Step 3: Update color theme from indigo to red**

In the CSS `:root` section (line 12), change the accent color:

Replace:
```css
--a:#6366f1;--abg:#eef2ff;
```
with:
```css
--a:#ef4444;--abg:#fef2f2;
```

- [ ] **Step 4: Update nav links to JP dashboards**

Replace the top-nav section (around line 208-215):

Old:
```html
    <div style="padding:8px 20px;background:#6366f1;color:#fff;cursor:default">Amazon PPC</div>
    <a href="../content-dashboard/index.html" ...>Content Intelligence</a>
    <a href="../pipeline-dashboard/index.html" ...>Pipeline CRM</a>
    <a href="../financial-dashboard/index.html" ...>Financial KPIs</a>
```

New:
```html
    <div style="padding:8px 20px;background:#ef4444;color:#fff;cursor:default">🇯🇵 Amazon JP PPC</div>
    <a href="../content-dashboard/index.html?region=jp" style="padding:8px 20px;color:#64748b;text-decoration:none;cursor:pointer;transition:.15s;display:flex;align-items:center" onmouseover="this.style.background='#fce7f3';this.style.color='#ec4899'" onmouseout="this.style.background='';this.style.color='#64748b'">Content Intelligence</a>
    <a href="../pipeline-dashboard-jp/index.html" style="padding:8px 20px;color:#64748b;text-decoration:none;cursor:pointer;transition:.15s;display:flex;align-items:center" onmouseover="this.style.background='#fef3c7';this.style.color='#f59e0b'" onmouseout="this.style.background='';this.style.color='#64748b'">Pipeline CRM</a>
    <a href="../financial-dashboard/index.html#jp" style="padding:8px 20px;color:#64748b;text-decoration:none;cursor:pointer;transition:.15s;display:flex;align-items:center" onmouseover="this.style.background='#ecfdf5';this.style.color='#10b981'" onmouseout="this.style.background='';this.style.color='#64748b'">Financial KPIs</a>
```

- [ ] **Step 5: Change to single brand (Grosmimi JP)**

Replace the brand arrays and selectors. Find `['Grosmimi','Naeiae','CHA&MOM']` (line ~1243) and replace all 3-brand references:

Replace:
```javascript
    ['Grosmimi','Naeiae','CHA&MOM'].forEach(function(brand){
```
with:
```javascript
    ['Grosmimi JP'].forEach(function(brand){
```

Find `BRAND_API_KEY` and `ACOS_TARGET` objects and update:

Replace (or add after existing):
```javascript
var BRAND_API_KEY = {'grosmimijp': 'Grosmimi JP'};
var ACOS_TARGET   = {'grosmimijp': 25};
```

Remove brand selector tabs in analytics section (around line 621). Replace the 3-brand tab div with a single fixed label:

```html
    <div style="padding:6px 16px;border-radius:6px;font-size:11px;font-weight:700;background:var(--abg);border:1px solid var(--a);color:var(--a)">🇯🇵 Grosmimi JP</div>
```

- [ ] **Step 6: Update currency formatting to JPY**

Find the `fmtN` or dollar-formatting functions and add JPY support. Search for `$` signs in template literals and update:

Add a currency helper at the top of the script section:
```javascript
var CURRENCY = '¥';
var CURRENCY_DECIMALS = 0; // JPY has no decimals
function fmtJPY(v) { return CURRENCY + Math.round(v).toLocaleString(); }
```

Replace `'$'+` formatting with `fmtJPY()` in key display areas (stats, charts, tables). Key locations:
- Stats display: `'$'+fmtN(spend7)` → `fmtJPY(spend7)`
- Chart Y-axis labels: `'$'+fmtN(maxSales/2/1000)+'K'` → `CURRENCY+fmtN(maxSales/2/1000)+'K'`

- [ ] **Step 7: Update API brand filter**

In `fetchLiveMetrics()` (line ~1221), the API calls fetch all brands. Add brand filter to the API URL:

Replace:
```javascript
      fetch(API_BASE+'/query/?table=amazon_ads_daily&limit=10000&date_from='+d30s, {mode:'cors'}),
```
with:
```javascript
      fetch(API_BASE+'/query/?table=amazon_ads_daily&limit=10000&date_from='+d30s+'&brand=Grosmimi+JP', {mode:'cors'}),
```

Same for sales:
```javascript
      fetch(API_BASE+'/query/?table=amazon_sales_daily&limit=5000&date_from='+d30s+'&brand=Grosmimi', {mode:'cors'}),
```

And campaigns:
```javascript
      fetch(API_BASE+'/query/?table=amazon_campaigns&limit=2000&brand=Grosmimi+JP', {mode:'cors'}),
```

- [ ] **Step 8: Commit**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1"
git add docs/jp-ppc-dashboard/
git commit -m "feat: create JP PPC dashboard (clone of US with JP modifications)"
```

---

### Task 8: Add JP PPC tab to Financial Dashboard

**Files:**
- Modify: `docs/financial-dashboard/index.html:153-160` (section divs)
- Modify: `docs/financial-dashboard/index.html:204-211` (JP_TABS array and _allSecs)

- [ ] **Step 1: Add section div for JP PPC iframe**

In `docs/financial-dashboard/index.html`, after line 153 (`<div id="sec-jp-amazon" ...>`), insert:

```html
<div id="sec-jp-ppc" style="display:none">
  <iframe id="ifr-jp-ppc" src="" style="width:100%;height:90vh;border:none;border-radius:12px;background:var(--bg)"></iframe>
</div>
```

- [ ] **Step 2: Add JP PPC tab to JP_TABS array**

Replace the `JP_TABS` array (lines 204-209):

Old:
```javascript
var JP_TABS = [
  {id:'jp-amazon',   label:'Amazon JP + 라쿠텐',   sec:'sec-jp-amazon',   ifr:null,              src:null,                                            color:'#ef4444'},
  {id:'jp-content',  label:'Content Intelligence', sec:'sec-jp-content',  ifr:'ifr-jp-content',  src:'../content-dashboard/index.html?embed=1&region=jp',       color:'#ec4899'},
  {id:'jp-pipeline', label:'Pipeline CRM',         sec:'sec-jp-pipeline', ifr:'ifr-jp-pipeline', src:'../pipeline-dashboard-jp/index.html?embed=1',   color:'#8b5cf6'},
  {id:'jp-fin',      label:'Financial KPIs',       sec:'sec-jp-fin',      ifr:null,              src:null,                                            color:'#10b981'}
];
```

New:
```javascript
var JP_TABS = [
  {id:'jp-amazon',   label:'Amazon JP + 라쿠텐',   sec:'sec-jp-amazon',   ifr:null,              src:null,                                            color:'#ef4444'},
  {id:'jp-ppc',      label:'Amazon PPC',           sec:'sec-jp-ppc',      ifr:'ifr-jp-ppc',      src:'../jp-ppc-dashboard/index.html?embed=1',        color:'#f97316'},
  {id:'jp-content',  label:'Content Intelligence', sec:'sec-jp-content',  ifr:'ifr-jp-content',  src:'../content-dashboard/index.html?embed=1&region=jp',       color:'#ec4899'},
  {id:'jp-pipeline', label:'Pipeline CRM',         sec:'sec-jp-pipeline', ifr:'ifr-jp-pipeline', src:'../pipeline-dashboard-jp/index.html?embed=1',   color:'#8b5cf6'},
  {id:'jp-fin',      label:'Financial KPIs',       sec:'sec-jp-fin',      ifr:null,              src:null,                                            color:'#10b981'}
];
```

- [ ] **Step 3: Add `sec-jp-ppc` to `_allSecs` array**

Replace the `_allSecs` line (line ~210):

Old:
```javascript
var _allSecs = ['sec-amazon-ppc','sec-content-intel','sec-pipeline-crm','sec-fin-kpis',
                'sec-jp-amazon','sec-jp-content','sec-jp-pipeline','sec-jp-fin'];
```

New:
```javascript
var _allSecs = ['sec-amazon-ppc','sec-content-intel','sec-pipeline-crm','sec-fin-kpis',
                'sec-jp-amazon','sec-jp-ppc','sec-jp-content','sec-jp-pipeline','sec-jp-fin'];
```

- [ ] **Step 4: Commit**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1"
git add docs/financial-dashboard/index.html
git commit -m "feat(financial-dashboard): add JP PPC tab with iframe embed"
```

---

### Task 9: Smoke test and verify

- [ ] **Step 1: Verify data_keeper.py loads without errors**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1" && python3 -c "
import sys; sys.path.insert(0, 'tools')
from env_loader import load_env; load_env()
from data_keeper import _fetch_ads_profiles, _fresh_amz_ads_headers, ADS_ENDPOINTS
headers = _fresh_amz_ads_headers()
profiles = _fetch_ads_profiles(headers)
for p in profiles:
    cc = p.get('countryCode','?')
    name = p.get('accountInfo',{}).get('name','?')
    base = p.get('_ads_base_url','?')
    print(f'{cc} | {name} | {base}')
print(f'Total: {len(profiles)} profiles')
"
```

Expected: US profiles listed (JP will appear after console auth). No errors.

- [ ] **Step 2: Open JP PPC dashboard locally**

```bash
cd "/c/Users/wjcho/Desktop/WJ Test1"
# On Windows, open in browser
start docs/jp-ppc-dashboard/index.html
```

Verify: Login gate appears with red theme, title says "Amazon JP PPC Intelligence".

- [ ] **Step 3: Open Financial Dashboard and check JP PPC tab**

```bash
start docs/financial-dashboard/index.html
```

Verify: Click 🇯🇵 JP → "Amazon PPC" tab appears between "Amazon JP + 라쿠텐" and "Content Intelligence".

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: smoke test fixes for JP PPC integration"
```
