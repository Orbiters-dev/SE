---
name: 참고 릴스 받으면 호스트 30포스트 분석 먼저
description: 참고 콘텐츠 호스트는 1포스트 메타로 끝내지 말고 recent 30 + bio + 해시태그 분포까지 분석 후 검색 기준 도출
type: feedback
---

참고 릴스/콘텐츠 받았을 때 첫 fetch는 호스트 프로필 + recent 30 posts.

**Why:** 2026-05-08 baby cooking 발굴에서 deanna.hauk / macygubitoso 단일 포스트 메타 (caption + hashtag 5개)만 보고 검색 시작 → 4번 연속 실패. 마지막에 @rin_mama0805 30포스트 분석하고서야 본질 (#台所育児 + #1歳児 + 일상 vlog) 잡힘.

**How to apply:**
1. 참고 릴스/포스트 URL 받으면 — `apify/instagram-scraper directUrls` (메타 1건)
2. **즉시** 호스트 프로필 + 30 posts — `apify/instagram-profile-scraper resultsType=posts resultsLimit=30`
3. 분석 출력:
   - bio
   - Top 30 hashtags (Counter most_common)
   - 최근 10건 캡션 100자 미리보기 + likes/views
   - is_business / category
4. 위에서 본질 키워드 도출 → 검색 해시태그/필터 결정

캡션 단일 포스트만으로 본질 매칭 가정 금지. 호스트의 메인 해시태그 패턴 + bio 가 더 정확.
