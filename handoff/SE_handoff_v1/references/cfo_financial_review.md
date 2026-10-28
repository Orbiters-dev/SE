# CFO Financial Review Workflow

## Objective

Generator agent (재무 모델링 담당) 의 산출물을 CFO orchestrator 가 독립 감사관(AICPA/KICPA 기준) 을 통해 검증하고, 숫자 불일치 시 수정을 지시하는 하네스 구조 재무 검토 프로세스.

**핵심 원칙**: 생성(Generator) 과 검증(Auditor) 을 분리한다.
Generator 에게 자기 결과를 스스로 검토하게 하지 않는다 — 항상 별도 감사관이 독립 검증.

Reference: https://www.anthropic.com/engineering/harness-design-long-running-apps

---

## When to Use

- Generator 가 P&L, 3-statement, DCF, 벤더 단가 분석 등 중요 재무 모델을 만들었을 때
- 재무 데이터 내부 정합성 확인 필요할 때
- 숫자가 의심스러울 때 (이상치, 불일치)
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
Generator Agent
    ├─ 데이터 소스 쿼리
    ├─ 재무 계산 (Python/openpyxl)
    └─ generator_output.json
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
    ├─ REVISE → correction_request.json → Generator (max 3 iterations)
    └─ ESCALATE → 수동 검토 필요
```

---

## Inputs

| Input | Source | Required |
|---|---|---|
| Task description | User | Yes |
| Date range | User or CFO inference | Yes |
| Segment/entity filter | User (optional) | No |
| Existing output file | Path (if audit-only mode) | For audit-only |

---

## Tools

| Tool | Role |
|---|---|
| `tools/cfo_harness.py` | Python harness (API 기반 자동화) |
| `.claude/skills/cfo/SKILL.md` | Claude Code CFO 스킬 |
| `.claude/skills/auditor/SKILL.md` | Claude Code 감사관 스킬 |

---

## Step-by-Step

### Option A: Full Harness (자동화)

```bash
# Full CFO → Generator → Auditor loop
python tools/cfo_harness.py --task "[Segment] Q1 P&L"

# Audit only (기존 generator output 있을 때)
python tools/cfo_harness.py --audit-file path/to/output.json
```

### Option B: Claude Code Manual (대화형)

1. 유저: "CFO야 직전 분석 결과 검토해줘"
2. CFO 스킬 활성화 → generator output 파악
3. 감사관 스킬 소환 → 독립 크로스체크
4. CFO 가 감사 결과 검토 → 승인 or 수정 지시
5. 수정 필요 시 generator 에게 specific correction point 전달

### Step 1: CFO Directive

CFO 가 작업 요청을 분석하고 generator 에게 지시:
- 필요한 데이터 테이블 명시
- 정확한 날짜 범위 지정
- 필수 출력 항목 나열
- Acceptance criteria 제시

### Step 2: Generator Execution

Generator 는 directive 를 받아:
- 데이터 소스 조회
- 재무 계산 수행
- **반드시** `generator_output.json` 저장 (감사관이 읽을 structured JSON)

```json
{
  "task": "...",
  "period": {"start": "...", "end": "..."},
  "data_sources": ["[your data tables]"],
  "financials": {
    "revenue": {"channel_a": 285000, "channel_b": 420000, "total": 705000},
    "cogs": {"total": 219550},
    "gross_profit": {"amount": 485450, "margin_pct": 68.9}
  },
  "key_metrics": {},
  "assumptions": [],
  "caveats": []
}
```

### Step 3: Auditor Review

감사관이 generator_output.json 을 독립 검토:
- Generator 에게 묻지 않는다
- 원천 데이터에서 직접 재확인 가능
- 6가지 체크리스트 수행
- audit_report.json 출력

### Step 4: CFO Decision

| Audit Status | CFO Action |
|---|---|
| PASS | Sign-off |
| WARN (MINOR/INFO만) | 노트 추가 후 Sign-off |
| FAIL (CRITICAL/MAJOR 있음) | 구체적 correction points 로 generator 에게 수정 지시 |

### Step 5: Correction Loop (최대 3회)

```json
{
  "iteration": 2,
  "corrections": [
    {
      "finding_id": "F001",
      "instruction": "Channel breakdown revenue 가 P&L total 과 불일치. [데이터 소스]에서 [기간], [필터] 재조회 후 reconcile."
    }
  ]
}
```

3회 후에도 FAIL → ESCALATE:
- CFO 가 남은 이슈 요약
- 검증된 섹션은 별도 명시
- 수동 검토 필요 항목 리스트업

---

## Outputs

| Output | Path | Description |
|---|---|---|
| Directive | `.tmp/cfo_sessions/{id}/directive.json` | CFO → Generator 지시 |
| Generator Output | `.tmp/cfo_sessions/{id}/generator_output.json` | Generator 산출물 |
| Audit Report | `.tmp/cfo_sessions/{id}/audit_report_{n}.json` | 감사관 리포트 |
| CFO Decision | `.tmp/cfo_sessions/{id}/cfo_decision_{n}.json` | CFO 결정 |
| Final Report | `[your output store]/cfo_review_{id}.json` | 최종 통합 리포트 |

---

## Edge Cases

| Situation | Handling |
|---|---|
| 데이터 소스 API unavailable | 캐시 폴백 → generator 가 caveat 명시 |
| Generator 3회 수정 후도 FAIL | CFO ESCALATE + 수동 검토 요청 |
| 감사관이 데이터 불일치 발견 | CRITICAL 발견으로 처리 — 반드시 재조회 |
| 기간 내 데이터 누락 | MAJOR 발견 — 누락 기간 명시 |
| 이상치이나 설명 가능 | INFO 로 기록 + generator caveat 에 추가 |

---

## Lessons Learned (도메인 무관)

- Generator 가 자기 숫자를 스스로 검증하면 실수를 못 찾는다 → 감사관 분리 필수
- Cross-table 불일치가 가장 흔한 오류 (P&L vs channel/segment breakdown)
- 날짜 범위 불일치 → 항상 period.start/end 를 명시적으로 output 에 포함
- 같은 이름·다른 정의의 metric 이 가장 위험 (예: "Amazon 매출" 이 marketplace 직판 vs Shopify channel='Amazon' FBA MCF 인지) — 데이터 사전 명시 필수
