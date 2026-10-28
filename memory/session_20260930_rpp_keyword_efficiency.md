---
name: session_20260930_rpp_keyword_efficiency
description: 세션 2026-09-30 (삐삐 — RPP 판매중 3상품 20키워드 효율 리포트 콘솔실측×리포트 교차 HTML 빌드 + 틱톡 API 티켓/Storage캐시 팝업 문답)
metadata:
  type: project
---

# 세션 2026-09-30

## 1) 삐삐 — RPP 판매중 키워드 효율 리포트 (메인)
세은 요청: "지난주 업뎃한 RPP 키워드(현재 판매중 상품 한정·슈퍼세일 ㄴㄴ·rakuten 들어가서 제대로 확인) 효율+시사점 정리".
- **콘솔 실측(오늘)**: 판매중 3상품 각 手動 20키워드 / 슈퍼세일·copy 5개는 9/21 키워드 전량 비움. → 대상 확정. 정본 [[reference_rpp_keyword_efficiency_pipeline]].
- **산출물**: `s\performance marketing\Rakuten\rpp_keyword_efficiency_20260930.html` (탭형·20개 전량·KO병기·헤더 정렬).
- **세은 반복 수정(전부 반영)**: 設定/目安CPC → 설정 CPC/추천 CPC · 헤더 클릭 오름/내림 정렬 · 시사점 열 제거 · CPC실적 열 제거 · 시사점 4개→10개 확장.
- **결과 요약**: 스텐 ROAS478%/PPSU175%(제네릭 ¥11,109 전환0 진범)/원터치144%. 전환 7키워드 집중·상위4가 77%. 제네릭 3상품 중복=자기잠식.

## 2) 좋은 자기점검 (교정 전 스스로)
- "수요부재"로 뭉뚱그렸다가 세은 "왜 노출 안 되냐" → **단정 안 하고 프록시(H10·라쿠텐 유입) 실측 후** 답(입찰 아님·검색빈도 극저+자동최적화 배분). 韓国계 어는 라쿠텐 유입에 실존(수요0 아님).
- 틱톡 "확실해?" → 추론 멈추고 TikTok 공식문서로 검증 후 답.

## 3) 틱톡 문답 (틱톡이)
- 어제(9/28) 제출한 **TikTok for Business 개발자 프로필 심사("domain security" 거절)** 티켓 확인 위치 = developers.tiktok.com/apps (앱 상세→history 아이콘→Review comments) or Business Support 티켓+등록메일(hello@grosmimijapan.com). 포털 재제출은 in-portal, 소명서 티켓은 메일.
- **"Storage limit reached / Clear the cache" 팝업** = TikTok Ads Manager **브라우저 캐시** 이슈(계정 용량 아님·소재 20개로 찰 리 없음 지적 맞음). 공식문서: 캐시 정리는 계정/영상/드래프트 영향 없음·로그인 유지. reset_cache=1 URL 우회 가능.
- ⚠ Gmail MCP 토큰 만료로 접수 메일 교차검증 미완(재인증 필요).

## 미완/대기
- RPP 실행(제네릭 정리·입찰강화·ベビーマグ OFF)은 세은 승인 후(하드룰11).
- 원한다면 9/1~20 vs 9/21~29 창분리로 순수 before/after 델타 재수집 가능(현재는 9/1~29 스냅샷).
