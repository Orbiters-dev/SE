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

- **KST 08:00 daily** via Windows Task Scheduler (`DailySynclyExport`) — PC 꺼져있으면 실행 안됨
- **GitHub Actions** `syncly_daily.yml` — KST 08:00 (UTC 23:00) 자동 실행 (크롤링 + 시트 동기화 + SNS 탭 전체)
  - Required Secrets: `GOOGLE_SERVICE_ACCOUNT_JSON`, `GMAIL_OAUTH_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`, `PPC_REPORT_RECIPIENT`, `SYNCLY_SESSION_STATE` (browser profile)
  - Steps: Install Playwright browsers → Restore Syncly session → fetch_syncly_export (US+JP) → sync_syncly_to_sheets (US+JP) → sync_sns_tab (all brands) → syncly_daily_email
  - ⚠️ Playwright in CI: headless mode only, Syncly session may expire → check `SYNCLY_SESSION_STATE` secret freshness

### GitHub Actions 세션 초기화 & 갱신
**첫 설정 (한 번만):**
```bash
# 로컬 브라우저 프로필 백업
tar -czf syncly_session.tar.gz ~/.syncly_state/chrome_profile/
# Base64 인코딩
base64 -w0 syncly_session.tar.gz > syncly_session_b64.txt
# GitHub > Settings > Secrets > New secret
# Name: SYNCLY_SESSION_STATE
# Value: (syncly_session_b64.txt 내용 붙여넣기)
```

**세션 만료 판별:**
- GitHub Actions 로그에서 `Syncly: Login required` 또는 `403 Forbidden` 에러
- 최근 3주 이상 CI 실행 안 했을 경우 (Syncly cookie TTL ~30일)

**세션 갱신 (만료 시):**
```bash
# 1. 로컬에서 수동 갱신
python tools/fetch_syncly_export.py --region us --login
# → Chrome profile 재인증 (Google OAuth)
# 2. 새 프로필 백업 & Base64 인코딩
tar -czf syncly_session.tar.gz ~/.syncly_state/chrome_profile/
base64 -i syncly_session.tar.gz > syncly_session_b64.txt
# 3. GitHub secret 갱신
# Settings > Secrets > SYNCLY_SESSION_STATE > Update value
# 4. Verify
python tools/fetch_syncly_export.py --region us
# 성공 → GitHub Actions 재실행
```

### Troubleshooting

| 증상 | 원인 | 해결 |
|------|------|------|
| `Error: Failed to download Syncly CSV` | 세션 만료 | 갱신 절차 실행 |
| `base64: command not found` (Windows) | PowerShell 환경 | `certutil -encode syncly_session.tar.gz syncly_session_b64.txt` 사용 |
| CI 성공하나 데이터 업로드 안 됨 | `GOOGLE_SERVICE_ACCOUNT_JSON` 누락 | Secrets 확인 (모두 5개) |
| 로컬 크롤링은 성공, CI만 실패 | Playwright headless 미호환 | CI: `channel="chromium"` 사용 (번들 Chromium) |

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

## SNS 탭 파이프라인 (sync_sns_tab*.py)

Syncly D+60 Tracker + Shopify PR/샘플 주문 데이터를 매칭해 브랜드별 SNS 탭에 기록.

### 4개 툴 (브랜드별)

| 툴 | 타겟 시트 | 탭 | 브랜드 |
|----|----------|-----|--------|
| `sync_sns_tab.py` | ONZENNA SNS (`1SwO4...`) | SNS | Grosmimi US (onzenna.com 주문) |
| `sync_sns_tab_chaenmom.py` | CHA&MOM SNS (`16XUPd...`) | SNS | CHA&MOM |
| `sync_sns_tab_jp.py` | (별도) | SNS | Grosmimi JP |
| `sync_sns_tab_grosmimi.py` | (별도) | SNS | Grosmimi 통합 |

### 데이터 흐름

