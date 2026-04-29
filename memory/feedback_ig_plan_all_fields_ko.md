---
name: IG 기획안 모든 필드 한국어 병기 필수
description: 캡션만이 아니라 소제목·대제목·비주얼 방향·주제 등 일본어 필드 전부 한국어 번역 병기. 세은 반복 지시.
type: feedback
---

IG 주간 기획안 Excel에서 **일본어로 작성된 모든 필드는 반드시 한국어 번역 병기**.

**대상 필드:**
- 소제목(JP) → 소제목(KO)
- 대제목(JP) → 대제목(KO)
- 주제(JP) → 주제(KO) (기존)
- 비주얼 방향(JP) → 비주얼 방향(KO)
- 캡션(JP) → 캡션(KO) (기존)
- 해시태그 → 그대로 (번역 불필요)

**Why:** 2026-04-24 세은 피드백 "캡션 말고도 다 한국어 번역 넣으라니까?? 항상". 현재 tool은 주제/캡션만 KO 병기.

**How to apply:**
- `tools/plan_weekly_content.py` 프롬프트의 출력 요구사항에 `subtitle_ko`, `title_ko`, `visual_direction_ko` 추가
- Excel writer 컬럼 확장
- 다른 IG 기획 관련 산출물도 마찬가지 — 일본어 필드는 무조건 한국어 병기
