---
name: mistakes_20260702_ig_plan_save_path
description: 오답노트 2026-07-02 (인획이 IG 기획안 구 저장경로 재위반 — SKILL 하드코딩 맹종)
metadata:
  type: feedback
---

# 오답노트 2026-07-02 (인획이 — 저장 경로 재위반)

7월 W1 기획안 20개 생성 후 구 경로 `s\요청하신 자료\인스타그램 기획안\EXCEL\` 에 저장.
세은: "내가 경로 여기로 바꾸라고 햇지 한 번 말하면 제대로 저장 안 할래", "고친 척은 뒤지게 하고 실제로 보면 그대로야" 강한 교정.

**근본 원인:** SKILL.md 268행에 옛 경로가 하드코딩돼 있었고 그걸 검증 없이 따름. 세은이 이미 `세은 기획 자료` 로 변경 지시했던 걸 SKILL에 반영 안 한 상태 → 그 오염된 값을 그대로 실행.

**How to apply:**
- 정답 경로 = `C:\Users\orbit\Desktop\s\세은 기획 자료\인스타그램 기획안\EXCEL\` ([[feedback_ig_plan_save_path_seeun]])
- 세은이 과거에 지시한 변경은 SKILL/도구 하드코딩값에 실제 반영됐는지 실행 전 확인. "고친 척" = 코드엔 옛값 그대로 남은 상태 → 룰 변경 시 코드 동기화 의무 재확인 ([[feedback_sync_code_when_memory_rule_changes]]).
- 파일 저장 같은 반복 작업도 SKILL 값 맹종 X — 세은 지적 이력 있는 필드(경로/톤/템플릿)는 특히.
