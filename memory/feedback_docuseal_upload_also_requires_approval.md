---
name: 계약서 SOP — DOCX + DocuSeal --no-send URL까지 자동, 본 발송만 명시 승인
description: 정보 수령 → DOCX 생성 → DocuSeal --no-send 업로드 → 서명 URL 보고 까지 한 묶음 자동. 세은이 URL 클릭해 직접 검토. 본 발송(--resend)만 「발송해」 명시 승인 후.
type: feedback
---

정보 (풀네임 + 이메일) 수령 시:
1. DOCX/PDF 생성 (`generate_influencer_contract.py`)
2. DocuSeal `--no-send` 업로드 (`send_docuseal_contract.py --no-send`)
3. 서명 URL 보고 — **세은이 클릭해서 바로 내용 확인 가능한 상태로 만들어 두기**

여기까지 한 묶음 자동. 본 발송(`--resend SUBMITTER_ID`)만 세은 「발송해」 명시 후.

**Why:** 2026-05-22 玉木様 케이스에서 DOCX만 생성하고 「DocuSeal 업로드해도 될까요?」 승인 대기 → 세은 「생성해서 url까지 생성한 다음에 내가 바로 누를 수 있는 상태로 만들라고」. URL 없이 DOCX/PDF 파일 경로만 보고하면 세은이 매번 파일 열어서 확인해야 함 — 비효율. 서명 페이지 클릭 한 번이 가장 빠른 검토 path.

**5/21 ゆっち 룰 (「--no-send 도 사전 승인 필요」) → 본 룰로 OVERRIDE.** 5/21 사고의 본질은 본 발송이 아닌 「발송됐다고 거짓 보고」 + 「자동 진행 후 사후 통보」. 보고 정확성·URL 동봉·본 발송 별도 승인을 지키면 --no-send 자동 OK.

**How to apply:**
- 풀네임 + 이메일 둘 다 수령 + 협상 단계(STEP 6) 정보 충분 → DOCX 생성 + DocuSeal --no-send 업로드 자동 진행
- 출력물: ① Submission ID ② 인플루언서 + 핵심 조건 1줄 ③ **서명 URL (https://docuseal.orbiters.co.kr/s/...)**
- 안내 DM, 본 발송, 추가 액션은 X — 세은 「발송해」 / 「OK」 / 「DM 보내」 명시 후
- 검증 필수: `--check {id}` 로 `sent_at: null` + `send_email: false` 확인 후 보고 (도구 stdout 만 신뢰 X)
- contract_workflow_guard hook 마커: `# seeun-approved: YYYY-MM-DD <사유>` — 「URL 만들어 두는 영구 룰」 사유로 박기
