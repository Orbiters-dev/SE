---
name: mistakes-20261002-channel-perf-declared-unavailable
description: 채널 성과를 "수집 불가/미확정/착수 보류"로 단정하기 전에 수집 루트(DataKeeper·브라우저)부터 소진하라 — PPC 아마존 SP·TikTok 2건 동시 발생 (2026-10-02 세은 강한교정)
metadata:
  type: feedback
---

위클리 덱 채널 현황에서 **성과를 "없음/미확정"으로 비워둔 2건**을 세은이 강하게 교정.

## 무엇을 틀렸나
1. **PPC(아마존 JP SP)** — "트래픽/세션 무인 수집이 BA 롤로 막혀 성과 미확정"이라 비워둠. → 세은 「내가 지금 로그인해 줄 테니까 성과를 넣어야 될 거 아니야 장난하나」. 실제로 **광고 성과(지출·매출·ACOS·ROAS)는 DataKeeper `amazon_ads_daily`에 이미 수집**돼 있었음. BA 롤이 막는 건 **트래픽/세션·검색어 세부 축뿐**인데 그 blocker 범위를 "성과 전체 수집 불가"로 과대적용.
2. **TikTok** — "개발자 API 심사 거절(domain security)이라 파이프라인 착수 보류, blocked"로 처리. → 세은 「아니 그건 있어 그냥 api를 안 주는 걸걸?」. 거절된 건 **자동 수집용 Marketing API**뿐이고 **광고 계정(littlefingerusa_adv)은 정상 운영 중**. 브라우저(Playwright)로 Ads Manager 긁으면 성과 다 나옴(9월 ¥64,126 트래픽 캠페인).

**Why:** 둘 다 공통 근본원인 = "한 수집 경로(무인 API)가 막혔다 → 그 채널 성과는 못 넣는다"로 **단일 경로 실패를 채널 전체 불가로 비약**. blocker의 **정확한 범위**(무엇이 막히고 무엇은 되는지)를 안 가림.

## How to apply
- 채널 성과를 "미확정/수집불가/보류"로 **본문에 쓰기 전에**: ① **DataKeeper 해당 테이블부터 조회**(amazon_ads_daily·meta_ads_daily 등 — 광고 성과는 대부분 적재돼 있음) ② API 막히면 **브라우저 수동 수집**(세은 로그인 1회+지속 프로필) 가능한지 확인.
- blocker 기술 시 **막히는 축을 정확히 한정**("BA 롤=트래픽/세션 세부만, 지출·ROAS는 DK 실측 가능"). 전부 막힌 것처럼 쓰지 마라.
- 리포트/덱에 "미확정" 칸을 남기는 건 거의 항상 **조사 미완 신호** — 세은이 로그인/권한을 줄 수 있으면 요청해서라도 실수치를 채운다. [[feedback-root-cause-not-symptom-fix-all]]

관련: [[reference-tiktok-marketing-api-rejection-domain-security]] · [[mistakes-20260907-partial-data-repeated-assertion]] · [[reference-jpdash-catchup-selfheal]]
