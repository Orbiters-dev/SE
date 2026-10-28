---
name: mistakes-20260917-dashboard-stale-signal-missed
description: 대시보드 스크린샷에 "세션 수집 9/14 16:05"(3일 stale) 증거가 화면에 다 있는데 못 읽고, ROAS·클릭 불일치를 늘어놓으며 「숫자 틀렸냐/성과냐 둘 중 뭐 보라는 거냐」 객관식으로 되물음 → 「데이터가 안 들어오잖아 이새끼야」
metadata:
  type: reference
---

세은이 아마존 JP 대시보드 스크린샷 + 「야 ㅡ」를 던졌다. 화면 헤더에 **「세션 수집 2026-09-14 16:05」** 이 찍혀 있었고 표 데이터는 9/13까지뿐 — 오늘(9/17) 기준 **3일 stale 증거가 화면에 전부 노출**돼 있었다. 나는 그걸 못 짚고 (1) 상단 클릭 1.1K vs 표 854 불일치 (2) ROAS 30% 성과를 늘어놓은 뒤 「대시보드 숫자가 틀렸다는 거냐 / ROAS 성과냐, 둘 중 뭘 보라는 거냐」고 객관식으로 되물었다. 실제 문제는 **데이터 미수집(stale)** 하나였고 세은은 짜증(「데이터가 안 들어오잖아 이새끼야 진짜」).

**핵심:** 대시보드·리포트 화면에 찍힌 **「수집 시점 / 최신일」이 오늘보다 뒤처져 있으면 = 데이터 stale이 1순위 진단.** 성과 수치(ROAS/CVR) 해석이나 내부 정합성 비교(클릭 vs 세션)보다 **신선도 먼저**. 특히 "수집 시점"이 과거로 박혀 있는데 최근일 데이터가 비어 있으면 그게 곧 미수집 신호다 — 다른 데를 파기 전에 파이프라인 축별 freshness부터 실측(`catchup_jp_collectors.py --dry-run`).

**재발 방지:**
1. 대시보드 스크린샷/데이터 이의제기 = **화면의 수집시점·최신일부터 오늘과 대조.** stale이면 성과 논의 보류하고 수집 축 진단.
2. 화면에 진단 증거가 이미 다 있으면 객관식으로 되묻지 마라 — [[feedback-resolve-dont-offer-when-verifiable]] · [[feedback-yesno-question-stop-at-fact]] 재발. 「야」+명백한 stale 화면 = 물어볼 게 아니라 파이프라인부터 판다.
3. 이 축(아마존 트래픽/세션)은 [[mistakes-20260914-unverified-ui-text-then-overretreat]] 세션에서 이미 한 번 stale 복구한 이력 — 같은 화면 또 밀렸으면 "또 그 축" 먼저 의심.

관련: [[feedback-root-cause-not-symptom-fix-all]] · [[session-20260917-amz-traffic-stale]]
