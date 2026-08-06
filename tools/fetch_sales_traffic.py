#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SP-API Sales & Traffic 리포트 (일별 세션·주문·전환율) 수집.

Amazon Business Report의 세션수/전환 데이터를 GET_SALES_AND_TRAFFIC_REPORT로 취득.
FE(Amazon JP)는 로컬 .env, NA(Amazon US)는 GitHub Actions 시크릿으로 실행.

CLI:
  python tools/fetch_sales_traffic.py --region FE --days 30 --out .tmp/traffic_jp.json
  python tools/fetch_sales_traffic.py --region NA --days 30 --out .tmp/traffic_us.json
출력 JSON: {region, label, fetched_range, rows: [{date, sessions, page_views,
            orders, units, cvr_pct, unit_session_pct, sales}]}
"""
import argparse
import gzip
import io
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

REGIONS = {
    "FE": {
        "endpoint": "https://sellingpartnerapi-fe.amazon.com",
        "marketplace_id": os.getenv("AMAZON_MARKETPLACE_ID", "A1VC38T7YXB528"),
        "label": "Amazon JP",
        "client_id": os.getenv("AMZ_SP_GROSMIMI_JP_CLIENT_ID") or os.getenv("AMAZON_LWA_CLIENT_ID"),
        "client_secret": os.getenv("AMZ_SP_GROSMIMI_JP_CLIENT_SECRET") or os.getenv("AMAZON_LWA_CLIENT_SECRET"),
        "refresh_token": os.getenv("AMZ_SP_REFRESH_TOKEN_GROSMIMI_JP") or os.getenv("AMAZON_REFRESH_TOKEN"),
    },
    "NA": {
        "endpoint": "https://sellingpartnerapi-na.amazon.com",
        "marketplace_id": "ATVPDKIKX0DER",
        "label": "Amazon US",
        "client_id": os.getenv("AMZ_SP_GROSMIMI_CLIENT_ID") or os.getenv("AMAZON_LWA_CLIENT_ID"),
        "client_secret": os.getenv("AMZ_SP_GROSMIMI_CLIENT_SECRET") or os.getenv("AMAZON_LWA_CLIENT_SECRET"),
        "refresh_token": os.getenv("AMZ_SP_REFRESH_TOKEN_GROSMIMI") or os.getenv("AMAZON_US_REFRESH_TOKEN"),
    },
}


def check_credentials(region: str, cfg: dict):
    """필수 자격증명 3종 검증 — 누락 시 어떤 env 가 비었는지 명시하고 종료."""
    env_names = {
        "FE": {"client_id": "AMZ_SP_GROSMIMI_JP_CLIENT_ID|AMAZON_LWA_CLIENT_ID",
               "client_secret": "AMZ_SP_GROSMIMI_JP_CLIENT_SECRET|AMAZON_LWA_CLIENT_SECRET",
               "refresh_token": "AMZ_SP_REFRESH_TOKEN_GROSMIMI_JP|AMAZON_REFRESH_TOKEN"},
        "NA": {"client_id": "AMZ_SP_GROSMIMI_CLIENT_ID|AMAZON_LWA_CLIENT_ID",
               "client_secret": "AMZ_SP_GROSMIMI_CLIENT_SECRET|AMAZON_LWA_CLIENT_SECRET",
               "refresh_token": "AMZ_SP_REFRESH_TOKEN_GROSMIMI|AMAZON_US_REFRESH_TOKEN"},
    }[region]
    missing = [f"{k} (env: {v})" for k, v in env_names.items() if not cfg.get(k)]
    if missing:
        raise SystemExit(f"{region}: 자격증명 누락 —\n  " + "\n  ".join(missing))


def access_token(cfg):
    r = requests.post(LWA_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
    }, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def fetch(region: str, days: int, max_wait: int = 600) -> dict:
    cfg = REGIONS[region]
    check_credentials(region, cfg)
    token = access_token(cfg)
    hdr = {"x-amz-access-token": token, "Content-Type": "application/json"}

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    body = {
        "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
        "marketplaceIds": [cfg["marketplace_id"]],
        "dataStartTime": f"{start}T00:00:00Z",
        "dataEndTime": f"{end}T23:59:59Z",
        "reportOptions": {"dateGranularity": "DAY", "asinGranularity": "PARENT"},
    }
    r = requests.post(f"{cfg['endpoint']}/reports/2021-06-30/reports",
                      json=body, headers=hdr, timeout=30)
    r.raise_for_status()
    report_id = r.json()["reportId"]
    print(f"{region}: 리포트 생성 요청 {report_id} ({start} ~ {end})")

    doc_id = None
    for i in range(max(1, max_wait // 10)):
        time.sleep(10)
        r = requests.get(f"{cfg['endpoint']}/reports/2021-06-30/reports/{report_id}",
                         headers=hdr, timeout=30)
        r.raise_for_status()
        st = r.json()
        if st["processingStatus"] == "DONE":
            doc_id = st["reportDocumentId"]
            break
        if st["processingStatus"] in ("CANCELLED", "FATAL"):
            raise SystemExit(f"{region}: 리포트 실패 {st['processingStatus']}")
    if not doc_id:
        raise SystemExit(f"{region}: 리포트 타임아웃")

    r = requests.get(f"{cfg['endpoint']}/reports/2021-06-30/documents/{doc_id}",
                     headers=hdr, timeout=30)
    r.raise_for_status()
    doc = r.json()
    if not doc.get("url"):
        raise SystemExit(f"{region}: 리포트 문서 응답에 url 없음 — {doc}")
    raw = requests.get(doc["url"], timeout=60).content
    if doc.get("compressionAlgorithm") == "GZIP":
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    data = json.loads(raw)

    rows = []
    for d in data.get("salesAndTrafficByDate", []):
        sales = d.get("salesByDate", {})
        traffic = d.get("trafficByDate", {})
        sessions = traffic.get("sessions", 0)
        orders = sales.get("totalOrderItems", 0)
        rows.append({
            "date": d["date"],
            "sessions": sessions,
            "page_views": traffic.get("pageViews", 0),
            "orders": orders,
            "units": sales.get("unitsOrdered", 0),
            "cvr_pct": round(orders / sessions * 100, 2) if sessions else 0,
            "unit_session_pct": traffic.get("unitSessionPercentage", 0),
            "sales": sales.get("orderedProductSales", {}).get("amount", 0),
        })
    rows.sort(key=lambda x: x["date"])
    return {"region": region, "label": cfg["label"],
            "fetched_range": [str(start), str(end)], "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", choices=["FE", "NA"], required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-wait", type=int, default=600,
                    help="리포트 생성 대기 상한(초), 기본 600")
    args = ap.parse_args()

    result = fetch(args.region, args.days, args.max_wait)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    total_s = sum(r["sessions"] for r in result["rows"])
    total_o = sum(r["orders"] for r in result["rows"])
    print(f"{args.region}: {len(result['rows'])}일 저장 → {out}")
    print(f"  세션 {total_s:,} / 주문 {total_o:,} / CVR {total_o/total_s*100:.2f}%" if total_s else "  세션 0")


if __name__ == "__main__":
    main()
