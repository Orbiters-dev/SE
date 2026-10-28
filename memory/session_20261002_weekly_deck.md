---
name: 세션 2026-10-02 (JP 위클리 리포트 덱 — 핵심작업 3 + 채널현황 4탭 + 9월 인플루언서 퍼널 + TikTok 브라우저 수집 / 강한교정 3)
description: 10/1 노션 위클리 기반 탭형 HTML 덱 제작. RPP키워드·그로미미Overview·정성심사 + RPP/PPC/TikTok/Meta 현황. 9월 퍼널 실측 추가. 세은 교정 3건(PPC성과·심사갭·TikTok운영중) 전부 실측 반영.
metadata:
  type: project
---

# 세션 2026-10-02

## 산출물
`operations/jp_weekly_deck_20261002.html` — 탭형 9개(개요·RPP키워드개선·그로미미Overview·정성심사·9월퍼널·현황Meta/RPP/PPC/TikTok). 그로미미 핑크테마. 전 탭 Playwright 렌더검증(각 1페이지). 빌더/스크립트 `.tmp/weekly_deck_1002/`. 데이터 소스 정본 = [[reference-weekly-funnel-data-sources]].

## 세은 요청 반영
- 3대 핵심작업 탭: RPP 키워드 수정방향(제네릭 정리·ベビーマグ OFF·브랜드+속성 강화) / 그로미미 Overview = **인플루언서 전달용 파일 제작·수정 중**(상태만, 상세는 세은 직접) / 인플루언서 정성 심사 제작.
- 그로미미 Overview 탭에 **가이드라인 버튼 2개**(브랜드 안내·영상 제작 — claude.ai/artifact 링크, target=_blank).
- **9월 인플루언서 퍼널 탭**: 계약 서명 82 → 콜라보 업로드 37 → 정량 통과 30(측정32·94%) → 심사 29 → 집행 20. 전부 실측.
- RPP 탭: **상품별 전환 발생 키워드 표**(스텐=속성 保冷·ステンレス 견인 / PPSU·원터치=브랜드 グロミミ 의존 / 제네릭 단독=전환0 낭비).
- Meta 탭: **WL vs IHV 차이** 표(WL=인플루언서 콘텐츠 광고화·크리에이터 명의 / IHV=자사 제작영상). 이번주 WL(CPLPV ¥34~77) ≫ IH Testing(¥166).

## 강한교정 3건 (전부 실측 반영)
1. **PPC "미확정" 비워둠** → 「장난하나」. Amazon SP 성과는 DK `amazon_ads_daily`(currency=JPY 분리)에 있었음. 9월 ¥550,791 지출·ROAS 21%·ACOS 466% 적자·전환0 UNKNOWN 2캠 낭비. [[mistakes-20261002-channel-perf-declared-unavailable]]
2. **정성 심사 퍼널을 사전 게이트처럼 그림** → 「심사 전에 그냥 올라간 애들도 있지 않아?」. 실제 심사 소급(9/23·9/28·10/2)·미심사 8/37. "집행 먼저→사후 심사"로 수정. [[mistakes-20261002-retroactive-gate-as-sequential]]
3. **TikTok "심사 거절로 보류"** → 「그건 있어 그냥 api를 안 주는 걸걸?」. 광고 계정 littlefingerusa_adv 운영 중. 브라우저(Playwright 지속프로필)로 9월 실측: 트래픽 캠페인 1개 ¥64,126·CTR 16.32%·CPC ¥1·전환40,082. [[reference-tiktok-marketing-api-rejection-domain-security]]

## 미완 / 다음
- 정성 심사 10월부터 **업로드 전 사전 게이트**로 전환(현재 소급).
- TikTok 트래픽 → 구매 전환 연결 측정 · 틱톡샵 JP 오픈 후 GMV.
- Amazon SP 전환0 UNKNOWN 2캠 OFF + category 타겟 지혈.
- TikTok 세션 저장됨(`.tmp/tiktok_probe/userdata`) — 재수집 로그인 불필요.
