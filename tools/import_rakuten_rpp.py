"""
import_rakuten_rpp.py - Rakuten RPP (Rakuten Promotion Platform) CSV Importer

Rakuten RMS API 2.0 does NOT expose RPP advertising data programmatically.
This tool imports manually downloaded RPP performance CSVs from the RMS console
and writes them to the DataKeeper `rakuten_ads_daily` table.

Usage:
    python tools/import_rakuten_rpp.py --file .tmp/rpp_report.csv
    python tools/import_rakuten_rpp.py --file .tmp/rpp_report.csv --dry-run
    python tools/import_rakuten_rpp.py --dir .tmp/rpp_exports/          # all CSVs in dir
    python tools/import_rakuten_rpp.py --status                         # check latest data

CSV export from Rakuten RMS console:
    RMS > 広告・アフィリエイト > RPP広告 > パフォーマンスレポート > CSVダウンロード

Expected CSV columns (Japanese headers):
    日付, 商品管理番号, 商品名, 表示回数, クリック数, クリック率,
    注文件数, 売上金額, CPC, 広告費, ROAS, CVR
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
TMP_DIR = ROOT / ".tmp"

# Column name mapping: Japanese -> English
COLUMN_MAP = {
    "日付": "date",
    "商品管理番号": "item_id",
    "商品名": "item_name",
    "表示回数": "impressions",
    "クリック数": "clicks",
    "クリック率": "ctr",
    "注文件数": "orders",
    "売上金額": "sales",
    "CPC": "cpc",
    "広告費": "cost",
    "ROAS": "roas",
    "CVR": "cvr",
    # Alternative column names (some RMS versions use different labels)
    "インプレッション": "impressions",
    "広告費用": "cost",
    "売上": "sales",
    "コンバージョン率": "cvr",
}


def _parse_number(val: str) -> float:
    """Parse Japanese-formatted numbers: remove ¥, commas, % signs."""
    if not val or val.strip() in ("-", "—", ""):
        return 0.0
    val = val.strip().replace("¥", "").replace(",", "").replace("%", "").replace("円", "")
    try:
        return float(val)
    except ValueError:
        return 0.0


def _parse_date(val: str) -> str:
    """Parse date from various Japanese formats."""
    val = val.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


def parse_rpp_csv(filepath: str) -> list[dict]:
    """Parse a Rakuten RPP CSV file into normalized rows."""
    rows = []
    path = Path(filepath)

    # Try different encodings (RMS exports as Shift-JIS or UTF-8 BOM)
    content = None
    for enc in ("utf-8-sig", "shift_jis", "cp932", "utf-8"):
        try:
            content = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        print(f"  [ERROR] Cannot decode {filepath}")
        return []

    reader = csv.DictReader(content.splitlines())

    for raw_row in reader:
        # Map Japanese column names to English
        row = {}
        for jp_key, value in raw_row.items():
            en_key = COLUMN_MAP.get(jp_key.strip(), jp_key.strip())
            row[en_key] = value

        if "date" not in row:
            continue

        parsed = {
            "date": _parse_date(row.get("date", "")),
            "brand": "Grosmimi JP",
            "platform": "rakuten",
            "item_id": row.get("item_id", "").strip(),
            "item_name": row.get("item_name", "").strip(),
            "impressions": int(_parse_number(row.get("impressions", "0"))),
            "clicks": int(_parse_number(row.get("clicks", "0"))),
            "ctr": _parse_number(row.get("ctr", "0")),
            "orders": int(_parse_number(row.get("orders", "0"))),
            "sales": _parse_number(row.get("sales", "0")),
            "cpc": _parse_number(row.get("cpc", "0")),
            "cost": _parse_number(row.get("cost", "0")),
            "roas": _parse_number(row.get("roas", "0")),
            "cvr": _parse_number(row.get("cvr", "0")),
            "currency": "JPY",
        }

        if parsed["date"] and (parsed["impressions"] > 0 or parsed["cost"] > 0):
            rows.append(parsed)

    return rows


def upload_to_datakeeper(rows: list[dict], dry_run: bool = False) -> dict:
    """Upload parsed RPP rows to DataKeeper rakuten_ads_daily table."""
    import requests

    api_base = os.getenv("DATAKEEPER_API_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
    user = os.getenv("ORBITOOLS_USER", "")
    passwd = os.getenv("ORBITOOLS_PASS", "")

    if not user or not passwd:
        print("[ERROR] ORBITOOLS_USER/PASS not set")
        return {"status": "error", "message": "No credentials"}

    if dry_run:
        print(f"  [DRY-RUN] Would upload {len(rows)} rows to rakuten_ads_daily")
        for r in rows[:5]:
            print(f"    {r['date']} | {r['item_name'][:30]} | ¥{r['cost']:,.0f} cost | ¥{r['sales']:,.0f} sales | ROAS {r['roas']:.1f}")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5} more rows")
        return {"status": "dry_run", "rows": len(rows)}

    # Aggregate to daily level for the table
    resp = requests.post(
        f"{api_base}/ingest/",
        auth=(user, passwd),
        json={"table": "rakuten_ads_daily", "rows": rows},
        timeout=60,
    )
    if resp.status_code < 300:
        result = resp.json()
        print(f"  [OK] Uploaded {len(rows)} rows -> rakuten_ads_daily")
        return {"status": "ok", "rows": len(rows), "response": result}
    else:
        print(f"  [ERROR] Upload failed: {resp.status_code} {resp.text[:200]}")
        return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}


def check_status():
    """Check latest rakuten_ads_daily data."""
    import requests

    api_base = os.getenv("DATAKEEPER_API_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
    user = os.getenv("ORBITOOLS_USER", "")
    passwd = os.getenv("ORBITOOLS_PASS", "")

    try:
        resp = requests.get(
            f"{api_base}/query/",
            params={"table": "rakuten_ads_daily", "days": 30},
            auth=(user, passwd),
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            rows = data if isinstance(data, list) else data.get("rows", [])
            if rows:
                dates = sorted(set(r.get("date", "") for r in rows))
                total_cost = sum(float(r.get("cost", 0)) for r in rows)
                total_sales = sum(float(r.get("sales", 0)) for r in rows)
                print(f"  rakuten_ads_daily: {len(rows)} rows")
                print(f"  Date range: {dates[0]} ~ {dates[-1]}")
                print(f"  Total cost: ¥{total_cost:,.0f}  |  Total sales: ¥{total_sales:,.0f}")
                if total_cost > 0:
                    print(f"  Overall ROAS: {total_sales / total_cost:.1f}x")
            else:
                print("  rakuten_ads_daily: No data (table may not exist yet)")
        else:
            print(f"  [ERROR] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [ERROR] {e}")


def main():
    parser = argparse.ArgumentParser(description="Import Rakuten RPP CSV to DataKeeper")
    parser.add_argument("--file", type=str, help="Path to RPP CSV file")
    parser.add_argument("--dir", type=str, help="Directory containing RPP CSV files")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't upload")
    parser.add_argument("--status", action="store_true", help="Check latest data")
    args = parser.parse_args()

    if args.status:
        check_status()
        return

    files = []
    if args.file:
        files.append(args.file)
    elif args.dir:
        dirpath = Path(args.dir)
        files = [str(f) for f in dirpath.glob("*.csv")]
        if not files:
            print(f"[ERROR] No CSV files found in {args.dir}")
            sys.exit(1)
    else:
        print("[ERROR] Specify --file or --dir")
        parser.print_help()
        sys.exit(1)

    all_rows = []
    for f in files:
        print(f"Parsing {f}...")
        rows = parse_rpp_csv(f)
        print(f"  -> {len(rows)} rows")
        all_rows.extend(rows)

    if not all_rows:
        print("[WARN] No valid rows parsed")
        sys.exit(0)

    # Summary
    dates = sorted(set(r["date"] for r in all_rows))
    total_cost = sum(r["cost"] for r in all_rows)
    total_sales = sum(r["sales"] for r in all_rows)
    print(f"\nTotal: {len(all_rows)} rows, {len(dates)} days ({dates[0]} ~ {dates[-1]})")
    print(f"Cost: ¥{total_cost:,.0f}  |  Sales: ¥{total_sales:,.0f}  |  ROAS: {total_sales / total_cost:.1f}x" if total_cost else "Cost: ¥0")

    # Save parsed JSON (always, for debugging)
    out_path = TMP_DIR / "rakuten_rpp_parsed.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Saved parsed data to {out_path}")

    # Upload
    result = upload_to_datakeeper(all_rows, dry_run=args.dry_run)
    print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    main()
