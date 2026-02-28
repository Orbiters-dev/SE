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

# COGS (Q2 2단계 - 선택)
SHOPIFY_COGS_SHEET_ID=...   # Polar > Connectors > Google Sheets에서 확인
```

### 캐시 재사용 (크레덴셜 없는 플랫폼)
아래 파일은 기존 Polar 데이터를 그대로 사용:
- `.tmp/polar_data/q3_amazon_brand.json` — Amazon COGS
- `.tmp/polar_data/q5_amazon_ads_campaign.json` — Amazon Ads
- `.tmp/polar_data/q7_google_ads_campaign.json` — Google Ads
- `.tmp/polar_data/q8_tiktok_ads_campaign.json` — TikTok Ads ($0 spend)

---

## Step 1: 데이터 수집 (직접 API)

### 1-A. Meta Ads 월별 집계 → Q6 생성
```
python tools/fetch_meta_ads_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q6_facebook_ads_campaign.json`
- 소요 시간: 약 3~5분 (월별 반복 API 호출)

### 1-B. Shopify 매출 집계 → Q1 생성
```
python tools/fetch_shopify_sales_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q1_channel_brand_product.json`
- 소요 시간: 약 5~10분
- ⚠️ 주의: Shopify에 없는 채널(Amazon/Target+)은 미포함. 기존 Polar Q1과 비교 권장.

### 1-C. Shopify COGS/브랜드별 집계 → Q2 생성
```
python tools/fetch_shopify_cogs_monthly.py --start 2024-01 --end 2026-02
```
- 출력: `.tmp/polar_data/q2_shopify_brand.json`
- COGS: `SHOPIFY_COGS_SHEET_ID` 없으면 0으로 처리 (CM 탭에 영향)

### 1-D. Supplemental 데이터 (기존 툴 그대로 사용)
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
| Amazon 매출 (Q1/Q3) | Polar 캐시 재사용 | Amazon SP-API 크레덴셜 추가 후 `fetch_amazon_sales_monthly.py` 구현 |
| Amazon Ads (Q5) | Polar 캐시 재사용 | Amazon Ads API 크레덴셜 추가 후 구현 |
| Google Ads (Q7) | Polar 캐시 재사용 | Google Ads API OAuth 설정 후 구현 |
| COGS (Q2) | GSheet ID 없으면 0 | `SHOPIFY_COGS_SHEET_ID` 환경변수 추가로 자동화 |
| Shopify 채널 매핑 | source_name/tags 기반 | 실제 운영 데이터 보고 채널 태깅 규칙 보완 |

---

## 포터빌리티

`.env` 파일만 복사하면 어느 머신에서도 동일하게 동작.
API key/token은 머신에 종속되지 않음.
