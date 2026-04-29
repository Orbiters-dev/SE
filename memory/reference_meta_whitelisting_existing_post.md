---
name: 메타 광고 화이트리스팅 — Use existing post + Post ID 가이드
description: Partnership ad code vs Use existing post 차이, partner content 그리드, Post ID 4 methods. 이전 광고 좋아요 누적 유지하면서 새 광고 셋업.
type: reference
---

## Partnership ad code vs Use existing post

**Partnership ad code 입력하면:**
- "The format of this ad has been set by the partnership ad code" 안내 뜨고 ad source 잠김
- Use existing post / Create ad / Creative Hub mockup 변경 불가
- 1회용 코드 — 새 광고마다 새 ad post 생성 → 좋아요 누적 안 됨

**Use existing post 방식 (좋아요 누적 유지하려면 이거 사용):**
- 새 광고 생성 시 partnership ad code 입력 **없이** 진행
- Ad creative → "Use existing post" 선택
- 두 가지 옵션:
  1. **Partner content 그리드에서 인플루언서 영상 직접 클릭** ← 인플루언서 측 partnership ad permission ON이면 여기 영상 노출됨
  2. **Enter Post ID** — 기존 광고 Post ID 직접 입력

## Post ID 찾는 4가지 방법 (출처: [adsuploader.com](https://adsuploader.com/blog/facebook-post-id) + [Meta 공식](https://www.facebook.com/business/help/405841712841961))

**Method 1 — URL 추출 (가장 빠름):**
1. Ads Manager에서 광고 선택
2. ad preview pane에서 "View post on Facebook" 클릭
3. 새 탭 URL의 15~17자리 숫자 = Post ID

**Method 2 — Preview Creative:**
1. 광고 ad details에서 "Preview Creative" 버튼
2. 모달 → "Post with Comments" 선택
3. URL 또는 모달 헤더에 Post ID

**Method 3 — Page Source (가장 확실):**
1. Facebook 게시물 페이지 우클릭 → "View Page Source"
2. Ctrl+F → `post_id` 검색
3. `"post_id":"숫자"` 패턴 복사

**Method 4 — Graph API Explorer:** 개발자용

## Thumbnail 동작

- Ads Manager 광고 목록 thumbnail은 ad creative의 첫 미디어를 보여줌
- **Processing 상태에서는 ad creative thumbnail이 아직 generation 안 돼서 페이지 프로필 사진 fallback** 표시될 수 있음
- Active로 전환되면 영상 썸네일로 자동 교체 (검증 완료 2026-04-29)

## 한계 / 주의사항

- **Flexible / dynamic creative ad**는 여러 Post ID 생기므로 단일 Post ID 복제 불가 → Creative ID로 fallback (단 fork 방식 — 복제 시점부터 engagement 분리됨)
- Partnership ad의 Post ID로 일반 광고를 만들 때 동작하는지는 메타 공식 문서 명시 없음 — 실제 시도 후 확인 필요

## 인플루언서가 해줘야 할 것

Partner content 그리드에 영상이 안 뜨면:
- 인플루언서가 IG 게시물 ⋮ → "Partnership ad permissions" → "Get partnership ad code" 토글 ON
- 한 번 발급한 게시물은 그 후로도 partner content에 떠있음 (영구 권한)
