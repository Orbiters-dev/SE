---
name: feedback-no-inventory-dump-when-task-concrete
description: 구체 작업 + 도구 경로 이미 앎(SKILL 문서화) → .tmp 인벤토리 스캔 생략, 바로 데이터 축 실행
metadata:
  type: feedback
---

구체적 작업 지시를 받았고 필요한 도구·데이터 경로가 이미 SKILL/메모리에 문서화돼 있으면, `ls`/`find`/`grep`로 `.tmp` 도구 인벤토리를 재카탈로그하지 말고 **바로 답을 내는 데이터 축을 실행**한다.

**Why:** 2026-09-04 삐삐 슈퍼세일 RPP 키워드 확장 — 작업은 명확(US 대시보드 승자 + JP 유입 승자 → 세은 슈퍼세일 세팅분 제외 → 미등록 리스팅)했고 도구 경로(Data Keeper, `inflow_keywords_monthly.json`, RPP 콘솔 `/rpp/api/keyword`)도 SKILL에 다 있었는데, `.tmp/ppc_setup_0810`·`kw_recheck` 인벤토리 스캔을 두 라운드 돌림 → 「개소리여 다시 진행해」 강한 교정.

**How to apply:** 착수 즉시 (1) 답을 내는 데이터 축을 3개 이내로 특정 → (2) 독립 축은 병렬 subagent, 무거운 축(콘솔 로그인 등)은 내가 직접 → (3) 인벤토리가 진짜 필요하면 딱 그 축에 필요한 파일 하나만 확인. SKILL 「도구·데이터」 표에 경로 있으면 재탐색 불요. [[feedback-surface-interim-during-slow-ops]]의 "좁은범위 즉답" 원칙과 짝.
