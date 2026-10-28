---
name: 오답노트 2026-05-07b
description: 매일 9시 발송 부탁 잊음 + GH Actions schedule "가끔 skip" 추측 + commenter yml 주석만 보고 의도 정지 단정. 강한 교정 3건.
type: project
---

# 2026-05-07b 사고 3건

## 1. "내가 뭐하라했어" — 매일 9시 Meta JP daily 발송 부탁 잊음

**상황:** 세은이 /메타몽 호출 → 메뉴만 띄움. 실제로는 매일 아침 9시 자동 발송 시켜놨고 그날 안 와서 부른 것.

**문제:**
- 세은이 시킨 자동 트래킹 부재
- 부르면 직전 작업/펑크난 거 확인 먼저 (`feedback_check_mistake_when_called`) 룰 미적용
- "어떤 작업 도와드릴까요?" 메뉴부터 띄움 → "야 내가 니 뭐하라했어" 강한 교정

**룰:** 자동 발송·정기 작업 알고 있는 게 펑크 났으면 부르기 전에 ci_watchdog가 잡아야. (이번에 워치독도 알림 안 가던 상태 → fix 완료)

## 2. "가끔이 아니라 한 번도 한 적 없다" — GH Actions schedule 추측

**상황:** GH Actions schedule cron이 어쩌다 안 돌았는지 진단할 때 "high load 시 skip 가능"이라고 추측.

**문제:**
- `feedback_verified_only_no_speculation` 룰 미적용
- 처음부터 `gh run list --workflow=X --json event` 으로 schedule 발화 횟수 확인했어야
- "가끔 skip"이라고 단정 → 세은: "한 번도 한 적이 없다"

**진짜 원인 (확인 후 fact):**
- meta_jp_daily / commenter: schedule 발화 자체 0회 (yml에 cron 적혀있어도 GH가 안 띄움)
- einstein/kantoku/chousa/kikaku/hashtag: 발화는 되지만 secret 누락 + tools/*.py 100여개 untracked로 매번 fail (27/26/7/3/3회 모두 fail)

**룰:** GH Actions schedule 진단 시 → 추측 금지. `gh run list --json event,conclusion` 으로 "발화 횟수 / 성공 횟수" fact부터.

## 3. "정지 풀린 지 오억년" — commenter yml 주석만 보고 단정

**상황:** commenter.yml에 `schedule: 一時停止中（アカウント停止のため 2026-03-20）` 주석으로 적혀있는 거 보고 "의도된 정지" 단정. 첫 보고에서 "(a) commenter — 정지 유지? 재개?" 로 세은 결정 떠넘김.

**문제:**
- yml 코멘트만 신뢰. 트위터 계정 상태 사실 확인 안 함
- tweet.yml은 같은 트위터 계정으로 통과 → 정지 풀린 증거 있었는데 못 잡음
- 세은: "정지 풀리고 새 계정 판 지 오억년 지남 도대체 얼마나 멈춰있었던 거야"

**룰:** "정지 사유" 같은 yml 주석은 시점 정보. 코드 작성 시점 사실이고 현재는 다를 수 있음. 동일 자원(같은 계정·토큰) 다른 워크플로우 작동 여부로 사실 확인 후 판정.

---

## 종합 — 검증 절차 자가 점검

세 사고 다 같은 패턴: **사실 확인 안 하고 추측·단정**.

1. ❌ "가끔 skip" 추측 → ✅ `gh run list` 발화 횟수 fact
2. ❌ yml 주석 보고 의도 정지 단정 → ✅ 같은 자원 사용 다른 워크플로우 상태 확인
3. ❌ 부르면 메뉴 띄움 → ✅ 직전 작업/펑크 먼저 확인

기존 메모리 룰 다 있음. 적용 미흡이 문제.
