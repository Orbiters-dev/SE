---
name: session-20261014-meta-currency
description: 세션 2026-10-14 (메타몽 — JP 계정 KRW→USD 통화 변경 가능 여부 조사. 결론=변경 기능은 있으나 실체는 기존 계정 폐쇄+새 계정 생성. 전부 공식 문서 실측)
metadata:
  type: project
---

# 세션 2026-10-14 — 메타몽: Meta 광고 계정 통화 KRW→USD 변경 조사

세은 질문: JP 계정(act_4117678028561958, KRW) 통화를 USD로 바꿀 수 있나. 전부 firecrawl로 Meta 공식 문서 실측.

## 확정 결론 (출처 URL 포함)

1. **통화 변경 = 기존 계정 폐쇄 + 새 계정 생성** — 라이브 광고 전부 즉시 중지, 재활성화 불가. 60일 1회·잔액 0·admin 필요. 월별 인보이스 계정은 변경 자체 불가.
   - https://www.facebook.com/business/help/291404291014138 (변경 절차 3단계 바로 아래 문단에 명시)
   - https://www.facebook.com/business/help/754049591334898 ("You can't reactivate this account" 명시 — 공유용으로 제일 명확)
   - https://www.facebook.com/business/help/1798922733589154 (통화/타임존 폐쇄 계정 = 재활성화 불가 예외조항)
2. **날아감**: 캠페인/애드셋/광고 전부 재생성, 애드셋 학습 전부 리셋(탈출=1주 내 약 50 results, help/112167992830700), 성과 이력은 구 계정에 갇힘.
3. **유지**: 픽셀/데이터셋=BM 자산 → 새 계정에 연결 가능(help/1556728331732865). Page·IG·인플루언서 원본 게시물(social proof 포함).
4. **WL 파트너십 권한 = 광고 계정 무관, IG 비즈니스 계정(grosmimi_japan 17841473805016400) 바인딩** → 새 계정에서도 유효. 개발자 문서로 확정:
   - account-level: `/{business-account-id}/branded_content_ad_permissions` (developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/partnership-ads/account-level-permissioning)
   - post-level: `sponsor_id=<비즈니스 계정 ID>` (같은 경로 /post-level-permissioning)
   - 단 코드 방식(WL-P) 라이브 광고는 새 계정에서 코드 재입력·재생성 필요. 코드의 "동시 2파트너" 슬롯이 새 광고 계정을 별도 카운트하는지 = 확인 못 함(코드 재발급 언제든 가능이라 리스크 낮음). 최종 실효 검증 = 광고 effective_status ACTIVE + issues null.
5. **"머신러닝 사라짐"을 한 문장으로 쓴 Meta 공식 문서는 없음** — 공식 2개(291404+112167992830700) 조합 결론. verbatim 서드파티: https://zenweb.my/blog/facebook-ads-wrong-currency/ ("What does not carry over is the old account's campaign history and its learning phase").

## 권고 (세은에게 전달 완료)

- Payment settings에서 바꾸기(라이브 즉사)보다 **같은 BM에 USD 신규 계정 생성 → 세팅·라이브 → 안정 후 KRW 순차 OFF** 병행 이전.
- JP는 LPV 최적화라 재학습 자체는 짧음(₩8,000/day·CPLPV 41~190 → 일 42~195 LPV → 50 기준 수일 내). 진짜 비용 = 전 애드셋 동시 D0~2 리셋 + 전환 공백 + 자동화 전면 교체(META_JP_AD_ACCOUNT_ID 하드코딩 — GHA·판정보드·DK 수집).

## 미완 / 대기

- 세은 "KRW라서 전환이 어렵다"의 구체 증상(결제 실패/환율/리포팅?) 미회신 — 증상 따라 통화 변경 없이 풀 수도.
- 실제 전환 결정 시: 새 계정 테스트 WL 광고 1건으로 권한 실효 실측 필요.

관련: [[reference-jp-platform-live-operation]]·[[reference-wl-partnership-ad-permission]]·[[feedback-source-verbatim-vs-synthesis]]
