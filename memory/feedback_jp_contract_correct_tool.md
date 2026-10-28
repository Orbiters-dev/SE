---
name: JP 인플루언서 계약서 = send_docuseal_contract.py --type gifting/paid + JP 일본어 PDF
description: JP 인플루언서 계약서 업로드는 영문 템플릿 도구 X. JP 전용 도구 + 일본어 PDF 사용. send_influencer_contract_docuseal.py(Template ID 1 "Influencer Agreement (Paid)")는 US 인플루언서용
type: feedback
---

# JP 인플루언서 계약서 — 올바른 도구

## 도구 선택

| 인플루언서 지역 | 도구 | 템플릿 |
|---|---|---|
| **JP** | `tools/send_docuseal_contract.py --type gifting/paid --pdf {jp_pdf}` | 일본어 PDF (방식 A) |
| US | `tools/send_influencer_contract_docuseal.py` | 영문 Template ID 1 "Influencer Agreement (Paid)" |

## JP 흐름 (SKILL.md line 36~40)

1. `tools/generate_influencer_contract.py --handle @{핸들}` 또는 `--manual` JSON → **JP 일본어 DOCX 생성**
2. `tools/send_docuseal_contract.py --name "실명" --email "email" --pdf "JP_DOCX_PATH" --type gifting --no-send` → DocuSeal 업로드 (메일 X)
   - ⚠️ `--pdf` 옵션 이름이지만 **DOCX 경로 전달이 정답**. DOCX면 DocuSeal이 text tag 자동 제거. PDF로 업로드하면 `{{필드명;role=...;type=...}}` 마커 텍스트 그대로 남아 시각적 사고 (line 342 도구 주석: "DOCX 경로 권장 — text tag 자동 제거됨")
3. 서명 URL 보고 + 검토
4. 검증 후 본 발송 (세은 「발송해」 후)

## 절대 금지

- JP 인플루언서에 `send_influencer_contract_docuseal.py` 사용 — 영문 PAID 템플릿 박힘
- US 영문 템플릿으로 JP 무상 케이스 처리

**Why:** 2026-05-29 橘高様 (JP 무상) 케이스에 `send_influencer_contract_docuseal.py` 영문 PAID 템플릿 잘못 사용 → Submission #63 영문 PAID 라벨로 업로드 → 「너 설마 이거 보낸 거 아니지? 정신나간것아?」 강한 교정 → Submission #63 archive로 정리. 메모리 5/22 玉木様 무상 케이스에서 「DOCX {이름}_{날짜}.docx」 박혀있는 게 힌트 — DOCX 생성 도구 따로 + JP PDF 업로드.

**How to apply:**
- DM 호칭 (○○様) 톤이 일본어면 JP 인플루언서 확정 → `send_docuseal_contract.py --type {gifting|paid} --pdf {jp_pdf}` 사용
- SKILL.md line 38·39 둘 다 도구 명시. line 38 = 방식 A (JP) / line 39 = 방식 B (US 영문 템플릿)
- 도구 선택 헷갈리면 도구 사용법 헤더 주석 확인 (`send_docuseal_contract.py` 헤더 = "JP 인플루언서용" 명시됨)
