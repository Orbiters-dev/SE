---
name: apify-crawl-auditor
description: >
  Apify 콘텐츠 파이프라인 데이터 크롤링 감사관.
  This skill should be used when the user mentions "크롤링 감사", "crawl audit",
  "Apify 감사", "파이프라인 헬스체크", "데이터 검증", "crawl auditor",
  "apify health", "크롤러 검증", "파이프라인 상태",
  or asks to verify that the Apify content pipeline is running correctly.
  Checks GitHub Actions status, Data Storage freshness, Google Sheets integrity,
  D+60 Tracker structure, and brand classification coverage.
---

# Apify Crawl Auditor — 데이터 크롤링 감사관

Apify 콘텐츠 파이프라인(IG + TikTok → Google Sheets)이 정상 작동하는지 3개 레이어로 감사하는 에이전트.

## Architecture — Dual-AI Verification (Claude + Codex)

```
[Orchestrator (Claude Code)]
         |
    ┌────┴────┐
    │ Loop ×3 │  ← Claude 직접 실행
    └────┬────┘
         │
  Iter 1: INFRA      → GitHub Actions, secrets, credentials
  Iter 2: DATA       → Data Storage files, Sheets row counts, freshness
  Iter 3: INTEGRITY  → D+60 columns, brand coverage, duplicate check
         │
    .tmp/crawl_audit/audit_{ts}.json
         │
         ▼
┌────────────────────────────────────────┐
│  Codex Verifier (독립 2차 검증)          │
│  codex_auditor.py --domain crawl        │
│    ├── audit JSON 읽기                   │
│    ├── 6 axes 독립 재검증                │
│    └── JSON verdict 반환                 │
└────────────────────────────────────────┘
         │
    Claude verdict vs Codex verdict 비교
    불일치 시 → 해당 axis 재검토
```

### Codex 크롤링 감사 CLI
```bash
PYTHON="C:/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe"
WJ="C:/Users/wjcho/Desktop/WJ Test1"

# Claude 감사 후 Codex 독립 재검증
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain crawl --audit
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain crawl --audit --region us
"$PYTHON" "$WJ/tools/codex_auditor.py" --domain crawl --health
```

## Audit Layers (6 Axes)

| # | Axis | Layer | What It Checks |
|---|------|-------|----------------|
| 1 | GitHub Actions | INFRA | apify_daily.yml 최근 실행 결과, 연속 실패 횟수 |
| 2 | Secrets | INFRA | APIFY_API_TOKEN, GOOGLE_SERVICE_ACCOUNT, META_GRAPH_IG_TOKEN |
| 3 | File Freshness | DATA | Data Storage/apify/ JSON 파일 존재 + 나이 (<36h OK, >72h CRITICAL) |
| 4 | Sheet Rows | DATA | 6개 탭 존재 여부, 행 수 (Posts Master >10, D+60 >0) |
| 5 | D+60 Structure | INTEGRITY | 192열 구조, D+0 Cmt/Like/View 헤더 패턴 |
| 6 | Brand Coverage | INTEGRITY | Posts Master brand열 커버리지 (>80% good), 중복 Post ID |

## Severity Levels

| Level | Meaning | Exit Code |
|-------|---------|-----------|
| CRITICAL | 파이프라인 중단됨 (데이터 수집 불가) | 2 (FAIL) |
| MAJOR | 데이터 품질 이슈 (누락, 지연, 부정합) | 1 (WARN) |
| MINOR | 경고 (optional secret 누락, 미미한 이슈) | 0 |
| INFO | 정상 확인 | 0 |

## CLI Usage

```bash
# Harness mode (3-loop, recommended)
python tools/apify_crawl_auditor.py --harness

# Harness + specific region
python tools/apify_crawl_auditor.py --harness --region us

# Single layer
python tools/apify_crawl_auditor.py --layer infra
python tools/apify_crawl_auditor.py --layer data
python tools/apify_crawl_auditor.py --layer integrity

# JSON output (for programmatic use)
python tools/apify_crawl_auditor.py --harness --json
```

## Target Sheet

- **Sheet ID**: `1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY`
- **URL**: https://docs.google.com/spreadsheets/d/1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY/edit

### 6 Tabs

| Tab | Region | Content |
|-----|--------|---------|
| US Posts Master | US | 포스트 메타데이터 + 브랜드 분류 |
| US D+60 Tracker | US | 60일간 Cmt/Like/View 일별 스냅샷 |
| US Influencer Tracker | US | 인플루언서별 포스팅 이력 매트릭스 |
| JP Posts Master | JP | (동일 구조, 일본 마켓) |
| JP D+60 Tracker | JP | |
| JP Influencer Tracker | JP | |

## Data Storage Files (Expected Daily)

```
Data Storage/apify/
  YYYY-MM-DD_us_tagged_raw.json      # IG tagged posts
  YYYY-MM-DD_us_tiktok_raw.json      # TikTok search results
  YYYY-MM-DD_us_follower_map.json    # Follower counts
  YYYY-MM-DD_jp_tagged_raw.json
  YYYY-MM-DD_jp_tiktok_raw.json
  YYYY-MM-DD_jp_follower_map.json
```

## Output

```
.tmp/crawl_audit/audit_YYYYMMDD_HHMMSS.json
```

Report structure:
```json
{
  "health": "PASS|WARN|FAIL",
  "summary": {"critical": 0, "major": 0, "minor": 0, "info": 5},
  "iteration_reports": [...],
  "findings": [
    {"severity": "...", "category": "...", "description": "...", "expected": "...", "actual": "..."}
  ]
}
```

## Integration

- **Upstream**: `fetch_apify_content.py` (파이프라인 실행)
- **Workflow**: `apify_daily.yml` (GitHub Actions 스케줄)
- **Downstream**: `build_apify_report.py` (이메일 리포트)
- **Cross-ref**: `sync_sns_tab.py` (SNS 탭 동기화)
- **Codex Verifier**: `tools/codex_auditor.py --domain crawl` (독립 2차 검증)

### Dual-AI Audit Protocol

크롤링 감사 호출 시:
1. Claude `apify_crawl_auditor.py --harness` 실행 → `audit_{ts}.json`
2. Codex `codex_auditor.py --domain crawl --audit` 독립 실행
3. 양쪽 결과 비교 → 불일치 시 해당 axis 집중 재검토

## Credentials

- `GITHUB_TOKEN` / `GH_TOKEN` — GitHub Actions API (optional, skips if missing)
- `GOOGLE_SERVICE_ACCOUNT_PATH` — Google Sheets API (required for data/integrity layers)
- `APIFY_API_TOKEN` — Apify API (checked for existence, not called)

## Troubleshooting

| 증상 | 원인 | 해결 |
|------|------|------|
| Layer 1 skipped | GITHUB_TOKEN 없음 | `~/.wat_secrets`에 GH_TOKEN 추가 |
| Layer 2/3 skipped | Service account 없음 | `credentials/google_service_account.json` 확인 |
| CRITICAL: file not found | 파이프라인 미실행 | `apify_daily.yml` 수동 실행 또는 로컬 `--daily` |
| MAJOR: brand coverage low | 브랜드 감지 키워드 누락 | `fetch_apify_content.py` 키워드 리스트 업데이트 |
