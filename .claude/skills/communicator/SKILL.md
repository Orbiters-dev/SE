---
name: communicator
description: >
  ORBI Communicator — 12시간 단위 통합 상태 이메일 에이전트.
  Data Keeper 채널 freshness, GitHub Actions 워크플로우 이력, 다음 예정 작업,
  실패·지연 알림을 모아 예쁜 HTML 이메일로 자동 발송한다.
  PST 0:00 / 12:00에 GitHub Actions로 자동 실행된다.

  트리거: "커뮤니케이터", "상태 이메일", "리포트 발송", "communicator",
  "데이터 현황 이메일", "워크플로우 이력 이메일", "상태 체크 이메일",
  "status report", 또는 통합 상태 이메일 발송 관련 모든 요청.
---

# ORBI Communicator

12시간마다 시스템 전체 상태를 이메일로 정리해 보내는 에이전트.

## 아키텍처

```
run_communicator.py
  ├── get_datakeeper_status()     → orbitools API (9개 채널 freshness)
  ├── get_syncly_stats()          → Google Sheets (6개 탭 row 수 + 상세)
  ├── get_gh_runs()               → GitHub API (최근 24시간 워크플로우 이력)
  ├── get_next_schedules()        → 정적 스케줄 → 향후 12시간 예정 목록
  ├── get_naeiae_ppc_tracking_html() → .tmp/naeiae_execution_baseline.json
  ├── get_seo_insights_html()     → DataForSEO + GSC (orbitools API)
  └── build_html()                → 이메일 HTML 생성
        └── send_gmail.py         → Gmail OAuth로 발송
```

## 이메일 섹션 구성 (실제 순서)

| 순서 | 섹션 | 내용 |
|------|------|------|
| 1 | **태스크 업데이트** | 실행된 워크플로우별 섬머리 + 관련 링크. Syncly: 6개 탭 row 수 포함 |
| 2 | **데이터 수집 현황** | 9채널 freshness 간략 표 (🟢/🟡/🔴) |
| 3 | **향후 12시간 예정** | 다음 실행될 워크플로우 목록 |
| 4 | **알림** | 연속 실패 에스컬레이션 ("쪼기") — `ESCALATE_THRESHOLD=2`회 이상 시 표시 |
| 5 | **Naeiae PPC 변경 추적** | 실행 전/후 ROAS·ACOS·Spend·Sales 비교 (baseline 있을 때만) |
| 6 | **SEO / 키워드 인사이트** | DataForSEO 브랜드별 검색량·CPC + GSC 상위 8 쿼리 (데이터 있을 때만) |

## 주요 명령

| 명령 | 설명 |
|------|------|
| `python tools/run_communicator.py` | 즉시 발송 |
| `python tools/run_communicator.py --dry-run` | 발송 없이 콘솔 확인 |
| `python tools/run_communicator.py --preview` | `.tmp/communicator_preview.html` 저장 |
| `python tools/run_communicator.py --to other@email.com` | 수신자 변경 |
| `python tools/run_communicator.py --cc other@email.com` | CC 추가 |
| `python tools/run_communicator.py --reset-state` | 연속 실패 카운터 초기화 |

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `COMMUNICATOR_RECIPIENT` | 수신자 이메일 | `PPC_REPORT_RECIPIENT` 폴백 → `wj.choi@orbiters.co.kr` |
| `COMMUNICATOR_CC` | CC 이메일 | `mj.lee@orbiters.co.kr` |
| `GITHUB_REPOSITORY` | `owner/repo` 형식 | GitHub Actions에서 자동 설정 |
| `GH_PAT` | GitHub Personal Access Token (로컬 실행 시) | — |
| `GITHUB_TOKEN` | GitHub Actions 내부 토큰 (자동) | — |
| `ORBITOOLS_USER` / `ORBITOOLS_PASS` | orbitools API 인증 | 필수 |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Service Account JSON 경로 | `credentials/google_service_account.json` |

## Syncly 탭 모니터링

`get_syncly_stats()` 가 Google Sheets에서 직접 row 수를 읽어 이메일에 포함.

| 탭 | 시트 | 헤더 행 수 |
|----|------|-----------|
| US Posts Master | SYNCLY_SRC_ID (`1bOXr...`) | 1 |
| US D+60 Tracker | SYNCLY_SRC_ID | 2 |
| JP Posts Master | SYNCLY_SRC_ID | 1 |
| JP D+60 Tracker | SYNCLY_SRC_ID | 2 |
| ONZENNA SNS 탭 | ONZENNA_SNS_ID (`1SwO4...`) | 2 |
| CHA&MOM SNS 탭 | CHAENMOM_SNS_ID (`16XUPd...`) | 2 |

