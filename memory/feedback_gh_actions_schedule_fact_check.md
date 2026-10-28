---
name: GH Actions schedule 진단은 fact부터
description: cron 펑크 진단 시 "high load skip" 추측 X. gh run list로 발화 횟수 / 성공 횟수 fact 확인 후 판정.
type: feedback
---

GH Actions schedule cron이 안 돌 때 "GitHub이 high load 시 skip 가능" 추측 금지. 발화 자체가 0회인 케이스 / 발화는 되는데 매번 fail인 케이스가 더 흔함.

**Why:** 2026-05-07b 세션에 9개 워크플로우 펑크 진단 시 "가끔 skip"이라고 추측 → 세은 "한 번도 한 적 없다" 강한 교정. 실제는:
- 2개(meta_jp_daily, commenter): schedule 발화 0회 (yml에 cron 적혀있어도 GH가 안 띄움)
- 5개(einstein/kantoku/chousa/kikaku/hashtag): 발화 됐는데 매번 fail (27/26/7/3/3회 전수 fail) — secret 누락 + 코드 untracked

**How to apply:**
1. 진단 첫 명령: `gh run list --workflow=X.yml --json event,conclusion --limit 50` → schedule trigger 카운트
2. 분류:
   - schedule 발화 0회 → cron 등록 자체 안 됨 (신규 yml 첫 발화 지연 / 60일 비활성 룰 / yml 문법)
   - 발화 됐는데 매번 fail → 코드/secret/runner 환경 문제
   - 가끔 skip → 진짜 high-load (드물다)
3. 추측 금지. fact 보고 판정.
4. 같은 자원(secret, 코드) 쓰는 다른 워크플로우 작동 여부도 같이 확인 — 자원 레벨 문제인지 판별.
