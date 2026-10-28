---
name: feedback-check-form-before-claiming-no-product
description: "WL 자동집행이 '제품미상' 찍어도 그대로 믿고 세은한테 제품 묻지 마라 — 투고완료 폼 col11「お受け取りいただいた商品」부터 교차확인. 직접 파악 가능한 걸 떠넘긴 강한 교정(2026-10-07)."
metadata:
  type: feedback
---

2026-10-07 강한 교정 (메타몽 — 「왜 안 찾아보고 제품 매핑 안 된다고 지랄하냐」·「앞으로 폼에 안 확인해 보고 지랄 떨면 죽는다」):

WL 자동집행(`wl_auto_upload.py`)이 `제품미상(폼 매칭실패/모호)` 으로 보류해도 **그 도구 출력을 그대로 믿고 세은한테 "제품 알려주세요" 묻지 마라.** 제품은 거의 항상 **투고완료 폼 col11「お受け取りいただいた商品」에 이미 기재돼 있다.**

**왜:** 파이프라인의 `제품미상`은 "제품 정보 없음"이 아니라 **핸들↔제품 조인 실패**(통합탭을 IG핸들 키로만 조회 → 실명/DK미크롤 건은 매칭 불발)일 뿐. 폼엔 제품이 멀쩡히 있음. [[reference-wl-autoupload-cloud-dk-cred-missing]]

**How to apply:**
- `제품미상` 뜨면 → 폼 투고완료탭(FORM_SHEET_ID, FORM_TAB_ID) 해당 shortcode 행 col11 먼저 읽는다.
- 핸들 역추적 필요 시: `GET /{GROS_IG}/branded_content_advertisable_medias?permalinks=[sc]` → media id → `GET /{media_id}?fields=username` (SYS토큰).
- 폼 col11 제품텍스트를 `resolve_product()` 에 넣어 (ASIN,LP,utm) 확정 → 집행.
- 폼에도 진짜 없거나 모호할 때만 세은한테 물어라. 그 전엔 금지.
- 일반화: 도구가 "없음/실패/미상" 찍으면 = 도구 한계 신호. 2차 소스(폼·시트·Graph)로 교차확인 후 판단. 직접 파악 가능한 걸 세은한테 떠넘기지 마라 (CLAUDE.md 절대룰).

[[reference-wl-autoupload-cloud-dk-cred-missing]] · [[mistakes-20260930-dk-overload-false-norow]]
