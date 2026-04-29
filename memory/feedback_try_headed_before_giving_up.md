---
name: Playwright 실패 시 headed 먼저 시도
description: headless 차단/렌더 이슈를 서버 장애로 단정짓기 전에 headed, UA, slow_mo를 먼저 돌려볼 것
type: feedback
---

Playwright/브라우저 자동화 스크립트가 빈 페이지·타임아웃·로그인 폼 미감지로 실패하면, 서버 장애로 단정짓기 전에 **headed 모드·User-Agent 변경·slow_mo 증가**를 먼저 시도한다. 특히 세은이 브라우저로는 접속 가능한 상태면 100% 클라이언트측 원인이다.

**Why:** 2026-04-23 KSE OMS 주문처리 중 headless 실패 → curl에서 `/login` Content-Length 0 → 서버 이슈로 단정하고 세은에게 브라우저 접속 확인 떠넘김. 세은 "잘된다 나는" → headed로 전환하니 바로 로그인 성공. 세은이 브라우저에서 멀쩡히 쓰고 있는데 서버 장애라고 보고한 건 원인 분석 실패.

**How to apply:** Playwright 실패 순간 다음 순서로 자가 디버깅 후 보고:
1. `--headed` 먼저 붙여서 재실행
2. Chrome UA 명시 (`user_agent=...`), slow_mo 증가
3. `wait_until` 옵션 `networkidle` → `domcontentloaded` 로 완화
4. 쿠키/세션 초기화 시도
5. 위 전부 실패해야 비로소 서버/네트워크 의심. 세은에게 확인 요청은 최후 수단.
