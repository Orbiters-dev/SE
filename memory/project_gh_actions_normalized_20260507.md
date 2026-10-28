---
name: GH Actions 9개 정상화 + 워치독 알림 fix (2026-05-07)
description: GH Actions schedule 펑크 9개 정상화 + ci_watchdog Teams 알림 작동. 9개 정상 / 1개 미해결.
type: project
---

# GH Actions 정상화 결과 (2026-05-07b 세션)

**Why:** 9개 워크플로우가 schedule 발화 안 되거나 매번 fail. 세은 알림도 못 받던 상태 → 즉시 정상화 + 워치독 알림 작동시킴.

**How to apply:** 다음 세션 진단·운영 시 이 인프라 변경 기준으로 판단.

---

## 정상화 완료 (9개) ✅

| 워크플로우 | schedule | 정상화 시점 |
|---|---|---|
| einstein_daily | 매일 18:00 KST | 5/7 |
| kantoku | 매일 09:00 KST | 5/7 |
| chousa | 매주 화/목 08:00 KST | 5/7 |
| kikaku | 매주 금 09:00 KST | 5/7 |
| hashtag | 매주 금 08:00 KST (twitter_hashtag.py 신규 작성) | 5/7 |
| meta_jp_daily | 매일 08:55 KST | 5/7 |
| meta_ads_daily | 매일 17:00/05:00 KST | 5/7 |
| tweet | 매일 10:00/19:00 KST | 5/7 |
| soukantoku | 매일 09:00 KST | 5/7 |
| commenter | 매일 12-16시 JST 매시 (트위터 정지 풀린 후 schedule 재개) | 5/7 |

## 미해결 (1개) ❌

- **wednesday_ig_competitor** — picnob.com 봇 차단(403). 4개 IG 프로필 다 fetch 실패.
  - **해결 plan:** Apify IG profile scraper로 데이터 소스 교체. 별도 작업.
  - 매주 수 10:00 KST.

## ci_watchdog (워치독) 변경

| 항목 | 변경 |
|---|---|
| Teams 알림 | Adaptive Card → 단순 text `{"text":"..."}` (`feedback_teams_simple_text` 룰 적용) |
| 알림 대상 | failure만 → failure + no_runs (cron 발화 X도 알림) |
| REPO 기본값 | WJ-Test1 → Orbiters-dev/SE |
| MONITORED 추가 | meta_jp_daily |
| 발화 schedule | 매일 10:00/22:00 KST |

→ 내일부터 cron 펑크 시 즉시 Teams (TEAMS_WEBHOOK_URL_SEEUN) 알림 수신.

## 신규 등록 GH Secrets (17개)

ANTHROPIC_API_KEY, FIRECRAWL_API_KEY, TEAMS_WEBHOOK_URL, TEAMS_MASTER_WEBHOOK_URL, TEAMS_GRAPH_CLIENT_ID/SECRET, TEAMS_TENANT_ID, TEAMS_MASTER_CHANNEL_ID, META_AD_ACCOUNT_ID, META_REPORT_RECIPIENT, PPC_REPORT_RECIPIENT, TWITTER_API_KEY/API_SECRET/BEARER_TOKEN/ACCESS_TOKEN/ACCESS_TOKEN_SECRET/CLIENT_ID/CLIENT_SECRET

## 신규 코드

- `tools/twitter_hashtag.py` (289줄) — Firecrawl로 일본 인기 해시태그 4 카테고리 12 쿼리 검색 → Claude use_score 평가 → Teams 발송 + intel 저장 (기획맨용)
- `tools/ci_watchdog.py` 수정 — Teams 알림 simple text + no_runs 포함

## 다음 세션이 알아야 할 것

1. **5/8 새벽 cron 자동 발화 결과 확인** — 9개 정상화된 워크플로우의 자동 schedule 발화 잘 잡히는지. 안 잡히면 GH Actions 신뢰성 문제 → n8n 옮길지 결정.
2. **wednesday_ig_competitor 별도 plan** — Apify 데이터 소스 교체.
3. **commenter 시범 운영** — 매일 5번 (12-16시 JST) 자동 발송. 첫 사이클 결과 확인.
