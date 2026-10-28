---
name: Notion table column 추가는 통째 교체 (table_width 변경 불가)
description: Notion API는 기존 table block의 width 수정 X. 컬럼 추가·삭제 시 새 table 생성 + after로 위치 지정 + 기존 archive.
type: reference
---

5/21 일일 보고 메타 표 5개 「가이드라인」 빈 칸 추가 작업 중 정립.

**Why:** Notion API의 PATCH `/v1/blocks/{table_id}` 는 `table_width` 필드를 mutate 못함. 컬럼 추가하려면 통째 교체 필요.

**How to apply:**
1. 기존 table의 rows 조회: `GET /v1/blocks/{table_id}/children` (각 row = table_row block with `cells` array)
2. 새 rows 빌드 — header row에 새 컬럼명 추가, 데이터 row에는 빈 `[]` cell 추가
3. 새 table block 생성 — `table_width: 기존+1`
4. `PATCH /v1/blocks/{parent_id}/children` with `after: 기존_table_직전_블록_id` (위치 보존)
5. `DELETE /v1/blocks/{기존_table_id}` (archive)

**주의:**
- `after` 파라미터 없으면 페이지/토글 끝에 붙음 → 순서 깨짐
- 여러 표 동시 처리 시 archive 전에 새 table id 받아두면 검증 가능
- table block은 `has_column_header`, `has_row_header` 필드 같이 지정

**관련 케이스:**
- 5/21 메타 표 5개 width+1 작업 — `.tmp/notion_521_update.py` 패턴
