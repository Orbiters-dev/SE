---
type: architecture
domain: pipeline-dashboard
agents: [pipeliner]
status: active
created: 2026-04-05
updated: 2026-04-05
tags: [dashboard, UI, creators-tab, batch-actions, draft-preview, owner-tabs]
---

# Pipeline Dashboard — Creators Tab UI (2026-04-05)

## Owner Sub-tabs
- Color-coded pill buttons above filter bar: All / Jeehoo(green) / Laeeka(cyan) / Soyeon(amber) / Unassigned
- Clicking sets `cr-assigned` dropdown and reloads
- `selectOwnerTab(btn)` function
- Owner mapping: `_BRAND_OWNERS = {Grosmimi: Jeehoo, CHA&MOM: Laeeka, Naeiae: Soyeon}`

## Checkbox Column + Batch Actions
- First column = checkbox, header has select-all
- Auto-checked statuses: `Draft Ready`, `Needs Review`
- Batch action bar (purple): shows "N selected" + target status dropdown + Execute + Clear
- `executeBatchMove()`: loops checked IDs, PUT each to new status
- `updateBatchBar()`: toggles bar visibility based on check count

## Draft Email Preview
- "Draft" button appears on Draft Ready / Sent creators
- Accordion row below creator: fetches from `/pipeline/conversations/?creator_email=X&status=Draft+Ready`
- Shows: subject, brand badge, timestamp, full email body (pre-wrap)
- `toggleDraftPreview(creatorId, email)` function

## Email History Accordion
- Existing feature: toggleEmailHistory() — shows conversations + reply logs
- Also uses `/pipeline/conversations/?creator_email=X`

## PipelineConversation Model
- Table: `onz_pipeline_conversations`
- Fields: creator_email, creator_handle, direction, channel, subject, message_content, brand, outreach_type, status, gmail_thread_id, gmail_message_id, created_at, updated_at
- API: GET/POST at `/pipeline/conversations/`
- GET params: `creator_email`, `status`, `limit`
- n8n stores drafts here after generating from transcript

## Batch Pipeline Webhook UX
- Steps 3 (draft_gen) and 4 (send) run webhook inline with polling
- Snapshot stats → spin gear → poll /stats/ every 5s for 60s → show diff
- CSS: `.spin-icon`, `.btn-running`, `.btn-done`, `.btn-fail`

## Brand Hierarchy (CRITICAL)
- **onzenna** = umbrella brand (NOT a real brand). Covers all sub-brands
- **Grosmimi** = sender "Jane"
- **CHA&MOM** = sender "Laeeka"
- **Naeiae** = sender "Selina"
- CC1 cross-check: skip brand mismatch when `assignedBrand === 'onzenna'`

## n8n Workflow: Draft Generation (`fwwOeLiDLSnR77E1`)
- "Update Creator: Draft Ready" node writes brand from Detect Product node
- CC1 cross-check patched: onzenna umbrella bypass
- Stores drafts via POST /pipeline/conversations/
