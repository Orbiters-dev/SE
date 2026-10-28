---
name: 월령 불명 시 최근 포스트 자동 조사 필수
description: IG 바이오에 월령 정보 없을 때 세은에게 묻지 말고, 무조건 최근 포스트 조사해서 월령 추적부터 한다.
type: feedback
---

리치아웃 대상 IG 핸들의 바이오에 월령 정보가 없을 때, 세은에게 「어느 제품으로 진행할까요?」 식으로 묻지 않는다. **항상 최근 포스트 8개 정도를 자동 조사**해서 월령 단서를 찾는다.

**Why:** 2026-05-08 ha_chan_happydays 케이스. 바이오에 월령 정보 없어 세은에게 제품 결정 묻자 「나한테 묻지 말고 항상 최근 포스트 추가 조사 후 월령 추적 필수」 강한 교정. 세은이 직접 결정하는 건 월령 단서가 정말 없을 때만. 직접 파악할 수 있는 건 묻지 말 것 룰의 연장.

**How to apply:**
- `fetch_ig_profile.py` 결과에 child_age.estimated_months 가 None 이면 즉시 후속 조사
- Apify `apify~instagram-scraper` actor + `directUrls=[https://www.instagram.com/{handle}/]`, `resultsType=posts`, `resultsLimit=8` 로 최근 포스트 캡션 조회
- 캡션에서 「○ヶ月」「○m」「○か月」「生後○」「○歳」「YYYY.MM 출생」 등 키워드 추출 → 현재 날짜 기준 월령 환산
- PYTHONIOENCODING=utf-8 필수 (cp949 깨짐 방지)
- 월령 확정되면 워크플로우 룰 적용:
  - ~12ヶ月 → PPSU ストローマグ
  - 12~24ヶ月 → ワンタッチ
  - 24ヶ月↑ → 대상 외
- 8개 포스트 봐도 월령 단서가 정말 없을 때만 세은에게 보고
- 자녀 다명 시 막내 기준
