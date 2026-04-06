---
type: errlog
domain: ads
agents: [amazon-ppc-agent]
severity: high
status: resolved
created: 2026-04-06
updated: 2026-04-06
tags: [ppc, config, bug]
moc: "[[MOC_광고]]"
---

# errlog_ppc_config_override

## 증상
config field를 새로 추가했는데 에이전트가 새 값을 무시하고 기존 기본값으로 실행됨.

## 원인
`_apply_brand_config()` 함수에 새 field 매핑이 누락됨.
config 객체에서 값을 읽어도 실제 적용 로직에 반영이 안 된 상태.

## 해결
config field 추가 시 반드시 `_apply_brand_config()` 함수에 매핑 추가.

## 교훈
새 config field 추가 = `_apply_brand_config()` 수정 필수. 세트임.
