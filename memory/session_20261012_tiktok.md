---
name: session-20261012-tiktok
description: 세션 2026-10-12 (틱톡이 — Marketing API 반려 건 재점검. 포털 "앱 없음" 화면 = 프로필 미온보딩 표시임을 규명, 플랜B(도메인 교체 재제출) 실행 지시 전달. 강한교정 없음.
metadata:
  type: project
---

# 세션 2026-10-12 (틱톡이 — TikTok Marketing API 반려 재점검)

## 경과
1. 세은 「틱톡 api 연결이 안 되고 있잖아」 + 포털 스크린샷 2장.
   - ①`/portal/apps` "You currently don't have any apps" + Become a Developer
   - ②프로필 신청 Rejected 화면 (Update Application 링크·거절사유 domain security 그대로)
2. 규명: **두 화면 = 한 상태** — 프로필 심사 반려 → 미온보딩 → 앱 목록 빈 것. 10/1 반려에서 진전 없음. 앱 신청 소멸 아님. 정본 [[reference-tiktok-marketing-api-rejection-domain-security]] 10/12 섹션 업데이트.
3. 교차검증 시도:
   - Gmail MCP = 토큰만료(9/30~) → 틱톡 회신 메일 확인 못 함.
   - probe 저장 세션으로 포털 접근 → **로그아웃 상태**(ads.tiktok.com 전용) → 직접 확인 불가.
4. **플랜B 실행 지시 전달** (반려 2주 경과 조건 충족):
   - Update Application → Company Website를 `orbiters.co.kr`(200 확인)로 교체
   - Description 끝 재제출 소명 영문 문단 복붙 제공 (도메인 보안 사유 인지·운영사 공식 도메인으로 교체·재심사 요청)
   - 대체 도메인 실측: zezebaebae/onzenna/orbiters 전부 200, grosmimi.co.kr 000.
5. 긴급도 완화 명시: 광고 송출·성과 수집(Playwright 스크랩, 10/8까지 수집)은 API 무관 정상 — 이 API는 자동수집 편의용.

## 교훈 (교정은 아니나 톤 신호)
- 세은 「이지랄~ 나더러 뭘 어쩌라고?」 — 막힌 외부 UI 스크린샷을 들고 올 땐 상태 분석보다 **"딱 1가지 할 일 + 복붙 텍스트"** 형태가 정답. 이번엔 그렇게 전환해서 종결.

## 미완/대기
- **세은 재제출 실행 여부 + 재심사 결과 대기.** 또 반려 시 → business-api 포털 developer ticket (세은 로그인 1회 후 내가 브라우저 제출).
- Gmail MCP 재인증 (9/30부터 계속 걸려 있음).
- (기존) TT Ads OFF 5본 승인 대기 · 물류사 창고/반송 메일 발송 대기.
