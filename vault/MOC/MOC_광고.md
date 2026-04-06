---
type: moc
domain: ads
agents: [amazon-ppc-agent, meta-ads-agent]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [ads, amazon, meta, ppc]
---

# MOC_광고

## 에이전트
- **amazon-ppc-agent** — PPC 분석/최적화/실행 (Sponsored Products, Brands, Display)
- **meta-ads-agent** — Meta Ads 진단, Breakdown Effect 처리

## Error Logs
- [[errlog_ppc_config_override]] — config field 추가 시 `_apply_brand_config()` 매핑 필수
- [[errlog_search_term_timeout]] — 빈 배열 = silent fail. timeout 30분
- [[errlog_autocomplete_wrong_metric]] — 메트릭 정의 유저와 먼저 확인

## 주요 규칙
- PPC 실행 전 DataKeeper 빈 채널 수집 필수 → [[feedback_nodata_datakeeper]]
- Meta Breakdown Effect: 캠페인/광고세트/광고 레벨 데이터 분리 필수

## 브랜드
| 브랜드 | Amazon Profile | Meta Account |
|--------|---------------|-------------|
| Grosmimi | 별도 seller | 별도 ad account |
| CHA&MOM | | |
| Naeiae | | |
| Onzenna | | |
