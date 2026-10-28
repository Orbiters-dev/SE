---
name: 유상 계약서 報酬額은 「(税込)」 명시 필수
description: 유상 계약서 생성 시 「報酬額：XX円（税込）」 형식. 도구 generate_influencer_contract.py 기본값은 「XX円 JPY」라 후처리로 「(税込)」 부착 필요.
type: feedback
---

유상 계약서(`collab_type=paid`)는 보수 금액 뒤에 반드시 「（税込）」 명시. 「報酬額：27,500円（税込）」 형식.

**Why:** 2026-05-13 はるくんママ 계약서 생성 시 「報酬額：27,500円 JPY」로 떨어져 세은 강한 교정. 인플루언서 답신 본문이 「27,500円（税込）」였는데 계약서에는 미반영 — 사후 세금 분쟁 리스크.

**How to apply:**
- `tools/generate_influencer_contract.py --manual` 시 `compensation_amount` 그대로 숫자 입력 → 결과 DOCX의 「{{PAYMENT_AMOUNT}}円 JPY」 자리에 숫자만 들어감
- 생성 직후 DOCX 후처리로 「XX,XXX円 JPY」 → 「XX,XXX円（税込）」 치환 후 PDF 재생성 (docx2pdf)
- 후처리 스니펫:
  ```python
  from docx import Document
  from generate_influencer_contract import replace_text_in_paragraph
  doc = Document(path)
  for tb in doc.tables:
      for row in tb.rows:
          for cell in row.cells:
              for p in cell.paragraphs:
                  if '{amount}円 JPY' in p.text:
                      replace_text_in_paragraph(p, '{amount}円 JPY', '{amount}円（税込）')
  doc.save(path)
  ```
- 또는 향후 도구 패치로 `tax_included: true` 옵션 추가 (TODO)
- 무상(gifting) 계약서는 報酬 라인 없으므로 해당 없음
