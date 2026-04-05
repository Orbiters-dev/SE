---
type: errlog
domain: pipeline
agents: [generate_fin_data]
severity: critical
status: resolved
created: 2026-04-05
updated: 2026-04-05
tags: [hashtag, classification, content, hero-tab, tautology-bug]
moc: "[[MOC_파이프라인]]"
---

# errlog: Hashtag Classification Tautology Bug

## Summary
`_classify_post_by_hashtags()` in `generate_fin_data.py` had a tautological condition that made `has_stainless` always True, causing ALL Grosmimi content to be classified as "Stainless Straw Cup" regardless of actual hashtags.

## Root Cause
```python
# BROKEN — t in tag_set is ALWAYS True (tag_set = set(tags))
has_stainless = any(t in tag_set or "stainless" in t for t in tags)
```
Since `tag_set` is built from `tags`, every `t` is already in `tag_set`. The `or` short-circuits, making `has_stainless = True` for ANY non-empty hashtag list.

Combined with the priority order (stainless checked before ppsu), every Grosmimi post with any hashtags was classified as Stainless Straw Cup.

## Impact
- **deanna.hauk**: 4 posts with `#PPSU #PPSUStrawcup` hashtags were classified as Stainless Straw Cup (321K+ views misattributed)
- **ALL Grosmimi creators**: Every creator with any hashtags was wrongly placed in Stainless Straw Cup category
- Only creators with NO hashtags (fallback to DB product_types or brand default) were correctly classified

## Fix (commit 1b52544)
```python
# FIXED — only check for actual "stainless" substring
has_stainless = any("stainless" in t for t in tags)

# PPSU-specific hashtags take priority over generic straw/cup
if has_ppsu:
    if has_bottle:
        return "PPSU Baby Bottle"
    return "PPSU Straw Cup"
if has_stainless and has_tumbler:
    return "Stainless Tumbler"
if has_stainless:
    return "Stainless Straw Cup"
```

## Additional Fixes in Same Commit
1. **JP creator filtering**: Creators with ANY post in `region=jp` are excluded from US Hero tab (31 creators filtered)
2. **Post URL links**: Creator links now go to content posts (highest-views post), not profile pages
3. **post_url field**: Added to creator data pipeline (generate_fin_data.py → fin_data.js → index.html)

## Lesson Learned
- **Never use `t in tag_set` when tag_set is derived from the same iterable** — it's a tautology
- **Always test classification with known-hashtag posts** before deploying
- **Priority order matters**: PPSU (more specific) should be checked before stainless (more generic) to avoid ambiguity with tags like `strawcup` or `cup`
- **Cross-check DB data**: Query the actual DB to verify hashtags match expectations before assuming code is correct
