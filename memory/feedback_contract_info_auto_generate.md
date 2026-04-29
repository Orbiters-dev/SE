---
name: 계약 정보 수령 시 즉시 DOCX 생성
description: 인플루언서가 フルネーム·메일·IG·계좌를 주면 즉시 계약서 DOCX 생성 + 세은 확인 → DocuSeal 발송
type: feedback
---

인플루언서가 계약서 기재용 정보(フルネーム·이메일·IG 핸들·유상인 경우 은행 계좌)를 제출하면, 나의 다음 액션은 `tools/generate_influencer_contract.py`로 DOCX·PDF 생성.

**Why:** 2026-04-20 りぃ様이 ¥4,000 유상 계약 정보(ナルセリサ / rii.mama.ikuji12@gmail.com / @rii_mama_ikuji / 楽天銀行 계좌)를 줬는데, 나는 DM 답장만 만들고 계약서 생성을 방치 → 세은이 "내가 이런 정보 줬으면 너 뭐해야 돼" 지적.

**How to apply:**
- 계약 정보 수령 → 즉시 `generate_influencer_contract.py --manual '{"collab_type":"paid|gifting", ...}'` 실행
- DOCX 저장 경로 확인 → 세은에게 경로·내용 보고
- 세은 OK → `send_influencer_contract_docuseal.py --handle {핸들}` 로 DocuSeal 발송
- カタカナ만 받았으면 계약서 생성 전에 한자 이름 재확인 요청 (별도 feedback 메모리)
- 계약서 생성 → 세은 확인 → DocuSeal 발송 → STEP 6.5 DM 세트가 1사이클
