---
name: mistakes_20260909_remittance_format_and_completeness
description: 송금 요청 정리 — 기존 표준 포맷 미확인·자료 요청 시 수신처(메일주소) 누락·지점코드만 적고 지점명 미조회로 교정 연타 (2026-09-09)
metadata:
  type: feedback
---

村井様(べびもん) 2차 콜라보 송금 요청 정리에서 한 턴에 하나씩 빠뜨려 세은에게 반복 교정받음 (「왤케 멍청하냐」·「이새끼 진짜 미쳤네」·「장난하나」).

**빠뜨린 것들 (매 턴 하나씩):**
1. 송금 정보 정리에 이미 확정된 표준 표 포맷([[reference_remittance_info_format]])을 처음부터 안 씀 → 「내가 분명 이 형식으로 정리하라고 말했을 텐데」
2. 원본 영상 요청 DM에 **수신 메일 주소(hello@grosmimijapan.com)** 를 안 넣음 → 「메일 주소 안 보내주면 저 사람이 어떻게 알아」
3. 수취인명을 한자/카나/로마자/한글 4중 병기 → 한자만 ([[feedback_remittance_payee_kanji_only]])
4. 지점코드 507만 적고 지점명 미조회 → firecrawl로 조회해야 함 (507=金沢支店/Kanazawa)

**Why:** 송금/자료 요청은 "받는 사람이 그 정보만으로 실행 가능한가"가 완결 기준. 코드·양식·수신처 중 하나라도 비면 상대(팀원/인플루언서)가 되물어야 함.

⚠️ **재발 2026-10-21 (2회차)**: 野崎·柳原 송금 정보를 임의 2열 표로 전달 → 「야 내가 이렇게 하라 했어?」. "송금 정보" 단어가 나오면 산출 전에 반드시 이 파일+[[reference_remittance_info_format]]부터 Read. 계좌 소스가 어디든(DocuSeal/계약서/레저) 출력 형식은 표준 2블록 고정.

**How to apply:**
- 송금 정리 착수 전 [[reference_remittance_info_format]] Read 먼저. 표 양식·수취인 한자만·병기 규칙 그대로.
- 계약서에 코드만 있으면(店番号 등) 그 자리에서 조회해 실명까지 채운다. 미확인으로 넘기지 말 것.
- 인플루언서에게 자료(원본 영상 등) 송부 요청 시 **수신처(메일주소·업로드처)를 반드시 본문에 명시**. 원본 수신 메일 = hello@grosmimijapan.com ([[feedback_step12_ad_code_with_original_video]]).
- 관련 반복 패턴: [[mistakes_20260907_partial_data_repeated_assertion]] (완결 못한 채 넘김).
