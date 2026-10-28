---
name: 일일 보고 = 노션 toggleable heading_2 (PDF X · child_page X)
description: /장보고 일일 보고는 노션 Seeun Daily Report 페이지 35a86c6d에 toggleable heading_2 한 개 append. PDF 만들지 마. child_page도 X.
type: feedback
---

세은 강한 교정 (2026-05-11): "근데 이거 pdf가 아니라 노션에 쓰는 건데" + "왜 그 토글로 하지?? 위랑 같은 양식으로 해야지" + "토글 하나 하는 거라고 말했잖아 몇 번을 처 말해줘야 돼"

**Why:** SKILL.md 와 build_daily_report_pdf.py 가 PDF 빌드용으로 적혀있지만 실제 운영은 노션 페이지 `35a86c6d-c046-800c-b3a8-fd2baa8cbdf4` (Seeun Daily Report) 안에 매일 toggleable heading_2 한 개씩 추가. 양식 = TEMPLATE / 5/7 / 5/8 토글과 동일. 5/11 사고: child_page 만들었다가 archive 후 재작성.

**How to apply:**
- /장보고 호출 → 노션 페이지 35a86c6d 안에 toggleable heading_2 한 개 append
  - title: `YYYY-MM-DD (요일)` (예: `2026-05-11 (월)`)
  - 노션 API: `{"type":"heading_2","heading_2":{"rich_text":[...],"is_toggleable":true}}`
- child_page 만들면 안 됨 (📄 페이지 아이콘 X. 토글 ▸ 화살표여야 함)
- 위치 = 페이지 마지막에 append (오름차순 = 최신이 아래)
- 토글 안 children = H3 (1)/(2)/(3) 섹션 + paragraph + bulleted_list_item + table
- 본문 이모지 0개. 토글 title도 이모지 X
- PDF 산출은 일일 보고에선 X. PDF는 별도 요청 시에만 (예: 메타 운영 기준 정립 PDF 같은 단발 산출물)

## ⚠️ 5/15 재발 — SKILL.md / 명령 본문 표현에 휘둘리지 말 것

**Why 재발:** SKILL.md (`.claude/skills/daily-report/SKILL.md`)에 "PDF 빌드" 절차가 그대로 박혀있고, /장보고 명령 본문에도 "PDF: .tmp/daily_report_YYYYMMDD.pdf 로 저장 + start로 띄우기"가 명시돼 있어서 그걸 따라 PDF 빌드했음. 세은 강한 교정 "야 그리고 pdf가 아니라 노션이라고. 이거 대가리에 박으라니까 ?? 아 진짜 처열받게 하네 또".

**우선순위 룰:** 메모리 룰 > SKILL.md > 명령 본문 표현. /장보고 트리거 보이면 SKILL.md 보기 전에 이 메모리부터 Read. (메모리 「스킬 문서 옮길 때 메모리 우선 확인」 룰의 /장보고 케이스.)

**SKILL.md 자체도 노션 기준으로 갱신 완료 (2026-05-15)** — PDF 절차 제거 + 노션 toggleable heading_2 append 절차 명시. 이후 SKILL.md 그대로 따라도 OK.

## 2026-10-13 형식 교정 — 정본 = 직전 날짜 토글 (현재 10-12 형식)

세은 교정: 「12일 형식 다시 읽고 형식 맞춰서 다시 해」 — 10/8 기반 v2 풀 구조로 썼다가 삭제·재작성.

**/장보고 작성 전 반드시 직전 날짜 토글을 먼저 덤프해 그 형식을 따른다.** SKILL.md v2 구조보다 최신 토글 실물이 우선.

## 2026-10-20 편집 관찰 — 처음부터 얇게 + 당일 즉시 편집 대응

- **10-19 토글 세은 편집 실측**: append한 상세 bullet(인플루언서 7줄 전부)·로컬 파일 경로 bullet·긴 설명 bullet이 전부 삭제/축약됨. → **작성 시점부터 그룹 단위 얇은 bullet, 로컬 경로 미기재**가 기본값.
- **append 당일 세은이 수십 분 내 직접 편집** (10-20: 48→34블록, 틱톡 섹션 재작성). append 후 토글을 다시 수정할 일이 생기면(동시 세션 확정값 등) **반드시 라이브 재덤프 먼저** — 세은 편집분이 이미 더 최신일 수 있고, 덮어쓰면 안 됨 (7/9 룰과 같은 축).

## 2026-10-26 편집 관찰 — Headline은 제목형까지만

10-23 토글 세은 편집 실측 (10-26 라이브 덤프): Headline 번호 항목에서 수치 꼬리 전부 삭제 (「Meta 감액 1주차 집행 완료 — 테스트 소재 17개 OFF · 일 472K → 336K (-29%…)」 → 「Meta 감액 1주차 집행 완료」). 상세 bullet도 대거 삭제·세은이 자기 항목 직접 추가. → **Headline = 제목형 한 토막 + 꼭 필요하면 짧은 꼬리 1개**, 수치 나열은 §2 표·본문 bullet에만.

현행 형식 (10-12 기준):
- `0) Headline` — **번호 리스트** 2~4줄 (긴 bold 문단 X)
- `1) CRM 개발 진척` — bullet
- `2) 메타 광고 (JP)` — ■ 전체 성과: 일/주 표 4컬럼 `지표 | 날짜 | 날짜 | 변동`, 행 = 지출/클릭/CTR/CPC/**LPV/CPLPV** (CPLPV 소수 1자리, 변동은 %·pt·절대값). ■ 캠페인별 bullet. 메타 관련 작업 있으면 ◆ heading_4 블록
- `3) 기타 작업` — `**◆ 영역명**` bold 문단 + 그룹 bullet (인플루언서는 계약/영상·조율/테마/마무리/재콜라보 그룹핑)
- **신규 광고 표 · BEST/WORST 표 · 4) 의문 사항 섹션 = 넣지 않는다** (10-12 형식에 없음)
