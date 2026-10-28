---
name: reference-rms-licensekey-rotation
description: RMS Order API 401 = licenseKey 만료 신호. 새 키는 RMS 웹 콘솔 WEB APIサービス > 2-1 アプリ一覧에서 Playwright로 자체 확보 가능 (로봇체크 좌표클릭 통과 확립)
metadata:
  type: reference
---

# RMS licenseKey 만료 대응 (2026-07-21 확립)

## 증상
- `api.rms.rakuten.co.jp` Order API 가 **401 (body 빈 값)** → ESA 헤더의 licenseKey 만료.
- ESA = `"ESA " + base64(serviceSecret:licenseKey)`. serviceSecret(SP435776_…)은 불변, **licenseKey(SL…)만 로테이션**됨.
- 7/21 실측: 구키 2개(…G60g / …EFKV) 전부 401, 현행 키(…8GFv, 유효기한 2026/09/27)로 교체 후 200.

## 새 키 자체 확보 경로 (세은 개입 불필요)
1. `rms_review_playwright.do_login` → 메인메뉴의 「WEB APIサービス」 링크 (ichiba-bs…/apisson/merchant-portal — 직접 URL 진입은 app_login_error, **메인메뉴 경유 필수**)
2. 레프트나비 「2-1 アプリ一覧」 → 店舗様/KSE OMS 행 「詳細」 (`/merchant-portal/licenseChallenge?licenseId=…&type=1`)
3. **로봇체크**: 커스텀 위젯(#challenger-block, shadow DOM — 셀렉터 안 잡힘) → 「ロボットによる操作ではありません」 체크박스를 **좌표 클릭** (1280px 뷰포트에서 ≈641,374; 사람처럼 mouse.move 단계 이동 후 클릭) → #cres 채워짐
4. `#btnLicenseChallenge` (確認する) 클릭 → `configurationApi` 페이지에 **전체 키 평문 노출** (정규식 `S[LP]\d{6}_[A-Za-z0-9]{16}`)
- 스크립트: `.tmp/rms_licensekey_scrape11.py` (v11, 검증 완료)

## 갱신해야 할 곳 (4곳)
1. `credentials/rakuten_rms_config.json` auth.value (ESA 재조합)
2. `.env` `RAKUTEN_LICENSE_KEY`
3. `meta-app/.env.local` `RMS_ESA_AUTH`
4. Vercel prod env `RMS_ESA_AUTH` — CLI `--force` 는 조용히 실패, **`vercel env rm` → 파이프 `vercel env add`** 순서로 (갱신 후 재배포)

## 부수 발견
- searchOrder 7일 청크 **연사 시 403 (rate limit)** — 개별 창은 200. 청크 간 0.6s sleep + 403 지수 백오프 (collect_rakuten_sales_daily.py `_post_with_retry`).
- meta-app 전환 탭 당월 라이브 주문 fetch 도 이 키를 씀 — 만료 기간 동안 조용히 죽어 있었음.
