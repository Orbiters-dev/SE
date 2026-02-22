# Klaviyo Email Flow & Campaign Dashboard

## Overview
Klaviyo 이메일 플로우(자동화) + 캠페인(수동) 퍼포먼스를 Excel로 생성하는 도구.
Polar Analytics MCP에서 데이터를 JSON으로 추출 → Python 툴이 읽어서 분류·포맷팅된 Excel 5탭 생성.

## Prerequisites
- Polar Analytics에 Klaviyo 커넥터 연결 (status: incremental)
- `.tmp/polar_data/` 디렉토리에 JSON 데이터 파일
- Python + openpyxl 패키지

## 실행 방법

### Step 1: Polar MCP 데이터 새로고침
Claude에서 Polar MCP를 통해 두 개의 쿼리 실행:

**KL1 — Flow Monthly:**
```
generate_report:
  metrics: flow_revenue, flow_orders, flow_send, flow_unique_open,
           flow_unique_click_excl_bot, flow_unique_open_rate,
           flow_unique_click_rate_excl_bot, flow_placed_order_rate,
           flow_revenue_per_subscriber, flow_bounce_rate, flow_unsubscribe_rate
  dimensions: flow
  granularity: month
  dateRange: 2024-01-01 ~ current
  connector: klaviyo
```

**KL2 — Campaign Monthly:**
```
generate_report:
  metrics: campaign_revenue, campaign_orders, campaign_send, campaign_unique_open,
           campaign_unique_click_excl_bot, campaign_unique_open_rate,
           campaign_unique_click_rate_excl_bot, campaign_placed_order_rate,
           campaign_revenue_per_subscriber, campaign_bounce_rate, campaign_unsubscribe_rate
  dimensions: campaign, subject
  granularity: month
  dateRange: 2024-01-01 ~ current
  connector: klaviyo
```

결과를 `.tmp/polar_data/save_kl.py`로 JSON 저장 (또는 수동 저장).

### Step 2: 툴 실행
```bash
python tools/klaviyo_email_dashboard.py
```

### Step 3: 출력 확인
`.tmp/klaviyo_email_dashboard_YYYY-MM-DD_HHMM.xlsx`

## Excel 구조 (5탭)

| 탭 | 내용 |
|---|---|
| Flow_Summary | 스토어별·카테고리별 플로우 퍼포먼스, New/Existing 태그 |
| Campaign_Summary | 스토어별·카테고리별 캠페인 + Top 20 + 저성과 |
| Monthly_Trends | 월별 매출 추이, New vs Existing 카운트, 신규 항목 로그 |
| Category_Analysis | 카테고리별 종합 비교 (Flow + Campaign) |
| Data_Notes | 분류 규칙, 방법론, 한계점 |

## 카테고리 분류 규칙

### Flow (자동화)
| 카테고리 | 키워드 |
|----------|--------|
| Welcome/Onboarding | welcome, pop-up |
| Cart/Browse Recovery | abandoned cart, browse abandon |
| Post-Purchase/Retention | first purchase, bounce back, replenishment, reminder |
| Win-back | winback |
| Back in Stock | back in stock |

### Campaign (수동)
| 카테고리 | 키워드 예시 |
|----------|-------------|
| Promotional/Sales | bfcm, sale, deal, prime day, free, bundle, save, friends and family 등 |
| Product Launch | launch, new arrival, introducing, pre-order, collection, new season 등 |
| Content/Educational | guide, tip, skincare, dry season, 3-step, rewards program 등 |
| Seasonal/Holiday | holiday, christmas, easter, valentine, spring, summer, winter 등 |
| Back in Stock | back in stock, restock |

## New vs Existing 로직
- 해당 월에 첫 이메일 발송 = **New**
- 다음 달부터 = **Existing**
- 롤링 방식: 매월 자동 판별

## 메트릭
| 메트릭 | 설명 | Good | Bad |
|--------|------|------|-----|
| Open Rate | 오픈율 | >= 50% (녹색) | < 30% (빨간색) |
| Click Rate | 클릭율 (봇 제외) | >= 3% | < 1% |
| Order Rate | 주문율 | >= 2% | < 0.5% |
| Revenue | 매출 ($) | — | — |
| Rev/Recip | 수신자당 매출 | — | — |
| Bounce Rate | 바운스율 | < 0.5% | >= 2% |
| Unsub Rate | 구독해지율 | < 0.1% | >= 0.5% |

## 관련 파일
- `tools/klaviyo_email_dashboard.py` — 메인 툴
- `.tmp/polar_data/kl1_flow_monthly.json` — Flow 데이터
- `.tmp/polar_data/kl2_campaign_monthly.json` — Campaign 데이터
- `.tmp/polar_data/save_kl.py` — JSON 저장 스크립트

## 알려진 한계
1. Campaign 카테고리는 키워드 매칭 — 일부 오분류 가능
2. Polar 데이터 동기화 주기에 따라 최신 데이터 지연 가능
3. Revenue attribution은 Klaviyo 기본 attribution window 기준
4. Bounce/Unsub Rate는 소계에서 weighted average 계산 불가 (raw count 부재)
