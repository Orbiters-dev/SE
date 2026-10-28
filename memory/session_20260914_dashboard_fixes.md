---
name: session-20260914-dashboard-fixes
description: 세션 2026-09-14 (메타몽 — JP 대시보드 2건 수리: RPP 키워드 분류 버그 + 아마존 세션 스테일 복구 + 장보고 노션) + 무검증 카드문구 단정→과잉후퇴 교정
metadata:
  type: project
---

## JP 대시보드 수리 2건 (build_jp_dash.py = .tmp/ceo_ads_report/, catchup_jp_collectors.py 가 호출)

**1. RPP 등록 키워드 분류 버그 수정 (배포 완료)**
- 증상: 등록 키워드 카드에서 `グロミミ ステンレスマグ`(브랜드+제품 조합)이 branded 아닌 generic으로 오분류.
- 원인: [build_jp_dash.py:175](.tmp/ceo_ads_report/build_jp_dash.py#L175) `cls, ko = KW_CLASS.get(k, ("generic",""))` — 브랜드 판정이 **정확일치 딕셔너리**(`グロミミ`·`grosmimi`만 exact 키). 조합 키워드는 딕셔너리에 없어 generic 기본값으로 샘. 같은 파일 아마존 `amzCls()`(L708)는 부분포함(`in`)이라 정상 — RPP만 규칙 달랐음.
- 수정: generic 확정 전 `any(b in k for b in ("グロミミ","グロスミミ")) or "grosmimi" in k.lower()` → branded 승격. seed 재생성 후 브랜드 포함 5키워드 전부 branded 검증 → build+deploy(vercel --prod) 완주.
- 잔여: competitor(먼치킨/피죤) 조합도 같은 exact 한계 있으나 별개. 세은 지시 시 통일.

**2. 아마존 세션 데이터 스테일 복구 (배포 완료)**
- 증상: Traffic&Conversion(아마존 JP) 카드 세션·전환이 9/08 정지(6일 stale). 세션축=로그인 수집.
- 근본: JP SP-API 앱에 **Brand Analytics 롤 없어 `GET_SALES_AND_TRAFFIC_REPORT` 403** → 무인 불가. 확인 앵커=[sales_traffic_us.yml](.github/workflows/sales_traffic_us.yml) 주석 + 무인 경로 [fetch_sales_traffic.py](tools/fetch_sales_traffic.py)(US는 이걸로 이미 무인). 로그인 수집기=`.tmp/brand_analytics/br_traffic_login_collect.py`(영구 프로필 ba_profile·max_auth_age=300 일체형·headed).
- 조치: 로그인 수집기 실행(세은 OTP)→4/1~9/13 166일 수집(9/11·12·13 세션 161·184·186)→build+deploy. amz-traffic-seed.json 9/13 검증.
- 부수 규명: 라쿠텐 카드 최근일 Organic 0 = 라쿠텐 방문(총방문) 데이터 익일 지연(버그 아님, RPP주문>총주문 모순이 미수집 증거). 아마존 세션 무인화 근본해결 = **BA 롤 승인(대외 신청)** — 승인 시 코드·배선 준비됨.

## 장보고 (노션 토글, PDF X)
- Seeun Daily Report 35a86c6d 에 `2026-09-14 (월)` 토글 append(25블록·표 6). §1 대시보드 2건·§2 메타(일 D-1/주7일·신규22·BEST=TWINS_RUAMOA 15.44%/WORST=NAO_BABYGRAM 8.4%)·§3 없음·§4 결정요청(BA 롤).
- 메타 주7일 지출 205.5만원(+2.4%)·CTR 11.75%·CPC 56원. 빌더 .tmp/daily_meta_fetch_0914.py + daily_notion_0914.py.

## 교정
- 무검증 카드문구 단정→과잉후퇴 [[mistakes-20260914-unverified-ui-text-then-overretreat]] (「왜 자동화된다고 했어」·「열받게 하네」). [[feedback-resolve-dont-offer-when-verifiable]] 재발.
