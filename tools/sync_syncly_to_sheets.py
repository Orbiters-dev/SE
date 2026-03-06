"""
Syncly -> Google Sheets D+60 Tracker v2
========================================
v2 변경사항:
  - D+60 Tracker: Post Date 옆에 D+ Days(수식), Curr Cmt/Like/View(수식) 4열 추가
  - 기존 시트 자동 마이그레이션 (v1→v2: 열 4개 삽입)
  - 신규 탭: Influencer Tracker (인플루언서별 날짜 열, D+60 Tracker로 하이퍼링크)

사용법:
  python tools/sync_syncly_to_sheets.py
  python tools/sync_syncly_to_sheets.py --csv "Data Storage/syncly/2026-02-27_....csv"
  python tools/sync_syncly_to_sheets.py --sheet-id "1abc..."

D+60 Tracker 구조 (v2):
  Row 1: 그룹 헤더  | Post Info (merged) | Auto (merged) | D+0 | D+1 | ...
  Row 2: 서브 헤더  | Post ID | URL | Username | Post Date | D+ Days | Curr Cmt | Curr Like | Curr View | Cmt | Like | View | ...
  Row 3+: 데이터

Influencer Tracker 구조:
  Row 1: Username | Nickname | Followers | First Seen | Total Posts | 2026-01-01 | 2026-01-02 | ...
  Row 2+: 인플루언서별 데이터 (날짜 셀 클릭 → D+60 Tracker 해당 행으로 이동)
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

SYNCLY_DIR = PROJECT_ROOT / "Data Storage" / "syncly"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

MASTER_SHEET = "Posts Master"
TRACKER_SHEET = "D+60 Tracker"
INF_SHEET = "Influencer Tracker"

# ──── D+60 Tracker Config (v2) ────
# v1: FIXED_COLS = 4 (Post ID, URL, Username, Post Date)
# v2: FIXED_COLS = 8 (+D+ Days, Curr Cmt, Curr Like, Curr View)
FIXED_COLS = 8
METRICS_PER_DAY = 3       # Comments, Likes, Views
MAX_DAYS = 61             # D+0 ~ D+60
TOTAL_TRACKER_COLS = FIXED_COLS + MAX_DAYS * METRICS_PER_DAY  # 8 + 183 = 191

# D+0 starts at column index 8 (0-based) = column I (1-based)
D0_COL_LETTER = "I"

METRIC_KEYS = [
    "extraction.engagement.comment",
    "extraction.engagement.like",
    "extraction.engagement.view",
]
METRIC_LABELS = ["Comment", "Like", "View"]

# ──── Influencer Tracker Config ────
INF_FIXED_COLS = 5
INF_FIXED_HEADERS = ["Username", "Nickname", "Followers", "First Seen", "Total Posts"]

# ──── Master Config ────
MASTER_COLS = [
    "source.id", "source.url", "source.platform",
    "author.username", "author.nickname", "author.follower_count",
    "extraction.content", "extraction.hashtags",
    "analyzation.theme", "analyzation.brand", "analyzation.product",
    "analyzation.sentiment_theme_ brand_product",
    "date",
]
MASTER_HEADERS = [
    "Post ID", "URL", "Platform",
    "Username", "Nickname", "Followers",
    "Content", "Hashtags",
    "Theme", "Brand", "Product",
    "Sentiment",
    "Post Date",
]


# ──── Helpers ────

def _borders():
    border = {"style": "SOLID", "color": {"red": 0.78, "green": 0.78, "blue": 0.78}}
    return {"top": border, "bottom": border, "left": border, "right": border}


def get_credentials():
    from env_loader import load_env
    load_env()
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)
    return Credentials.from_service_account_file(sa_path, scopes=SCOPES)


def open_sheet(gc, sheet_id=None):
    if sheet_id:
        return gc.open_by_key(sheet_id)
    id_file = SYNCLY_DIR / ".sheet_id"
    if id_file.exists():
        stored_id = id_file.read_text().strip()
        if stored_id:
            return gc.open_by_key(stored_id)
    print("[ERROR] No sheet ID. Provide --sheet-id or create Data Storage/syncly/.sheet_id")
    sys.exit(1)


def col_letter(n):
    """0-indexed 열 번호 → 알파벳 (A, B, ..., Z, AA, ...)"""
    result = ""
    while n >= 0:
        result = chr(n % 26 + ord("A")) + result
        n = n // 26 - 1
    return result


def parse_csv(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_latest_csv():
    csvs = sorted(SYNCLY_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    csvs = [c for c in csvs if "debug" not in c.name]
    return csvs[0] if csvs else None


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def safe_int(val):
    if not val or val in ("N/A", "TBU", ""):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def safe_float(val):
    if not val or val in ("N/A", "TBU", ""):
        return 0.0
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return 0.0


def serial_to_date(val):
    """Sheets/Excel 날짜 시리얼 번호(예: 46044)를 'YYYY-MM-DD' 문자열로 변환."""
    try:
        n = int(str(val).strip())
        if 40000 <= n <= 60000:
            from datetime import date, timedelta
            return (date(1899, 12, 30) + timedelta(days=n)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return str(val)


def tracker_formulas(sheet_row):
    """
    D+60 Tracker v2에서 특정 행에 들어갈 수식 4개 반환.
      col E: D+ Days   - 오늘 기준 포스팅 후 며칠 지났는지 (자동 갱신)
      col F: Curr Cmt  - D+ Days 열 기준 해당 날짜의 댓글 수 (OFFSET)
      col G: Curr Like - 동일
      col H: Curr View - 동일
    D+0 데이터는 col I(index 8)부터 시작.
    OFFSET($I{row}, 0, MIN(E,60)*3+n) 으로 해당 D+N 메트릭 참조.
    """
    r = sheet_row
    days_f  = f'=IF(D{r}="","",INT(TODAY()-D{r}))'
    cmt_f   = f'=IF(OR(E{r}="",E{r}<0),"",OFFSET(${D0_COL_LETTER}{r},0,MIN(E{r},60)*3))'
    like_f  = f'=IF(OR(E{r}="",E{r}<0),"",OFFSET(${D0_COL_LETTER}{r},0,MIN(E{r},60)*3+1))'
    view_f  = f'=IF(OR(E{r}="",E{r}<0),"",OFFSET(${D0_COL_LETTER}{r},0,MIN(E{r},60)*3+2))'
    return [days_f, cmt_f, like_f, view_f]


# ──── Tracker Headers ────

def build_tracker_headers():
    """D+60 Tracker v2 헤더 2행 생성."""
    # Row 1: 그룹 헤더
    row1 = ["", "", "", "", "Current Status", "", "", ""]  # Post Info 4 + Current Status 4
    for d in range(MAX_DAYS):
        row1.extend([f"D+{d}", "", ""])

    # Row 2: 서브 헤더
    row2 = ["Post ID", "URL", "Username", "Post Date", "D+ Days", "Curr Comment", "Curr Like", "Curr View"]
    for d in range(MAX_DAYS):
        row2.extend(METRIC_LABELS)

    return row1, row2


# ──── Migration: v1 → v2 ────

def detect_tracker_version(tracker_ws):
    """서브헤더(Row2) 5번째 열이 'D+ Days'면 v2, 아니면 v1."""
    try:
        headers = tracker_ws.row_values(2)
        if len(headers) >= 5 and "D+ Days" in headers[4]:
            return "v2"
        return "v1"
    except Exception:
        return "v1"


def migrate_tracker_v1_to_v2(sh, tracker_ws):
    """
    기존 v1 시트(FIXED_COLS=4)에 4열 삽입하여 v2로 업그레이드.
    Post Date 열(D, index 3) 바로 다음에 E~H 삽입.
    기존 데이터 행 전체에 수식도 자동 추가.
    """
    print("[MIGRATE] D+60 Tracker v1 → v2 업그레이드 (D+ Days + Current Metrics 열 추가)...")

    # 1) 열 4개 삽입 (index 4 ~ 7)
    sh.batch_update({"requests": [{
        "insertDimension": {
            "range": {
                "sheetId": tracker_ws.id,
                "dimension": "COLUMNS",
                "startIndex": 4,
                "endIndex": 8,
            },
            "inheritFromBefore": False,
        }
    }]})

    # 2) 헤더 업데이트
    tracker_ws.update("E1:H1", [["Current Status", "", "", ""]], value_input_option="RAW")
    tracker_ws.update("E2:H2", [["D+ Days", "Curr Comment", "Curr Like", "Curr View"]], value_input_option="RAW")

    # 3) 기존 데이터 행에 D+ Days 수식만 삽입 (F/G/H는 다음 sync에서 실제값으로 채워짐)
    all_data = tracker_ws.get_all_values()
    formula_updates = []
    for i in range(2, len(all_data)):  # all_data index (0-based), 헤더 2행 제외
        sheet_row = i + 1  # 1-indexed
        if all_data[i] and all_data[i][0]:
            days_f = f'=IF(D{sheet_row}="","",INT(TODAY()-D{sheet_row}))'
            formula_updates.append({
                "range": f"E{sheet_row}",
                "values": [[days_f]],
            })

    if formula_updates:
        tracker_ws.batch_update(formula_updates, value_input_option="USER_ENTERED")
        print(f"[MIGRATE] 완료. {len(formula_updates)}개 행에 D+ Days 수식 추가.")
    else:
        print("[MIGRATE] 완료.")


# ──── Formatting ────

def format_master(sh, ws, num_data_rows):
    num_cols = len(MASTER_HEADERS)
    num_rows = num_data_rows + 1
    requests = []

    requests.append({
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }
    })

    if num_rows > 1:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": num_rows,
                          "startColumnIndex": 0, "endColumnIndex": num_cols},
                "cell": {"userEnteredFormat": {
                    "verticalAlignment": "MIDDLE", "wrapStrategy": "CLIP",
                    "borders": _borders(),
                }},
                "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.borders",
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": num_rows,
                          "startColumnIndex": 5, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
                }},
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    requests.append({"addBanding": {"bandedRange": {
        "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": num_rows,
                  "startColumnIndex": 0, "endColumnIndex": num_cols},
        "rowProperties": {
            "headerColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
            "firstBandColor": {"red": 1, "green": 1, "blue": 1},
            "secondBandColor": {"red": 0.95, "green": 0.97, "blue": 1.0},
        },
    }}})

    for i, px in enumerate([130, 320, 80, 140, 140, 100, 350, 200, 120, 100, 100, 200, 100]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize",
        }})

    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 36}, "fields": "pixelSize",
    }})
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})

    try:
        sh.batch_update({"requests": requests})
    except Exception as e:
        # addBanding 중복 오류 무시하고 나머지 포맷만 적용
        if "addBanding" in str(e) or "already" in str(e).lower():
            requests_no_band = [r for r in requests if "addBanding" not in r]
            if requests_no_band:
                sh.batch_update({"requests": requests_no_band})
        else:
            raise


def format_tracker(sh, ws):
    """D+60 Tracker v2 포맷 적용."""
    requests = []
    sid = ws.id

    # ── Row 1: 그룹 헤더 ──
    # Post Info (cols 0-3): 짙은 남색
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": 4},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.20, "green": 0.24, "blue": 0.35},
            "textFormat": {"bold": True, "fontSize": 10,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # Auto group (cols 4-7): 짙은 초록
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 4, "endColumnIndex": 8},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.13, "green": 0.40, "blue": 0.25},
            "textFormat": {"bold": True, "fontSize": 10,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})
    requests.append({"mergeCells": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 4, "endColumnIndex": 8},
        "mergeType": "MERGE_ALL",
    }})

    # D+N 그룹 헤더: 교대 색상 (청록 / 갈색)
    colors = [
        {"red": 0.16, "green": 0.50, "blue": 0.50},
        {"red": 0.65, "green": 0.32, "blue": 0.18},
    ]
    for d in range(MAX_DAYS):
        sc = FIXED_COLS + d * METRICS_PER_DAY
        c = colors[d % 2]
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": sc, "endColumnIndex": sc + METRICS_PER_DAY},
            "cell": {"userEnteredFormat": {
                "backgroundColor": c,
                "textFormat": {"bold": True, "fontSize": 9,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }})
        requests.append({"mergeCells": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": sc, "endColumnIndex": sc + METRICS_PER_DAY},
            "mergeType": "MERGE_ALL",
        }})

    # ── Row 2: 서브 헤더 ──
    # Post Info sub (cols 0-3)
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2,
                  "startColumnIndex": 0, "endColumnIndex": 4},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.85, "green": 0.87, "blue": 0.91},
            "textFormat": {"bold": True, "fontSize": 9},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # Auto sub (cols 4-7): 연한 초록
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2,
                  "startColumnIndex": 4, "endColumnIndex": 8},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.82, "green": 0.94, "blue": 0.87},
            "textFormat": {"bold": True, "fontSize": 9},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # D+N 서브헤더 (교대 색상)
    light_colors = [
        {"red": 0.85, "green": 0.93, "blue": 0.93},
        {"red": 0.93, "green": 0.87, "blue": 0.82},
    ]
    for d in range(MAX_DAYS):
        sc = FIXED_COLS + d * METRICS_PER_DAY
        lc = light_colors[d % 2]
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": sc, "endColumnIndex": sc + METRICS_PER_DAY},
            "cell": {"userEnteredFormat": {
                "backgroundColor": lc,
                "textFormat": {"bold": True, "fontSize": 8},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }})

    # ── 데이터 영역 ──
    # Post Info data (cols 0-3)
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 500,
                  "startColumnIndex": 0, "endColumnIndex": 4},
        "cell": {"userEnteredFormat": {
            "verticalAlignment": "MIDDLE", "borders": _borders(),
        }},
        "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.borders",
    }})

    # D+ Days (col 4): 연한 초록 배경, 중앙 정렬
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 500,
                  "startColumnIndex": 4, "endColumnIndex": 5},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.94, "green": 0.99, "blue": 0.96},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # Curr Cmt/Like/View (cols 5-7): 연한 초록 배경, 우측 정렬
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 500,
                  "startColumnIndex": 5, "endColumnIndex": 8},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.94, "green": 0.99, "blue": 0.96},
            "horizontalAlignment": "RIGHT", "verticalAlignment": "MIDDLE",
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # D+N 데이터 (cols 8+)
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 500,
                  "startColumnIndex": FIXED_COLS, "endColumnIndex": TOTAL_TRACKER_COLS},
        "cell": {"userEnteredFormat": {
            "horizontalAlignment": "RIGHT", "verticalAlignment": "MIDDLE",
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # ── 열 너비 ──
    for i, px in enumerate([130, 280, 120, 100, 60, 75, 75, 75]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize",
        }})
    for i in range(FIXED_COLS, TOTAL_TRACKER_COLS):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": 65}, "fields": "pixelSize",
        }})

    # 행 높이
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 32}, "fields": "pixelSize",
    }})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
        "properties": {"pixelSize": 28}, "fields": "pixelSize",
    }})

    # 행/열 고정 (헤더 2행 + Post ID 1열)
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {
            "frozenRowCount": 2, "frozenColumnCount": 1,
        }},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }})

    sh.batch_update({"requests": requests})


def format_influencer_tracker(sh, ws, num_date_cols):
    """Influencer Tracker 탭 포맷 적용."""
    requests = []
    sid = ws.id
    total_cols = INF_FIXED_COLS + num_date_cols

    # 헤더 행: fixed cols (짙은 남색)
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": INF_FIXED_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
            "textFormat": {"bold": True, "fontSize": 10,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # 헤더 행: date cols (청록) - TEXT 포맷으로 날짜 시리얼 변환 방지
    if num_date_cols > 0:
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": INF_FIXED_COLS, "endColumnIndex": total_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.16, "green": 0.50, "blue": 0.50},
                "textFormat": {"bold": True, "fontSize": 9,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "borders": _borders(),
                "numberFormat": {"type": "TEXT"},
            }},
            "fields": "userEnteredFormat",
        }})

    # 데이터 행
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 300,
                  "startColumnIndex": 0,
                  "endColumnIndex": max(total_cols, INF_FIXED_COLS)},
        "cell": {"userEnteredFormat": {
            "verticalAlignment": "MIDDLE", "borders": _borders(),
        }},
        "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.borders",
    }})

    # Followers / Total Posts: 숫자 포맷
    for col_i in [2, 4]:
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 300,
                      "startColumnIndex": col_i, "endColumnIndex": col_i + 1},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
                "horizontalAlignment": "RIGHT",
            }},
            "fields": "userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment",
        }})

    # 열 너비
    for i, px in enumerate([150, 150, 90, 110, 80]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize",
        }})
    for i in range(INF_FIXED_COLS, total_cols):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": 120}, "fields": "pixelSize",
        }})

    # 헤더 행 높이
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 36}, "fields": "pixelSize",
    }})

    # 고정: 헤더 1행 + Username 1열
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {
            "frozenRowCount": 1, "frozenColumnCount": 1,
        }},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }})

    if requests:
        sh.batch_update({"requests": requests})


# ──── Sync: Posts Master ────

def sync_master(sh, rows):
    is_new = False
    try:
        ws = sh.worksheet(MASTER_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=MASTER_SHEET, rows=500, cols=len(MASTER_HEADERS))
        ws.update([MASTER_HEADERS], range_name="A1", value_input_option="RAW")
        is_new = True
        print(f"[SHEETS] Created '{MASTER_SHEET}'")

    existing_ids = set()
    try:
        existing_ids = set(ws.col_values(1)[1:])
    except Exception:
        pass

    new_rows = []
    for row in rows:
        post_id = row.get("source.id", "")
        if post_id and post_id not in existing_ids:
            master_row = []
            for col in MASTER_COLS:
                val = row.get(col, "")
                if col == "author.follower_count":
                    val = safe_int(val)
                if isinstance(val, str) and len(val) > 400:
                    val = val[:397] + "..."
                master_row.append(val)
            new_rows.append(master_row)
            existing_ids.add(post_id)

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"[MASTER] +{len(new_rows)} posts")
    else:
        print(f"[MASTER] No new posts")

    if is_new:
        all_data = ws.get_all_values()
        format_master(sh, ws, len(all_data) - 1)
        print(f"[MASTER] Formatted")

    return ws


# ──── Sync: D+60 Tracker ────

def sync_tracker(sh, rows, today):
    """
    D+60 Tracker 동기화.
    Returns: (tracker_ws, post_to_sheet_row)
      post_to_sheet_row: {post_id: 1-indexed sheet row}
    """
    is_new = False
    try:
        ws = sh.worksheet(TRACKER_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=TRACKER_SHEET, rows=200, cols=TOTAL_TRACKER_COLS)
        row1, row2 = build_tracker_headers()
        ws.update([row1, row2], range_name="A1", value_input_option="RAW")
        is_new = True
        print(f"[SHEETS] Created '{TRACKER_SHEET}'")

    # 버전 확인 및 마이그레이션
    if not is_new:
        version = detect_tracker_version(ws)
        if version == "v1":
            migrate_tracker_v1_to_v2(sh, ws)
            format_tracker(sh, ws)
            print(f"[TRACKER] v2 포맷 적용 완료")

    # post_id → all_data index (0-based) 맵
    all_data = ws.get_all_values()

    # 헤더 자동 수정 (구버전: "Auto", "Curr Cmt" → 신버전으로 업데이트)
    if not is_new and all_data:
        header_fixes = []
        if len(all_data) > 0 and len(all_data[0]) > 4 and all_data[0][4] == "Auto":
            header_fixes.append({"range": "E1", "values": [["Current Status"]]})
        if len(all_data) > 1 and len(all_data[1]) > 5 and all_data[1][5] in ("Curr Cmt", "Cmt"):
            header_fixes.append({"range": "F2:H2", "values": [["Curr Comment", "Curr Like", "Curr View"]]})
        if header_fixes:
            ws.batch_update(header_fixes, value_input_option="RAW")
            print("[TRACKER] 헤더 업데이트 완료")

    post_row_map = {}
    for i, r in enumerate(all_data[2:], start=2):
        if r and r[0]:
            post_row_map[r[0]] = i

    updated = 0
    added = 0
    skipped_old = 0
    batch_cells = []

    for row in rows:
        post_id = row.get("source.id", "")
        post_date = parse_date(row.get("date", ""))
        if not post_id or not post_date:
            continue

        days_since = (today - post_date).days
        if days_since < 0 or days_since > 60:
            skipped_old += 1
            continue

        metrics = [
            safe_int(row.get("extraction.engagement.comment", 0)),
            safe_int(row.get("extraction.engagement.like", 0)),
            safe_int(row.get("extraction.engagement.view", 0)),
        ]
        col_start = FIXED_COLS + days_since * METRICS_PER_DAY

        if post_id in post_row_map:
            # 기존 행: D+N 메트릭 + Curr(F/G/H) 업데이트
            sheet_row = post_row_map[post_id] + 1  # 1-indexed
            sl = col_letter(col_start)
            el = col_letter(col_start + METRICS_PER_DAY - 1)
            batch_cells.append((f"{sl}{sheet_row}:{el}{sheet_row}", [metrics]))
            # Curr Comment/Like/View: 최신 스냅샷값으로 덮어쓰기
            batch_cells.append((f"F{sheet_row}:H{sheet_row}", [metrics]))
            updated += 1
        else:
            # 신규 행: 전체 행 작성
            next_sheet_row = len(all_data) + 1  # 1-indexed

            new_row = [""] * TOTAL_TRACKER_COLS
            new_row[0] = post_id
            new_row[1] = row.get("source.url", "")
            new_row[2] = row.get("author.username", "")
            new_row[3] = post_date.strftime("%Y-%m-%d")

            # E: D+ Days 수식 (자동 갱신)
            new_row[4] = f'=IF(D{next_sheet_row}="","",INT(TODAY()-D{next_sheet_row}))'
            # F-H: 현재 스냅샷 데이터 (매 sync마다 최신값으로 업데이트)
            new_row[5] = metrics[0]  # Curr Comment
            new_row[6] = metrics[1]  # Curr Like
            new_row[7] = metrics[2]  # Curr View

            # D+N 메트릭
            new_row[col_start]     = metrics[0]
            new_row[col_start + 1] = metrics[1]
            new_row[col_start + 2] = metrics[2]

            el = col_letter(TOTAL_TRACKER_COLS - 1)
            batch_cells.append((f"A{next_sheet_row}:{el}{next_sheet_row}", [new_row]))

            post_row_map[post_id] = len(all_data)
            all_data.append(new_row)
            added += 1

    if batch_cells:
        ws.batch_update(
            [{"range": r, "values": v} for r, v in batch_cells],
            value_input_option="USER_ENTERED",
        )
        print(f"[TRACKER] +{added} 신규, ~{updated} 업데이트")
    else:
        print(f"[TRACKER] 변경 없음")

    if skipped_old:
        print(f"[TRACKER] {skipped_old}건 스킵 (D+0~60 범위 외)")

    if is_new:
        format_tracker(sh, ws)
        print(f"[TRACKER] 포맷 적용")

    # post_id → 1-indexed sheet row (Influencer Tracker 하이퍼링크용)
    post_to_sheet_row = {pid: idx + 1 for pid, idx in post_row_map.items()}
    return ws, post_to_sheet_row


# ──── Sync: Influencer Tracker ────

def sync_influencer_tracker(sh, rows, tracker_ws, post_to_sheet_row, spreadsheet_id):
    """
    Influencer Tracker 탭 동기화.
    - 인플루언서별 1행, 날짜별 1열
    - 날짜 셀 = HYPERLINK → D+60 Tracker 해당 포스트 행
    """
    is_new = False
    try:
        inf_ws = sh.worksheet(INF_SHEET)
    except gspread.WorksheetNotFound:
        inf_ws = sh.add_worksheet(title=INF_SHEET, rows=300, cols=150)
        is_new = True
        print(f"[SHEETS] Created '{INF_SHEET}'")

    tracker_gid = tracker_ws.id

    # ── 인플루언서 데이터 구성 ──
    # {username: {date_str: [post_id, ...]}}
    inf_data = {}
    inf_meta = {}

    for row in rows:
        username = row.get("author.username", "").strip()
        if not username:
            continue

        post_id  = row.get("source.id", "")
        post_date = parse_date(row.get("date", ""))
        if not post_date:
            continue

        date_str = post_date.strftime("%Y-%m-%d")

        if username not in inf_data:
            inf_data[username] = {}
            inf_meta[username] = {
                "nickname":   row.get("author.nickname", ""),
                "followers":  safe_int(row.get("author.follower_count", 0)),
                "first_seen": date_str,
            }
        else:
            if date_str < inf_meta[username]["first_seen"]:
                inf_meta[username]["first_seen"] = date_str
            # 팔로워는 최신값으로 갱신
            inf_meta[username]["followers"] = safe_int(row.get("author.follower_count", 0))

        if date_str not in inf_data[username]:
            inf_data[username][date_str] = []
        if post_id:
            url = row.get("source.url", "")
            inf_data[username][date_str].append((post_id, url))

    # ── 현재 시트 상태 읽기 ──
    all_vals = inf_ws.get_all_values()

    if all_vals and all_vals[0]:
        existing_header = all_vals[0]
        # 시리얼 번호(예: 46044)로 저장된 날짜를 YYYY-MM-DD 문자열로 변환
        existing_dates = [serial_to_date(d) for d in existing_header[INF_FIXED_COLS:] if d]
    else:
        existing_header = []
        existing_dates  = []

    # 신규 날짜 수집 및 통합 정렬
    new_dates_set = set()
    for dates in inf_data.values():
        new_dates_set.update(dates.keys())

    all_dates = sorted(set(existing_dates) | new_dates_set)
    date_to_col = {d: INF_FIXED_COLS + i for i, d in enumerate(all_dates)}

    full_header = INF_FIXED_HEADERS + all_dates

    # 인플루언서 행 맵: username → all_vals index (0-based)
    inf_row_map = {}
    for i, r in enumerate(all_vals[1:], start=1):
        if r and r[0]:
            inf_row_map[r[0]] = i

    updates = []

    # 헤더 업데이트 (날짜 추가 시) - RAW 모드로 별도 저장 (날짜 시리얼 자동변환 방지)
    header_changed = (
        full_header != existing_header[:len(full_header)]
        or len(full_header) > len(existing_header)
    )
    if header_changed:
        inf_ws.batch_update([{
            "range": f"A1:{col_letter(len(full_header) - 1)}1",
            "values": [full_header],
        }], value_input_option="RAW")

    for username, dates in inf_data.items():
        meta = inf_meta[username]
        total_posts = sum(len(pids) for pids in dates.values())

        if username in inf_row_map:
            row_idx   = inf_row_map[username]
            sheet_row = row_idx + 1  # 1-indexed
        else:
            # 신규 인플루언서
            row_idx   = len(all_vals)
            sheet_row = row_idx + 1
            inf_row_map[username] = row_idx
            all_vals.append([username] + [""] * (len(full_header) - 1))

        # Fixed cols 업데이트
        updates.append({
            "range": f"A{sheet_row}:{col_letter(INF_FIXED_COLS - 1)}{sheet_row}",
            "values": [[
                username,
                meta["nickname"],
                meta["followers"],
                meta["first_seen"],
                total_posts,
            ]],
        })

        # 날짜별 포스트 하이퍼링크 → 실제 영상 URL로 연결
        for date_str, post_ids in dates.items():
            if not post_ids:
                continue

            col_idx = date_to_col[date_str]
            cell_ref = f"{col_letter(col_idx)}{sheet_row}"

            # post_ids: [(post_id, url), ...]
            primary_pid, primary_url = post_ids[0]

            # 표시 텍스트: 포스트 ID (너무 길면 일부만)
            display_text = primary_pid[:25] if len(primary_pid) > 25 else primary_pid
            if len(post_ids) > 1:
                display_text += f" (+{len(post_ids) - 1})"

            display_escaped = display_text.replace('"', '""')
            url_escaped = primary_url.replace('"', '%22') if primary_url else ""

            if url_escaped:
                formula = f'=HYPERLINK("{url_escaped}","{display_escaped}")'
            else:
                formula = display_text

            updates.append({
                "range": cell_ref,
                "values": [[formula]],
            })

    if updates:
        inf_ws.batch_update(updates, value_input_option="USER_ENTERED")
        print(f"[INF] {len(inf_data)}명 인플루언서, {len(all_dates)}개 날짜 열 업데이트")
    else:
        print(f"[INF] 변경 없음")

    # 신규 생성, 날짜 열 추가, 또는 헤더 변경 시 포맷 적용
    dates_added = set(all_dates) - set(existing_dates)
    if is_new or dates_added or header_changed:
        format_influencer_tracker(sh, inf_ws, len(all_dates))
        print(f"[INF] 포맷 적용")

    # 날짜 헤더 셀 TEXT 포맷 항상 적용 (시리얼 번호 재변환 방지)
    if all_dates:
        sh.batch_update({"requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": inf_ws.id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": INF_FIXED_COLS,
                    "endColumnIndex": INF_FIXED_COLS + len(all_dates),
                },
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
                "fields": "userEnteredFormat.numberFormat",
            }
        }]})

    return inf_ws


# ──── Sync: Posts Master Username Links ────

def update_master_username_links(sh, master_ws, inf_ws, spreadsheet_id):
    """
    Posts Master D열(Username)을 Influencer Tracker로 이동하는 HYPERLINK 수식으로 업데이트.
    """
    inf_gid = inf_ws.id

    # Influencer Tracker: username → sheet row (1-indexed)
    inf_usernames = inf_ws.col_values(1)  # Column A
    inf_row_map = {}
    for i, uname in enumerate(inf_usernames[1:], start=2):  # 헤더 제외, 1-indexed
        if uname:
            inf_row_map[uname.strip()] = i

    # Posts Master D열(Username) 읽기
    master_usernames = master_ws.col_values(4)  # Column D (1-indexed)

    updates = []
    for i, uname in enumerate(master_usernames[1:], start=2):  # 헤더 제외
        uname = uname.strip() if uname else ""
        if not uname:
            continue

        inf_row = inf_row_map.get(uname)
        if inf_row:
            url = (
                f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
                f"/edit#gid={inf_gid}&range=A{inf_row}"
            )
            escaped = uname.replace('"', '""')
            formula = f'=HYPERLINK("{url}","{escaped}")'
        else:
            formula = uname

        updates.append({"range": f"D{i}", "values": [[formula]]})

    if updates:
        master_ws.batch_update(updates, value_input_option="USER_ENTERED")
        print(f"[MASTER] Username 링크 {len(updates)}개 업데이트")


# ──── Main Orchestrator ────

def sync_to_sheets(csv_path, sheet_id=None):
    print(f"[SYNC] CSV: {csv_path}")

    rows = parse_csv(csv_path)
    print(f"[SYNC] {len(rows)} posts loaded")

    csv_name = Path(csv_path).stem
    collection_date = (
        csv_name[:10] if csv_name[:10].count("-") == 2
        else datetime.now().strftime("%Y-%m-%d")
    )
    today = datetime.strptime(collection_date, "%Y-%m-%d")
    print(f"[SYNC] Collection date: {collection_date}")

    creds = get_credentials()
    gc = gspread.authorize(creds)
    sh = open_sheet(gc, sheet_id)
    print(f"[SHEETS] Connected: {sh.title}")

    spreadsheet_id = sh.id

    # 탭별 동기화
    master_ws = sync_master(sh, rows)
    tracker_ws, post_to_sheet_row = sync_tracker(sh, rows, today)
    inf_ws = sync_influencer_tracker(sh, rows, tracker_ws, post_to_sheet_row, spreadsheet_id)
    update_master_username_links(sh, master_ws, inf_ws, spreadsheet_id)

    # 임시 시트 정리
    for temp_name in ["_temp", "Sheet1"]:
        try:
            sh.del_worksheet(sh.worksheet(temp_name))
        except Exception:
            pass

    print(f"\n[DONE] {sh.url}")
    return sh.url


def main():
    parser = argparse.ArgumentParser(description="Syncly -> Google Sheets D+60 Tracker v2")
    parser.add_argument("--csv", help="Path to Syncly CSV file")
    parser.add_argument("--sheet-id", help="Existing Google Sheet ID")
    args = parser.parse_args()

    csv_path = args.csv
    if not csv_path:
        latest = find_latest_csv()
        if not latest:
            print("[ERROR] No CSV found in Data Storage/syncly/")
            sys.exit(1)
        csv_path = str(latest)

    sync_to_sheets(csv_path, args.sheet_id)


if __name__ == "__main__":
    main()
