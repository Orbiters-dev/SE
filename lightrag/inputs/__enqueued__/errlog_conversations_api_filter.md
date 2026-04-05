---
type: errlog
domain: pipeline-dashboard
status: resolved
created: 2026-04-05
tags: [API, filter, query-param, conversations]
---

# Error: Conversations API Filter Mismatch (2026-04-05)

## Symptom
Draft preview showed "No draft found for this creator" even though 2,787 drafts exist in DB.

## Root Cause
Frontend sent `?email=X` but Django view expects `?creator_email=X`.
The API silently returned all records unfiltered, then client-side filter also failed
because it compared `creator_email` field against the wrong variable in some paths.

## Fix
- Changed all frontend calls from `?email=` to `?creator_email=`
- Also added `&status=Draft+Ready` server-side instead of client-side filtering

## Lesson
**Always verify API query parameter names match between frontend and backend.**
Django view uses `request.GET.get("creator_email")` — frontend must send exact same key.
When API returns unexpected results, check the query param names first before investigating data.

## Also: n8n stored drafts without `creator_handle`
- All 2,787 conversations have empty `creator_handle`
- Matching must use `creator_email` only
- Future: patch n8n to also send handle when storing draft
