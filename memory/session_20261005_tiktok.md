---
name: session_20261005_tiktok
description: 세션 2026-10-02~05 (틱톡이 — TikTok Marketing API 거절건 무응답 대응 조언 + FastMoss 구독=틱톡샵용 규명). 강한교정 없음.
metadata:
  type: project
---

# 세션 2026-10-02~05 (틱톡이)

## 1) TikTok Marketing API 무응답 — 열받음 토로 + 조언
- 상황: `Grosmimi JP Ads` 앱(business-api.tiktok.com 포털·Reporting용) "domain security" 거절 → 메일 회신 無(9/28 제출 기준 당시 4~5일째, 틱톡 공식 심사 며칠~2주라 **범위 내·방치 단정 X**).
- 조언(틱톡이, 근거 기반):
  - **메일 쪼아도 속도 못 당김** — 거절문이 "rep/developer ticket = 사람 수동 재심사" 지정. 자동 재제출로 안 뚫림.
  - **창구 교체**: 무응답인 `developers.tiktok.com` Support ≠ 거절 난 포털. `business-api.tiktok.com/portal` 자체 developer ticket(Need help→Log in→submit)이 거절 낸 팀 직통 = 메인 수단.
  - **블로킹 해제**: 이 API = 광고실적 **자동수집**(편의)이지 필수 아님 → 광고 집행 중이면 **Ads Manager 수동 export**로 당장 돌아감.
  - **플랜B**: 2주 초과 시 "도메인 보안" 안 풀리는 것 → 서브도메인/별도 도메인 재신청.
- 정본 [[reference-tiktok-marketing-api-rejection-domain-security]].

## 2) FastMoss = 틱톡샵용 (구독 활성 확인)
- 세은 "구독했었잖아·틱톡용이야 샵용이야" → **틱톡샵 TTS 세일즈 데이터 분석 툴**(광고 아님). 정본 [[reference-fastmoss-subscription-tts]].

## 미완/대기
- **포털 ticket 어느 창구에 냈는지 세은 답 대기** (developers.tiktok.com만 냈으면 엉뚱한 창구 두드린 것) → 답 오면 도메인 정상 근거 붙인 **영문 소명문** 작성 예정.
- FastMoss 로그인 계정 받으면 JP 베이비 카테고리 크리에이터·상품 랭킹 실데이터 뽑기(육아맘 침투도 검증).
