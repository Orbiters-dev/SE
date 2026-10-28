---
name: reference-grosmimi-review-collection-capture
description: 그로미미 3국(한/일/미) 리뷰 소스 URL·제품ID + firecrawl 브라우저 리뷰 수집·전문 캡쳐 파이프라인
metadata:
  type: reference
---

그로미미 스트로컵 리뷰 수집·캡쳐 정본 (2026-09-28 확립, 상세페이지 리뷰 작업).

## 소스 (스트로컵 3종)
- **라쿠텐(JP) 리뷰**: `https://review.rakuten.co.jp/item/1/435776_{itemid}/1.1/`
  - PPSU 기본 = `10000001` / Fliptop(원터치) = `10000002` / 스텐 = `10000008` (shop 435776=littlefingerusa)
- **네이버(KR) 브랜드스토어**: `https://brand.naver.com/grosmimi/products/{id}`
  - 기본 PPSU 빨대컵(다크 크림베이지 200ml, 1,335리뷰) = `5406085500` ← 세은 지정 "기본 PPSU만"
  - PPSU 원터치(돗꼼) = `8695508461` / 스텐빨대컵(돗꼼 자기주도 200ml) = `9107238035` / 돗꼼 PPSU 300ml = `8695512588`
  - ⚠️ 제외: 아기고래(993리뷰), 텀블러·젖병·세척솔·빨대리필·캡·식판
- **미국(onzenna, Shopify+Okendo)**: `https://onzenna.com/products/{slug}`
  - `ppsu-straw-cup-10oz-300ml` / `ppsu-straw-cup-with-flip-top-weight-10oz-300ml-1` / `grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-300ml`

## firecrawl 브라우저 캡쳐 파이프라인 (핵심 함정 포함)
- `firecrawl browser execute --python` 사용. **python-mode의 `print()` 출력은 stderr로 나감** → `> file 2>&1`로 받아야 함(`2>/dev/null` 하면 0바이트). **`open().write()`는 원격 샌드박스에 씀**(로컬 X) → 결과는 반드시 base64로 `print` 후 로컬 디코드.
- `page.evaluate(f"window.scrollTo(0,{y})")` (f-string). `arguments[0]` 방식은 patchright에서 `ReferenceError`.
- **네이버 요약카드는 CSS line-clamp로 본문을 자름** → "리뷰 전체보기" 클릭 후, 대상 요소+상위 7개에 `webkitLineClamp='unset'; maxHeight='none'; overflow='visible'` 주입하면 전문 노출. 긴 리뷰는 뷰포트 1500~1600으로 넓혀 clip 우측 잘림 방지.
- 전문 캡쳐 = get_by_text(고유 문구) → scroll_into_view → bounding_box → clip(위로 리뷰어/별점, 아래 본문 포함) → element/viewport screenshot base64.
- onzenna Okendo는 5개만 기본 렌더 → 스크롤+"Load more" 클릭 반복해야 전체(18+) 로드.

## firecrawl agent 백그라운드
- `firecrawl agent ... --wait &`를 Bash 툴 `&`로 띄우면 **셸 종료 시 로컬 프로세스가 죽음**. 그러나 **클라우드 잡은 살아있음** → 로그의 `Job ID`로 `firecrawl agent <job-id> --json -o file` 회수 가능. 장시간 작업은 Bash `run_in_background:true` 또는 job-id 회수 방식 사용.

## 산출물
- 결과 HTML: `C:\Users\orbit\Desktop\s\market place\Rakuten\2609 상세페이지 변경\GROSMIMI_JP_리뷰정리_상세페이지용_3제품_20260928.html` (캡쳐는 같은 폴더 `review_caps/`, 상대경로 — HTML과 함께 이동).
- 작업 캐시: `.firecrawl/grosmimi_reviews/`

관련: [[feedback-review-curation-one-km-excerpt]] · [[product-color-size-options]] · [[reference-jp-influencer-content-and-hosting]]
