# Onzenna Customer Survey System

## Objective

Collect structured customer data across 3 parts: Core Signup (checkout), Creator Branch (post-purchase), and Loyalty Unlock (dedicated page). Store data in both Shopify customer metafields and external DB via n8n.

---

## Architecture

```
Sign-in (no change) --> Checkout --> [Extension: Part 1 Q4-Q7]
                                          |
                                     Order Complete
                                          |
                                  Thank-you page --> [Extension: Part 2 Creator Branch]
                                          |               (only if Q7 = Yes)
                                          v
                                  /pages/loyalty-survey --> [Liquid: Part 3]
                                                              (discount code reward)
```

---

## Prerequisites

| Requirement | Status | How |
|-------------|--------|-----|
| Shopify Plus | Required | Checkout UI Extensions only work on Plus |
| Metafield definitions | Run once | `python tools/setup_survey_metafields.py` |
| Loyalty PriceRule | Run once | `python tools/setup_loyalty_price_rule.py` |
| OAuth scopes updated | Run once | `python tools/shopify_oauth.py` (includes `write_discounts`) |
| Shopify App registered | Run once | `cd onzenna-survey-app && shopify app config push` |
| n8n webhooks | Setup | Create 4 webhooks (see n8n section below) |

---

## Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| `setup_survey_metafields.py` | Register all metafield definitions | `python tools/setup_survey_metafields.py` |
| `setup_loyalty_price_rule.py` | Create discount PriceRule (one-time) | `python tools/setup_loyalty_price_rule.py` |
| `generate_survey_discount.py` | Generate unique coupon per customer | `python tools/generate_survey_discount.py --customer-id 123` |
| `deploy_loyalty_survey_page.py` | Deploy Part 3 Liquid page | `python tools/deploy_loyalty_survey_page.py` |
| `sync_survey_to_customer.py` | Sync order metafields to customer | `python tools/sync_survey_to_customer.py --order-id 123` |

---

## Deployment Steps

### Step 1: Foundation (one-time)

```bash
# Register metafield definitions
python tools/setup_survey_metafields.py

# Create loyalty discount PriceRule
python tools/setup_loyalty_price_rule.py

# Update OAuth token (if needed for new scopes)
python tools/shopify_oauth.py
```

### Step 2: Shopify App

```bash
cd onzenna-survey-app

# Install dependencies
npm install

# Link to store (first time only)
shopify app config push

# Development mode (preview URL, not visible to customers)
shopify app dev

# Deploy to production
shopify app deploy
```

After deploying, go to **Shopify Admin > Settings > Checkout > Customize** and:
1. Add "Onzenna - Tell Us About You" block after contact info
2. Add "Onzenna - Creator Profile & Loyalty" block to thank-you page
3. Configure the n8n webhook URL in extension settings

### Step 3: Loyalty Survey Page

```bash
# Deploy as hidden (test mode)
python tools/deploy_loyalty_survey_page.py --unpublish

# Deploy as public
python tools/deploy_loyalty_survey_page.py

# Rollback (remove theme assets)
python tools/deploy_loyalty_survey_page.py --rollback
```

### Step 4: n8n Webhooks

Create these webhooks in n8n:

| Webhook | Trigger | Action |
|---------|---------|--------|
| `/webhook/onzenna-order-survey-sync` | Shopify `orders/create` | Sync order metafields to customer |
| `/webhook/onzenna-creator-survey` | Thank-you page form submit | Save creator data to customer metafields |
| `/webhook/onzenna-loyalty-survey` | Loyalty page form submit | Save answers + generate discount code |
| `/webhook/onzenna-check-survey-status` | Loyalty page load (GET) | Check if customer already completed survey |

---

## Metafield Schema

### `onzenna_survey` (Part 1: Core Signup)
- `journey_stage`: trying_to_conceive / pregnant / new_mom_0_12m / mom_toddler_1_3y
- `baby_birth_month`: YYYY-MM
- `has_other_children`: boolean
- `other_children_detail`: free text
- `is_creator`: boolean
- `signup_completed_at`: datetime

### `onzenna_creator` (Part 2: Creator Branch)
- `primary_platform`: instagram / tiktok / youtube / pinterest / blog
- `primary_handle`: text
- `other_platforms`: JSON array of {platform, handle}
- `following_size`: under_1k / 1k_10k / 10k_50k / 50k_plus
- `hashtags`: comma-separated text
- `content_type`: JSON array
- `has_brand_partnerships`: boolean
- `creator_completed_at`: datetime

### `onzenna_loyalty` (Part 3: Loyalty Unlock)
- `challenges`: JSON array
- `advice_format`: JSON array
- `product_categories`: JSON array
- `purchase_frequency`: weekly / monthly / every_few_months / only_when_needed
- `product_discovery`: JSON array
- `purchase_criteria`: JSON array
- `discount_code`: text (e.g., ONZWELCOME-A7K3X2)
- `loyalty_completed_at`: datetime

---

## Testing

1. **Extension preview**: `shopify app dev` generates a preview URL
2. **Hidden page**: `--unpublish` flag keeps loyalty page invisible
3. **Fake payments**: Use Shopify Bogus Gateway
4. **Dry-run tools**: All Python tools support `--dry-run`

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Returning customer | Check `signup_completed_at` metafield, skip Part 1 |
| Guest checkout | Save as order metafields, reconcile when account created |
| Creator leaves thank-you page | Follow-up email with link |
| Duplicate loyalty submission | Return existing discount code |
| Incomplete checkout survey | Questions are optional, don't block checkout |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Extension not showing | Check: Checkout Editor > block enabled? App deployed? |
| Metafields not saving | Check: metafield definitions registered? Correct namespace? |
| Discount code not generating | Check: SHOPIFY_LOYALTY_PRICE_RULE_ID in .env? |
| Loyalty page shows login required | Customer must be signed in (uses `{% if customer %}`) |
| n8n webhook timeout | Check n8n server status at n8n.orbiters.co.kr |
