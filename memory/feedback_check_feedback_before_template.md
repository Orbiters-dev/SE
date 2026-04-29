---
name: DM 작성 전 관련 feedback 메모리 재조회 필수
description: 워크플로우 템플릿 찾아 쓰기 전에 feedback_*.md 먼저 확인. 워크플로우와 feedback 충돌 시 feedback 우선.
type: feedback
---

DM 작성 시 워크플로우 `grosmimi_japan_influencer_dm.md` 템플릿을 바로 꺼내기 전에 **관련 feedback_*.md 먼저 조회**한다.

**규칙:**
1. 인플루언서 메모리 파일 Read (기존 DM_CHECKLIST)
2. **해당 상황 관련 feedback_*.md 조회** (신규 체크)
3. 그 다음 워크플로우 템플릿 선택
4. 워크플로우 ≠ feedback 충돌 시 → **feedback 우선**

**Why:** 2026-04-20 遠藤様(상품 도착) 케이스에서 feedback_product_arrival_flow.md가 존재하는데도 워크플로우 STEP 10.5 풀 템플릿(날짜+투고 포인트)을 바로 꺼냈다가 질책받음. feedback은 "세은이 직접 내린 규칙"이고 워크플로우는 "일반 템플릿"이므로 전자가 우선.

**How to apply:** 
- 상황별 대표 feedback 예시:
  - 상품 도착 → `feedback_product_arrival_flow.md` (포인트 바로 X, 사용→감상→방향)
  - 영상 OK → `feedback_always_thumbnail_caption.md` (썸네일·캡션 확인)
  - STEP 2 → `feedback_guideline_adjustable_note.md` (가이드라인 조정 가능 안내 필수)
  - 링크 → `feedback_product_link_not_shop_root.md` (상품 페이지 URL)
  - 계약 정보 수령 → `feedback_contract_info_auto_generate.md` (즉시 DOCX)
  - カタカナ 이름 → `feedback_contract_name_kanji.md` (한자 재확인)
- Harness가 feedback과 다른 방향 제안해도 feedback 우선 유지
