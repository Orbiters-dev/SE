# Influencer Inbound Pipeline — "Inbound from ONZ"

## Overview

End-to-end pipeline for creator applications submitted via the Onzenna creator-signup form.

**Flow:**
```
Creator Signup Form -> n8n -> Airtable (applicant record) + IG Scrape
                                  |
                          지후님 reviews in Airtable
                                  |
                         [Accepted] -> Email w/ sample form link
                                  |
                     /pages/influencer-gifting2 -> n8n -> Shopify Draft Order + Airtable Update
```

---

## Tools

| Tool | Command | Purpose |
|------|---------|---------|
| `setup_airtable_inbound.py` | `python tools/setup_airtable_inbound.py` | Create Airtable base + Applicants table |
| `fetch_instagram_metrics.py` | `python tools/fetch_instagram_metrics.py --handle "xxx"` | Scrape IG metrics |
| `setup_n8n_creator_to_airtable.py` | `python tools/setup_n8n_creator_to_airtable.py` | n8n: creator-signup -> Airtable |
| `deploy_influencer_gifting2_page.py` | `python tools/deploy_influencer_gifting2_page.py` | Deploy sample request page |
| `setup_n8n_gifting2_order.py` | `python tools/setup_n8n_gifting2_order.py` | n8n: gifting2 -> draft order |

---

## Setup Steps

### 1. Prerequisites (one-time)

Add to `~/.wat_secrets`:
```
AIRTABLE_API_KEY=patXXXXXXXXXXX
INSTAGRAM_BUSINESS_USER_ID=XXXXXXXXXX
```

**Get IG User ID:**
```bash
python tools/fetch_instagram_metrics.py --find-ig-id
```

### 2. Create Airtable Base
```bash
python tools/setup_airtable_inbound.py
```
Then add the output IDs to `~/.wat_secrets`:
```
AIRTABLE_INBOUND_BASE_ID=appXXXXXX
AIRTABLE_INBOUND_TABLE_ID=tblXXXXXX
```

### 3. Create n8n Workflows
```bash
python tools/setup_n8n_creator_to_airtable.py
python tools/setup_n8n_gifting2_order.py
```
Add webhook URLs to `~/.wat_secrets`:
```
N8N_CREATOR_AIRTABLE_WEBHOOK=https://n8n.orbiters.co.kr/webhook/onzenna-creator-to-airtable
N8N_GIFTING2_WEBHOOK=https://n8n.orbiters.co.kr/webhook/onzenna-gifting2-submit
```

### 4. Redeploy Creator Signup Page
```bash
python tools/deploy_creator_profile_page.py
```
(Adds the Airtable webhook call to the form submit)

### 5. Deploy Gifting2 Page
```bash
python tools/deploy_influencer_gifting2_page.py
```

### 6. Setup Airtable Automation (Manual)

See "Airtable Automation Setup" section below.

---

## Airtable Automation Setup

This must be configured directly in Airtable (not via API):

### Step-by-step:

1. **Open Airtable** -> Go to "Inbound from ONZ" base -> "Applicants" table
2. Click **Automations** (top-right) -> **Create automation**
3. Name it: **"Send Sample Form on Accepted"**

### Trigger:
- **When a record matches conditions**
- Table: `Applicants`
- Condition: `Status` is `Accepted` AND `Sample Form Sent` is NOT checked

### Action 1: Send Email
- **Send an email**
- To: `{Email}` (from the record)
- Subject: `You've been accepted as an Onzenna Creator! Choose your samples`
- Body (use rich text):

```
Hi {Name},

Congratulations! You've been accepted as an Onzenna Creator!

As a next step, please fill out our sample request form to choose your free products:

https://onzenna.com/pages/influencer-gifting2?email={Email}&cid={Shopify Customer ID}

You'll be able to select products based on your child's age and choose your preferred colors.

Welcome to the Onzenna family!

- The Onzenna Team
```

### Action 2: Update Record
- **Update record**
- Table: `Applicants`
- Record ID: Trigger record
- Field: `Sample Form Sent` = Checked (true)

### Activate:
- Toggle the automation ON
- Test by changing a record's Status to "Accepted"

---

## Data Flow Details

### Creator Signup -> Airtable
- Form payload includes: `customer_name`, `customer_email`, `customer_id`, `survey_data`
- n8n parses survey_data: primary_platform, primary_handle, following_size, content_type, etc.
- Creates Airtable record with Status = "New"
- If IG handle provided: scrapes followers_count, media_count via Meta Graph API
- Updates Airtable record with scraped metrics

### Gifting2 Submit -> Draft Order
- Form payload includes: personal_info, baby_info, selected_products, shipping_address
- n8n searches for existing Shopify customer by email
- Creates customer if not found (with influencer metafields + tags)
- Creates draft order with 100% discount + free shipping
- Updates Airtable record: Sample Form Completed = true, Draft Order ID = xxx

---

## Troubleshooting

- **IG scrape fails for personal accounts**: business_discovery only works on Business/Creator IG accounts
- **Airtable record not found**: Check that email in gifting2 URL matches email in Airtable
- **n8n workflow not triggering**: Check webhook is activated (green toggle in n8n)
- **Draft order missing customer**: Customer may not exist in Shopify; workflow creates one
