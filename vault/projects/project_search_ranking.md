---
type: project
domain: ads
agents: [amazon-ppc-agent, data-keeper]
status: active
created: 2026-04-06
updated: 2026-11-10
tags: [search-ranking, apify, keyword, dashboard]
moc: "[[MOC_광고]]"
---

# project_search_ranking

Generic 키워드 검색 순위 추적.

## 파이프라인
WONGI `amazon_search_ranking` 수집기(자체 Apify actor `orbiters_creators/amazon-rank-tracker`, 매일 09:30 UTC)
→ datakeeper `gk_amazon_search_ranking` → `tools/generate_fin_data.py` `_build_search_ranking_data` → Dashboard Tab 8.

SE 는 검색 순위를 수집하지 않고 읽기만 한다. 키워드는 WONGI datakeeper `BrandKeyword`(collector_name=amazon_search_ranking)에서 관리한다.

## 특징
- 일별 position matrix
- 트렌드 차트
- 신규 키워드 추적
