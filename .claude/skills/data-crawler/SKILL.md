---
name: data-crawler
description: "Large-scale spreadsheet extractor (50K+ rows). Use when: extracting filtered data from Google Sheets or local Excel, exporting subsets by column/value filters, natural language like 'JP 크리에이터만 뽑아줘' or '매출 100만 이상 추출'. Triggers: 데이터크롤러, 뽑아줘, 추출, 필터, 엑셀로, 시트에서, data crawler, spreadsheet extract, 데이터 뽑기"
---

# Data Crawler — Large Spreadsheet Filter & Extractor

## When to Use This Skill

- "5만 행 시트에서 JP 크리에이터만 뽑아줘"
- "이 엑셀에서 매출 100만 이상만 추출"
- "Sheet2에서 status=active인 것만 엑셀로"
- "Google Sheet에서 followers 1만 이상 US만"
- "데이터크롤러", "뽑아줘", "추출", "필터해서 엑셀로"
- Any large spreadsheet filtering/export task

## Architecture

```
User (Natural Language or CLI)
       │
       ▼
  Claude (This Skill)
  - Interprets intent
  - Maps to CLI params
       │
       ▼
  tools/data_crawler.py
  - Read source (Google Sheet / Excel)
  - Apply filters
  - Select columns
  - Stream-write Excel output
       │
       ▼
  .tmp/data_crawler/output/*.xlsx
```

## Core Tool

**`tools/data_crawler.py`**

### Input Sources
| Prefix | Source | Example |
|--------|--------|---------|
| `sheet:` | Google Sheets (ID or URL) | `--source "sheet:1dIAh..."` |
| `file:` | Local Excel (.xlsx) | `--source "file:data.xlsx"` |

### Filter Operators (AND logic)
| Op | Meaning | Example |
|----|---------|---------|
| `=` | Equals (case-insensitive) | `region=JP` |
| `!=` | Not equals | `status!=inactive` |
| `>` `<` `>=` `<=` | Numeric comparison | `sales>1000000` |
| `~` | Contains (case-insensitive) | `name~grosmimi` |
| `^` | Regex match | `email^.*@gmail` |

Multiple filters: `--filter "region=JP,sales>1000000,status=active"` (all must pass)

### Options
| Flag | Purpose |
|------|---------|
| `--columns "name,email"` | Select specific columns ("all" = default) |
| `--sheet-name "Tab2"` | Specific tab (default: first tab) |
| `--dry-run` | Preview: row count + 5 sample rows, no file output |
| `--no-cache` | Force re-download from Google Sheets |
| `--list-tabs` | Show available tab names |
| `--clear-cache` | Delete all cached data |
| `--output "result.xlsx"` | Custom output filename |

## Natural Language → CLI Mapping

When user speaks naturally, map intent to params:

| User says | Maps to |
|-----------|---------|
| "이 시트에서" + URL/ID | `--source "sheet:..."` |
| "이 엑셀에서" + path | `--source "file:..."` |
| "JP만", "일본 크리에이터" | `--filter "region=JP"` |
| "매출 100만 이상" | `--filter "sales>=1000000"` |
| "이름, 이메일만 뽑아줘" | `--columns "name,email"` |
| "Sheet2에서" | `--sheet-name "Sheet2"` |
| "미리 보여줘", "몇 개야" | `--dry-run` |
| "다시 다운로드" | `--no-cache` |

## Step-by-Step Execution

1. Identify source (Google Sheet URL/ID or file path)
2. If unsure about tab/column names → run `--list-tabs` or `--dry-run` first
3. Map filters from natural language to `--filter` syntax
4. Map column selection to `--columns`
5. Run: `python tools/data_crawler.py [params]`
6. Report: row count + output file path

## Commands

```bash
# Basic: JP creators from Google Sheet
python tools/data_crawler.py \
  --source "sheet:1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o" \
  --filter "region=JP" \
  --columns "Username,Email,region,followers" \
  --output "jp_creators.xlsx"

# Dry run: preview filter results
python tools/data_crawler.py \
  --source "sheet:SHEET_ID" \
  --filter "sales>1000000" \
  --dry-run

# Local Excel with multiple filters
python tools/data_crawler.py \
  --source "file:Data Storage/exports/data.xlsx" \
  --filter "status=active,region=US,followers>=10000"

# List tabs
python tools/data_crawler.py --source "sheet:SHEET_ID" --list-tabs

# Force re-download
python tools/data_crawler.py --source "sheet:SHEET_ID" --filter "region=JP" --no-cache

# Clear all cache
python tools/data_crawler.py --clear-cache
```

## Output

- Default: `.tmp/data_crawler/output/output_YYYYMMDD_HHMMSS.xlsx`
- Custom: `.tmp/data_crawler/output/{--output value}.xlsx`
- Cache: `.tmp/data_crawler/cache/cache_{sheet_id}_{tab}.json`

## Performance Notes

- **Google Sheets 50K rows**: ~10-30s download, ~20-30MB JSON cache. Second run instant from cache.
- **Local Excel 50K rows**: True streaming (read_only + iter_rows). Memory: ~50MB peak.
- **Write**: write_only mode, streams row-by-row to disk.
- Progress logged every 5,000 rows.

## Error Recovery

| Error | Fix |
|-------|-----|
| 503 from Google Sheets | Auto-retries 3x (30/60/90s backoff) |
| Column not found | Check spelling, run `--dry-run` to see available columns |
| Tab not found | Run `--list-tabs` to see available tabs |
| No rows match | Check filter values — try `--dry-run` first |
| Stale cache | Add `--no-cache` to force re-download |
| Memory issue | Local Excel is streaming; Google Sheets requires one-time full load (gspread limit) |

## Credentials

- Google Sheets: `credentials/google_service_account.json` (auto-loaded)
- Local Excel: no credentials needed
- Env loader: `tools/env_loader.py` (auto-import)


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
