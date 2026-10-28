---
name: orbitools-code-edit MCP cap 영역 매핑 (SE 보유 vs 부재 vs unknown)
description: WONGI 리포 코드 작업 시 SE가 PR 만들 수 있는 영역 매핑. datakeeper 영역은 registry 미등록 = 우회 또는 cap 신규 등록 필요. dashboard:backend.migrations 별도 cap.
type: reference
---

# orbitools-code-edit MCP cap 영역 (2026-05-26 발견)

## SE 보유 cap

- `code:edit:dashboard:backend.models` — `apps/orbitools/django_phases/models.py` 등 onzenna 영역 model
- `code:edit:dashboard:backend.services` — onzenna 서비스 레이어
- `code:edit:dashboard:backend.us_crm`
- `code:edit:dashboard:crm.*` — crm/services 등
- `code:edit:dashboard:intelligence.*` — `apps/orbitools/intelligence_next/**` 프론트엔드
- `code:edit:dashboard:shared`

## 발견된 별도 cap (SE 미보유)

- `code:edit:dashboard:backend.migrations` — `apps/orbitools/django_phases/migrations/*.py` migration 파일. SE에 없음 → **model만 추가 X (schema 변경 안 됨)**. `request_cap` 으로 요청 가능 (5/26 #5 발송).

## Registry 미등록 (unknown caps)

- `code:edit:datakeeper:*` — `apps/datakeeper/**` 영역 전체. registry 자체에 미등록 → `request_cap` 시 `unknown caps` error. 운영자(원기)가 cap 신규 등록부터 해야 함.

## 우회 패턴 — datakeeper 영역 변경 필요할 때

1. SE 가 datakeeper 컬럼 추가 X
2. 우회: `apps/orbitools/django_phases/models.py` 에 1:1 캐시 model 신규 (creator_id BigInteger anchor, cross-app FK 없음)
3. 후일 datakeeper cap 받으면 본체 합치고 우회 model drop

예시: `JpCreatorExtraction` (2026-05-26) — datakeeper.CreatorCRMProfile 컬럼 추가 대신 orbitools 영역에 1:1 캐시.

## 패치 형식 주의 (truncated_hunk 자주 발생)

- unified diff hunk header line count 엄격 매칭. `@@ -<from>,<n> +<from>,<m> @@` 의 n/m 정확해야.
- 새 파일은 `--- /dev/null` + `+++ b/path` + `@@ -0,0 +1,<line_count> @@` — line_count 정확히.
- 자주 실수: 코멘트/공백 줄 카운트 누락.

## 메시지 발송 path

`request_cap` 자체가 운영자 dashboard inbox 알림 자동 발송. Teams 백업 메시지는 운영자가 inbox 자주 안 보면 보완용. 외부 발송이라 세은 「발송해」 후에만.
