---
name: session-20261013-tiktok-api
description: 세션 2026-10-13 (틱톡이 — Marketing API "도메인 보안" 반려 원인 조사. Bytespider 차단 실측 발견, 플랜B(orbiters.co.kr) 철회, 관리자 차단해제 요청문 전달. 교정 2건(추측 혼입·onzenna 정합성).
metadata:
  type: project
---

# 세션 2026-10-13 (틱톡이 — TikTok Marketing API 반려 원인 조사)

## 성과 (전부 직접 실측)
1. **Bytespider 차단 발견**: grosmimijapan.com·orbiters.co.kr 모두 UA "Bytespider"(ByteDance 공식 크롤러)만 HTTP 400, 그 외 UA 전부 200. robots.txt 깨끗 = 서버 레벨. 둘 다 Nexcess/Liquid Web 인프라(ARIN RDAP 확정, 173.249.144.0/20). **onzenna.com은 Bytespider 200 통과.**
2. GSB 두 도메인 다 clean. 사례 수집: 같은 포털·같은 거절문 = 6연속 반려·해결자 0 (pullpush 아카이브 원문) → 무변경 재제출 = 확정 실패.
3. **플랜B(orbiters.co.kr 교체, 10/12 지시) 철회** — 같은 차단이라 교체 무의미.
4. Reddit 수법(firecrawl이 reddit 미지원·old.reddit도 차단) → **api.pullpush.io 아카이브로 우회 성공**.

## 확정 플랜 (대기 중)
1. 관리자에게 Bytespider 차단 해제 요청문 전달 (세은이 전달하기로 — 요청문 본문은 이 세션 대화에 복붙본 있음. 핵심: WP 보안플러그인/.htaccess → 없으면 Nexcess 티켓)
2. 해제되면 내가 curl 재검증 → **새 신청서 제출** (세은 선호 확인: Update 아닌 신규 제출. grosmimijapan.com 유지, 세은 포털 로그인 1회 → 내가 브라우저 작성 → 제출 전 멈춤 → 세은 승인)
3. 또 반려 시 → business-api developer ticket ("차단 해제까지 했는데 반려" 근거 지참)
4. ⚠️ 차단해제=승인 보장 아님을 세은에게 명시함 ("보장 못 합니다" 직답). TikTok이 Bytespider UA로 심사 접근하는지 = 비공개·확인 못 함.

## 교정 2건
1. 「확실한 정보 맞아? 추측해서 말하지 마」 — "실체를 찾았어요" 단정 톤 + 미검증 인용(Reddit 유저가 올린 TikTok 서포트 메일·타 포털 승인사례)을 근거처럼 혼입. 확실(실측)/확인못함 2단 분리로 교정. [[mistakes-20260928-fabricated-requirement-and-speculation]] 재발 축.
2. 「온제나는 우리 걸 설명하는 도메인이 아닌데 어떻게 내냐」 — onzenna.com 제안이 기술 조건(Bytespider 통과)만 보고 신청서 정합성 무시. → [[feedback-submission-domain-must-describe-applicant]]

## 미완
- 관리자 차단 해제 회신 대기 → 해제 검증 → 신규 제출.
- Gmail MCP 재인증 (9/30~ 계속).
- (기존) TT Ads OFF 5본 승인 · 물류사 창고/반송 메일 발송 대기.

관련: [[reference-tiktok-marketing-api-rejection-domain-security]] (10/13 섹션에 실측 정본 기록됨)
