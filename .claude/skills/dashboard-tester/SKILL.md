---
name: dashboard-tester
description: >
  Playwright 기반 자율주행 대시보드 E2E 테스터.
  JP Pipeline CRM 대시보드의 모든 탭/인터랙션을 headless Playwright로
  자동 순회하며 에러를 수집한다.
  dual_test_runner.py(Maker-Checker) + codex_auditor.py 연동 지원.
  Trigger: 대시보드 테스터, JP 테스트, 자율주행 테스트, dashboard test,
  e2e test, playwright test, 대시보드 검증, UI 테스트, 탭 테스트
---

# Dashboard Tester -- Playwright 자율주행 E2E

## Overview

JP Pipeline Dashboard의 8개 탭 + 기프팅 폼 + 모달을 headless Playwright로
자동 테스트하는 에이전트. bash 한 방에 전체 실행, 사람 승인 불필요.

## Architecture

```
autonomous_tester_jp.py
    |-- Playwright headless (chromium)
    |-- 10 stages (8 tabs + gifting form + modals)
    |-- Console/Network error collector
    |-- JSON report + fix_manifest.json
    |
    |-- [optional] dual_test_runner.py (Maker-Checker)
    |-- [optional] codex_auditor.py (Independent verification)
```

## CLI

```bash
PYTHON="C:/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe"

# 전체 headless 실행
"$PYTHON" tools/autonomous_tester_jp.py --run

# 특정 스테이지만
"$PYTHON" tools/autonomous_tester_jp.py --run --stages 0_dashboard,1_creators

# 화면 보이게 (디버깅)
"$PYTHON" tools/autonomous_tester_jp.py --run --no-headless --slow-mo 700

# + 파이프라이너 + codex 검증
"$PYTHON" tools/autonomous_tester_jp.py --run --dual --codex

# 환경 확인
"$PYTHON" tools/autonomous_tester_jp.py --status
```

## 10 Test Stages

| Stage | Tab | Tests |
|-------|-----|-------|
| 0_dashboard | Dashboard | stat cards, 3-row funnel, KPI table, DM budget, activity log |
| 1_creators | Creators | search, status dropdown (17), cards, select-all, DM thread modal |
| 2_sheet | Influencer Sheet | refresh, search, status/source filter, hide toggle, sort columns |
| 3_drafts | DM Drafts | batch size, generate, select-all, execute button |
| 4_contracts | Contracts | AI classify, gifting/paid split |
| 5_config | Config | daily limit, template, mistake log, FAQ, DocuSeal IDs |
| 6_samples | Samples | table, export CSV, mark sent |
| 7_failures | Failures | log table, clear button |
| 8_gifting | Gifting Form | 7-step wizard (name→email→phone→birthday→product→address→review) |
| 9_modals | Import + DM Thread | modal open/close, fields |

## Output

- `.tmp/autonomous_test_jp/{run_id}/result.json` — 전체 결과
- `.tmp/autonomous_test_jp/{run_id}/fix_manifest.json` — 실패 시 수정 대상
- `.tmp/autonomous_test_jp/{run_id}/*.png` — 스테이지별 스크린샷

## Fix Loop

1. 테스트 실행 → fix_manifest.json 확인
2. console_errors_nearby로 원인 파악
3. HTML 소스 수정
4. `--stages {failed}` 로 재테스트
5. 반복 (최대 3회)

## Decision Framework

| User says | Action |
|-----------|--------|
| "대시보드 테스트 돌려" | `--run` (전체 headless) |
| "JP 테스트 결과 보여줘" | `--status` (최근 결과 확인) |
| "기프팅 폼만 테스트" | `--run --stages 8_gifting` |
| "화면 보면서 테스트" | `--run --no-headless --slow-mo 700` |
| "codex까지 검증" | `--run --dual --codex` |
