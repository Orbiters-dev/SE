---
type: moc
domain: ops
agents: [제갈량, resource-finder]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [ops, strategy, cso, wat]
---

# MOC_운영

## 에이전트
- **제갈량 (CSO)** — SCAN→THINK→PLAN→EXECUTE→VERIFY→REPORT
- **resource-finder** — 파일/이메일 검색 (Z:, SynologyDrive, Gmail)

## WAT Framework
- **Workflows:** `workflows/*.md` — SOPs
- **Agents:** Claude 인스턴스 (의사결정)
- **Tools:** `tools/*.py` — 결정론적 실행

## 멀티 에디터 분배
| 에디터 | 환경 | 담당 |
|--------|------|------|
| WJ Test1 | 로컬 Claude Code | 메인 개발, 디버깅, 배포 |
| GitHub Codex | 클라우드 Agent | PR 기반, 대규모 리팩토링 |
| 바바 | 별도 Claude | 독립 리서치, 문서 |

## 제갈량 프레임워크
```
SCAN → THINK → PLAN → EXECUTE → VERIFY → REPORT
```
세션 리포트: `Shared/ONZ Creator Collab/제갈량/`

## Architecture
- [[mistakes]] — 에이전트별 실수 기록 (M-001~M-014)
