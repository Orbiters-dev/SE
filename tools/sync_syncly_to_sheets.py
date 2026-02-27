"""
Syncly -> Google Sheets D+30 Tracker (Wide Format)
====================================================
Syncly CSV를 Google Sheets에 동기화.
포스트별 engagement 변화를 D+0 ~ D+30까지 가로(Wide) 형태로 추적.

사용법:
  python tools/sync_syncly_to_sheets.py
  python tools/sync_syncly_to_sheets.py --csv "Data Storage/syncly/2026-02-27_....csv"
  python tools/sync_syncly_to_sheets.py --sheet-id "1abc..."

시트 구조:
  - Posts Master: 포스트 기본 정보 (1행 = 1포스트)
  - D+30 Tracker: Wide format (1행 = 1포스트, D0~D30 메트릭이 오른쪽으로 확장)

Tracker 레이아웃:
  Row 1: 그룹 헤더  |  Post Info (merged)  |  D+0 (merged)  |  D+1 (merged)  | ...
  Row 2: 서브 헤더  | ID | URL | User | Date | Cmt | Like | View | Cmt | Like | View | ...
  Row 3+: 데이터
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
TRACKER_SHEET = "D+30 Tracker"

# ──── Wide Tracker Config ────
FIXED_COLS = 4  # Post ID, URL, Username, Post Date
METRICS_PER_DAY = 3  # Comments, Likes, Views (compact - most useful)
MAX_DAYS = 31  # D+0 through D+30
TOTAL_TRACKER_COLS = FIXED_COLS + MAX_DAYS * METRICS_PER_DAY  # 4 + 93 = 97

METRIC_KEYS = [
    "extraction.engagement.comment",
    "extraction.engagement.like",
    "extraction.engagement.view",
]
METRIC_LABELS = ["Cmt", "Like", "View"]

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


# ──── Tracker Headers ────

def build_tracker_headers():
    """Build 2-row header for Wide Format tracker."""
    # Row 1: Group headers (will be merged later)
    row1 = ["", "", "", ""]  # Post Info group (4 cols)
    for d in range(MAX_DAYS):
        row1.extend([f"D+{d}", "", ""])  # 3 cols per day, merge later

    # Row 2: Sub-headers
    row2 = ["Post ID", "URL", "Username", "Post Date"]
    for d in range(MAX_DAYS):
        row2.extend(METRIC_LABELS)

    return row1, row2


# ──── Formatting ────

def format_master(sh, ws, num_data_rows):
    num_cols = len(MASTER_HEADERS)
    num_rows = num_data_rows + 1
    requests = []

    requests.append({
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
                "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }
    })

    if num_rows > 1:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": num_rows, "startColumnIndex": 0, "endColumnIndex": num_cols},
                "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE", "wrapStrategy": "CLIP", "borders": _borders()}},
                "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.borders",
            }
        })
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": num_rows, "startColumnIndex": 5, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    requests.append({"addBanding": {"bandedRange": {
        "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": num_rows, "startColumnIndex": 0, "endColumnIndex": num_cols},
        "rowProperties": {
            "headerColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
            "firstBandColor": {"red": 1, "green": 1, "blue": 1},
            "secondBandColor": {"red": 0.95, "green": 0.97, "blue": 1.0},
        },
    }}})

    for i, px in enumerate([130, 320, 80, 140, 140, 100, 350, 200, 120, 100, 100, 200, 100]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
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

    sh.batch_update({"requests": requests})


def format_tracker(sh, ws):
    """Apply formatting to Wide Format tracker."""
    requests = []
    sid = ws.id

    # ── Row 1: Group headers ──
    # "Post Info" group: cols 0-3
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": FIXED_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.20, "green": 0.24, "blue": 0.35},
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # D+ group headers: alternating teal/coral colors
    colors = [
        {"red": 0.16, "green": 0.50, "blue": 0.50},  # teal
        {"red": 0.65, "green": 0.32, "blue": 0.18},  # brown
    ]
    for d in range(MAX_DAYS):
        start_col = FIXED_COLS + d * METRICS_PER_DAY
        c = colors[d % 2]
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": start_col, "endColumnIndex": start_col + METRICS_PER_DAY},
            "cell": {"userEnteredFormat": {
                "backgroundColor": c,
                "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }})
        # Merge the D+N label across 3 columns
        requests.append({"mergeCells": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": start_col, "endColumnIndex": start_col + METRICS_PER_DAY},
            "mergeType": "MERGE_ALL",
        }})

    # ── Row 2: Sub-headers ──
    # Fixed cols sub-header
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": FIXED_COLS},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.85, "green": 0.87, "blue": 0.91},
            "textFormat": {"bold": True, "fontSize": 9},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})
    # Metric sub-headers
    light_colors = [
        {"red": 0.85, "green": 0.93, "blue": 0.93},  # light teal
        {"red": 0.93, "green": 0.87, "blue": 0.82},  # light brown
    ]
    for d in range(MAX_DAYS):
        start_col = FIXED_COLS + d * METRICS_PER_DAY
        lc = light_colors[d % 2]
        requests.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": start_col, "endColumnIndex": start_col + METRICS_PER_DAY},
            "cell": {"userEnteredFormat": {
                "backgroundColor": lc,
                "textFormat": {"bold": True, "fontSize": 8},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "borders": _borders(),
            }},
            "fields": "userEnteredFormat",
        }})

    # ── Data area: number format + borders ──
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 200, "startColumnIndex": FIXED_COLS, "endColumnIndex": TOTAL_TRACKER_COLS},
        "cell": {"userEnteredFormat": {
            "horizontalAlignment": "RIGHT", "verticalAlignment": "MIDDLE",
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            "borders": _borders(),
        }},
        "fields": "userEnteredFormat",
    }})

    # Fixed cols data area
    requests.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 200, "startColumnIndex": 0, "endColumnIndex": FIXED_COLS},
        "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE", "borders": _borders()}},
        "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.borders",
    }})

    # ── Column widths ──
    # Fixed cols
    for i, px in enumerate([130, 280, 120, 100]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize",
        }})
    # Metric cols: compact
    for i in range(FIXED_COLS, TOTAL_TRACKER_COLS):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": 65}, "fields": "pixelSize",
        }})

    # Row heights
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 32}, "fields": "pixelSize",
    }})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
        "properties": {"pixelSize": 28}, "fields": "pixelSize",
    }})

    # Freeze 2 header rows + 1 col (Post ID)
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 1}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }})

    sh.batch_update({"requests": requests})


# ──── Main Sync ────

def sync_to_sheets(csv_path, sheet_id=None):
    print(f"[SYNC] CSV: {csv_path}")

    rows = parse_csv(csv_path)
    print(f"[SYNC] {len(rows)} posts loaded")

    csv_name = Path(csv_path).stem
    collection_date = csv_name[:10] if csv_name[:10].count("-") == 2 else datetime.now().strftime("%Y-%m-%d")
    today = datetime.strptime(collection_date, "%Y-%m-%d")
    print(f"[SYNC] Collection date: {collection_date}")

    creds = get_credentials()
    gc = gspread.authorize(creds)
    sh = open_sheet(gc, sheet_id)
    print(f"[SHEETS] Connected: {sh.title}")

    # ━━━━━ Posts Master ━━━━━
    is_new_master = False
    try:
        master_ws = sh.worksheet(MASTER_SHEET)
    except gspread.WorksheetNotFound:
        master_ws = sh.add_worksheet(title=MASTER_SHEET, rows=500, cols=len(MASTER_HEADERS))
        master_ws.update([MASTER_HEADERS], range_name="A1", value_input_option="RAW")
        is_new_master = True
        print(f"[SHEETS] Created '{MASTER_SHEET}'")

    existing_ids = set()
    try:
        existing_ids = set(master_ws.col_values(1)[1:])
    except Exception:
        pass

    new_master_rows = []
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
            new_master_rows.append(master_row)
            existing_ids.add(post_id)

    if new_master_rows:
        master_ws.append_rows(new_master_rows, value_input_option="USER_ENTERED")
        print(f"[MASTER] +{len(new_master_rows)} posts")
    else:
        print(f"[MASTER] No new posts")

    if is_new_master or new_master_rows:
        all_master = master_ws.get_all_values()
        format_master(sh, master_ws, len(all_master) - 1)
        print(f"[MASTER] Formatted")

    # ━━━━━ D+30 Tracker (Wide Format) ━━━━━
    is_new_tracker = False
    try:
        tracker_ws = sh.worksheet(TRACKER_SHEET)
    except gspread.WorksheetNotFound:
        tracker_ws = sh.add_worksheet(title=TRACKER_SHEET, rows=200, cols=TOTAL_TRACKER_COLS)
        row1, row2 = build_tracker_headers()
        tracker_ws.update([row1, row2], range_name="A1", value_input_option="RAW")
        is_new_tracker = True
        print(f"[SHEETS] Created '{TRACKER_SHEET}'")

    # Read current tracker data (row 0=group header, row 1=sub header, row 2+=data)
    all_data = tracker_ws.get_all_values()
    # Build post_id -> row_index map (0-indexed in all_data, 1-indexed in sheet)
    post_row_map = {}
    for i, r in enumerate(all_data[2:], start=2):  # skip 2 header rows
        if r and r[0]:
            post_row_map[r[0]] = i  # all_data index

    updated = 0
    added = 0
    skipped_old = 0

    # Collect batch updates
    batch_cells = []  # list of (range_str, values)

    for row in rows:
        post_id = row.get("source.id", "")
        post_date = parse_date(row.get("date", ""))
        if not post_id or not post_date:
            continue

        days_since = (today - post_date).days
        if days_since < 0 or days_since > 30:
            skipped_old += 1
            continue

        # Metrics for this day
        metrics = [
            safe_int(row.get("extraction.engagement.comment", 0)),
            safe_int(row.get("extraction.engagement.like", 0)),
            safe_int(row.get("extraction.engagement.view", 0)),
        ]

        # Column offset for this D+ value
        col_start = FIXED_COLS + days_since * METRICS_PER_DAY  # 0-indexed

        if post_id in post_row_map:
            # Update existing row
            sheet_row = post_row_map[post_id] + 1  # 1-indexed for A1 notation
            start_letter = col_letter(col_start)
            end_letter = col_letter(col_start + METRICS_PER_DAY - 1)
            cell_range = f"{start_letter}{sheet_row}:{end_letter}{sheet_row}"
            batch_cells.append((cell_range, [metrics]))
            updated += 1
        else:
            # New post: add row with fixed info + this day's metrics
            new_row = [""] * TOTAL_TRACKER_COLS
            new_row[0] = post_id
            new_row[1] = row.get("source.url", "")
            new_row[2] = row.get("author.username", "")
            new_row[3] = post_date.strftime("%Y-%m-%d")
            new_row[col_start] = metrics[0]
            new_row[col_start + 1] = metrics[1]
            new_row[col_start + 2] = metrics[2]

            # Append row
            next_row_idx = len(all_data) + 1  # 1-indexed sheet row
            start_letter = "A"
            end_letter = col_letter(TOTAL_TRACKER_COLS - 1)
            cell_range = f"{start_letter}{next_row_idx}:{end_letter}{next_row_idx}"
            batch_cells.append((cell_range, [new_row]))

            # Track for subsequent posts in same batch
            post_row_map[post_id] = len(all_data)
            all_data.append(new_row)
            added += 1

    # Execute batch update
    if batch_cells:
        # gspread batch_update for multiple ranges
        tracker_ws.batch_update(
            [{"range": r, "values": v} for r, v in batch_cells],
            value_input_option="USER_ENTERED",
        )
        print(f"[TRACKER] +{added} new posts, ~{updated} updated (D+{days_since if rows else '?'})")
    else:
        print(f"[TRACKER] No updates")

    if skipped_old:
        print(f"[TRACKER] Skipped {skipped_old} (outside D+0~30)")

    # Format tracker (only on creation)
    if is_new_tracker:
        format_tracker(sh, tracker_ws)
        print(f"[TRACKER] Formatted")

    # Cleanup
    try:
        sh.del_worksheet(sh.worksheet("_temp"))
    except Exception:
        pass
    try:
        sh.del_worksheet(sh.worksheet("Sheet1"))
    except Exception:
        pass

    print(f"\n[DONE] {sh.url}")
    return sh.url


def main():
    parser = argparse.ArgumentParser(description="Syncly -> Google Sheets D+30 Tracker")
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