## Naeiae PPC 변경 추적

`.tmp/naeiae_execution_baseline.json` 이 있을 때만 섹션 표시.

파일 구조:
```json
{
  "executed_date": "2026-03-08",
  "before": {"roas_7d": 2.33, "acos_7d": 43.0, "spend_7d": 84.0, "sales_7d": 196.0},
  "changes_executed": {
    "negatives_added": [{"term": "teething wafers", "reason": "..."}],
    "bid_reductions": [{"target": "ASIN B0BMJCWYB6", "change": "$0.80 → $0.64"}],
    "keywords_harvested": [{"term": "pop rice", "roas_14d": 4.2}],
    "wasted_spend_14d": 100.0
  }
}
```

현재 DataKeeper에서 Naeiae 7일 ROAS를 실시간 조회해 실행 전과 비교.
attribution lag(2-3일)가 있으므로 실행 직후 변화 작음 — 정상.

## 연속 실패 에스컬레이션

- 상태 파일: `.tmp/communicator_state.json`
- `ESCALATE_THRESHOLD = 2` — 2회 연속 실패 시 이메일에 🔴 알림 표시
- `--reset-state` 플래그로 카운터 초기화
- 데이터 채널 + 워크플로우 모두 추적

## SEO Insights 섹션

`get_seo_insights_html()` — DataForSEO + GSC 데이터가 있을 때만 포함.

- **DataForSEO**: `dataforseo_keywords` 테이블 최근 7일. 브랜드별 상위 4 키워드 (월 검색량·CPC·경쟁도)
- **GSC**: `gsc_daily` 테이블 최근 7일. 사이트별 상위 8 쿼리 (클릭·노출·CTR)

## GitHub Actions 스케줄

- `communicator.yml` — `0 8 * * *` (PST 0:00) + `0 20 * * *` (PST 12:00)
- 필요한 Secrets: `GITHUB_TOKEN`(자동), `ORBITOOLS_USER`, `ORBITOOLS_PASS`,
  `GMAIL_OAUTH_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`,
  `COMMUNICATOR_RECIPIENT`, `COMMUNICATOR_CC`

## 워크플로우 스케줄 목록 (WORKFLOW_SCHEDULE)

수정 시 `run_communicator.py` 내 `WORKFLOW_SCHEDULE` 리스트 직접 편집.

| 파일 | 레이블 | 실행 시간 (PST) |
|------|--------|----------------|
| `data_keeper.yml` | Data Keeper | 00:00, 12:00 매일 |
| `amazon_ppc_daily.yml` | Amazon PPC | 08:00, 20:00 매일 |
| `meta_ads_daily.yml` | Meta Ads | 00:00, 12:00 매일 |
| `syncly_daily.yml` | Syncly Sync | 08:00 매일 |
| `kpi_weekly.yml` | KPI Weekly | 08:00 월요일 |
| `communicator.yml` | Communicator | 00:00, 12:00 매일 |

## 채널 freshness 기준

| 채널 | 허용 지연 |
|------|----------|
| shopify_orders_daily, amazon_sales_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily, ga4_daily, klaviyo_daily | 14시간 |
| amazon_campaigns, meta_campaigns | 25시간 |

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 워크플로우 이력 없음 | `GH_PAT` 또는 `GITHUB_REPOSITORY` 미설정 | `.env`에 추가 |
| Data Keeper 상태 없음 | `ORBITOOLS_PASS` 오류 또는 EC2 다운 | orbitools 서버 확인 |
| Gmail 전송 실패 | OAuth token 만료 | `python tools/send_gmail.py` 로 토큰 갱신 |
| 채널 🔴 표시 | 데이터 수집 자체 실패 | Data Keeper 워크플로우 로그 확인 |
| Syncly 탭 통계 없음 | Service Account JSON 없음 | `credentials/google_service_account.json` 확인 |
| Naeiae PPC 섹션 없음 | baseline JSON 없음 | `amazon_ppc_executor.py --execute` 실행 후 생성됨 |
| SEO 섹션 없음 | dataforseo/gsc 테이블 비어있음 | Data Keeper `--channel dataforseo` 실행 |

## 파일

| 파일 | 역할 |
|------|------|
| `tools/run_communicator.py` | 메인 실행 스크립트 |
| `tools/send_gmail.py` | Gmail OAuth 발송 |
| `.github/workflows/communicator.yml` | 자동 실행 스케줄 |
| `.tmp/communicator_state.json` | 연속 실패 상태 파일 |
| `.tmp/communicator_preview.html` | `--preview` 출력 |
| `.tmp/naeiae_execution_baseline.json` | PPC 실행 전/후 비교 기준 |
