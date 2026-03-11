---
name: syncly-crawler
description: "ONZENNA Syncly content metrics crawler and D+60 tracker agent. Use when: crawling Syncly for influencer post metrics, syncing content data to Google Sheets, checking D+60 tracker status, troubleshooting Syncly export issues, backfilling brand data, running daily content pipeline, or analyzing influencer content performance. Covers US (Onzenna/zezebaebae) and JP (Grosmimi Japan) regions."
---

# Syncly Content Metrics Crawler & D+60 Tracker

## When to Use This Skill

- "싱클리 크롤러" / "Syncly 크롤링" / "컨텐츠 트랙커" / "컨텐츠 메트릭" 명령
- Syncly 웹 크롤링 관련 (세션 만료, 크롤링 실패, 데이터 누락)
- 시트 내 데이터 분류/매칭 (Brand 감지, 포스트 분류, 인플루언서 매칭)
- D+60 Tracker 상태 확인, 열 추가, 구조 변경
- 인플루언서 콘텐츠 퍼포먼스 분석
- 일일 파이프라인 모니터링 / 스케줄 관리

## Core Capabilities

### 1. Web Crawling (Playwright)
- Syncly SaaS 대시보드에서 인플루언서 포스트 메트릭 자동 수집
- 100행 export 제한 → 30일 chunk 분할로 우회
- Google OAuth 세션 기반 인증 (API 없음, 브라우저 자동화)
- 날짜 필터 조작 → export 버튼 클릭 → CSV 다운로드
- US/JP 리전 별도 URL, 별도 CSV

### 2. Data Classification (Google Sheets)
- **Brand 자동 감지**: Content/Hashtags/Theme/Product 텍스트에서 7개 브랜드 키워드 매칭
- **Posts Master**: 포스트별 메타데이터 + Syncly AI 분석 결과 (Theme, Brand, Product, Sentiment)
- **D+60 Tracker**: 포스팅 후 60일간 Comment/Like/View 일별 스냅샷 추적
- **Influencer Tracker**: 인플루언서별 포스팅 이력 매트릭스 (하이퍼링크 연결)
- **중복 제거**: source.id 기준 dedup (CSV 합침 + 시트 신규 판별)
- **버전 마이그레이션**: v1→v2→v3 자동 감지 및 열 구조 업그레이드

## Architecture

```
Syncly Dashboard (social.syncly.app)
  ↓ Playwright browser automation (30-day chunks, 100-row limit bypass)
CSV files (Data Storage/syncly/)
  ↓ sync_syncly_to_sheets.py (region-aware CSV selection)
Google Sheets: ONZENNA Affiliates Tracker
  ├── US Posts Master      (gid=1472162449)
  ├── US D+60 Tracker      (gid=199526745)
  ├── US Influencer Tracker (gid=1593954988)
  ├── JP Posts Master      (gid=842545840)
  ├── JP D+60 Tracker      (gid=295191381)
  └── JP Influencer Tracker (gid=331042723)
  ↓ syncly_daily_email.py
Email notification (orbiters11@gmail.com → wj.choi@orbiters.co.kr)
```

## Regions

| Region | Syncly Query | CSV Keyword | Brands |
|--------|-------------|-------------|--------|
| US | `q=6976fe6546f8775e88ca86b8` | `zezebaebae`, `onzenna` | Grosmimi, Cha & Mom, Onzenna, Babyrabbit, Naeiae, Goongbe, Commemoi |
| JP | `q=69a941f3208fdb401a8043fb` | `grosmimi japan`, `japan` | Grosmimi (Japan market) |

## Tools

| Tool | Purpose | Command |
|------|---------|---------|
| `fetch_syncly_export.py` | Playwright 기반 Syncly CSV 다운로드 | `python tools/fetch_syncly_export.py --region us` |
| `sync_syncly_to_sheets.py` | CSV → Google Sheets 동기화 (v3: Brand열 포함) | `python tools/sync_syncly_to_sheets.py --region us` |
| `syncly_daily_email.py` | 업데이트 이메일 발송 | `python tools/syncly_daily_email.py` |
| `daily_syncly_export.bat` | 전체 파이프라인 (US+JP+Email) | `tools/daily_syncly_export.bat` |

## Credentials & Config

```
# Google Sheets (Service Account)
GOOGLE_SERVICE_ACCOUNT_PATH=credentials/google_service_account.json

# Gmail (OAuth2 - orbiters11@gmail.com)
GMAIL_OAUTH_CREDENTIALS_PATH=credentials/gmail_oauth_credentials.json
GMAIL_TOKEN_PATH=credentials/gmail_token.json
PPC_REPORT_RECIPIENT=wj.choi@orbiters.co.kr

# Syncly (Playwright session - NOT API key)
# Session stored at: ~/.syncly_state/chrome_profile/
# First-time setup: python tools/fetch_syncly_export.py --login
```

Python path: `/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe`

## Google Sheet

- **Sheet ID**: `1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc`
- **URL**: `https://docs.google.com/spreadsheets/d/1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc/edit`

## D+60 Tracker Structure (v3)

