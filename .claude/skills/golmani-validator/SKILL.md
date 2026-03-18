# 검증이 -- KPI Data Validator

## Persona

골만이 Squad의 Associate Analyst. 데이터 품질 전문.
모든 KPI 산출물이 DataKeeper에서 나오기 전에 6-layer 검증을 수행한다.
숫자는 통과시키거나 플래그하되, 절대 고치지 않는다 (고치는 건 골만이 역할).

---

## When to Use This Skill

- KPI 리포트 생성 전 데이터 검증
- DataKeeper 채널 데이터 품질 체크
- 매출/광고비 이상치 탐지
- Cross-table 정합성 확인 (Shopify vs Amazon SP-API)
- Through-date 일관성 검증
- 자동화 파이프라인의 validation step

Trigger keywords: 검증이, 데이터 검증, data validation, schema check, anomaly detection, cross-validation, 이상치 탐지

---

## Architecture

```
DataKeeper (PG API)
    │
    ▼
kpi_validator.py (orchestrator)
    ├── L1: kpi_schemas.py   (Pandera schema validation)
    ├── L2: identity check   (gross - disc = net)
    ├── L3: coverage check   (brand/channel completeness)
    ├── L4: through-date     (cross-table date alignment)
    ├── L5: cross-table      (Amazon reconciliation, discount sanity)
    └── L6: kpi_anomaly.py   (MoM + IQR anomaly detection)
    │
    ▼
.tmp/validation_report.json
```

---

## Commands

| Command | Description |
|---------|-------------|
| `python tools/kpi_validator.py` | Validate all 7 core tables |
| `python tools/kpi_validator.py --table shopify_orders_daily` | Single table |
| `python tools/kpi_validator.py --report-only` | No exit code on failure |
| `python tools/kpi_validator.py --days 90` | Custom lookback period |

---

## Validation Layers

| Layer | Check | Fail Action |
|-------|-------|-------------|
| L1 Schema | Column types, nulls, value ranges (Pandera) | FAIL row |
| L2 Identity | `gross_sales - discounts = net_sales` (±$0.02) | FAIL row |
| L3 Coverage | All expected brands/channels present | WARN |
| L4 Through-date | All tables aligned to same cutoff | FAIL report |
| L5 Cross-table | Amazon reconciliation, discount rate ≤50% | WARN |
| L6 Anomaly | MoM >50% / <-30% with seasonal adjustment | WARN + flag |

---

## Tables Validated

| Table | Schema | Identity | Coverage |
|-------|--------|----------|----------|
| `shopify_orders_daily` | Yes | Yes | Brands + Channels |
| `amazon_sales_daily` | Yes | No | Amazon brands |
| `amazon_ads_daily` | Yes | No | Brand detection |
| `meta_ads_daily` | Yes | No | Brand detection |
| `google_ads_daily` | Yes | No | Brand detection |
| `ga4_daily` | Yes | No | N/A |
| `klaviyo_daily` | Yes | No | N/A |

---

## Output

`validation_report.json`:
```json
{
    "timestamp": "2026-03-18T10:00:00-08:00",
    "through_date": "2026-03-17",
    "overall_status": "PASS | WARN | FAIL",
    "tables_validated": 7,
    "total_rows": 27109,
    "table_results": { ... },
    "cross_table": { ... }
}
```

---

## Dependencies

```
pandera>=0.20
pandas>=2.0
```

---

## Tools

| File | Purpose |
|------|---------|
| `tools/kpi_validator.py` | Main orchestrator |
| `tools/kpi_schemas.py` | Pandera schema definitions |
| `tools/kpi_anomaly.py` | IQR + Z-score anomaly detection |

---

## Integration

Part of 골만이 Squad pipeline:
1. **검증이** validates → 2. **골만이** computes → 3. **포맷이** formats

GitHub Actions: `kpi_validator.yml` runs daily at PST 1:00 AM.
`kpi_weekly.yml` runs validation before report generation.
