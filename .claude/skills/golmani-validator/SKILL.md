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

## Architecture — Dual-AI Verification (Claude + Codex)

```
DataKeeper (PG API)
    │
    ▼
┌───────────────────────────────────────────┐
│  Claude 검증이 (1차 — 6-layer validation)  │
│  kpi_validator.py (orchestrator)           │
│    ├── L1: kpi_schemas.py (Pandera)        │
│    ├── L2: identity (gross - disc = net)   │
│    ├── L3: coverage (brand/channel)        │
│    ├── L4: through-date (alignment)        │
│    ├── L5: cross-table (reconciliation)    │
│    └── L6: kpi_anomaly.py (MoM + IQR)     │
│    → .tmp/validation_report.json           │
└────────────────┬──────────────────────────┘
                 │
                 ▼
┌───────────────────────────────────────────┐
│  Codex Verifier (2차 — 독립 재검증)         │
│  codex_auditor.py --domain kpi             │
│    ├── validation_report.json 읽기          │
│    ├── DataKeeper에서 직접 데이터 확인        │
│    ├── 6 layers 독립적으로 재검증             │
│    └── JSON verdict 반환                    │
└────────────────┬──────────────────────────┘
                 │
                 ▼
           결과 비교 → 불일치 시 재검증 루프
```

**Dual-AI 핵심:** Claude가 검증한 결과를 Codex가 다시 독립적으로 확인.
두 AI가 동의하면 PASS, 불일치하면 해당 항목 집중 재검토.

### Codex 검증 CLI
```bash
PYTHON="C:/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe"
WJ="C:/Users/wjcho/Desktop/WJ Test1"

# Claude 검증 후 Codex 독립 재검증
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain kpi --audit
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain kpi --audit --table shopify_orders_daily
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain kpi --health
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
1. **검증이** validates → 2. **Codex 독립 재검증** → 3. **골만이** computes → 4. **포맷이** formats

GitHub Actions: `kpi_validator.yml` runs daily at PST 1:00 AM.
`kpi_weekly.yml` runs validation before report generation.

### Dual-AI Validation Protocol

검증이 스킬 호출 시:
1. Claude `kpi_validator.py` 실행 → `validation_report.json`
2. Codex `codex_auditor.py --domain kpi --audit` 독립 실행
3. 양쪽 결과 비교:
   - 양쪽 PASS → 골만이에게 데이터 전달
   - 한쪽 FAIL → 불일치 항목 재검증
   - 양쪽 FAIL → CRITICAL, 데이터 소스 문제

## References

- `tools/kpi_validator.py` — Main orchestrator
- `tools/kpi_schemas.py` — Pandera schema definitions
- `tools/kpi_anomaly.py` — IQR + Z-score anomaly detection
- `tools/codex_auditor.py` — Codex CLI 독립 검증 래퍼 (kpi domain)

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
