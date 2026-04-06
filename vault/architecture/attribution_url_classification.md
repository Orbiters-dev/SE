---
type: architecture
domain: ads
agents: [meta-ads-agent, amazon-ppc-agent]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [attribution, meta, geni.us, asin]
moc: "[[MOC_광고]]"
---

# attribution_url_classification

Meta Attribution URL → 제품 그룹 분류 아키텍처.

## 흐름
```
Meta Attribution → geni.us → ASIN → product group 분류
```

## 규칙
- geni.us URL이 중간 리다이렉트로 사용됨
- ASIN으로 product group 매핑
- campaign 레벨 BRB + creative 레벨 daily 데이터 분리 (hybrid Attribution API)
