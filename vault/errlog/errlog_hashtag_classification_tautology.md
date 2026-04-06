---
type: errlog
domain: pipeline
agents: [syncly-crawler, pipeliner]
severity: critical
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [hashtag, classification, bug, tautology]
moc: "[[MOC_파이프라인]]"
---

# errlog_hashtag_classification_tautology

## 증상
모든 Grosmimi 콘텐츠가 Stainless 카테고리로 분류됨.

## 원인
항등식 버그:
```python
# 잘못된 코드
has_stainless = t in tag_set  # t는 tag_set에서 꺼낸 원소 → 항상 True
```
`t`는 `tag_set`을 순회하는 원소인데, `t in tag_set`이므로 항상 `True`.

## 해결
```python
# 올바른 코드
has_stainless = any(tag in STAINLESS_KEYWORDS for tag in tag_set)
```

## 교훈
set/list 순회 중 `element in same_set` 패턴은 항등식. 의미없는 조건.
코드 리뷰 시 이런 패턴 눈여겨볼 것.
