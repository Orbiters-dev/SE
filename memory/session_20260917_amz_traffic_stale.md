---
name: session-20260917-amz-traffic-stale
description: 세션 2026-09-17 (메타몽 — 아마존 JP 트래픽/세션 축 9/13→9/16 stale 복구: 저장세션 OTP없이 자동통과·build+deploy 화면반영 + 교정: 화면의 stale 신호 못읽고 객관식 되물음)
metadata:
  type: project
---

## 작업: 아마존 JP 트래픽/세션 축 stale 복구 (완료·배포)

- **증상:** 세은이 대시보드 스크린샷 던짐 — Traffic&Conversion(아마존 JP) 세션 수집이 9/14 16:05에 멈춰 9/13까지만. 오늘 9/17 → 3일 stale.
- **진단(실측):** `catchup_jp_collectors.py --dry-run` → 4축 중 **아마존 트래픽분해만 STALE(최신 9/13)**, 나머지(일별매출·RPP·라쿠텐트래픽)는 9/16 fresh.
- **근본:** 이 축은 SP-API에 **Brand Analytics 롤 없어 `GET_SALES_AND_TRAFFIC_REPORT` 403 → 무인 수집 불가.** catchup은 이 축을 MONITOR(경보 전용)로만 둠. 9/14에 세은 OTP로 채운 뒤 아무도 안 돌려 3일 만에 재stale. **재발은 구조상 정상** — BA 롤 승인 전까지 수동 복구 반복(9/14 장보고 §4 결정요청 항목).
- **복구:** `.tmp/brand_analytics/br_traffic_login_collect.py`(headed, ba_profile 영구프로필) 실행 → **저장세션 살아있어 OTP 없이 자동통과** → 169일(4/01~9/16) 재수집. 9/14 세션171 · 9/15 세션155·주문1 · 9/16 세션172·주문1.
- **화면반영:** `build_jp_dash.py` → `amz-traffic-seed.json` 169일 재생성 → `deploy_to_meta_app.ps1`(vercel --prod) → READY, `meta-app-one.vercel.app` alias 갱신 검증.

## 미결 (세은 판단 대기)
- **catchup 자동화 개선안 제안함(세은 답 전):** 아마존 트래픽 STALE 감지 시 catchup이 로그인수집기를 headed 자동시도 → 세션 살아있으면(=이번처럼) 세은 모르게 치유, 만료 시에만 경보. 부작용: 3시간마다 headed 창 잠깐 뜸(세션 살아있으면 수초, 만료 시 최대 12분 대기창). **넣을지 세은 미결.**
- **근본 완전해결 = BA 롤 승인(대외 신청)** — 승인 시 US처럼 `fetch_sales_traffic.py` 무인화(코드·배선 준비됨).

## 교정
- **화면의 stale 신호(수집 9/14·데이터 9/13) 못 읽고** 클릭 불일치·ROAS 늘어놓으며 「숫자 틀렸냐/성과냐 둘 중 뭐냐」 객관식 되물음 → 「데이터가 안 들어오잖아 이새끼야」. [[mistakes-20260917-dashboard-stale-signal-missed]]. [[feedback-resolve-dont-offer-when-verifiable]] 재발.
