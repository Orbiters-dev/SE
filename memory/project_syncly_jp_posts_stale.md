---
name: Syncly JP Posts Master 5/8 이후 갱신 X (점검 필요)
description: ONZENNA Affiliates Tracker JP Posts Master (gid=842545840) 마지막 데이터 2026-03-11. JP 크롤링 파이프라인 점검 트리거.
type: project
---

5/22 weekly 작성 시 발견.

**Fact:** Google Sheets `1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc` 의 JP Posts Master 탭 23 rows, 가장 최근 row 가 `2026-03-11`. 5/8~5/21 게시물 0건 잡힘.

**Why:** Syncly JP 크롤링 파이프라인 (`fetch_syncly_export.py --region jp` + `sync_syncly_to_sheets.py`) 가 일별 자동 갱신되어야 하는데 멈춰있음. US Posts Master (gid=9206142) 는 동일 시기 218 rows로 정상.

**How to apply:**
- weekly 작성 시 평균 조회수 / Top Post / 콘텐츠 누적 OKR 산출 불가 → "데이터 확인 필요" 라벨로 빼고 진행
- 점검 path:
  1. `python tools/fetch_syncly_export.py --region jp` 실행 결과 확인
  2. Playwright session expired 가능 (`~/.syncly_state/chrome_profile/`)
  3. `python tools/sync_syncly_to_sheets.py --region jp` CSV → Sheets 동기화 단계 점검
- syncly-crawler skill 호출 시 JP region 우선 트리거

**Status:** Pending — 다음 주 점검 예정 (W22 Top Priority 6번에 박힘)
