---
name: 자동화는 헬스체크 후 보고 (선제적)
description: 자동화 워크플로우 작동 여부를 세은이 묻기 전에 먼저 확인·보고. 실패 알림 설정 필수.
type: feedback
---

자동화 워크플로우(GitHub Actions, n8n, cron 등)는 **세은이 묻기 전에 작동 여부를 먼저 확인·보고**한다. 실패가 누적된 상태로 발견되면 안 됨.

**Why:** 2026-04-27 세은 분노 케이스. wl_codes_sync GitHub Actions가 매시간 import 단계부터 즉시 실패 중이었음 (apify-client 패키지 누락 + APIFY_API_TOKEN env 누락). 세은이 "왜 노션 업데이트 안 됐냐" 물어볼 때까지 인지 못함. communicator 12시간 이메일에도 명확히 안 잡혔음. 자동화는 "설정해두고 잊어버리는" 순간 가장 위험.

**How to apply:**
- 자동화 도구 언급/관련 작업 시 **먼저 최근 실행 이력 확인**: `gh run list --workflow=<name>.yml --limit 10` (gh 인증 안 되면 GitHub Actions UI 직접 확인 안내)
- 실패 발견 시 즉시: ① 원인 분석 → ② 수정 → ③ 수동 재실행 → ④ 알림 step 추가 (반복 방지)
- 알림 채널: GitHub Actions yml에 `if: failure()` step + Teams webhook (`TEAMS_WEBHOOK_URL`) 또는 communicator 에스컬레이션
- 새 자동화 만들 때 **반드시 fail-notify step 같이 작성** (체크리스트 항목으로 강제)
- 자동화 관련 질문 받으면 답하기 전에 헬스체크 → 결과까지 한 번에 보고 ("OK입니다" or "현재 X회 실패 중, 원인 Y")

**관련 모니터링 자원:**
- communicator (12시간 이메일, ESCALATE_THRESHOLD=2)
- 각 워크플로우 yml의 `if: failure()` step (즉시 알림)