```
Col A: Post ID
Col B: URL
Col C: Username
Col D: Post Date
Col E: Brand          ← v3에서 추가
Col F: D+ Days        (수식: =INT(TODAY()-D{row}))
Col G: Curr Comment   (OFFSET 수식 → D+N 메트릭 참조)
Col H: Curr Like
Col I: Curr View
Col J+: D+0 Cmt/Like/View, D+1 Cmt/Like/View, ... D+60 Cmt/Like/View
```

- FIXED_COLS = 9, METRICS_PER_DAY = 3, MAX_DAYS = 61
- D+0 시작 열: J (index 9)
- 총 열 수: 192 (9 + 61×3)

## Brand Auto-Detection

`analyzation.brand` 필드가 비어있을 때 Content, Hashtags, Theme, Product 텍스트에서 자동 감지:

| Keyword | Canonical Name |
|---------|---------------|
| grosmimi, growmimi, gros mimi | Grosmimi |
| cha & mom, cha&mom, chaandmom, chamom | Cha & Mom |
| onzenna, zezebaebae | Onzenna |
| babyrabbit, baby rabbit | Babyrabbit |
| naeiae, naeia | Naeiae |
| goongbe | Goongbe |
| commemoi | Commemoi |

여러 브랜드 언급 시 콤마로 구분: `Grosmimi,Onzenna,Babyrabbit`

## Schedule

- **KST 08:00 daily** via Windows Task Scheduler (`DailySynclyExport`)
- PC 꺼져있으면 실행 안됨 — NAS 이전 시 cron으로 전환 필요

## Pipeline Steps

```
1. fetch_syncly_export.py --region us
   → CSV: Data Storage/syncly/YYYY-MM-DD_syncly_zezebaebae_raw_*.csv

2. sync_syncly_to_sheets.py --region us
   → US Posts Master: 신규 포스트 추가 (Brand 자동 감지 포함)
   → US D+60 Tracker: D+N 메트릭 업데이트, 신규 행 추가
   → US Influencer Tracker: 인플루언서별 날짜 매트릭스 업데이트

3. fetch_syncly_export.py --region jp
   → CSV: Data Storage/syncly/YYYY-MM-DD_syncly_Grosmimi Japan_raw_*.csv

4. sync_syncly_to_sheets.py --region jp
   → JP Posts Master/D+60/Influencer 동일 처리

5. syncly_daily_email.py
   → 각 탭 행 수 집계 → HTML 이메일 발송 (시트 링크 포함)
```

## Known Issues & Fixes

| Issue | Fix |
|-------|-----|
| Syncly 100행 export 제한 | 30일씩 chunk 분할 후 merge (source.id 기준 dedup) |
| 세션 만료 | `--login` 재실행 필요 (Google OAuth 기반) |
| `find_latest_csv()` region 무시 | v3에서 수정: region별 keyword 필터링 적용 |
| JP에 US 데이터 오염 | region-aware CSV 선택으로 해결. 오염 시 Post ID 기준으로 삭제 |
| Brand 열 누락 (v2→v3) | 자동 마이그레이션: 열 삽입 + Posts Master에서 Brand 매칭 |
| Syncly date filter UI 변경 | debug_screenshot.png 저장됨 → UI 셀렉터 수정 필요 |
| Playwright headless 한글 렌더링 | `channel="chromium"` 사용 (시스템 Chrome 아닌 번들 Chromium) |
| D+60 지난 포스트 | `days_since > 60` → 자동 스킵 (TRACKER에서 제외) |

## Version History

| Version | Changes |
|---------|---------|
| v1 | FIXED_COLS=4 (Post ID, URL, Username, Post Date) |
| v2 | FIXED_COLS=8 (+D+ Days, Curr Cmt/Like/View 수식 열) |
| v3 | FIXED_COLS=9 (+Brand 열, region-aware CSV, Brand 자동 감지) |

## Troubleshooting Commands

```bash
# 세션 상태 확인
ls ~/.syncly_state/chrome_profile/

# 수동 US 크롤링
python tools/fetch_syncly_export.py --region us

# 수동 동기화 (크롤링 없이)
python tools/sync_syncly_to_sheets.py --region us

# 특정 CSV로 동기화
python tools/sync_syncly_to_sheets.py --region jp --csv "Data Storage/syncly/2026-03-07_syncly_Grosmimi Japan_raw_03072026.csv"

# 이메일만 발송
python tools/syncly_daily_email.py

# 전체 파이프라인 실행
tools/daily_syncly_export.bat

# Task Scheduler 확인
powershell.exe -Command "schtasks /query /tn 'DailySynclyExport' /v /fo list"
```

## Cross-Platform Context

- 인플루언서 콘텐츠가 참조하는 제품: **Shopify DTC** (onzenna.com, zezebaebae.com)
- 인플루언서 관리: Airtable (`appT2gLRR0PqMFgII`)
- 광고 성과와 연계: Amazon PPC (`amazon-ppc-agent`), Meta Ads (`meta-ads-agent`)
- 재무 모델: `tools/no_polar/` (Shopify/Amazon/Meta/Google 월간 데이터)
