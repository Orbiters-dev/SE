---
name: 외부 도구 한계 단정 전 공식 문서·커뮤니티 확인
description: "X 기능 불가능합니다" 단정 전 반드시 해당 도구의 공식 docs/community 검색. Meta/IG API 표준만 기준 삼지 말 것.
type: feedback
---

ManyChat, Zapier, Make, IG 관련 자동화 도구의 기능 한계를 단정하기 전에 **반드시 해당 도구의 공식 문서 또는 공식 커뮤니티**를 먼저 검색해야 한다. Meta/IG 공식 API 기준으로만 판단하면 도구 내부 자체 구현(스크래핑 등)을 놓친다.

**Why:** 2026-04-20 ManyChat 팔로우 게이트 논의에서 "IG 공식 API는 is_following 실시간 검증 불가"를 근거로 **버튼 탭 + honor system** 방식을 제안. 세은이 "근데 내가 보니까 딴 사람들은 그렇게 하던데?" 반박 → firecrawl 검색 후 ManyChat에 **"Check Follower" / "Follows your Account" 조건**이 공식 기능으로 존재함 확인. 이미 많은 계정이 사용 중. 세은 원안(팔로우 감지 시 자동 쿠폰)이 완전히 가능했는데 불가능하다고 돌려서 "디질라고 ;;" 짜증 유발.

**How to apply:**
- 외부 도구 기능 단정형 답변("불가능합니다", "지원 안 됩니다") 내기 전 필수 체크:
  1. 해당 도구의 공식 docs (예: help.manychat.com)
  2. 공식 community forum (예: community.manychat.com)
  3. firecrawl search "{tool} {feature} 2024" or "2025"
- 공식 API 기준으로만 판단하면 놓치는 것들:
  - 도구 자체 스크래핑/크롤링 우회 구현
  - 최근 추가된 기능 (Meta API가 커버 안 해도 도구가 자체 구현)
  - 플랜별 기능 차이 (Pro에서만 되는 조건 등)
- **세은이 "근데 딴 사람들은..." 류로 반박하면 즉시 재확인**. 기존 답변 방어 금지.
- 확신 없는 경우 "IG 공식 API 기준으로는 제약이 있는데, ManyChat 등 도구 자체 기능 있는지 확인해 보고 답변드릴게요" 로 유보.