```
Shopify PR/샘플 주문
  (.tmp/polar_data/q10_influencer_orders.json)
      +
PayPal 인플루언서 결제
  (.tmp/polar_data/q11_paypal_transactions.json)
      +
Syncly D+60 Tracker (Posts Master + D+60 Tracker 탭)
      ↓
계정명(Account) 기준 매칭
      ↓
SNS 탭 기록 (No, Channel, Name, Account, Product Type1~4,
              Product Name, Influencer Fee, Shipping Date,
              Content Link, D+ Days, Curr Cmt/Like/View, ...)
```

### SNS 탭 헤더 (19개 열)

```
No | Channel | Name | Account |
Product Type1 | Product Type2 | Product Type3 | Product Type4 |
Product Name | Influencer Fee | Shipping Date |
Content Link | Approved for Cross-Market Use |
D+ Days | Curr Comment | Curr Like | Curr View | Profile URL
```

### Product Type 분류 (7개 카테고리)

| 카테고리 | 해당 제품 |
|----------|----------|
| PPSU Straw Cup | PPSU 소재 빨대컵 (Flip Top 포함) |
| PPSU Tumbler | PPSU 텀블러 |
| PPSU Baby Bottle | PPSU 젖병 |
| Stainless Straw Cup | 스테인리스 빨대컵 |
| Stainless Tumbler | 스테인리스 텀블러 |
| Accessory | Tray, Brush, Teether, Lunch Bag |
| Replacement | Strap, Accessory Pack, Straw Kit |

### 계정 추출 패턴

- IG handle: 주문 노트에서 `IG (@handle)` 정규식 파싱
- TikTok: `TikTokOrderID:` 또는 `@scs.tiktokw.us` 이메일 도메인 기준

### 실행 명령

```bash
python tools/sync_sns_tab.py               # ONZENNA SNS
python tools/sync_sns_tab.py --dry-run     # 프리뷰만
python tools/sync_sns_tab_chaenmom.py      # CHA&MOM SNS
python tools/sync_sns_tab_chaenmom.py --dry-run
```

### 필터링 규칙

- Grosmimi 제품 포함 주문만 (non-Grosmimi 브랜드 제외)
- giveaway/이벤트 주문 제외
- Syncly 포스트 중 non-Grosmimi 컨텐츠 키워드 포함 시 제외

## Cross-Platform Context

- 인플루언서 콘텐츠가 참조하는 제품: **Shopify DTC** (onzenna.com, zezebaebae.com)
- 인플루언서 관리: Airtable (`appT2gLRR0PqMFgII`)
- 광고 성과와 연계: Amazon PPC (`amazon-ppc-agent`), Meta Ads (`meta-ads-agent`)
- 재무 모델: `tools/no_polar/` (Shopify/Amazon/Meta/Google 월간 데이터)
- SNS 탭 상태는 Communicator 이메일에 자동 포함 (`run_communicator.py`)

## Ops Checklist (→ `_ops-framework/OPS_FRAMEWORK.md`)

### EVALUATE (크롤링 건강체크)
- Syncly 세션 유효성 (로그인 상태)
- Google Sheets API 접근 가능 (6 tabs US/JP)
- 마지막 sync 시각 vs 현재 (freshness)
- CSV export 100-row 제한 내 동작 확인
- 출력: PASS / NEEDS_FIXES / BLOCKED

### AUDIT (데이터 정합성)
- v3 스키마 일치 (192 columns = 9 fixed + 61 days × 3 metrics)
- 브랜드 auto-detection 정확도 (7 keywords per canonical)
- US vs JP region 분리 정상 여부
- Google Sheets 탭별 row count vs Syncly source 일치
- Dedup 정상 (source.id 기준 중복 없음)

### FIX (크롤링 장애 복구)
1. `--login` 으로 Syncly 세션 갱신
2. Region-aware CSV 필터 확인
3. v3 auto-migration 트리거 (스키마 변경 시)
4. Google Sheets 수동 sync 실행
5. D+60 tracker 재계산

### IMPACT (크롤링 중단 영향)
- D+60 tracker 업데이트 중단 → 콘텐츠 성과 추적 불가
- Communicator 이메일의 Syncly row count 섹션 stale
- 마케터 콘텐츠 메트릭 판단 근거 누락
- 일간 이메일 리포트 빈 데이터


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
