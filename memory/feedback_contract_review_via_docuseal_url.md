---
name: 계약서 검수는 DocuSeal URL로 — 로컬 PDF 보여주기 X
description: 계약서 [2] 세은 검수 단계는 로컬 DOCX/PDF 경로가 아니라 DocuSeal --no-send 업로드 후 서명 URL로 받는다.
type: feedback
---

계약서 SOP [2] 세은 검토 단계에서, 생성된 로컬 DOCX/PDF 파일 경로만 보여주고 "확인 부탁드립니다" 하면 안 된다.

**올바른 순서:** [1] DOCX 생성 → [3] DocuSeal `--no-send` 업로드(이메일 X) → 서명 URL을 세은에게 전달 → 세은이 실제 렌더링된 계약서로 검수 → OK 시 `--resend SUBMITTER_ID` 본 발송.

즉 `--no-send` 업로드는 [2] 검수의 일부. 「로컬 파일 검수 먼저 → 그 다음 업로드」 순서가 아니라, **검수받을 때부터 DocuSeal URL을 줘야 한다.**

**Why:** 2026-06-12 金原様(@nao_babygram) 무상 계약 — DOCX 생성 후 로컬 PDF 경로로 검수 요청 → 「야!!! 발송 전에 url 로 주고 검사 받으라고 진짜 몇 번 말해」 강한 교정 (반복 교정). 로컬 파일은 placeholder 치환·필드 배치가 실제 DocuSeal 렌더와 다를 수 있어 세은이 실물 URL로 봐야 함.

**How to apply:**
- 정보 수령 → DOCX 생성 → 바로 `send_docuseal_contract.py --no-send` 로 업로드해서 서명 URL 확보 → 그 URL을 세은에게 검수용으로 제시
- 본 발송(`--resend`)은 세은이 URL 보고 명시 OK 한 후에만
- reference [[reference-contract-sop]] / [[feedback-docuseal-upload-also-requires-approval]] 와 함께 적용. --no-send 업로드 자체는 외부 시스템 액션이지만 이메일 발송이 아니므로 검수 목적 업로드는 진행 가능 (단 사전 1줄 보고)
- 본 룰 재위반 = 강한 교정 대상
