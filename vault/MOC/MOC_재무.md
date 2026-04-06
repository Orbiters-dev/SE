---
type: moc
domain: finance
agents: [golmani, auditor, cfo, kpi-monthly]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [finance, kpi, dcf, audit]
---

# MOC_재무

## 에이전트
- **golmani** — DCF/LBO/3-statement, 투자 분석 (openpyxl, python-pptx)
- **auditor** — AICPA/KICPA 이중 자격 독립 감사인
- **cfo** — Orchestrator (golmani → auditor loop, max 3회)
- **kpi-monthly** — KPI 월간 리포트 (run_kpi_monthly.py)

## CFO Harness 구조
```
CFO (Orchestrator)
  → golmani (Generator)
  → auditor (Evaluator)
  → REVISE 시 correction point 명시 → 루프
```
세션 파일: `.tmp/cfo_sessions/{session_id}/`

## KPI 탭 구조
- KPI_할인율, KPI_광고비, KPI_시딩비용
- KPI_Amazon할인_상세, COGS 분석
- Executive Summary, D2C KPI

## Projects
- [[project_ppc_sku_golmani]] — SKU-level margin + ASIN breakdown
