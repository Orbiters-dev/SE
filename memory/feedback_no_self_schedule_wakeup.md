---
name: 파이프라인 중간 체크용 ScheduleWakeup 금지
description: 작업 실행 중 자기 자신을 깨우는 ScheduleWakeup 예약은 사용자 메시지로 오인되어 재실행을 유발한다
type: feedback
---

풀 파이프라인 등 장시간 백그라운드 작업 중, "중간 상태 체크"를 명목으로 동일 프롬프트("주문처리" 등)로 ScheduleWakeup을 거는 행동은 금지.

**Why:** 2026-04-23 Rakuten 주문처리 1차 완료 후, 5분 뒤 깨우도록 걸어둔 ScheduleWakeup("주문처리")이 발동했는데, 나는 그걸 세은의 새 요청으로 착각하고 2차 파이프라인을 돌렸다. 세은은 요청한 적 없었다. 세은이 "2차 실행을 왜했는데?"로 질책.

**How to apply:**
- 백그라운드 태스크는 task-notification으로 자동 통지된다. 별도 wakeup 불필요.
- ScheduleWakeup을 정말 써야 한다면, 작업 실행 트리거 키워드와 겹치지 않는 별도 체크 프롬프트로 설정할 것.
- 자기 자신이 보낸 wakeup 메시지인지 분간 안 되면 실행 말고 세은에게 확인부터.
