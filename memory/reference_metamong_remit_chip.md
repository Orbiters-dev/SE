---
name: reference-metamong-remit-chip
description: 메타몽 크리에이터 탭 「송금」 칩 정본 (2026-10-23 — DocuSeal 계좌 필드→세은 ①~④ 팝업·全銀 zengin-code 자동해석·여권식 로마자 ITO·우편번호/지점코드 분리 행·영문주소 자동생성 28건)
type: reference
---

## 구조 (meta-app)
- **데이터**: `lib/docuseal-contracts.ts` fetchContracts() 가 completed 계약 values 에서 계좌 필드(金融機関名·支店名·口座種別·口座番号·口座名義·電話·郵便·住所) 추출 → `DsContract.remit`. **계좌 기입란 보유 = 유상 템플릿 확정 마커** (기프팅 템플릿엔 필드 자체 無 — 유상/무상 판별 정본).
- **해석**: `lib/remit.ts` buildRemitInfo() — zengin-code(全銀 전 은행·지점 데이터셋, 서버 전용 번들·클라이언트는 type-only import)로 은행/지점 자동 해석. 지점 입력 혼형(코드만 "372"·이름만·"小倉支店（318）"·한자숫자 "八四八"·개명은행 별칭 住信SBI→ドコモSMTB) 전부 수용 — 유상 34건 백테스트 33 해석·충돌 0. zengin roma 필드는 품질 불량 → **kana + 자체 변환기** 사용.
- **로마자**: kanaToRomaji(요음 sha/cho/ju 정확) + collapseLong(**여권식: ou·oo→o, uu→u — イトウ→ITO, 2026-10-23 세은 확정**).
- **영문 주소**: `lib/remit-addresses.ts` (자동 생성 28건) — 재생성: `.tmp/gen_remit_addresses2_20261023.py`(zipcloud 공식 카나·잔여 한자 사전·郡+町/市+区 분해) → `.tmp/bake_remit_addresses_20261023.py`. 수기 검증 OVERRIDES(remit.ts·#251/#294/#259)가 우선.
- **UI**: `components/kpi/RemitChip.tsx` — 칩 클릭→Modal, 세은 ①~④ 섹션 고정, **支店コード·郵便番号 분리 행**, 전 필드 클릭 복사(✓ 피드백).
- 폼 합성 행: `app/influencer/creators/page.tsx` — Master DB 미등록도 기본정보 폼 값으로 행 합성(formOnly·✎ 비활성·「폼」 배지), 222→258명.

## 운영
- 신규 유상 계약 서명 → 칩 자동 생성. 영문 주소만 신규 건 재생성 스크립트 1회 (혹은 입금 시점 수동 등재).
- Paid 드롭다운 일괄: `.tmp/wl_paid_status_bulk_20261023.py` (dry→--apply·리드백 검증).
- 배포 `vercel --prod` (meta-app·git push 아님). prod E2E: 도메인 **meta-app-one.vercel.app** (…-projects.vercel.app 은 Vercel SSO 차단), 로그인 pw 0812.

## 함정
- **ScrollableTable 드래그 후 클릭 삼킴 버그 (수정됨)**: onDown 이 버튼에서 early-return 하면 dragged 플래그가 안 풀려 capture 단계 onClick 이 이후 모든 버튼 클릭을 삼킴 — onDown 첫 줄에서 dragged=false. E2E 통과≠실동선 통과: **드래그→클릭 동선 재현 필수**.
- ドコモSMTBネット銀行 공식 영문 행명 미확인(—). 구계약 7건(#86·74·73·59·58·57·41)은 주소란 없는 템플릿.
- ぴま(@pima_ikuji) WL 행 자체 없음 — 핸들 전각 ＿ 는 NFKC 정규화로 매칭할 것.
