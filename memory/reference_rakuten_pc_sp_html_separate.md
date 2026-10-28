---
name: 라쿠텐 상품 페이지 PC/SP 설명문 별개 영역
description: 라쿠텐 RMS 상품은 PC용 「商品説明文」과 SP용 「商品説明文（スマートフォン用）」이 별개 HTML로 관리됨. PC 페이지 fetch로 SP HTML 확인 불가 — SP 작업 전 별도 확보 필요.
type: reference
---

# 라쿠텐 상품 페이지 PC/SP 설명문 구조

라쿠텐 RMS의 상품 정보는 **PC용·SP용 설명문이 별개 HTML 필드**로 저장된다. `item.rakuten.co.jp` PC URL을 firecrawl scrape 해도 SP 영역 본문은 응답에 포함되지 않음 (PC HTML만 옴).

## 영역 구조

| 영역 | RMS 필드명 | 표시 위치 |
|---|---|---|
| PC | 商品説明文 | PC 브라우저 페이지 |
| SP | 商品説明文（スマートフォン用） | 스마트폰 브라우저 페이지 |

같은 상품이라도 두 영역 HTML이 다르게 작성되어 있는 경우가 일반적 (PC는 width="700" 고정 폭, SP는 width="100%" 또는 `<p><img></p>` 래퍼).

## SP HTML 확보 path

1. **세은한테 RMS 편집화면 HTML 복붙 요청** (가장 확실)
   - 「RMS 商品編集 → 商品説明文（スマートフォン用） → HTML 編集 모드 텍스트 주세요」
2. firecrawl browser 모드 + 모바일 UA emulation
3. mobile.rakuten.co.jp 형식의 SP URL fetch (지원 여부 case-by-case)

## 사례

2026-05-28 `grosmimi_srawnipple_4p_copy` SUPER SALE 배너 교체 — PC HTML 247번 줄에 보라색 배너 발견했지만 SP HTML은 별도 확보 필요했음. 세은이 직접 복붙해서 SP 보라색 배너 위치 확인 (`<p><img src="...12521669/imgrc0129520466.jpg" width="100%" alt=""></p>`).

## How to apply

라쿠텐 상품 페이지 작업이 PC+SP 양쪽 필요한 경우:
- PC HTML 분석 후 SP 작업 들어갈 때 SP HTML 별도 확보 path 즉시 결정
- SP HTML 미확보 상태에서 SP용 교체 코드 단정 작성 X (추측 금지)
- 확보 막히면 「商品説明文（スマートフォン用） HTML 복붙」 한 줄로 명확히 요청 (옵션 객관식 X)
