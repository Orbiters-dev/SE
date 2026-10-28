---
name: feedback_contract_payment_amount_zeikomi
description: 유상 계약서 報酬額은 반드시 「○○円（税込）」 — 税込 표기 누락 금지
metadata:
  type: feedback
---

유상 계약서 第5条 報酬額은 **「{금액}円（税込）」** 형태로 나와야 한다. 「円 JPY」 / 税込 누락 금지.

**Why:** 2026-06-30 小野寺緑様(しーたん) 계약서에서 税込 빠짐 → 「税込 넣으라고 몇 번을 말하는질」 반복 강한 교정.

**How to apply:** 원본 템플릿 `インフルエンサーコンテンツ契約書（有償）.docx` 42행을 `報酬額：{{PAYMENT_AMOUNT}}円（税込）` 로 수정 완료 (2026-06-30). 이제 generate_influencer_contract.py 가 자동으로 税込 포함. 계약서 생성 후 검증 단계에서 `報酬額` 단락에 「（税込）」 들어갔는지 grep로 확인할 것. [[reference_contract_sop]]
