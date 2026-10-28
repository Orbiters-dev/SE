---
name: 인플루언서 계약정보 폼 응답 시트 + 신규/재협업 폼 URL 2종
description: STEP3 계약정보 폼 응답 = 시트 1Gd8JrWm... 「기본정보」 탭(C열 IG핸들). 리치아웃 폼 2종 구분 — 신규(...Scy3qvzsR...) vs 재협업(...Sexi5V8uTM...).
metadata:
  type: reference
---

## 계약정보 폼 응답 시트 (조회용)
- **시트 ID**: `1Gd8JrWm-nOzscmL2tPLTW23EoC_QGtA07C0xMY6Jr8E` (tools/rename_form_uploads.py SHEET_ID와 동일)
- **탭 4개**: `통합` / `기본정보` (신규 계약정보 폼) / `투고완료` (투고완료 폼) / **`재협업 정보`** (재협업 폼 응답)
- **「기본정보」 컬럼 (0-base)**:
  - 0 日時 / 1 お名前(フルネーム) / 2 Instagramアカウント名(@〜) / 3 ご職業 / 4 メールアドレス / 5 お子様の月齢
  - 6 PPSU ワンタッチ / 7 ステンレスストローマグ / 8 PPSU ストローマグ (선택 제품에 색상·용량 기입) / 10 ご希望の商品
- **「재협업 정보」 컬럼 (0-base)** (2026-10-05 村田 건에서 실측):
  - 0 Timestamp / 1 お名前(フルネーム) / 2 Instagramアカウント名(@〜) / 3 メールアドレス / 4 PPSU ストローマグ / 5 PPSU ワンタッチ / 6 ステンレスストローマグ / 7 Column7 / 8 切り替えのストロー(替えストロー 세트, 라쿠텐 srawnipple_2-2)
  - ⚠️ 재협업 폼엔 **직업·월령·보수 금액 항목 없음** → 보수/제품 구성은 세은 확인 (원장 stale 가능)
- 조회법: `get_sheets_client().open_by_key(ID).worksheet('기본정보')` (재협업은 `worksheet('재협업 정보')`) `.get_all_values()` → 핸들 또는 이름(1열)으로 매칭. SA = influence-sync@influencer-db-claude(.env GOOGLE_SERVICE_ACCOUNT_PATH)
- ⚠️ `.env INFLUENCER_SHEET_ID`(`1DPI_zxG...`)는 **CRM/캠페인 시트**지 폼 응답 아님. 폼 응답은 위 `1Gd8JrWm...`.

## 리치아웃 폼 URL 2종 (DM 발송용)
- **신규 인플루언서**: `https://docs.google.com/forms/d/e/1FAIpQLScy3qvzsRGf7dgr4ELPZvrhOpa00qGSjP1mZOzJI4G6jD_4oA/viewform`
- **재협업 인플루언서**: `https://docs.google.com/forms/d/e/1FAIpQLSexi5V8uTM0Pug2Rrpm4JHLOvieCepPRE_FLaGTMyjLx_TEjw/viewform` (2026-10-01 세은 확정 — 재협업은 이 폼. 편집 링크 `1KZifqgrRod1h_nOOd66Du_yctzLyKfGnXiwamwcs5Rs`)

## Google Forms API
- 프로젝트 `influencer-db-claude`에서 **Forms API 비활성화** (2026-10-01 403 SERVICE_DISABLED) → 폼 질문/이미지 자동 편집 불가. 폼 구조 수정은 세은이 UI에서 수동(선택지 추가 + hover 시 이미지 아이콘 업로드, 구글폼 자동저장). 활성화하려면 콘솔 Enable + SA를 폼 편집자로 공유 필요.

[[feedback-influencer-handle-form-lookup]]
