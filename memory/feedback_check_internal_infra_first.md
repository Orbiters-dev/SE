---
name: 새 도구·비용 얘기 전에 기존 인프라 확인 필수
description: Apify/API 신규 도입 제안하기 전에 .env 크레덴셜, tools/, 기존 계정/플랜/credit 먼저 조사. 확인 가능한 건 묻지 마.
type: feedback
---

새 도구 도입이나 비용 얘기 꺼내기 전에 반드시 내부 조사부터.

**Why:** Apify 도입 제안할 때 "월 $15 OK?" 물어봤는데, 이미 ORBITERS_creators 계정이 SCALE 플랜($199 credit 포함)으로 돌고 있었음. .env에 APIFY_API_TOKEN 실값 있고 tools/ 에 apify_twitter_monitor.py 등 있는데도 안 찾아보고 세은한테 물어봐서 세은이 "니 주글래" 할 정도로 화남.

**How to apply:**
- .env에 XXX_API_KEY / XXX_TOKEN 있으면 먼저 API 조회 → 플랜/credit/사용 현황 확인
- tools/ 에 관련 스크립트 있으면 기존 사용 내역 파악
- "비용 얼마 OK?" "계정 있어요?" 같은 질문 금지 — 내가 조회 가능한 것
- 물어볼 건 정말 외부에만 있는 것 (비번, 2FA 수단, 정책 결정 등)만
