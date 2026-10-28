---
name: 오답노트 2026-05-07c (보고서 작성 세션)
description: 일일 보고 PDF 만들면서 받은 강한 교정 6건 — CRM 정의 / 이모지 / SKU 단순화 / 메타 권장액션 X / 가독성 / 자체 조사 못해서 단정.
type: project
---

# 2026-05-07c — 보고서 작성 교정 6건

세은 외부용 일일 보고 PDF 만들면서 받은 교정 누적. 모두 `daily-report` 스킬과 `reference_sku_simplified_naming.md` 메모리에 박음.

## 1. "CRM 작업이 아닌 개인적인 agent 작업 관련 내용은 치워"

GH Actions 정상화 / 트위터 부대 / einstein / harness / commenter 등 자동 agent 코드 push를 "1) CRM 개발 진척" 섹션에 적었음. 세은 강한 교정.

**원칙**: CRM 개발 = JP CRM / US CRM / pipeline-crm / WONGI / orbitools / intelligence_next 코드 작업만. 자동 agent / 인프라 / 마존이 / 메타몽 진단은 다른 카테고리.

## 2. "없긴 왜 없어 미쳤나 하루종일 crm 개발했구만"

memory/session_*.md 만 빠르게 보고 "오늘 CRM 개발 0건" 단정. 트랜스크립트(`C:\Users\orbit\.claude\projects\...\*.jsonl`)는 안 뒤짐. 세은이 "제갈량이랑 작업한 거 찾아"라고 명시 후에야 트랜스크립트 분석 → JP CRM 409 Conflict 진단 + WONGI PR #570 작성 + orbitools-code-edit MCP 등록 발견.

**원칙**: 단일 소스(메모리·git log) 0건이라고 단정 X. 트랜스크립트까지 교차 검증. CLAUDE.md "검증 한 번 = 도구 한 개로 끝나면 안 됨" 룰 위반.

## 3. "쓰잘 데 없는 이모지는 치워"

PDF 섹션 헤더와 표 라벨에 📊📈🥇⚠️🔴🟢🧠✅ 잔뜩 박음. 세은 "쓰잘 데 없는 이모지는 치워" 강한 교정.

**원칙**: 외부용 보고서·PDF는 이모지 0개. 비즈니스 톤. CLAUDE.md 글로벌 룰("Only use emojis if the user explicitly requests it")과도 일치.

## 4. SKU 표기 — "stainless / ppsu / fliptop 3개로. 원터치는 fliptop"

처음에 "ステンレスストローマグ 200ml オリーブピスタチオ" 식으로 일본어+색상+용량 다 표기 → 한글 변환 → 그래도 길음. 세은 "stainless, ppsu, fliptop 이 세가지로. 색상 및 용량은 안 적어도 됨". 그 후 원터치 빨대컵을 ppsu로 매핑 → 또 교정 "원터치 머그 있었잖아. 원터치는 fliptop으로 표기하라니까".

**원칙**:
- 보고서 SKU 표기 = `stainless` / `ppsu` / `fliptop` 3종만
- 색상·용량 X
- **원터치(ワンタッチ式) = fliptop** (ppsu 아님)

→ `reference_sku_simplified_naming.md` 신규 + MEMORY.md 인덱스 박음.

## 5. "메타 광고 권장 액션이랑 한 줄 요약은 치워"

받은 자동 메타 분석 보고에 "❌ WORST 광고 즉시 정지", "✅ BEST 광고 변형 소재 제작", "✅ 한 줄 요약" 같은 액션 권고가 있어서 PDF에 그대로 옮김. 세은이 "치워" 교정.

**원칙**: 메타 광고 보고서에 권장 액션·한 줄 요약 X. 데이터(전체 성과·캠페인·BEST/WORST·신규·공부 중)만.

## 6. BEST/WORST — "CTR 기준이 아니라 CPC랑 CTR 모두 분석해서"

처음에 BEST/WORST를 CTR 단독 정렬로 매김. 세은 "cpc랑 ctr 모두 분석해서 해 주면 좋겠는데".

**원칙**: BEST/WORST는 CTR + CPC 둘 다 종합 (지출 1,000 KRW 이상 광고만, 학습 단계 제외).

## 부수 교정 (작은 것)

- "줄글로 각 10줄 이내" → 다음 턴에 블랙닷 다시 요구. **블랙닷이 디폴트**
- "내용 간 간격이 너무 좁아" → H1 spaceBefore 22 / H2 spaceBefore 16 / BULLET spaceAfter 7
- "체크 표시는 지우고 이미지만" → 캘린더 강조는 명시 요청 있을 때만
- "마지막에 크게 쓰면 어떡해 (CRM KPI 분리)" → 같은 카테고리 항목은 H2 새로 X, 부수 작업 하위 블랙닷
- "원기님께 부탁한 것 같은 레벨로 평탄화" → "이전 5/4 부탁 2건" 헤더 빼고 블랙닷만
- "/장보고 이렇게 저장해" → slash command 한글 파일명 OK

## 학습 산출물

- `.claude/skills/daily-report/SKILL.md` 신규 — 절차·룰·자주 받은 교정 박음
- `.claude/commands/장보고.md` 신규 — slash command
- `tools/build_daily_report_pdf.py` 신규 — 영구 템플릿
- `memory/reference_sku_simplified_naming.md` 신규
- `CLAUDE.md` anchor 갱신
- `MEMORY.md` SKU 단순 표기 + 이 오답노트 추가
