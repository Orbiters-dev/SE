"""Upload Amazon Search Query Performance (Brand View) CSVs to DataKeeper.

Usage:
    python load_ba_sqp_csv.py
    python load_ba_sqp_csv.py --dir C:/Users/wjcho/Downloads
    python load_ba_sqp_csv.py --dry-run

Downloads from: Seller Central → Brand Analytics → Search Query Performance → Brand View
File pattern: US_Search_Query_Performance_Brand_View_Comprehensive_Week_YYYY_MM_DD.csv
"""
import os, sys, csv, glob, re, argparse, requests

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

ORBITOOLS_BASE = os.getenv("ORBITOOLS_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

# Branded keyword filter — same as frontend _bVariants
BRAND_VARIANTS = {
    "GROSMIMI": ["grosmimi", "grosmini", "grossini", "gros mimi", "grossmimi"],
    "NAEIAE":   ["naeiae", "nae iae"],
    "CHA&MOM":  ["cha&mom", "chaenmom", "cha and mom", "commemoi"],
    "ALPREMIO": ["alpremio"],
}


def is_branded(query: str, brand: str) -> bool:
    variants = BRAND_VARIANTS.get(brand.upper(), [brand.lower()])
    ql = query.lower()
    return any(v in ql for v in variants)


def parse_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    if not lines:
        return []

    # Row 0: metadata — Brand=["GROSMIMI"], Reporting Range=...
    meta = lines[0]
    brand_match = re.search(r'Brand=\["([^"]+)"\]', meta)
    brand = brand_match.group(1).upper() if brand_match else "UNKNOWN"

    # Row 1: header
    reader = csv.DictReader(lines[1:])
    for r in reader:
        query = (r.get("Search Query") or "").strip()
        if not query:
            continue
        # Only load branded keywords
        if not is_branded(query, brand):
            continue

        week_end = (r.get("Reporting Date") or "").strip()
        if not week_end:
            continue

        def _int(v): return int(float(v)) if v and v.strip() not in ("", "-") else 0
        def _flt(v): return round(float(v), 4) if v and v.strip() not in ("", "-") else 0.0

        rows.append({
            "week_end": week_end,
            "brand": brand,
            "search_query": query,
            "search_query_score": _int(r.get("Search Query Score")),
            "search_query_volume": _int(r.get("Search Query Volume")),
            "impressions_brand": _int(r.get("Impressions: Brand Count")),
            "clicks_brand": _int(r.get("Clicks: Brand Count")),
            "clicks_brand_share": _flt(r.get("Clicks: Brand Share %")),
            "purchases_brand": _int(r.get("Purchases: Brand Count")),
            "purchases_brand_share": _flt(r.get("Purchases: Brand Share %")),
        })
    return rows


def upload_rows(rows: list[dict], dry_run: bool = False) -> dict:
    if dry_run:
        print(f"  [DRY-RUN] Would upload {len(rows)} rows")
        return {"created": 0, "updated": 0, "dry_run": True}

    resp = requests.post(
        f"{ORBITOOLS_BASE}/save/",
        json={"table": "amazon_sqp_brand", "rows": rows},
        auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="C:/Users/wjcho/Downloads",
                        help="Directory containing the CSV files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse only, don't upload")
    args = parser.parse_args()

    pattern = os.path.join(args.dir, "US_Search_Query_Performance_Brand_View_Comprehensive_Week_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No files found matching pattern in: {args.dir}")
        sys.exit(1)

    # Deduplicate files by (brand, week_end) — keep first occurrence
    seen = set()
    deduped = []
    for f in files:
        # Quick dedup by filename date portion (handles "(1)" duplicates)
        date_match = re.search(r'Week_(\d{4}_\d{2}_\d{2})', f)
        key = date_match.group(1) if date_match else f
        if key not in seen:
            seen.add(key)
            deduped.append(f)
        else:
            print(f"  SKIP (duplicate): {os.path.basename(f)}")

    print(f"Processing {len(deduped)} files...")
    total_created = total_updated = 0

    for path in deduped:
        fname = os.path.basename(path)
        rows = parse_csv(path)
        print(f"  {fname}: {len(rows)} branded keyword rows")

        if not rows:
            continue

        result = upload_rows(rows, dry_run=args.dry_run)
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        total_created += created
        total_updated += updated
        if not args.dry_run:
            print(f"    → created={created}, updated={updated}")

    print(f"\nDone: {total_created} created, {total_updated} updated across {len(deduped)} files")


if __name__ == "__main__":
    main()
