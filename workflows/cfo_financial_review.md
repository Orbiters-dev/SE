# CFO Financial Review Workflow

## Objective

골만이(재무 모델링 VP)의 산출물을 CFO가 독립 감사관(AICPA/KICPA)을 통해 검증하고,
숫자 불일치 시 수정을 지시하는 하네스 구조 재무 검토 프로세스.

**핵심 원칙**: 생성(Golmani)과 검증(Auditor)을 분리한다.
골만이에게 자기 결과를 스스로 검토하게 하지 않는다 — 항상 별도의 감사관이 독립적으로 검증.

Reference: https://www.anthropic.com/engineering/harness-design-long-running-apps

---

## When to Use

- 골만이가 P&L, 3-statement, DCF 등 중요 재무 모델을 만들었을 때
- 재무 데이터의 내부 정합성 확인이 필요할 때
- 숫자가 의심스러울 때 (이상치, 불일치 등)
- 공식 재무 보고서 배포 전 final check

---

## Architecture

```
User Request
    │
    ▼
CFO (Orchestrator)
    │ directive.json
    ▼
Golmani (Generator)
    ├─ DataKeeper 쿼리 (data_keeper_client.py)
    ├─ 재무 계산 (Python/openpyxl)
    └─ golmani_output.json
    │
    ▼
Auditor (Evaluator) — 독립 실행
    ├─ A: Arithmetic 검증
    ├─ B: Cross-Table 일치 여부
    ├─ C: 기간 일관성
    ├─ D: 부호 일관성
    ├─ E: GAAP/K-GAAP 기준
    └─ F: Materiality & Sanity
    │
    ▼
audit_report.json
    │
    ▼
CFO Decision
    ├─ APPROVE → sign-off
    ├─ REVISE → correction_request.json → Golmani (max 3 iterations)
    └─ ESCALATE → 수동 검토 필요
```

---

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| Task description | User | Yes |
| Date range | User or CFO inference | Yes |
| Brand filter | User (optional) | No |
| Existing output file | Path (if audit-only mode) | For audit-only |

---

## Tools

| Tool | Role |
|------|------|
| `tools/cfo_harness.py` | Python harness (API 기반 자동화) |
| `tools/data_keeper_client.py` | Golmani의 DataKeeper 접근 |
| `.claude/skills/cfo/SKILL.md` | Claude Code CFO 스킬 |
| `.claude/skills/auditor/SKILL.md` | Claude Code 감사관 스킬 |

---

## Step-by-Step

### Option A: Full Harness (자동화)

```bash
# Full CFO → Golmani → Auditor loop
python tools/cfo_harness.py --task "Grosmimi Q1 2026 P&L"

# Audit only (기존 골만이 output 있을 때)
python tools/cfo_harness.py --audit-file "Data Storage/golmani/output.json"
```

### Option B: Claude Code Manual (대화형)

1. 유저: "CFO야 골만이 결과 검토해줘"
2. CFO 스킬 활성화 → 골만이 output 파악
3. 감사관 스킬 소환 → 독립 크로스체크
4. CFO가 감사 결과 검토 → 승인 or 수정 지시
5. 수정 필요 시 골만이에게 specific correction point 전달

### Step 1: CFO Directive

CFO가 작업 요청을 분석하고 골만이에게 지시:
- 필요한 DataKeeper 테이블 명시
- 정확한 날짜 범위 지정
- 필수 출력 항목 나열
- Acceptance criteria 제시

### Step 2: Golmani Execution

골만이는 directive를 받아:
- `data_keeper_client.py`로 DataKeeper 조회
- 재무 계산 수행
- **반드시** `golmani_output.json` 저장 (감사관이 읽을 structured JSON)

```json
{
  "task": "...",
  "period": {"start": "...", "end": "..."},
  "data_sources": ["shopify_orders_daily", "amazon_sales_daily"],
  "financials": {
    "revenue": {"shopify": 285000, "amazon": 420000, "total": 705000},
    "cogs": {"total": 219550},
    "gross_profit": {"amount": 485450, "margin_pct": 68.9},
    ...
  },
  "key_metrics": {...},
  "assumptions": [...],
  "caveats": [...]
}
```

