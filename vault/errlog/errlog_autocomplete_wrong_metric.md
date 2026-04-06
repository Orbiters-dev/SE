---
type: errlog
domain: ads
agents: [amazon-ppc-agent]
severity: medium
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [autocomplete, metric, definition]
moc: "[[MOC_광고]]"
---

# errlog_autocomplete_wrong_metric

## 증상
autocomplete 분석 결과가 유저 기대와 다름. 메트릭 정의가 서로 달랐음.

## 원인
에이전트가 임의로 메트릭을 정의하고 분석 진행.
유저가 생각하는 메트릭과 에이전트가 사용한 메트릭이 불일치.

## 해결
분석 시작 전 메트릭 정의를 유저와 먼저 합의.

## 교훈
메트릭 이름이 같아도 정의가 다를 수 있다. 항상 먼저 확인.
