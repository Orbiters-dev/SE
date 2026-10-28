---
name: reference_km_ssot_edit
description: KM SSOT_GR 시트 편집 SOP + append 컬럼밀림 함정 (2026-09-22 GR_S02_F18 추가 시 실측)
metadata:
  type: reference
---

# KM SSOT_GR 편집 SOP + 함정

정본: Inhouse Content Tracker, 시트 `1HnouC4gMRVTcGwGeInJlGJl_W7eNgI_4m63ZDSxzfZY` / 탭 `KM SSOT_GR` gid **44578416**. 코드 체계 GR_S##_F##.

## 컬럼 레이아웃 (A열은 통째로 빈칸)
`A=(빈칸)` `B=Date Added` `C=Code(S##)` `D=Subject(KO)` `E=Subject(EN)` `F=Focus Code(GR_S##_F##)` `G=Focus(KO)` `H=Focus(EN)` `I=해당 제품` `J~P=[VID]/[IMG] 테스트·ROAS` `Q=Notes`

## ⚠ 함정: gspread `append_row` 한 칸 밀림
A열이 전부 비어 있어 gspread가 데이터 테이블 시작을 **B열**로 오인 → `append_row([...])` 하면 값이 A가 아닌 B부터 채워져 **전 컬럼 우측 1칸 밀림**(Date가 C로 감).

## 안전 편집 순서
1. 편집 전 `get_all_values()` 백업 → `.tmp/km_backup/*.json`.
2. 중복 방지: 새 Focus Code 이미 있는지 flat 검색.
3. 행 추가 후 **반드시 셀 위치 검증** — 정상행(예: 직전 F17)과 `(컬럼레터, 값)` 대조.
4. 밀렸으면 `ws.update(range_name="A{n}:R{n}", values=[[...]], value_input_option="USER_ENTERED")` 로 **절대좌표 덮어쓰기** (A는 빈 "", B부터 실값, 잔재 셀까지 클리어).
5. 신규 코드 = 해당 S## 최대 F 번호 +1 (append는 하단, 시트는 Date Added 순).

## 연동
매일 09:35 `tools/sync_km_dropdown_lists.py` (Task Scheduler)가 `KM SSOT_GR` → JP Influencer Tracker `_dropdown_lists` 동기화 → 편집 익일 태깅 드롭다운 반영. 자동 태깅 정답 코드 목록도 이 탭 기준(`tools/tag_jp_content.py`). [[feedback-canonical-km-source-not-improvise]]
