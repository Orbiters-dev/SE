# No-Polar Financial Model Workflow

## Objective
Polar Analytics MCP 없이 직접 API 호출로 동일한 Financial Model Excel 아웃풋 생성.
기존 `polar_financial_model.py`는 변경 없이 그대로 사용.

---

## 전제 조건

### 필수 환경변수 (.env)
```
# Shopify (Q1, Q2)
SHOPIFY_SHOP=mytoddie.myshopify.com
SHOPIFY_ACCESS_TOKEN=...

# Meta Ads (Q6)
META_ACCESS_TOKEN=...
META_AD_ACCOUNT_ID=act_...

# Amazon SP-API (Q3 - 주문 매출)
AMZ_SP_CLIENT_ID=...
AMZ_SP_CLIENT_SECRET=...
AMZ_SP_REFRESH_TOKEN=...
AMZ_SP_MARKETPLACE_ID=ATVPDKIKX0DER

# Amazon Ads API (Q5 - 광고 성과)
AMZ_ADS_CLIENT_ID=...
AMZ_ADS_CLIENT_SECRET=...
AMZ_ADS_REFRESH_TOKEN=...

# Google Ads API (Q7)
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID=...

# COGS (Q2 2단계 - 선택)
SHOPIFY_COGS_SHEET_ID=...   # Polar > Connectors > Google Sheets에서 확인
```

### 캐시 재사용 (크레덴셜 없는 플랫폼)
아래 파일은 기존 Polar 데이터를 그대로 사용 (크레덴셜 없을 경우):
- `.tmp/polar_data/q8_tiktok_ads_campaign.json` — TikTok Ads ($0 spend, 변경 없음)

---

## Step 1: 데이터 수집 (직접 API)

### 1-A. Meta Ads 월별 집계 → Q6 생성
```
python tools/no_polar/fetch_meta_ads_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q6_facebook_ads_campaign.json`
- 소요 시간: 약 3~5분 (월별 반복 API 호출)

### 1-B. Shopify 매출 집계 → Q1 생성
```
python tools/no_polar/fetch_shopify_sales_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q1_channel_brand_product.json`
- 소요 시간: 약 5~10분
- 주의: Amazon/Target+ 채널은 Shopify 외부 데이터라 미포함. 기존 Polar Q1과 비교 권장.

### 1-C. Shopify COGS/브랜드별 집계 → Q2 생성
```
python tools/no_polar/fetch_shopify_cogs_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q2_shopify_brand.json`
- COGS: `SHOPIFY_COGS_SHEET_ID` 없으면 0으로 처리 (CM 탭에 영향)

### 1-D. Amazon SP-API 주문 매출 → Q3 생성
```
python tools/no_polar/fetch_amazon_sales_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q3_amazon_brand.json`
- 소요 시간: 약 10~20분 (월별 리포트 생성 대기 포함)
- 참고: total_fees, cost_of_products는 현재 0 (향후 Finances API로 보완 예정)
- 의존성: `AMZ_SP_CLIENT_ID`, `AMZ_SP_CLIENT_SECRET`, `AMZ_SP_REFRESH_TOKEN`

### 1-E. Amazon Ads 광고 성과 → Q5 생성
```
python tools/no_polar/fetch_amazon_ads_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q5_amazon_ads_campaign.json`
- 소요 시간: 약 10~20분 (Ads Reporting v3 비동기 리포트)
- 의존성: `AMZ_ADS_CLIENT_ID`, `AMZ_ADS_CLIENT_SECRET`, `AMZ_ADS_REFRESH_TOKEN`

### 1-F. Google Ads 광고 성과 → Q7 생성
```
python tools/no_polar/fetch_google_ads_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q7_google_ads_campaign.json`
- 의존성: `GOOGLE_ADS_*` 환경변수 5개
- 패키지 필요: `pip install google-ads`

### 1-G. Supplemental 데이터 (기존 툴 그대로 사용)
```
python tools/fetch_influencer_orders.py    # Q10: 인플루언서 PR 주문
python tools/fetch_paypal_transactions.py  # Q11: PayPal 결제 내역
```

---

## Step 2: Financial Model 생성 (변경 없음)

```
python tools/polar_financial_model.py
```
- 읽는 파일: `.tmp/polar_data/q*.json` (위에서 생성한 파일들)
- 출력: `Data Storage/polar/financial_model_YYYY-MM-DD_vN.xlsx`

---

## Step 3: 검증

1. **Q6 검증**: Meta Ads 총 spend가 기존 Polar 수치와 유사한지 확인
   - 예상 차이 원인: Polar BUILDING 상태로 일부 누락되었던 데이터가 이번에는 완전할 수 있음

2. **Q1 검증**: D2C 채널 매출이 Polar Q1 D2C와 유사한지 확인
   - Amazon/Target+ 채널은 Shopify 외부 데이터라 0으로 나옴 → 허용

3. **Q2 검증**: 브랜드별 gross_sales 합계가 Q1 D2C 합계와 유사한지 확인

---

## 알려진 한계 및 향후 개선

| 항목 | 현재 | 향후 |
|------|------|------|
| Amazon 수수료 (Q3) | total_fees = 0 | SP-API Finances API로 FBA fee 추가 |
| Amazon COGS (Q3) | cost_of_products = 0 | `SHOPIFY_COGS_SHEET_ID` 설정 후 보완 |
| COGS (Q2) | GSheet ID 없으면 0 | `SHOPIFY_COGS_SHEET_ID` 환경변수 추가로 자동화 |
| Shopify 채널 매핑 | source_name/tags 기반 | 실제 운영 데이터 보고 채널 태깅 규칙 보완 |
| TikTok Ads (Q8) | Polar 캐시 재사용 ($0) | TikTok Ads API 크레덴셜 취득 시 구현 |

---

## 포터빌리티

`.env` 파일만 복사하면 어느 머신에서도 동일하게 동작.
API key/token은 머신에 종속되지 않음.

---

## 최근 실행 기록

### 2026-02-28 (최초 테스트)

**아웃풋**: `Data Storage/polar/financial_model_2026-02-28_v1.xlsx`

| 데이터 | 수치 | 비고 |
|--------|------|------|
| Q1 Shopify 매출 | $2,345,926 / 891 rows | D2C, B2B, PR, Target+, TikTok, Amazon 일부 포함 |
| Q2 Shopify 브랜드 | $2,308,471 / 248 rows | COGS = 0 (GSheet ID 미설정) |
| Q6 Meta Ads | $254,703 spend / 274 rows | Polar BUILDING 때보다 완전한 데이터 |
| Q3/Q5/Q7/Q8 | Polar 캐시 재사용 | 2026-02-22 기준 Polar 데이터 |

**탭 생성**: Sales, Ads, Summary, ADS Campaign Details, Organic Sales, Search Volume, Influencer Dashboard, Promo Analysis, CM, Model Check (총 10개)
