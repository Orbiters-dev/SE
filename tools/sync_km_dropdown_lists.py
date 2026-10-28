"""KM SSOT_GR → JP Influencer Tracker _dropdown_lists 자동 동기화.

소스: Inhouse Content Tracker 'KM SSOT_GR' 탭 (헤더 2행 — C=Subject Code, D=Subject KO,
      F=Focus Code, G=Focus KO)
대상: JP Influencer Tracker '_dropdown_lists' 탭
      A: subjects ("S01 바디 소재")
      C: all_focus ("S01_F01 설명")
      F/G: map_subject / map_range (종속 드롭다운용 subject→focus 열 범위)
      H~: subject별 focus 열 (row1 = subject code)
      E(hooks_visual)는 별도 소스(Hook Type) — 건드리지 않음.

2026-07-27 세은 지시: KM SSOT_GR 항목 갱신 시 자동 반영. Task Scheduler 매일 09:35.

Usage:
    python tools/sync_km_dropdown_lists.py            # 실제 반영
    python tools/sync_km_dropdown_lists.py --dry-run  # 변경 내용만 출력
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sheets_utils import get_sheets_client, safe_range  # noqa: E402

SRC_ID = "1HnouC4gMRVTcGwGeInJlGJl_W7eNgI_4m63ZDSxzfZY"
SRC_GID = 44578416          # 'KM SSOT_GR'
DST_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
DST_TAB = "_dropdown_lists"

# 오동기 가드 — 소스가 이보다 작으면 (읽기 실패/탭 훼손) 대상 시트를 지우지 않는다
MIN_SUBJECTS = 8
MIN_FOCUS = 50

SUBJECT_COL_START = 8       # H열부터 subject별 focus 열


def col_letter(idx):
    """1-based index → column letter."""
    out = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def read_source(gc):
    sh = gc.open_by_key(SRC_ID)
    ws = next(w for w in sh.worksheets() if w.id == SRC_GID)
    rows = ws.get_values("B2:G")
    if not rows:
        raise RuntimeError("KM SSOT_GR 탭이 비어 있음 — 동기화 중단 (대상 시트 보존)")
    header = rows[0]
    if len(header) < 6 or "Code" not in header[1] or "Focus" not in header[5]:
        raise RuntimeError(f"KM SSOT_GR 헤더 구조 변경 감지 — 확인 필요: {header}")

    subjects = {}                 # code -> KO name (first seen)
    focus = []                    # (focus_code, focus_ko)
    seen_focus = set()
    for r in rows[1:]:
        scode = (r[1] if len(r) > 1 else "").strip()
        sko = (r[2] if len(r) > 2 else "").strip()
        fcode = (r[4] if len(r) > 4 else "").strip()
        fko = (r[5] if len(r) > 5 else "").strip()
        if scode and sko and re.fullmatch(r"S\d{2}", scode) and scode not in subjects:
            subjects[scode] = sko
        if fcode and fko and re.fullmatch(r"S\d{2}_F\d{2,}", fcode) and fcode not in seen_focus:
            seen_focus.add(fcode)
            focus.append((fcode, fko))
    return subjects, focus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gc = get_sheets_client()
    subjects, focus = read_source(gc)
    print(f"[src] subjects={len(subjects)} focus={len(focus)}")
    if len(subjects) < MIN_SUBJECTS or len(focus) < MIN_FOCUS:
        raise RuntimeError(
            f"소스 규모 가드 미달 (subjects {len(subjects)}<{MIN_SUBJECTS} or "
            f"focus {len(focus)}<{MIN_FOCUS}) — 동기화 중단, 대상 시트 보존")

    codes = sorted(subjects)
    by_subject = {c: [] for c in codes}
    for fcode, fko in focus:
        prefix = fcode.split("_")[0]
        if prefix in by_subject:
            by_subject[prefix].append(f"{fcode} {fko}")
        else:
            print(f"[warn] subject 미등록 focus (all_focus 에는 포함됨): {fcode}")

    sh = gc.open_by_key(DST_ID)
    ws = sh.worksheet(DST_TAB)
    old_rows, old_cols = ws.row_count, ws.col_count

    subjects_list = [f"{c} {subjects[c]}" for c in codes]
    all_focus_list = [f"{fc} {fk}" for fc, fk in focus]
    need_rows = max(len(all_focus_list) + 1, max(len(v) for v in by_subject.values()) + 1, old_rows)
    need_cols = SUBJECT_COL_START - 1 + len(codes)
    if need_rows > old_rows or need_cols > old_cols:
        ws.resize(rows=max(need_rows, old_rows), cols=max(need_cols, old_cols))

    data = []

    def put(col_idx, start_row, values):
        letter = col_letter(col_idx)
        end_row = start_row + len(values) - 1
        data.append({
            "range": safe_range(DST_TAB, f"{letter}{start_row}:{letter}{end_row}"),
            "values": [[v] for v in values],
        })

    # A: subjects / C: all_focus (row1 헤더 유지, 2행부터)
    pad_a = [""] * max(0, old_rows - 1 - len(subjects_list))
    pad_c = [""] * max(0, old_rows - 1 - len(all_focus_list))
    put(1, 2, subjects_list + pad_a)
    put(3, 2, all_focus_list + pad_c)

    # F/G: map_subject / map_range
    map_rows = []
    for i, c in enumerate(codes):
        letter = col_letter(SUBJECT_COL_START + i)
        n = len(by_subject[c])
        map_rows.append((c, f"'{DST_TAB}'!{letter}2:{letter}{n + 1}"))
    pad_m = [""] * max(0, old_rows - 1 - len(map_rows))
    put(6, 2, [m[0] for m in map_rows] + pad_m)
    put(7, 2, [m[1] for m in map_rows] + pad_m)

    # H~: subject별 열 (row1 = code)
    for i, c in enumerate(codes):
        vals = by_subject[c]
        pad = [""] * max(0, old_rows - 1 - len(vals))
        put(SUBJECT_COL_START + i, 1, [c] + vals + pad)

    # subject 수 축소 시 잔존 열 클리어 — 기존 row1 이 S## 인 열만 (다른 용도 열 보호)
    old_row1 = ws.get_values(f"A1:{col_letter(old_cols)}1")
    old_row1 = old_row1[0] if old_row1 else []
    for idx in range(SUBJECT_COL_START + len(codes), len(old_row1) + 1):
        head = old_row1[idx - 1].strip() if idx <= len(old_row1) else ""
        if re.fullmatch(r"S\d{2}", head):
            put(idx, 1, [""] * old_rows)
            print(f"[clear] stale subject col {col_letter(idx)} ({head})")

    if args.dry_run:
        print(f"[dry-run] subjects {len(subjects_list)} / all_focus {len(all_focus_list)}")
        for c in codes:
            print(f"  {c}: {len(by_subject[c])} focus")
        print(f"  map_range 예: {map_rows[0]} ... {map_rows[-1]}")
        return

    ws.spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": data})
    print(f"[OK] synced — subjects {len(subjects_list)} / all_focus {len(all_focus_list)} / "
          f"subject cols {len(codes)} (H~{col_letter(SUBJECT_COL_START + len(codes) - 1)})")

    # 재조회 검증 — 불일치면 비정상 종료 (스케줄러가 실패로 기록)
    ws2 = gc.open_by_key(DST_ID).worksheet(DST_TAB)
    a = [v[0] for v in ws2.get_values("A2:A1000") if v and v[0]]
    c_vals = [v[0] for v in ws2.get_values("C2:C1000") if v and v[0]]
    ok = a == subjects_list and c_vals == all_focus_list
    print(f"[verify] A(subjects)={len(a)} C(all_focus)={len(c_vals)} match={ok}")
    if not ok:
        raise SystemExit("[FAIL] 재조회 검증 불일치 — 시트 상태 확인 필요")


if __name__ == "__main__":
    main()
