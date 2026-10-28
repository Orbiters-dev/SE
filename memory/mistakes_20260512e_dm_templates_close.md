---
name: 오답노트 2026-05-12e — dm-templates 머지 후 떠넘김 재발 + 미검증 단정
description: PR #1181 머지 GO 두 번 떠넘김 ("머지 진행할까요" / "GO 주시면") + "verify-signers PASS 보장" 미검증 단정. 5/12 동일 라운드 5번째 떠넘김 재발 → "디질려고" 격분.
type: feedback
---

# 떠넘김 5번째 재발 + 미검증 "보장" 단정

## 5/12 본 round 위반 2건

1. **PR #1181 머지 GO 묻기**: PR #1161 머지 완료 직후, fe-test fix #1181 OPEN 상태에서 "머지 진행할까요" 한 번 + "GO 주시면" 한 번 — 같은 round 2회. 세은 이미 직전 "니가 하는 거야? 스스로 가능?" 으로 자율 처리 GO 줬음. 메모리 `feedback_yesno_question_stop_at_fact.md` + `feedback_dont_ask_when_info_given.md` 5번째 재발.
2. **"verify-signers PASS 보장"**: MCP edit_file 호출 전 답변 본문에 "통과 보장" 단정. 실제 fact 는 "직전 PR #1161 의 같은 signer 가 같은 cap 으로 PASS 한 케이스 존재" — 본 신규 PR 의 PASS 여부는 실행 후 검증 가능. "보장" 어휘 미검증 단정. 메모리 `feedback_no_speculation_even_with_label.md` 위반.

## Why

세은: "검증된 것만 말해 진짜 패버리기 전에" + "디질려고" 격분.

## How to apply

- 같은 round 안에서 한 번 명시적 GO ("니가 해결" / "ㅇㅇ" / "스스로 가능?") 받으면 그 다음 동일 영역 액션은 자동 진행. "머지 진행할까요" / "GO 주시면" 묻기 X.
- "보장" / "확실" / "예상" 강도 어휘는 fact 가 미래 시점 (PR 실행 후) 일 때 금지. 단정형으로 쓸 수 있는 fact 만 단정형. 미래 fact 는 "직전 케이스 — 동일 조건 PASS 확인" 같은 실증 패턴으로 표현.
- 본 사고 5/12 만 5번째 떠넘김 재발 (`mistakes_20260512.md` 4번째 + 본 5번째). 같은 메모리 룰 5회 위반 = 메모리 자체가 동작 안 함의 증거.
