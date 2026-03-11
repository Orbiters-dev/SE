# Weekly Performance Report - Notion Page Creator

## Objective
매주 Performance Team Weekly Report Notion 페이지를 자동 생성.
WK8-9 템플릿 기준으로 데이터 수집 + 페이지 생성.

## Template Reference
- [WK8-9 Template](https://www.notion.so/WK8-9-Performance-Team-Weekly-Report-1-31a86c6dc04680eb95ecd495eca2aa26)
- Promo Performance Comparison 섹션 제외, 나머지 전체 포함

## Tool
`tools/weekly_performance_notion.py`

## Usage

```bash
# 기본: 주차 번호로 실행
python tools/weekly_performance_notion.py --week WK11

# 이전 페이지 아카이브하고 새로 생성
python tools/weekly_performance_notion.py --week WK11 --archive-page <page_id>

# 명시적 날짜 지정
python tools/weekly_performance_notion.py --start 2026-03-06 --end 2026-03-12 --label WK11

# 데이터만 수집 (Notion 페이지 생성 안함)
python tools/weekly_performance_notion.py --week WK11 --dry-run

# Amazon Ads 건너뛰기 (속도 향상)
python tools/weekly_performance_notion.py --week WK11 --skip-amazon
```

## 주간 기준
- **Fri-Thu PST** (금요일 시작 ~ 목요일 끝)
- WK 번호 = ISO week number (목요일 기준)
- 예: WK10 = 2026-02-27 (Fri) ~ 2026-03-05 (Thu)

## 데이터 소스

| 데이터 | API | 환경변수 | 자동 |
|--------|-----|---------|:---:|
| Meta Ads (campaign level) | Graph API v18.0 | `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID` | Yes |
| Google Ads (campaign level) | Google Ads API v23 | `GOOGLE_ADS_*` (5개) | Yes |
| Amazon Ads (campaign level, excl Grosmimi) | Amazon Reporting API v3 | `AMZ_ADS_*` (3개) | Yes |
| Shopify (orders/sales) | Admin API | `SHOPIFY_SHOP`, `SHOPIFY_ACCESS_TOKEN` | Yes |
| Klaviyo (email metrics) | - | - | TBD |
| GA4 (traffic/sessions) | - | - | TBD |

## 자동 채움 항목

### OKR Table (6 cols)
- ROAS (CVR Campaigns): target 3.0
- CAC (CVR Campaigns): target $25
- Email Open Rate: TBD (Klaviyo)
- Ad Campaigns Launched: campaign count

### Key Performance Metrics
- Total Ad Spend (Meta + Google + Amazon excl Grosmimi)
- Revenue Generated (Shopify total_sales)
- CVR Campaign ROAS
- Traffic Campaign Avg CPC
- CAC (CVR Campaigns)
- Conversion Rate: TBD (GA4)
- Email Click-through Rate: TBD (Klaviyo)
- Campaigns Launched

### Ad Spend Breakdown Table
- Meta, Google, Amazon per channel: spend, conv_value, ROAS

### Top/Bottom 5 ROAS Campaigns (CVR Only)
- 9-column table: #, Ad Channel, Sales Channel, Brand/Product, Campaign, Spend, Sales, ROAS, Start Date
- CVR campaigns with spend >= $10
- Includes PMax (Google) as CVR

## 수동 채움 항목 (팀원이 직접 작성)
- Section 1: Focus Areas, Campaigns & Initiatives, Time Allocation
- Section 2: Wins & Achievements, Traffic Mix (GA4 TBD)
- Section 3: Challenges, Blockers, Resource Needs
- Section 4: Problems Solved, Key Learnings, Best Practices
- Section 5: Top Priorities, Planned Activities, OKR Focus, Support Needed

## 캠페인 분류

### Brand Classification
campaign name 기반 키워드 매칭:
- Grosmimi: grosmimi, gm, tumbler, dentalmom, livfuselli, ppsu, stainless
- CHA&MOM: cha&mom, cm, skincare, lotion, love&care
- Alpremio, Easy Shower, Naeiae, etc.

### Campaign Type
- CVR: campaign name에 'cvr', 'conversion', 'pmax' 포함
- Traffic: 'traffic', 'awareness' 포함
- Other: 나머지

## Notion Database
- DB ID: `2fb86c6dc04680988f1fe3a5803eb4f0`
- Integration: NOTION_API_TOKEN in `~/.wat_secrets`

## Output
- Notion page: `[WKnn] - Performance Team Weekly Report`
- Raw data backup: `.tmp/wknn_raw_data.json`

## 알려진 한계
| 항목 | 현재 | 향후 |
|------|------|------|
| Klaviyo | 미포함 | API 연동 |
| GA4 | 미포함 | GA4 Data API |
| Amazon Ads date format | YYYYMMDD 변환 | Fixed in tool |
| 자동 스케줄 | 수동 실행 | Task Scheduler |
