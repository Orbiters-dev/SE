---
name: 스킬 문서 옮길 때 메모리 우선 확인
description: SKILL.md를 다른 곳(n8n sticky, 워크플로우 SOP)에 옮길 때 무조건 memory/feedback_<skill>_* 먼저 Read. SKILL.md보다 메모리가 더 최신.
type: feedback
---

스킬/에이전트 문서를 새 위치(n8n sticky note, 워크플로우 SOP, 보고용 문서 등)에 옮기거나 요약할 때 **반드시 메모리 먼저 확인**.

**Why:** 2026-05-12 사고. `.claude/skills/daily-report/SKILL.md` 가 PDF 중심으로 적혀있어 그걸 그대로 n8n Operations Hub sticky로 옮김 → 강한 교정. 실제 운영 룰은 `memory/feedback_daily_report_notion_toggle.md`(2026-05-11)에 "PDF X / 노션 toggleable heading_2 append"로 이미 박혀있었음. 메모리가 SKILL.md보다 최신.

**How to apply:**
1. 대상 스킬·에이전트 이름으로 `ls memory/ | grep -i <skill>` 또는 `grep` 검색
2. 매칭되는 `feedback_*` / `project_*` 파일 전건 Read
3. SKILL.md 와 메모리가 충돌 → **메모리 우선**, SKILL.md는 정정 대상으로 표시
4. 특히 산출물 형태(PDF/노션/Sheets/Teams), 호칭, 채널, 톤은 메모리에 가장 최근 feedback이 들어있을 확률 높음

**대상 작업류 (이 룰 적용 필수):**
- n8n sticky note 작성·갱신
- 외부 보고용 문서 (PDF/노션) 작성
- 워크플로우 SOP 작성
- 한 에이전트의 룰을 다른 에이전트가 참조할 때
