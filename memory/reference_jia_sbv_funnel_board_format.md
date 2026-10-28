---
name: reference_jia_sbv_funnel_board_format
description: 대표님/최원준이 지정한 퍼포먼스 마케팅 보드 목표 양식 = 김지아 "SBV 퍼널 개정 v0.8" (Amazon SP→SBV). 구조+운영룰+변경관리(현행/개정·액션로그)를 한 보드에. 세은 JP 보드를 이 양식으로 만들어야 함.
metadata:
  type: reference
---

# 지아님 SBV 퍼널 보드 = 목표 양식 (2026-10-06 최원준 전달)

claude.ai 코드 아티팩트(공개) 51c88d26-6d3e-4de6-b59b-6155bce5046c. 스크랩본 .firecrawl/artifact_sbv.md.
최원준: "전체적으로 그리고자 하는 양식 + 변경로그 어떻게 넣을지가 보임. 메타몽으로 필요한 부분 발췌해서 만들어달라." → 세은 JP 퍼포먼스 보드를 이 양식으로.

## 양식 핵심 (단순 구조도 아님 = 구조+운영룰+변경관리 통합)
1. **4단계 가로 플로우**: ①SP 구조·셋업 → ②SP 감사·판정(금요일) → ③SBV 셋업 → ④SBV 판정·하베스트. (플랫폼별 "구조 → 판정/감사" 흐름)
2. **노드 안 `현행` vs `개정` 병기 = 변경로그 핵심**: 각 노드가 "지금 집행(현행=원본값)" + "개정안(WJ 승인 후 적용)" 같이 표기. 승인 전엔 개정=미리보기.
3. **색 범례**: 확정/현행 룰 · 초안/WJ드래프트 · 미정/WJ결정필요 · 피드백루프. 배지: CUT·WATCH·SCALE·신설·수정.
4. **판정 = 숫자 2개 (E·I)**:
   - E = 지출 ÷ 구간 주문당 광고비 = "평균이면 나왔을 주문 수" (문턱: E10/E20/E33). E 넘기 전엔 I 나빠도 무조치(위생 예외).
   - I = ROAS ÷ 제품군 BEP(광고 전 공헌이익 기준). I<0.6 CUT·0.6~0.8 WATCH·0.8~1.0 KEEP·≥1.0 SCALE.
   - 상대 I(SBV 소재) = 실제ROAS ÷ (같은검색어 SP ROAS × 0.4~0.5).
   - 창 = 최근 4주, 끝 D-3.
5. **티어 사다리**: T1~T3(입찰 검증 키워드) · H1~H3(하베스트 검색어 등급). I로 승강급.
6. **액션 로그 (하단·필수)**: 실행마다 한 줄 = 대상ID · 전→후 · rule_id · 사유코드(CUT/WATCH-1/SCALE-BUDGET/BID-PERF/BID-REACH/HARVEST-ADD/NEG/CAP/REPLACE/HOLD-*/EXCEPTION). "WJ보드 자동" 변경이력 수집·판정일 CSV·효과 리포트.
7. **용어집** + **판정 전 체크**(재고<30일·행사±7일·구조변경 후 7일·최근3일 미성숙 → 보류).

## ⚠️ JP 적용 시 현실 (내 독립 판단)
- 예시 = **Amazon US 1개 플랫폼 극단 깊이**. E/I·BEP(PPSU 3.89x·SS 3.09x)·$문턱 전부 US 실측. JP에 그대로 못 씀.
- **Meta**: 판정 게이트 데이터 완비(CPC≤95·CTR≥8%·CPLPV≤130=현행 / 개정은 세은 결정) → 이 양식 바로 가능.
- RPP: 부분(¥5,000 OFF·미노출 퇴출). Amazon JP·TikTok: 구조만, JP 판정수치 없음.
- → Meta부터 템플릿 확정 후 확장이 합리적 (세은 확인 대기).

관련: [[project_miro_jp_perf_route_map]] · [[reference_meta_wl_testing_gate_criteria]] · [[feedback_keyword_types_branded_competitor_generic]]