### Step 3: Auditor Review

감사관이 golmani_output.json을 독립적으로 검토:
- 골만이에게 묻지 않는다
- DataKeeper에서 직접 재확인 가능
- 6가지 체크리스트 수행
- audit_report.json 출력

### Step 4: CFO Decision

| Audit Status | CFO Action |
|-------------|------------|
| PASS | Sign-off, 포맷이에게 전달 |
| WARN (MINOR/INFO만) | 노트 추가 후 Sign-off |
| FAIL (CRITICAL/MAJOR 있음) | 구체적 correction points로 골만이에게 수정 지시 |

### Step 5: Correction Loop (최대 3회)

```
correction_request.json 예시:
{
  "iteration": 2,
  "corrections": [
    {
      "finding_id": "F001",
      "instruction": "Channel breakdown D2C revenue($285K)가 P&L total($312K)과 불일치. shopify_orders_daily에서 2026-01-01~2026-03-31, brand='Grosmimi' 재조회 후 reconcile."
    }
  ]
}
```

3회 후에도 FAIL → ESCALATE:
- CFO가 남은 이슈 요약
- 검증된 섹션은 별도 명시
- 수동 검토 필요 항목 리스트업

---

## Outputs

| Output | Path | Description |
|--------|------|-------------|
| Directive | `.tmp/cfo_sessions/{id}/directive.json` | CFO → Golmani 지시 |
| Golmani Output | `.tmp/cfo_sessions/{id}/golmani_output.json` | 골만이 산출물 |
| Audit Report | `.tmp/cfo_sessions/{id}/audit_report_{n}.json` | 감사관 리포트 |
| CFO Decision | `.tmp/cfo_sessions/{id}/cfo_decision_{n}.json` | CFO 결정 |
| Final Report | `Data Storage/cfo/cfo_review_{id}.json` | 최종 통합 리포트 |

---

## Edge Cases

| Situation | Handling |
|-----------|----------|
| DataKeeper API unavailable | NAS 캐시 폴백 → 골만이가 caveat 명시 |
| Golmani 3회 수정 후도 FAIL | CFO ESCALATE + 수동 검토 요청 |
| 감사관이 DataKeeper 불일치 발견 | CRITICAL 발견으로 처리 — 반드시 재조회 |
| 기간 내 데이터 누락 | MAJOR 발견 — 누락 기간 명시 |
| 이상치이나 설명 가능 | INFO로 기록 + 골만이 caveat에 추가 |

---

## ORBI-Specific Rules (감사관 체크 필수)

1. **P&L 시작점**: Gross Revenue (수수료 차감 전) — net revenue 시작 시 MAJOR flag
2. **COGS**: landed cost = FOB × 1.15 — SKU별 바코드 매칭
3. **Grosmimi Price Cutoff**: 2025-03-01 전후 가격 기준 다름
4. **Amazon Channel vs Shopify Channel=Amazon**: `amazon_sales_daily`가 진짜 Amazon 판매, `shopify_orders_daily` channel='Amazon'은 FBA MCF (Shopify DTC 물건)
5. **광고비 소스**: Amazon ads → `amazon_ads_daily`, Meta → `meta_ads_daily`, Google → `google_ads_daily`
6. **B2B 할인**: Faire 등 B2B는 소매가의 ~52%

---

## Lessons Learned

- 골만이는 자기 숫자를 스스로 검증하면 실수를 못 찾는다 → 감사관 분리 필수
- Cross-table 불일치가 가장 흔한 오류 (P&L vs channel breakdown)
- 날짜 범위 불일치 → 항상 period.start/end를 명시적으로 output에 포함시킬 것
- DataKeeper `shopify_orders_daily` channel='Amazon' ≠ Amazon marketplace sales (반복 실수)
