# Workflow: Influencer Data Sync (Google Sheets -> Notion)

## Objective

Read influencer data from Google Sheets (read-only) and sync key fields to a Notion database. Detects new records, changed records, and orphaned Notion records.

**Google Sheets is READ-ONLY** — this tool never modifies the spreadsheet.

---

## Prerequisites

### .env Required Keys

```
NOTION_API_TOKEN=ntn_xxx
INFLUENCER_SHEET_ID=1DPI_zxG6XiCliyi7Vw6YY_ojue4ZYor-vDX6EN7nUOY
INFLUENCER_SHEET_GID=1592924077
INFLUENCER_NOTION_DB_ID=30c86c6dc0468080a4e0d591414d733b
GOOGLE_SERVICE_ACCOUNT_PATH=credentials/google_service_account.json
```

### Notion Integration Setup (One-Time)

1. Go to https://www.notion.so/my-integrations
2. Create new integration (or use existing), copy the token
3. Open the target Notion database
4. Click `...` > Connections > Add the integration
5. Add token to `.env` as `NOTION_API_TOKEN`

### Google Service Account Setup (Required for Brand Tabs)

1. Go to https://console.cloud.google.com/
2. Select or create a project
3. APIs & Services > Enable **Google Sheets API**
4. Credentials > Create Service Account > Download JSON key
5. Save JSON file to `credentials/google_service_account.json`
6. Share the Google Sheet with the Service Account email (Viewer)
7. Set path in `.env` as `GOOGLE_SERVICE_ACCOUNT_PATH`

**Without Service Account**: Master DB tab is still accessible via CSV export (public link). Brand tabs require Service Account.

---

## How to Run

### Step 1: Discover Schemas (First Time / Debug)

```bash
python tools/sync_influencer_notion.py --discover
```

Shows:
- Notion database properties and their types
- Notion workspace users (for Owner field mapping)
- Google Sheets column headers
- Available brand tabs
- Existing Notion pages

### Step 2: Dry Run (Preview Changes)

```bash
python tools/sync_influencer_notion.py --dry-run --master-only
```

Or with brand tabs (requires Service Account):

```bash
python tools/sync_influencer_notion.py --dry-run
```

### Step 3: Execute Sync

```bash
python tools/sync_influencer_notion.py --sync --master-only
```

Or full sync with brand tabs:

```bash
python tools/sync_influencer_notion.py --sync
```

---

## Data Flow

### Sources

| Source | Tab | Data |
|--------|-----|------|
| Google Sheets | Master DB (GID: 1592924077) | Personal info: Full Name, Email, Social IDs, Date Discovered, Recent Rate |
| Google Sheets | Brand tabs (Grosmimi Cp, etc.) | Campaign data: Flight Period, Platform, Product, Status, Fee, Content links |

### Mapping (PPT-based)

| Google Sheets | Notion Property | Type | Notes |
|---------------|----------------|------|-------|
| Creator ID | Influencer ID \| Project (title) | title | Format: "handle - Full Name" |
| Date Discovered / Flight Period | Outreach Date | date | Earlier of the two |
| Tab name | Brand | multi_select | e.g., "Grosmimi Cp" -> "Grosmimi" |
| Platform | Platform | multi_select | |
| Deliverable Type | Platform (+Story) | multi_select | Adds "Story" if deliverable is story |
| Product | Product | multi_select | |
| PIC | Owner | people | Matched by name to Notion users |
| Status | Stage | status | Mapped via STAGE_MAP |
| Actual Upload | Deadline / Posted Date | date | |
| Content 1 | Posted Content Link | url | |
| Fee | Content Rate + Total Paid Amount | number | Same value in both |
| Repeat count | Collaboration Count | select | Auto-calculated |
| Recent Rate | Notes | rich_text | |

### Matching Strategy

Records are matched between systems by:
1. **Exact title match** (handle - full name)
2. **Handle match** (Instagram/TikTok handle appears in Notion title)
3. **Full name match** (name appears in Notion title, min 4 chars)
4. If no match -> CREATE new page
5. If matched -> UPDATE existing page

---

## Expected Output

- **Notion database**: Updated with synced records
- **`.tmp/sync_influencer_notion/sync_report_YYYY-MM-DD.xlsx`**: Report with tabs:
  - Created: New records added to Notion
  - Updated: Existing records modified
  - Orphans: Records in Notion but not in Sheets
  - Errors: Any failed operations

---

## CLI Flags

| Flag | Description |
|------|-------------|
| `--discover` | Show schemas from both systems |
| `--dry-run` | Preview changes without writing to Notion |
| `--sync` | Execute actual sync |
| `--master-only` | Only sync Master DB tab (skip brand tabs) |

---

## Edge Cases & Notes

- **Duplicate @ID columns**: Master DB has `@ID (link)` under TikTok, Instagram, YouTube. Tool prefixes them (e.g., `Instagram:@ID (link)`) to distinguish.
- **Owner field**: Requires Notion user ID. Tool matches PIC name to workspace members. Partial matching supported.
- **Contract / Script files**: Notion `files` type cannot be uploaded via API. Skipped.
- **Rate limiting**: Notion API limited to ~3 req/s. Tool waits 0.35s between writes with exponential backoff on 429.
- **Empty Creator IDs**: Rows without Creator ID are skipped.
- **C-197+ rows**: Many later rows in Master DB have only Creator ID (no name/handle). These sync with minimal data.
- **.env parse warnings**: Lines 24-26 in `.env` contain Python code — harmless but produces warnings.

---

## Lessons Learned

- Notion API `2022-06-28` is the stable version. No SDK needed — `requests` is sufficient.
- Google Sheets CSV export works without auth if sheet is shared publicly. Good fallback for read-only access.
- Multi-row headers (merged cells) in Google Sheets require special handling — category row + column name row.
- Brand tab detection uses keyword matching in tab names against known brand list.
