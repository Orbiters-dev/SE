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
  ├── get_datakeeper_status()  → orbitools API (9개 채널 freshness)
  ├── get_gh_runs()            → GitHub API (최근 24시간 워크플로우 이력)
  ├── get_next_schedules()     → 정적 스케줄 → 향후 12시간 예정 목록
  └── build_html()             → 이메일 HTML 생성
        └── send_gmail.py      → Gmail OAuth로 발송
```

## 주요 명령

| 명령 | 설명 |
|------|------|
| `python tools/run_communicator.py` | 즉시 발송 |
| `python tools/run_communicator.py --dry-run` | 발송 없이 확인 |
| `python tools/run_communicator.py --preview` | `.tmp/communicator_preview.html` 저장 |
| `python tools/run_communicator.py --to other@email.com` | 수신자 변경 |

## 이메일 구성

1. **헤더** — 날짜/시간(PST) + 전체 헬스 배지 (🟢/🟡/🔴)
2. **알림** — 실패 워크플로우 / 지연·누락 채널 목록
3. **데이터 수집 현황** — 9개 채널별 최종 수집 시간, row 수, 기간
4. **워크플로우 이력** — 최근 24시간 GitHub Actions 실행 결과 및 소요 시간
5. **향후 12시간 예정** — 다음에 실행될 작업 목록

## 환경변수

| 변수 | 설명 | 필수 |
|------|------|------|
| `COMMUNICATOR_RECIPIENT` | 수신자 이메일 | 권장 (없으면 `PPC_REPORT_RECIPIENT` 폴백) |
| `GITHUB_REPOSITORY` | `owner/repo` 형식 | GitHub Actions에서 자동 설정 |
| `GH_PAT` | GitHub Personal Access Token (로컬 실행 시) | 로컬만 |
| `GITHUB_TOKEN` | GitHub Actions 내부 토큰 (자동) | Actions만 |
| `ORBITOOLS_USER` / `ORBITOOLS_PASS` | orbitools API 인증 | 필수 |
| `GMAIL_OAUTH_CREDENTIALS_PATH` | Gmail OAuth credentials.json 경로 | 필수 |
| `ZEZEBAEBAE_GMAIL_TOKEN_PATH` | Gmail token.json 경로 | 필수 |

## GitHub Actions 스케줄

- `communicator.yml` — `0 8 * * *` (PST 0:00) + `0 20 * * *` (PST 12:00)
- 필요한 Secrets: `GITHUB_TOKEN`(자동), `ORBITOOLS_USER`, `ORBITOOLS_PASS`,
  `GMAIL_OAUTH_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`,
  `COMMUNICATOR_RECIPIENT`(없으면 `PPC_REPORT_RECIPIENT` 사용)

## 채널 freshness 기준

| 채널 | 허용 지연 |
|------|----------|
| shopify_orders_daily, amazon_sales_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily, ga4_daily, klaviyo_daily | 14시간 |
| amazon_campaigns, meta_campaigns | 25시간 |

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 워크플로우 이력 없음 | `GH_PAT` 또는 `GITHUB_REPOSITORY` 미설정 | .env에 추가 |
| Data Keeper 상태 없음 | `ORBITOOLS_PASS` 오류 또는 EC2 다운 | orbitools 서버 확인 |
| Gmail 전송 실패 | OAuth token 만료 | `python tools/send_gmail.py` 로 토큰 갱신 |
| 채널 🔴 표시 | 데이터 수집 자체 실패 | Data Keeper 워크플로우 로그 확인 |

## 스케줄 확인/수정

`tools/run_communicator.py` 내 `WORKFLOW_SCHEDULE` 리스트 편집.
새 워크플로우 추가 시 이 리스트에도 항목 추가 필요.
