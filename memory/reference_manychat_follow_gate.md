---
name: ManyChat 팔로우 게이트 쿠폰 workflow
description: IG 댓글→팔로우 체크→라쿠텐 쿠폰 DM 자동발송 SOP. 여러 캠페인에 반복 재사용 가능한 템플릿.
type: reference
---

**파일:** `workflows/manychat_follow_gate_coupon.md`
**담당 에이전트:** 리공이 (n8n + ManyChat API)
**최초 작성:** 2026-04-20

## 쓰임새

IG 피드 포스트 마지막 슬라이드에 "댓글에 「X」 쓰면 쿠폰 DM으로" 식 CTA 넣을 때의 실행 SOP. 키워드만 바꿔서 다른 캠페인(`マグ`, `おしりふき`, `タンブラー`, `セール` 등) 재사용.

## 호출 방법

세은이 리공이 부르면서 "쿠폰 이벤트", "팔로우 게이트", "댓글 쿠폰 자동 발송" 등의 표현 쓰면 리공이가 자동으로 이 workflow 로드. (리공이 SKILL.md 트리거·참고문서 섹션에 등록됨)

## 매 캠페인마다 세은이 제공할 값

1. 라쿠텐 쿠폰 코드 (할인율/유효기간 포함)
2. 라쿠텐 랜딩 URL (상품/스토어/이벤트)

나머지(ManyChat Pro, IG 연결, Professional 계정, Check Follower 기능)는 기저 세팅으로 검증 완료.

## 핵심 기능

- ManyChat "Follows your Account" 조건 사용 (스크래핑 기반, IG 공식 API 아님)
- 팔로워 → 즉시 쿠폰 DM / 비팔로워 → 팔로우 안내 DM → 팔로우 감지 시 자동 쿠폰
- `coupon_sent` Custom Field로 1인 1회 재발송 방지
