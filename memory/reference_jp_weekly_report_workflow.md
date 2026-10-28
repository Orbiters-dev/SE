---
name: JP Weekly Report = daily 종합 + 5/7 양식 그대로
description: /weekly 또는 weekly 작성 요청 시 5/7 weekly 페이지 양식 참고 + daily 5/X~ 토글 종합. existing children archive 후 새로 채워 넣는 방식.
type: reference
---

5/22 W19~W21 통합 weekly 작성 중 정립.

**Where:**
- 부모 DB: `2fc86c6d-c046-8000-a671-e3ed32083c8f` (JP Weekly Report)
- 5/7 Seeun weekly (양식 참고용): `35986c6d-c046-804d-8748-ff18d2d14a6a`
- Daily 종합 페이지: `35a86c6d-c046-800c-b3a8-fd2baa8cbdf4` (Seeun Daily Report)

**양식 (5/7 weekly 따라):**
```
P: Team: JAPAN
P: Week of: MM/DD/YYYY (Wxx)
P: Team Member: seeun
divider
H2: 1️⃣ Primary Focus Area  → BUL × N + H3 Projects & Campaigns + H3 Time Allocation
divider
H2: 2️⃣ Results (OKRs)  → H3 OKR Progress + TABLE width=6 (Key Result/Target/Last Week/This Week/Progress/Status) + H3 Instagram/TikTok
H2: 🤝 인플루언서 협업 현황 (Wxx — m/d~m/d) → 신규 리치아웃 / 投稿완료 / 신규 계약 / 스케줄 / 지출 / Wins
divider
H2: 3️⃣ Challenges  → P Challenge N + BUL Impact + BUL Status
divider
H2: 4️⃣ Hypothesis  → Case A/B (광고 실험 등) — P/H3/TABLE 구조
divider
H2: 5️⃣ Next Week  → H3 Top Priorities (numbered_list_item × 6) + H3 OKR Focus (BUL)
```

**데이터 출처:**
- CRM / 메타 / 인플루언서: daily report 토글 dump (`.tmp/daily_dump_*.txt`)
- IG followers: Apify `apify~instagram-profile-scraper` (`@grosmimi_japan` 등) — 1회 호출
- 평균 조회수 / Top Post: Syncly JP Posts Master gid=842545840 (단, **stale 가능** — 갱신 확인 필요)
- 시딩 원가 / 출고건: 인플루언서 메모리 (`memory/influencers/*.md`)

**작업 path:**
1. 부모 DB query → 5/7 양식 page 본문 dump
2. Daily 5/X~ 토글 dump → 카테고리별 추출 (CRM / 메타 / 기타·인플)
3. Syncly + Apify로 OKR 수치 보강
4. 빈 weekly 페이지의 existing children 86개 archive (`DELETE /v1/blocks/{id}` × N)
5. 새 children 빌드 → `PATCH /v1/blocks/{page_id}/children` 90개씩 분할 append

**룰:**
- 데이터 모르는 값은 "데이터 확인 필요" 라벨로 빼고 진행 — 추측 단정 X
- daily 5/7 weekly가 이미 W18 다뤘으면 다음 weekly = 5/4부터 (또는 누락분 통째)
- 세은에게 묻는 건 "Week 범위" / "Case 후보" / "데이터 출처" 같은 정책 영역만

## 2026-09-18 확립: 메타 2️⃣ 섹션 = ssot.json 자동 생성 + Notion 직접 append

세은 "노션에 바로 쓰는 방식" 지시 시 = HTML 덱 아니라 Weekly DB 페이지 직접 생성(8/28 「템플릿 미생성 주」 절차와 동일). Meta 성과 표는 daily-dump 수기 대신 **ssot 자동**:
- 먼저 `build_jp_meta_deck.py` 실행 → `.tmp/jp_meta_deck/ssot.json` 갱신(재수집). ssot 신선도(ref_date·window_7d)·커버 주간 반드시 확인 — stale면 3주 추이가 어긋남. (덱 렌더는 [[reference-meta-ads-operations-folder-renamed]] 경로 이슈로 죽을 수 있으나 **ssot 저장은 렌더 전**이라 수집만 되면 OK)
- 빌더가 ssot 읽어 자동 생성: `weekly`(마지막 3개=3주 추이 표) · `totals_7d`/`totals_prev7`(이번주 Δ) · `ads_7d`(캠페인별 집계) · `new_launch_ads`(신규 콘텐츠) · `week_best`/`week_worst`(슬러그→ads_7d 매핑). 정본 빌더 예시 = `.tmp/weekly_report/create_weekly_0918.py` (→ Notion `POST /v1/pages` parent=Weekly DB).
- 업무 진척(1️⃣3️⃣4️⃣5️⃣ + 인플루언서 협업)은 이번 주 `memory/session_*.md` 실기록 기반. 효율 집계 윈도우 = 목→수([[weekly-report-효율-집계-기간-전-주-목-0000-그-주-수-2359]]).
- 커버 주간 = 오늘이 목/금이면 전 주 목~그 주 수 (예: 금 9/18 작성 → 9/11~9/17).
