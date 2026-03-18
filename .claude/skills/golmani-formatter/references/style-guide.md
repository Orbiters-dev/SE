# ORBI KPI Style Guide

## Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| HEADER_BG | #002060 | Dark blue headers, grand totals |
| SECTION_BG | #D6DCE4 | Light grey section headers |
| TOTAL_BG | #FFF2CC | Light yellow subtotals |
| NM_BG | #595959 | Dark grey "not measured" cells |
| OK_BG | #C6EFCE | Green status |
| WARN_BG | #FFF2CC | Yellow status |
| FAIL_BG | #FFC7CE | Red status |
| SUBTOTAL_BG | #D6E4F0 | Light blue brand subtotals |

## Font Rules

- Headers: Bold, white, 11pt
- Section headers: Bold, black, 11pt
- Channel-level rows: Italic, grey
- n.m cells: White, 8pt
- Normal data: 11pt

## Number Formats

- Currency: `#,##0` (no decimals for KPI)
- Percentage: `0.0%`
- Count: `#,##0`

## Layout

- Column A: 24px wide (labels)
- Data columns: 14px wide
- Freeze pane: Row 2, Column B
- Header row height: 42px

## Tab Naming Convention

- `KPI_할인율` - Discount rate analysis
- `KPI_광고비` - Ad spend analysis
- `KPI_시딩비용` - Seeding cost analysis
- `KPI_Amazon할인_상세` - Amazon discount detail
- `Data Status` - Data freshness status
- `Validation` - 검증이 validation results
- `Executive Summary` - Updated in-place
- `Summary` - D2C KPI section appended
