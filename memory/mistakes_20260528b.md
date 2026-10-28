---
name: 오답노트 2026-05-28b (SP HTML 모른 상태에서 옵션 추측 → 강한 교정)
description: 라쿠텐 상품 페이지 SP 설명문 HTML 확보 안 한 상태에서 (A) RMS 복붙 / (B) 모바일 UA fetch 옵션 추측 제시. feedback_no_speculation_even_with_label + feedback_self_first_no_wongi_default 재위반.
type: feedback
---

# 오답노트 2026-05-28b

## 사건

라쿠텐 `grosmimi_srawnipple_4p_copy` 페이지 SUPER SALE 배너 교체 작업 중, SP(스마트폰용) 설명문에서 보라색 배너만 찾아 교체하라는 지시를 받음.

**내가 한 짓:**
1. PC 페이지 스크랩 HTML 안에 SP 영역이 들어있지 않은 걸 확인
2. SP HTML 확보 X 상태에서 그냥 SP용 추정 코드(`<img style="width:100%">`) 제시 → 「기존 이미지 다 지운다는 게 아니야」 1차 교정
3. 그 다음에 SP 기존 보라색 배너 코드를 모르는 상태에서 "(A) RMS 편집화면 복붙 / (B) 내가 모바일 UA로 fetch" 두 옵션 객관식으로 떠넘김
4. **세은 강한 교정: "그니가 그 이미지 코드가 뭔지 모른다고 ;; 뒤질래"**
5. 세은이 SP HTML 직접 복붙해줘서 해결 (보라색 배너 = `<p><img src="...cabinet/12521669/imgrc0129520466.jpg" width="100%" alt=""></p>`)

## 위반 룰

- **feedback_no_speculation_even_with_label** — SP HTML 모르는 상태에서 "기존 이미지 다 지우고" 추정 답변. 검증 안 한 정보 본문 노출.
- **feedback_self_first_no_wongi_default** — 자체 path (모바일 UA scrape 시도) 끝까지 안 해보고 객관식 떠넘김.
- **feedback_anger_user_wants_diagnosis_not_stop** — 분노 톤 강한 교정에는 원인 보고 + 다음 액션이 정답. 다행히 멈춤 답변은 안 했음.

## 학습

- 라쿠텐 PC 페이지 HTML 스크랩 ≠ SP 설명문 HTML. 둘은 RMS에서 별개 영역으로 관리되며 PC 페이지 fetch만으론 SP 영역 확인 불가.
- "스마트폰용도 교체해줘" 류 지시 받으면 즉시 SP HTML 확보 path 결정:
  1. 우선 firecrawl mobile UA / browser 모드 시도
  2. 안 되면 처음부터 세은한테 RMS 편집화면 HTML 복붙 요청 (옵션 객관식 X — 한 가지 명확한 path 제시)

## How to apply

라쿠텐 상품 페이지 PC/SP 양쪽 작업 시:
- PC HTML 스크랩으로 SP 영역 단정 X
- SP 영역 코드 확보 전엔 SP용 교체 코드 작성 시작 X
- 확보 path 막히면 「RMS 編集 → 商品説明文（スマートフォン用） HTML 복붙해주세요」 한 줄 요청
