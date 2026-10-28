# SE Handoff v1 — 메타 검증 하네스 + 일본 시장 reference

세은(B2C) → 사수(B2B 도매·유통·벤더) handoff 패키지.

도메인 종속 코드(인플루언서·DM·B2C 채널·Shopify 등)는 전부 제외. 어느 환경에서도 그대로 쓸 수 있는 **메타 검증 시스템** + **일본 시장 일반 reference** 만 들어있음.

---

## 들어있는 것

### A. 적대감사 / 메타 검증 시스템

| 항목 | 위치 | 역할 |
|---|---|---|
| 3-LLM Harness (Generator + Codex + Gemini + Meta-Judge) | `tools/harness.py` + `harness_5stage.py` 외 | 산출물 자동 교차검증. 산업 도메인 무관 |
| Codex Evaluator | `tools/codex_evaluator.py` | 코드·재무·E2E 도메인별 감사. `--domain {general,cfo}` |
| Codex Auditor | `tools/codex_auditor.py` | 파이프라인 실행 결과 독립 감사 |
| Gemini Auditor / Evaluator | `tools/gemini_*.py` | 숫자·사실 축 평가자 |
| Claude Meta-Judge | `tools/claude_meta_judge.py` | Codex vs Gemini 의견 충돌 시 tie-breaker |
| Consensus Resolver | `tools/consensus_resolver.py` | 다수결 + 충돌 감지 |
| CFO Harness | `tools/cfo_harness.py` | Orchestrator → Generator → Auditor 루프 예시 구현 |

### B. 스킬 4개 (Skill 트리거)

| 스킬 | 트리거 | 역할 |
|---|---|---|
| `auditor` | "감사관", "감사해줘", "크로스체크", "AICPA" | AICPA/KICPA 6-point 체크리스트로 산출물 감사 |
| `cfo` | "CFO야", "재무검토", "감사" | Orchestrator. Generator 산출물 → Auditor 루프 |
| `제갈량` | "제갈량", "CSO", "전략회의", "큰그림" | Planner → Generator → Evaluator 3-agent 총괄 패턴 |
| `아인슈타인` | "아인슈타인" | 효율/창의성 단독 감사 |

### C. PostToolUse Hook

`Write`/`Edit` 후 대상 파일이 `HARNESS_PATTERNS` 매치하면 자동 harness 실행. FAIL = 다음 액션 block + 피드백, WARN = 통과 + 알림, PASS = 통과.

→ `.claude/hooks/harness_runner.py` 안의 `HARNESS_PATTERNS` 리스트를 **사수 repo 구조에 맞게 수정**해야 함 (자기 Django 앱 이름 / 워크플로우 폴더 등).

### D. 일본 시장 reference (도매·유통·벤더 응대)

| 파일 | 내용 |
|---|---|
| `references/japan_business_jp.md` | 호칭 (様/御中), 메일 정형, 비즈니스 표현, 톤 룰 |
| `references/japan_accounting.md` | 税込/税抜, インボイス制度 (T번호), 振込 관례, 청구서 필수항목 |
| `references/japan_contract_basics.md` | 基本取引契約書 표준 조항, NDA, 발주서, 도장 관례, 한국식 사고 함정 |
| `references/operating_patterns_from_b2c.md` | B2C 광고·매출 운영에서 추출한 평가 패턴 → 벤더 평가·거래선 churn·통화 검증 등에 적용 |
| `references/cfo_financial_review.md` | CFO 재무 검토 SOP (원본은 B2C 골만이 감사용, 패턴만 차용) |

---

## 설치 (clean install 가정)

### 1. 파일 배치

이 폴더를 사수 repo 루트에 통째 풀거나, 다음 매핑으로 옮김:

```
SE_handoff_v1/.claude/          → <repo>/.claude/         (기존 settings.json 있으면 hooks 섹션 머지)
SE_handoff_v1/tools/            → <repo>/tools/
SE_handoff_v1/references/       → <repo>/references/      (또는 사수가 원하는 reference 폴더)
```

### 2. Python 의존성

전부 stdlib만 사용. 단, harness가 외부 LLM CLI 호출:
- **Codex CLI** (OpenAI o3) — `npm install -g @openai/codex-cli` 또는 사수 환경에 맞게
- **Gemini CLI** — Google AI Studio 또는 `gemini` CLI

CLI 없이 API 직접 호출하려면 `tools/codex_evaluator.py` 안의 subprocess 호출부 수정 필요.

### 3. API 키 (.env 또는 환경변수)

```
OPENAI_API_KEY=sk-...        # codex / claude_meta_judge
GEMINI_API_KEY=AIza...       # gemini_evaluator
ANTHROPIC_API_KEY=sk-ant-... # claude_meta_judge (선택)
```

→ **별도 보안 채널로 수령**. git 커밋 X. `.env` 는 반드시 `.gitignore`.

### 4. Hook 활성화

`.claude/settings.json` 의 `PostToolUse` 섹션이 이미 박혀 있음. 사수 기존 hooks 와 머지:

```json
"PostToolUse": [
  { "matcher": "Write|Edit", "hooks": [...기존..., {"type":"command","command":"python .claude/hooks/harness_runner.py", "timeout":320}] }
]
```

### 5. Hook 패턴 커스터마이즈

`.claude/hooks/harness_runner.py` 상단 `HARNESS_PATTERNS` 수정:

```python
HARNESS_PATTERNS = [
    r"(^|/)tools/.+\.py$",
    # 사수 Django 앱 이름 추가, 예:
    # r"(^|/)(b2b_orders|vendor_mgmt)/.+\.py$",
]
```

---

## 사용법

### CLI 직접

```bash
# 단일 파일 검증 (코드)
PYTHONIOENCODING=utf-8 python tools/harness.py run --type code --file path/to/file.py --gate build --max-loops 2 --json

# 재무 산출물 감사
python tools/codex_evaluator.py --domain cfo audit --files .tmp/your_output.json

# 상태 확인
python tools/harness.py status
```

### Claude Code 안에서

```
/감사관          → AICPA/KICPA 체크리스트로 직전 산출물 감사
/CFO야          → CFO orchestrator 발동 (Generator → Auditor 루프)
/제갈량          → Planner → Generator → Evaluator 3-agent 총괄
/아인슈타인       → 효율/창의성 감사
```

### Hook 자동 발동

`Write` / `Edit` 로 `HARNESS_PATTERNS` 매치 파일 수정 시 자동 실행. 별도 트리거 X.

---

## 영구 등록 (1회만) — CLAUDE.md 에 append

매 세션마다 paste 할 필요 없게 **CLAUDE.md** 에 박는다. CC 는 매 세션 시작 시 CLAUDE.md 를 자동 로딩한다.

1. `SE_handoff_v1/CLAUDE.md.snippet` 파일 열기
2. 내용 통째로 본 repo 루트의 `CLAUDE.md` 끝에 append (없으면 새로 생성)
3. CC 1회 재시작 → 그 다음부터 모든 세션 자동 적용

→ 이후 어느 세션을 열어도 하네스/스킬/reference 가 컨텍스트에 박혀있음.

---

## 안 들어간 것 (의도적 제외)

- 인플루언서 DM·계약·DocuSeal·ManyChat
- B2C 채널 (Amazon JP·Rakuten·Meta JP·Shopify·Twitter)
- ORBI 인프라 의존 도구 (Data Keeper·orbitools MCP·LightRAG vault)
- 세은 개인 메모리·세션 로그·피드백
- B2C 워크플로우 전체

→ 사수가 자기 도메인용으로 자체 추가.
