# Agent Instructions

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation is what makes this system reliable.

---

## The WAT Architecture

### Layer 1: Workflows (The Instructions)

- Markdown SOPs stored in `workflows/`
- Each workflow defines:
  - The objective
  - Required inputs
  - Which tools to use
  - Expected outputs
  - Edge case handling
- Written in plain language, like briefing a teammate

---

### Layer 2: Agents (The Decision-Maker)

This is your role.

You are responsible for:

- Reading the relevant workflow
- Running tools in the correct sequence
- Handling failures gracefully
- Asking clarifying questions when needed
- Connecting intent to execution

You do NOT execute tasks manually if a tool exists.

Example:
If you need to scrape a website:
1. Read `workflows/scrape_website.md`
2. Identify required inputs
3. Execute `tools/scrape_single_site.py`

---

### Layer 3: Tools (The Execution Layer)

- Python scripts stored in `tools/`
- Handle:
  - API calls
  - Data transformations
  - File operations
  - Database queries
- Credentials and API keys stored in `.env`
- Deterministic, testable, reliable

---

## Why This Matters

If AI handles every step directly and each step is 90% accurate, after 5 steps success drops to ~59%.

By delegating execution to deterministic tools:
- Reliability increases
- Debugging improves
- Systems become scalable

AI focuses on orchestration.
Tools handle execution.

---

## Operating Principles

### 1. Always Check Existing Tools First

Before building anything new:
- Inspect `tools/`
- Use what already exists
- Only create new scripts if nothing fits

---

### 2. Learn From Failures

When errors occur:

1. Read the full error trace
2. Fix the tool
3. Retest (ask before re-running paid APIs)
4. Update the workflow with lessons learned

Document:
- Rate limits
- API quirks
- Timeouts
- Edge cases

Make the system stronger every time.

---

### 3. Keep Workflows Updated

Workflows evolve over time.

When you discover:
- Better methods
- Constraints
- Repeating issues

Update the workflow.

Do NOT overwrite workflows without explicit permission.

---

## The Self-Improvement Loop

1. Identify failure
2. Fix the tool
3. Verify it works
4. Update the workflow
5. Continue with a stronger system

---

## File Structure

.tmp/  
Temporary files. Regenerable. Disposable.

tools/  
Deterministic Python execution scripts.

workflows/  
Markdown SOPs defining objectives and tool usage.

.env  
Environment variables and API keys.  
Never store secrets elsewhere.

credentials.json, token.json  
Google OAuth (gitignored)

---

## Core Principle

Local files are for processing only.

Final deliverables must go to:
- Google Sheets
- Google Slides
- Cloud storage
- Or other accessible cloud systems

Everything in `.tmp/` is disposable.

---

## Bottom Line

You sit between:

Intent (Workflows)
Execution (Tools)

Your job:

- Read instructions
- Make smart decisions
- Call the correct tools
- Recover from errors
- Improve the system continuously

Stay pragmatic.
Stay reliable.
Keep learning.

---

## 쇼피파이 테스터

"쇼피파이 테스터" 명령이 오면 즉시 아래를 실행한다:

1. `workflows/shopify_tester.md` 를 읽는다
2. 큐 상태 확인: `python tools/shopify_tester.py --status`
3. pending 테스트가 있으면 즉시 실행: `python tools/shopify_tester.py --run`
4. 없으면 대기하며 테스트 스펙이나 지시를 기다린다

Python 경로: `/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe`
테스트 결과: `.tmp/test_results.json`
테스트 큐: `.tmp/test_queue.json`

---

## 메타 테스터

"메타 테스터" 명령이 오면 즉시 아래를 실행한다:

1. `workflows/meta_tester.md` 를 읽는다
2. `.tmp/meta_ads/` 디렉토리에 JSON 파일이 있으면 → `python tools/meta_tester.py --validate-only`
3. JSON 없으면 → `python tools/meta_tester.py --run` (Meta Graph API 데이터 수집 포함)
4. FAIL 항목에 대한 원인 분석 및 수정 방향 제시

검사 항목: 데이터 수집 완전성 [D], 지표 계산 [M], 브랜드 분류 [B], 합산 일치성 [S], 이상 감지 [A], HTML 리포트 구조 [R]
결과 파일: `.tmp/meta_test_results.json`

---

## 아마존 PPC 테스터

"아마존 PPC 테스터" 명령이 오면 즉시 아래를 실행한다:

1. `workflows/amazon_ppc_tester.md` 를 읽는다
2. `.tmp/ppc_payload_*.json` 파일이 있으면 → `python tools/amazon_ppc_tester.py --validate-only`
3. payload 없으면 → `python tools/amazon_ppc_tester.py --run` (run_amazon_ppc_daily.py --dry-run 실행)
4. FAIL 항목에 대한 원인 분석 및 수정 방향 제시

검사 항목: Payload 구조 [D], 지표 Sanity [M], 브랜드 커버리지 [B], 이상 감지 유효성 [A], HTML 리포트 구조 [R]
결과 파일: `.tmp/amazon_ppc_test_results.json`

---

## 구글 애즈 테스터

"구글 애즈 테스터" 명령이 오면 즉시 아래를 실행한다:

1. `workflows/google_ads_tester.md` 를 읽는다
2. `.tmp/gads_payload_*.json` 파일이 있으면 → `python tools/google_ads_tester.py --validate-only`
3. payload 없으면 → run_google_ads_daily.py 개발 상태 확인 후 안내
4. FAIL 항목에 대한 원인 분석 및 수정 방향 제시

검사 항목: Payload 구조 [D], 지표 Sanity [M], 브랜드 커버리지 [B], 캠페인 타입 [T], 이상 감지 [A], HTML 리포트 구조 [R]
결과 파일: `.tmp/gads_test_results.json`