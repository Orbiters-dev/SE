---
name: 레퍼런스 IG 포스트는 이미지 alt-text까지 확인
description: "그대로 따라하기" 요청일 때 캡션만 보고 슬라이드 구성 추측 금지. 각 이미지의 실제 텍스트(alt/OCR) 확인 필수.
type: feedback
---

IG/SNS 포스트를 "그대로 따라하기" 요청받으면 캡션 텍스트만 보고 슬라이드 구성을 추측하지 말고, **각 이미지에 실제로 박힌 텍스트**까지 확인해야 한다.

**Why:** 2026-04-20 Grosmimi SG 포스트(DXOCQU0ERo2) "그대로 따라하기" 요청에서, picnob 캐시본(캡션만 나옴)만 보고 3슬라이드 구성을 "Why Grosmimi?" 후크 기반으로 임의 추측 → PPT 만들었다가 "제대로 읽은 거 맞니?" 강한 지적. 실제 원본은 "What's So Special" / "So Thoughtfully Designed! (8 features)" / "Available in 2 sizes!" 3장 구성이었음. imginn은 alt-text로 이미지 속 텍스트까지 제공하기 때문에 처음부터 imginn을 썼으면 바로 정확히 파악 가능했다. 이미 `feedback_follow_reference_exactly.md` 규칙이 있었는데도 또 위반.

**How to apply:**
- IG/SNS 포스트 레퍼런스 받으면 **반드시 imginn.com/p/{shortcode}/ 또는 동급 미러** 먼저 시도 (alt-text로 이미지 속 텍스트 나옴).
- picnob은 캡션만 나오고 이미지 속 텍스트 없음 → 단독 사용 금지.
- 3장 이상 Sidecar 포스트면 **슬라이드별 실제 텍스트/비주얼**을 원본-클론 매핑표로 먼저 정리한 뒤 PPT 작성.
- "그대로 따라하기"는 후크 슬로건 재사용이 아니라 **슬라이드 개수·텍스트 구조·비주얼 레이아웃**까지 일치시키는 것.
- 확신 없으면 세은한테 "SG 슬라이드 1/2/3 각각 어떤 내용인지 확인했습니다" 명시 후 진행.
