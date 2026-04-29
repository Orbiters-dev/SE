---
name: GitHub Actions 워크플로우 push 전 secret 등록 검증
description: 새 워크플로우 push 전에 참조하는 secret이 GitHub Secrets에 실제 등록돼있는지 확인. .env에 있다고 GitHub에도 있는 게 아님.
type: feedback
---

새 GitHub Actions 워크플로우를 push하기 전에 ① 참조하는 모든 `secrets.XXX`가 GitHub repo Secrets에 실제 등록돼있는지 확인 ② 등록 안 됐으면 `.env` 값을 먼저 `gh secret set XXX`으로 등록 ③ runner에 필요한 Python 의존성 (dotenv 등) 설치 여부 확인.

**Why:** 2026-04-29 세션. `twitter_slot_notify` 워크플로우 push 후 cron 발동했지만 알림 안 옴. "다른 워크플로우들도 같은 secret(`TEAMS_WEBHOOK_URL_SEEUN`)을 쓰니까 등록돼 있을 것"이라고 추측한 게 틀림. 실제 GitHub Secrets에는 7개만 있고 (`APIFY_API_TOKEN`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `INSTAGRAM_BUSINESS_USER_ID`, `META_ACCESS_TOKEN`, `N8N_API_KEY`, `N8N_BASE_URL`, `NOTION_API_TOKEN`) Teams webhook 자체가 등록 안 돼있었음. 또 dotenv 모듈도 runner에 미설치 → ModuleNotFoundError. 두 문제 모두 push 전에 1분 내 검증 가능했음.

**How to apply:**
1. push 전 검증 명령:
   ```bash
   gh api repos/<org>/<repo>/actions/secrets --jq '.secrets[].name' | grep -E "<참조하는 secret 이름>"
   ```
2. 빠진 secret 즉시 등록:
   ```bash
   VALUE=$(grep "^XXX=" .env | cut -d= -f2-)
   echo "$VALUE" | gh secret set XXX --repo <org>/<repo>
   ```
3. Python 의존성: GitHub Actions runner는 깨끗한 환경. 워크플로우에서 `pip install` 명시하거나, 코드에서 optional import (`try: from dotenv import load_dotenv; ... except ImportError: pass`).
4. push 후 즉시 `gh workflow run`으로 수동 trigger → `gh run view --log-failed` 검증까지 본인이 책임.

`grep -l TEAMS_WEBHOOK_URL_SEEUN .github/workflows/*.yml` 결과로 secret 등록 여부 추정 금지 (참조와 등록은 별개).
