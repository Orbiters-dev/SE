---
name: pipeliner
description: >
  Creator Collab Pipeline E2E 이중테스트 에이전트.
  This skill should be used when the user mentions "파이프라이너", "이중테스트", "dual test",
  "파이프라인 테스트", "E2E 테스트 돌려", "gifting 테스트", "pipeline test",
  "Maker-Checker", "executor verifier", "파이프라인 검증",
  or asks to test the influencer gifting automation pipeline.
  Covers dual_test_runner.py, test_influencer_flow.py, n8n PROD/WJ TEST workflows,
  and cross-system verification (Airtable, Shopify, PostgreSQL).
---

# Pipeliner -- Creator Collab Pipeline E2E Dual Tester

Maker-Checker 패턴으로 인플루언서 기프팅 파이프라인 8단계를 이중 검증하는 에이전트.
Executor(Maker)가 액션을 실행하고, Verifier(Checker)가 독립적으로 downstream 시스템을 검증한다.

## Architecture

```
[Orchestrator (Claude Code)]
         |
    +----+----+
    v         v
[Executor]  [Verifier]     <- dual_test_runner.py
    |         |
    | signal.json (stage 완료 신호)
    v         v
.tmp/dual_test/run_{ts}/
  config.json | executor_log.json | verifier_log.json | merged_report.html
```

## Pipeline 8 Stages

| Stage | Process | Type | n8n WF (PROD) |
|-------|---------|------|---------------|
| 0 | Syncly Discovery -> Airtable CRM | Auto | FzBJVEOTvr6qJPAL |
| 1 | Claude AI Email -> Gmail Send | Auto+Human | fwwOeLiDLSnR77E1 |
| 2 | Gifting Form -> Shopify Draft Order | Webhook | F0sv8RsCS1v56Gkw |
| 3 | Profile Review -> Accept/Decline | Human | - |
| 4 | Sample Select -> Draft Order | Webhook | KqICsN9F1mPwnAQ9 |
| 5 | Sample Sent -> Draft Complete | 5min poll | m89xU9RUbPgnkBy8 |
| 6 | Fulfillment -> Delivery Detection | 30min poll | ufMPgU6cjwuzLM0y |
| 6.5 | Guidelines Email | Auto | (fulfillment WF) |
| 7 | Content Posted Detection (Apify Crawler) | 6hr poll | FzBJVEOTvr6qJPAL |

## Dual Test CLI

Primary tool: `tools/dual_test_runner.py`

```bash
# Full dual test (4 stages: seed -> gifting -> gifting2 -> sample_sent)
python tools/dual_test_runner.py --dual

# Specific stages
python tools/dual_test_runner.py --dual --stages seed,gifting

# Dry run (no API calls)
python tools/dual_test_runner.py --dual --dry-run

# Keep test data (skip cleanup)
python tools/dual_test_runner.py --dual --no-cleanup

# Executor only (debug)
python tools/dual_test_runner.py --executor-only

# Verifier only (needs existing signal)
python tools/dual_test_runner.py --verifier-only --run-id dual_YYYYMMDD_HHMMSS

# Show recent results
python tools/dual_test_runner.py --results
```

## Dual Test Stages

| Stage | Executor (Maker) | Verifier (Checker) |
|-------|-------------------|--------------------|
| **seed** | Airtable Creator record 생성 | AT Creator 존재, AT Applicants 미존재(neg), Shopify 미존재(neg) |
| **gifting** | POST webhook -> 12s 대기 | AT Applicants 생성, AT Creators 상태=Needs Review, Shopify 고객, PG 저장, X-SYS 이메일 일치 |
| **gifting2** | POST webhook -> 15s 대기 | AT Draft Order ID, AT Creators 존재, PG 저장 |
| **sample_sent** | AT 상태 -> Sample Sent | AT 상태 변경, n8n WF active |

## Single Flow Tests

Existing tool: `tools/test_influencer_flow.py`

```bash
# Individual flows
python tools/test_influencer_flow.py --run --flow gifting
python tools/test_influencer_flow.py --run --flow creator
python tools/test_influencer_flow.py --run --flow sample
python tools/test_influencer_flow.py --run --flow gifting2

# Full pipeline (10 steps)
python tools/test_influencer_flow.py --run --flow pipeline

# Full customer journey (16 steps)
python tools/test_influencer_flow.py --run --flow journey

# All default flows
python tools/test_influencer_flow.py --run

# Environment check
python tools/test_influencer_flow.py --status
```

## Environment: PROD vs WJ TEST

| Item | PROD | WJ TEST |
|------|------|---------|
| Airtable Base | `appNPVxj4gUJl9v15` | `appT2gLRR0PqMFgII` |
| Shopify Store | mytoddie.myshopify.com | toddie-4080.myshopify.com |
| Triggers | scheduleTrigger (polling) | webhook (instant) + schedule |
| Config | Fetch Dashboard + Config Sheet | Read Config Sheet (GSheets) |
| PostgreSQL | None | Django API (orbitools) |
| Test Infra | None | Inject Test Record, Is Dry Run? |

**Dual test always uses WJ TEST environment** -- never touches PROD.

## Decision Framework

When "파이프라이너" is invoked, determine the appropriate action:

1. **"테스트 돌려" / "이중테스트"** -> `dual_test_runner.py --dual`
2. **"gifting만 테스트"** -> `test_influencer_flow.py --run --flow gifting`
3. **"파이프라인 상태 확인"** -> `test_influencer_flow.py --status` + n8n WF active check
4. **"마지막 결과"** -> `dual_test_runner.py --results`
5. **"특정 스테이지만"** -> `dual_test_runner.py --dual --stages seed,gifting`
6. **n8n 이슈** -> Check `references/troubleshooting.md`

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| n8n webhook 무응답 | `docker compose down && up -d` (EC2 SSH) |
| Task Runner "Offer expired" | Clean restart of n8n container |
| Airtable 429 rate limit | 0.2s delay between API calls (built-in) |
| Shopify customer not found | n8n uses mytoddie, test checks toddie-4080 (expected) |
| PG record missing | Check orbitools API: `curl -u admin:PW https://orbitools.orbiters.co.kr/api/onzenna/gifting/list/` |

## Additional Resources

### Reference Files

- **`references/n8n-workflows.md`** -- PROD/WJ TEST workflow IDs, node counts, status, environment mapping
- **`references/troubleshooting.md`** -- Detailed troubleshooting patterns, n8n server management, common failures

### Key Project Files

| File | Role |
|------|------|
| `tools/dual_test_runner.py` | Maker-Checker dual test runner |
| `tools/test_influencer_flow.py` | Single-flow E2E tester (3650 lines, 8 flows) |
| `tools/process_influencer_order.py` | Form -> Shopify customer + draft order |
| `docs/pipeline/ko.html` | Pipeline visual documentation |
| `docs/pipeline/tests-ko.html` | E2E test results documentation |

Python path: `/c/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe`
