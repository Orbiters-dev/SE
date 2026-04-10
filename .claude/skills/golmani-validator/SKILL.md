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

---

## L7: Financial Dashboard Cross-Check (generate_fin_data.py)

Financial Dashboard P&L 생성 후 자동 검증. KPI 리포트와 일관성 확인.

### 체크 항목

| Check | Rule | Threshold |
|-------|------|-----------|
| Revenue = Gross | `total_revenue` must use `gross_sales` not `net_sales` | Shopify gross > net by 5%+ |
| COGS/Gross ratio | 각 월 30-40% 범위 | <25% = partial month 의심, >45% = revenue 분모 오류 |
| Amazon Ads backfill | Jun-Nov 2025 Amazon Ads > $0 | $0이면 backfill 누락 |
| Influencer costs | 모든 월 >$0 (최소 shipping) | $0 = PR order 미반영 |
| FY합계 = 12개월 | FY2025 months count = 12 | <12 = Jan-May 누락 |
| Discount/Revenue ratio | 10-20% 범위 | <5% = disc 미반영, >30% = 과대 |
| KPI cross-match | Dashboard Rev vs KPI Rev ±5% | 5%+ 차이 = 데이터 소스 불일치 |

### 자동 실행 방법

`generate_fin_data.py` 실행 후 검증:
```bash
python tools/kpi_validator.py --table shopify_orders_daily --table amazon_sales_daily
python tools/validate_fin_data.py  # P&L output validation (planned)
```

### 오답노트 기반 규칙 (M-066~M-069)

이 규칙들은 실제 발생한 버그에서 추출됨. 반드시 체크:

1. **M-066**: Revenue가 net으로 들어가면 COGS% 40%+로 뻥튀기. gross_sales 필드 확인 필수.
2. **M-067**: COGS 비교는 SKU 바코드 1:1 매칭. 카테고리 평균은 오판 유발.
3. **M-068**: Dashboard 수정 시 `run_kpi_monthly.py`의 `analyze_discounts()`, `analyze_seeding_cost()` 로직 참조 필수.
4. **M-069**: `--months` 파라미터가 FY 전체를 커버하는지 확인. 기본 9개월이면 Jan-May 누락.


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
