# n8n Workflow Reference

## PROD Workflows

| ID | Name | Nodes | Interval | Status |
|----|------|-------|----------|--------|
| `fwwOeLiDLSnR77E1` | Draft Generation (Claude AI) | 42 | 30min poll | Active |
| `jf9uxkPww2xeCr82` | Approval Send | 16 | 1min poll | Active |
| `K99grtW9iWq8V79f` | Reply Handler (LT/HT) | 46 | 1min poll | Active |
| `F0sv8RsCS1v56Gkw` | Gifting (Influencer Application) | - | Webhook | Active |
| `KqICsN9F1mPwnAQ9` | Gifting2 (Sample Request -> Draft Order) | 14 | Webhook | Inactive |
| `ufMPgU6cjwuzLM0y` | Shopify Fulfillment -> Airtable | 34 | 30min poll | Active |
| `m89xU9RUbPgnkBy8` | Sample Sent -> Complete Draft Order | - | 5min poll | Active |
| `FzBJVEOTvr6qJPAL` | Syncly: Daily Content Metrics Sync | 5 | Daily | Active |
| **`k61gzrshITfju33V`** | **Shipped -> Delivered** | **14** | **30min poll** | **Inactive (migrated 2026-03-18)** |
| **`tvmHITPHpWFtcmh0`** | **Delivered -> Posted** | **10** | **6hr poll** | **Inactive (migrated 2026-03-18)** |
| **`isOQGE4ynRubL8We`** | **Content Tracking v2** | **39** | **6hr + daily** | **Inactive (migrated 2026-03-18)** |

## PROD Airtable (app3Vnmh7hLAVsevE)

| Table | ID | Purpose |
|-------|----|---------|
| Dashboard | `tblS7V4M9sqWuJPok` | Global settings (1 row) |
| Config | `tbl6gGyLMvp57q1v7` | Daily config rows |
| Creators | `tblv2Jw3ZAtAMhiYY` | Creator CRM |
| Conversations | `tblNeTyVwMomsfSk7` | Email thread log |
| Content | `tble4cuyVnXP4OvZR` | Post records + metrics |
| Orders | `tblQUz8zQRDdZvES3` | Sample orders / Inbound |
| Email Templates | `tblG3DoBW4Khz1ceU` | Forms + keywords + guidelines |
| Deals | `tblqzlSlueDpQt11b` | DocuSeal contracts |

## PROD Webhook URLs

| Key | URL |
|-----|-----|
| gifting | `https://n8n.orbiters.co.kr/webhook/influencer-gifting` |
| gifting2 | `https://n8n.orbiters.co.kr/webhook/onzenna-gifting2-submit` |

## PROD n8n Credentials

| ID | Name | Purpose |
|----|------|---------|
| `rIJuzuN1C5ieE7dr` | Shopify Admin API (Gifting) | mytoddie.myshopify.com Draft Order |
| `qgt7GDERfkz7KcAd` | Onzenna Airtable | PROD AT base access |

## Migration Log (2026-03-18)

WJ TEST → PROD migration via `tools/migrate_wjtest_to_prod.py`:

| WJ TEST ID | PROD ID | Name |
|------------|---------|------|
| `2vsXyHtjo79hnFoD` | `k61gzrshITfju33V` | Shipped -> Delivered |
| `82t55jurzbY3iUM4` | `tvmHITPHpWFtcmh0` | Delivered -> Posted |
| `zKmOX0tEWi6EBT9h` | `isOQGE4ynRubL8We` | Content Tracking v2 |

Replacements applied:
- Base: `appT2gLRR0PqMFgII` → `app3Vnmh7hLAVsevE`
- Creators: `tbl7zJ1MscP852p9N` → `tblv2Jw3ZAtAMhiYY`
- Conversations: `tblUnBCTmGzBb4BjZ` → `tblNeTyVwMomsfSk7`
- Content: `tblSva2askQRwgGV1` → `tble4cuyVnXP4OvZR`
- Orders: `tblCcWpvDZX7UZmSd` → `tblQUz8zQRDdZvES3`
- AT Credential: `59gWUPbiysH2lxd8` → `qgt7GDERfkz7KcAd`

## WJ TEST (deprecated)

WJ TEST 환경은 더 이상 사용하지 않음 (2026-03-18부터).

- Base: `appT2gLRR0PqMFgII`
- Shopify: `toddie-4080.myshopify.com`
- n8n tag: `wj-test-1`

## n8n API Patterns

```bash
# Check workflow status
curl -sk -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID"

# Trigger workflow
curl -sk -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID/run" \
  -d '{"data": {}}'

# Activate/Deactivate
curl -sk -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID/activate"

# IMPORTANT: PUT requires 'name' field
curl -sk -X PUT -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID" \
  -d '{"name":"required","nodes":[...]}'
```
