"""WL Code & Payment 탭 I(subject)/J(focus) 종속 드롭다운 설치.

2026-07-27 세은 지시: I=S(subject), J=F(focus) — S 선택 시 해당 S 의 F 만 노출.

구조:
  I4:I1000 검증 = '_dropdown_lists'!A2:A100 (subjects — sync_km_dropdown_lists 가 매일 갱신,
            빈 셀은 드롭다운에서 무시되므로 open-range 로 미래 증가 자동 수용)
  숨김 헬퍼 탭 '_dep_focus_wl' 행 r 의 A셀: =TRANSPOSE(FILTER(all_focus, S코드 = I{r} 의 S코드))
            → 가로로 spill (A셀 하나만 수식, 나머지 열은 spill 결과).
            INDEX(...,ROW()) 사용 — WL 탭 행 삽입/삭제에도 행 번호 기준 정렬 유지.
  J{r} 검증 = '_dep_focus_wl'!A{r}:AD{r} (자기 행 헬퍼 범위 → 종속)

한계:
  - subject 당 focus 가 HELPER_COLS(30) 를 넘으면 초과분은 드롭다운에 안 뜸 (현행 최다 23).
  - WL 탭 중간 행 삽입 시 새 행 J 검증은 위 행 것을 상속해 한 줄 어긋날 수 있음 —
    이 스크립트 재실행으로 재정렬 (멱등).

Usage: python tools/setup_wl_payment_km_dropdowns.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sheets_utils import get_sheets_client  # noqa: E402
from sync_km_dropdown_lists import col_letter  # noqa: E402

SHEET_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
WL_TAB = "WL Code & Payment"
DD_TAB = "_dropdown_lists"
HELPER_TAB = "_dep_focus_wl"
DATA_START = 4          # WL 탭 데이터 시작 행 (헤더 3행)
DATA_END = 1000
HELPER_COLS = 30        # subject 당 focus 최대 수용 (현행 최다 S01=23)
COL_I, COL_J = 8, 9     # 0-based column index


def main():
    gc = get_sheets_client()
    sh = gc.open_by_key(SHEET_ID)
    wl = sh.worksheet(WL_TAB)
    end_col = col_letter(HELPER_COLS)   # 30 -> AD

    # 1) 헬퍼 탭 확보 (없으면 생성 + 숨김)
    try:
        helper = sh.worksheet(HELPER_TAB)
        print(f"[helper] exists gid={helper.id}")
    except Exception:
        helper = sh.add_worksheet(HELPER_TAB, rows=DATA_END, cols=HELPER_COLS)
        sh.batch_update({"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": helper.id, "hidden": True},
                "fields": "hidden",
            }}]})
        print(f"[helper] created+hidden gid={helper.id}")

    # 2) 헬퍼 수식 — A셀 하나가 해당 행에서 가로로 spill.
    #    조건은 배열(LEFT(C2:C,3)) vs 스칼라(LEFT(INDEX..,3)) 비교 하나만 — FILTER 에
    #    스칼라 조건을 추가하면 range 불일치 오류가 나므로 금지.
    formula = (
        "=IFERROR(TRANSPOSE(FILTER("
        f"'{DD_TAB}'!$C$2:$C,"
        f"LEFT('{DD_TAB}'!$C$2:$C,3)=LEFT(INDEX('{WL_TAB}'!$I:$I,ROW()),3)"
        ")),)"
    )
    helper.spreadsheet.values_batch_update({
        "valueInputOption": "USER_ENTERED",
        "data": [{
            "range": f"'{HELPER_TAB}'!A{DATA_START}:A{DATA_END}",
            "values": [[formula]] * (DATA_END - DATA_START + 1),
        }],
    })
    print(f"[helper] formulas set A{DATA_START}:A{DATA_END}")

    # 3) 검증 규칙 설치 (기존 오복사 검증 Kazuki/Seeun 은 덮어써서 제거됨)
    def dv_request(start_row, end_row, col, range_formula):
        return {"setDataValidation": {
            "range": {"sheetId": wl.id,
                      "startRowIndex": start_row - 1, "endRowIndex": end_row,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {
                "condition": {"type": "ONE_OF_RANGE",
                              "values": [{"userEnteredValue": range_formula}]},
                "showCustomUi": True, "strict": False,
            },
        }}

    requests = [dv_request(DATA_START, DATA_END, COL_I, f"='{DD_TAB}'!$A$2:$A$100")]
    for r in range(DATA_START, DATA_END + 1):
        requests.append(
            dv_request(r, r, COL_J, f"='{HELPER_TAB}'!$A${r}:${end_col}${r}"))
    sh.batch_update({"requests": requests})
    print(f"[dv] I{DATA_START}:I{DATA_END} subjects 1건 + J 행별 종속 {DATA_END - DATA_START + 1}건 설치")


if __name__ == "__main__":
    main()
