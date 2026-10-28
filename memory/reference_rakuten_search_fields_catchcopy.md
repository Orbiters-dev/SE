---
name: reference-rakuten-search-fields-catchcopy
description: 라쿠텐 검색 인덱싱 4필드(商品名·PC캐치·모바일캐치·商品説明文) + 캐치카피 공개페이지 추출법 + RMS Item API 401(주문API만 열림).
metadata:
  type: reference
---

# 라쿠텐 상페 SEO — 검색 대상 필드 & 실측 루트 (2026-09-14)

## 검색 인덱싱 4필드 (전부 검색 대상, 검증됨)
1. **商品名** — 255자, 최우선. (9/10 그로미미 3상품 초안 완료)
2. **PC用キャッチコピー** — 174자~, PC·앱 검색.
3. **モバイル用キャッチコピー** — 174자~, 스마트폰.
4. **商品説明文 (PC/스마트폰)** — 사실상 무제한. **상품명·캐치에서 넘친 키워드 커버용**(라쿠텐 SEO 정석).
   - 경쟁(coni b.box·popomi/soyott-camp)은 상세 하단에 【関連キーワード】 블록으로 수백 단어 나열. 商品カテゴリ/対象・季節/ギフト/参加セール 4블록 + 카테고리 경로 구조.
   - 그로미미 3상품은 이 블록이 **통째로 비어 있음** = 최대 갭.
근거: 라쿠텐 SEO 실무(5springs·ecnomikata·itsumo365·proteinum 2026판).

## 캐치카피 실측 루트
- **공개 item 페이지에 노출**되나 firecrawl markdown·browser(봇탐지)로는 안 잡힘 → `firecrawl scrape --format rawHtml --wait-for 5000` 후 정규식 `【はじめて…】` 추출이 통함.
- 그로미미 3상품 캐치(2026-09-14): 스텐 `【はじめてのステンレスマグに】…保冷保冷最大6時間`(⚠️오타 保冷保冷·飲みやす 잘림) / 원터치 `【片手で開けられるワンタッチ式】…` / PPSU기본 `【はじめてのストローマグに】哺乳瓶からのステップアップ…`
- **RMS Item API는 401** (`/es/2.0/items/manage-numbers/{mn}` Un-Authorised) — 이 라이선스는 **주문관리 API만** 열림. ESA 인증(credentials/rakuten_rms_config.json)은 유효하나 상품 API 미포함. RMS 편집화면 캐치카피 필드 정밀 대조는 Playwright 로그인 필요.

## 그로미미 라쿠텐 3상품 slug (shop: littlefingerusa / id 435776)
- 스텐 보냉: `stainless_steel_strawcup_300`
- PPSU 원터치(fliptop): `grosmimi_ppsu_onetouch_srawcup` (review item 10000002)
- PPSU 기본: `grosmimi_ppsu_strawcup300` (review item 10000001)
