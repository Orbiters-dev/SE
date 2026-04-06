---
type: architecture
domain: pipeline
agents: [pipeliner, syncly-crawler, data-keeper]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [pipeline, data, architecture, layers]
moc: "[[MOC_파이프라인]]"
---

# pipeline_data_architecture

Creator Collab Pipeline 3-Layer 데이터 아키텍처.

## 3 Data Layers

```
Layer 1: Syncly
  → 콘텐츠 메트릭 (views, likes, comments)
  → 인플루언서 발견 소스

Layer 2: Config
  → 브랜드별 설정 (EmailReplyConfig)
  → 일별 파이프라인 설정 (creators_contacted, test_email_override)

Layer 3: Apify
  → 이메일 autofill
  → 인스타그램 프로필 데이터
  → 검색 순위 데이터
```

## 흐름
Syncly → Config → Apify → Claude Draft → HiL → Send
