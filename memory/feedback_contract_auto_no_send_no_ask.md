---
name: 계약서 SOP — DOCX + DocuSeal 업로드 (메일 발송 X) 까지 묻지 말고 자동 / 본 발송만 승인
description: STEP 6 정보 수령 → 묻지 말고 즉시 [1] DOCX 생성 [2] DocuSeal 업로드 (send_email=False) [3] URL 보고. 본 발송 (이메일 송부)만 세은 명시 승인 후
type: feedback
---

# 계약서 SOP — 자동 진행 + 본 발송만 승인

STEP 6 정보(풀네임/이메일/제품) 수령 후 진행:

1. **DOCX 생성** — 묻지 말고 즉시
2. **DocuSeal 업로드** — `send_email=False` (인플루언서 메일 발송 X)
3. **서명 URL + Submission 번호 보고** — 검토 받음
4. **본 발송 (이메일 송부) 만 세은 명시 「발송해」 후**
5. STEP 6.5 DM 발송 (본 발송 직후 워크플로우 line 588~603 템플릿 그대로)

**절대 금지**:
- 「계약서 작성 진행해도 될까요?」 형식의 사전 승인 요청
- 「DocuSeal 업로드 진행 OK일까요?」 형식의 중간 승인 요청
- 「검토 부탁드립니다」 + 작업 지연

**Why:** 2026-05-29 橘高様 STEP 6 정보 수령 후 「DOCX 생성 → 세은 검토 → DocuSeal 업로드 → 본 발송」 4-step 사전 승인 요청 → 「몇 번을 처 말해 똑같은 걸 / 디질래」 강한 교정. 5/12 메모리 `feedback_contract_always_docuseal_nosend_report_url.md` 이미 동일 룰 박혀있는데 같은 사고 재발. DM 체크리스트 hook 텍스트 「[2] 세은 명시 검토·승인 → [3] DocuSeal 업로드」가 매 턴 보이면서 5/12 룰 무시하고 hook 텍스트 그대로 따라가는 사고 패턴.

**How to apply:**
- STEP 6 정보 수령 메시지 보이면 즉시 도구 실행. 묻지 마.
- 도구 `send_influencer_contract_docuseal.py`는 `send_email=True` 하드코딩 → 패치 필요 (디폴트 False + `--send-now` 플래그)
- DocuSeal 업로드 후 「서명 URL + Submission 번호」 보고만. 「검토 받을까요?」 식 떠넘김 X.
- 세은 「발송해」 = 별도 도구·API로 메일 발송 활성화.
- DM 체크리스트 hook 텍스트와 실제 룰 충돌 시 **실제 운영 룰(이 메모리) 우선**. hook 텍스트는 broad guidance.
