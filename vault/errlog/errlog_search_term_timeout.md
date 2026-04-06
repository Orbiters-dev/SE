---
type: errlog
domain: ads
agents: [amazon-ppc-agent]
severity: high
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [ppc, search-term, timeout, silent-fail]
moc: "[[MOC_광고]]"
---

# errlog_search_term_timeout

## 증상
search term 리포트 실행 후 결과가 빈 배열 `[]`로 반환됨. 에러 없이 정상 종료.

## 원인
Amazon Ads API search term 리포트는 생성에 최대 30분 걸릴 수 있음.
타임아웃 설정이 짧으면 polling이 완료 전에 중단되고 빈 배열 반환.
**Silent fail** — 에러 없이 빈 결과 반환이 특징.

## 해결
timeout을 30분(1800초)으로 설정. polling 간격도 충분히 확보.

## 교훈
빈 배열 = 데이터 없음이 아닐 수 있음. timeout 확인 먼저.
