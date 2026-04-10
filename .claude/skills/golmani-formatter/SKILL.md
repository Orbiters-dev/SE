# 포맷이 -- KPI Report Formatter

## Persona

골만이 Squad의 Analyst. Excel 포맷팅 + 프레젠테이션 전문.
검증된 데이터를 클라이언트에게 보여줄 수 있는 수준으로 포맷팅한다.

---

## When to Use This Skill

- KPI Excel 포맷팅 (스타일, 차트, 조건부 서식)
- 클라이언트용 템플릿 적용 (executive / investor)
- Validation 결과를 Excel 탭으로 추가
- 기존 KPI 탭 스타일 수정

Trigger keywords: 포맷이, KPI 포맷, Excel 포맷, 클라이언트용, executive template, 프레젠테이션

---

## Architecture

```
검증이 output (.tmp/validation_report.json)
    │
    ▼
kpi_formatter.py (orchestrator)
    ├── add_validation_tab()    ← 검증이 결과 탭
    ├── kpi_style_engine.py     ← 통합 스타일 상수
    └── run_kpi_monthly.py      ← 기존 formatting 함수들 (점진적 마이그레이션)
    │
    ▼
Data Storage/kpi_reports/kpis_model_*.xlsx
```

---

## Commands

| Command | Description |
|---------|-------------|
| `python tools/kpi_formatter.py` | Full formatting |
| `python tools/kpi_formatter.py --template executive` | Executive-only tabs |
| `python tools/kpi_formatter.py --skip-legacy` | Skip legacy Polar tabs |
| `python tools/kpi_formatter.py --validation-report path/to/report.json` | Custom validation report |

---

## Templates

| Template | Tabs Included |
|----------|--------------|
| `full` | Data Status, Validation, KPI 할인율/광고비/시딩비용, Exec Summary, Amazon tabs, Sales/Ads/UE/Campaign/Influencer summaries, Legacy tabs |
| `executive` | Data Status, Validation, KPI 할인율/광고비/시딩비용, Exec Summary, Amazon tabs only |

---

## Style Guide

All styles defined in `tools/kpi_style_engine.py`:

| Element | Color | Font |
|---------|-------|------|
| Header row | #002060 (dark blue) | White, bold |
| Section header | #D6DCE4 (light grey) | Bold |
| Subtotal | #FFF2CC (yellow) | Bold |
| Grand total | #002060 (dark blue) | White, bold |
| n.m cell | #595959 (dark grey) | White, 8pt |
| OK status | #C6EFCE (green) | Default |
| WARN status | #FFF2CC (yellow) | Default |
| FAIL status | #FFC7CE (red) | Default |

---

## Tools

| File | Purpose |
|------|---------|
| `tools/kpi_formatter.py` | Main orchestrator + Validation tab |
| `tools/kpi_style_engine.py` | Centralized colors, fonts, fills, helpers |

---

## Integration

Part of 골만이 Squad pipeline:
1. **검증이** validates → 2. **골만이** computes → 3. **포맷이** formats

`run_kpi_monthly.py` main() now calls `format_kpi_report()` from this module.


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
