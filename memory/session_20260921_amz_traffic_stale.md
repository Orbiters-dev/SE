---
name: session-20260921-amz-traffic-stale
description: 세션 2026-09-21 (메타몽 — 아마존 JP 트래픽/세션 축 09-16→09-20 stale 재복구: 저장세션 OTP없이 자동통과 → seed 재생성 → vercel prod 배포. 9/17 교정 학습대로 되묻지 않고 즉시 복구·교정 0)
metadata:
  type: project
---

## 작업: 아마존 JP Traffic & Conversion 세션 축 stale 재복구 (완료·배포)

- **증상:** 세은이 메타몽 앱 스샷 던지고 「메타몽 앱에 이거 반영」 — Traffic&Conversion(아마존 JP) 세션이 09-16까지·수집 09-17T11:28에서 멈춤. 오늘 09-21 → 4일 stale.
- **판단:** 9/17 [[session-20260917-amz-traffic-stale]]과 판박이. 「이거 반영」 = 세션 안 들어오니 최신 수집해서 반영하라는 뜻(스샷 데이터=현 seed 그대로임을 실측 대조로 확인). 되묻지 않고 복구 파이프라인 실행.
- **복구 파이프라인 (3단계, 전부 절대경로):**
  1. `.tmp/brand_analytics/br_traffic_login_collect.py` (headed, ba_profile 영구프로필) → **저장세션 살아있어 OTP 없이 AUTH_OK 자동통과** → 173일(2026-04-01~09-20) 재수집 → `br_traffic_daily.json`. 신규 09-17~20 = 세션 148/140/145(09-18~20, 주문 1·1·0).
  2. `.tmp/ceo_ads_report/build_jp_dash.py` → `meta-app/lib/amz-traffic-seed.json` 173일 재생성(line 467 경로). updated_at 09-21T09:17·마지막 09-20.
  3. `.tmp/ceo_ads_report/deploy_to_meta_app.ps1` → decks 복사 + `vercel --prod --yes` → READY·`meta-app-one.vercel.app` alias 갱신. prebuild status-guard PASS.

## 함정·교훈
- **Bash 도구 cwd가 meta-app로 고정되면 훅(n8n/contract guard) 상대경로가 깨져 모든 bash 명령 실패.** `cd meta-app` 이 원인 — 훅은 명령 실행 前 cwd 기준. 회피: 절대경로 도구(Read/Glob/Grep) + **PowerShell 도구**(별도 cwd)로 파이썬 실행. SE 루트 cwd 유지가 정답.
- **배포 검증 함정:** deploy_to_meta_app.ps1 이 `vercel ... | Select-Object -Last 5` 로 잘라 마지막 JSON "next"만 보임 → 배포 성공 오판 위험. 직접 `vercel --prod --yes | Out-String` 전량 재확인해 readyState=READY·target=production·Aliased 확정 후 보고([검증] 룰).
- `/keyword/amazon` 은 proxy.ts 로그인 게이트 → 세션쿠키 없이 라이브 렌더 못 뜯음. 확정 근거는 배포 체인(로컬 seed 실측 → 그 seed로 build 성공 → prod READY → alias 갱신).

## 구조적 사실 (재발 정상)
- 이 축은 SP-API Brand Analytics 롤 미승인 → `GET_SALES_AND_TRAFFIC_REPORT` 403 → **무인 수집 불가.** catchup은 MONITOR(경보전용)만. **BA 롤 승인 전까지 며칠에 한 번 수동 복구 반복이 구조상 정상**(9/14 장보고 §4 결정요청). 근본해결=BA 롤 승인(대외). 승인 시 `fetch_sales_traffic.py` 무인화(배선 준비됨).

## 교정
- 없음. 9/17 [[mistakes-20260917-dashboard-stale-signal-missed]] / [[feedback-resolve-dont-offer-when-verifiable]] 학습대로 stale 신호 읽고 되묻지 않고 복구 → 통함.
