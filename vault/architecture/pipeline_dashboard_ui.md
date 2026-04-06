---
type: architecture
domain: pipeline
agents: [pipeliner, appster]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [dashboard, ui, pipeline, ux]
moc: "[[MOC_파이프라인]]"
---

# pipeline_dashboard_ui

Pipeline Dashboard UI 아키텍처.

## 주요 UI 컴포넌트
- **Owner tabs** — 담당자별 탭 분리
- **Checkboxes** — 배치 선택
- **Draft preview** — 이메일 초안 미리보기
- **Batch actions** — Archive, 상태 변경
- **PipelineConversation** — 대화 이력 뷰

## UX 규칙
- Transcript: 실제 대화만 표시 (caption 제외)
- Auto-load: email history + transcript + content views
- is_auto_sent 배지 표시 (AUTO 배지)
- Draft Ready: discovered.syncly 소스 숨김
