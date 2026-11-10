"""Data Keeper Client - Read from PostgreSQL (primary) or NAS/local cache (fallback).

All consumer tools import this instead of calling APIs directly.
PG is always the source of truth; NAS cache and local cache are fallbacks.

Usage:
    from data_keeper_client import DataKeeper

    dk = DataKeeper()
    # Get Amazon Ads data for last 30 days
    rows = dk.get("amazon_ads_daily", days=30)
    rows = dk.get("amazon_ads_daily", date_from="2026-02-05", date_to="2026-03-06")
    rows = dk.get("amazon_ads_daily", brand="CHA&MOM")

    # Get latest collection timestamp
    dk.last_updated("amazon_ads_daily")
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(DIR, "..", ".tmp", "datakeeper")
PST = timezone(timedelta(hours=-8))

# NAS shared cache (read-only for team members)
NAS_CACHE_DIR = os.path.normpath(os.path.join(
    DIR, "..", "..", "Shared", "datakeeper", "latest"
))

# Load env if not already loaded
try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
DK_TOKEN = os.getenv("DK_SE_READ_TOKEN") or os.getenv("DK_READ_TOKEN")

PAGE_ROWS = 10000   # /query/ 한 응답의 서버 상한 — 넘는 limit 은 잘리고 next_offset 으로 다음 장을 알린다
PAGE_GAP_SEC = 4    # 한 키의 /query/ 는 분당 30회이고 여러 작업이 나눠 쓴다 — 이어 읽기는 그 절반만 쓴다
RETRY_STATUS = (429, 503)
MAX_TRIES = 5

# 재시도 끝에 실패한 /query/ 읽기의 (표, 사유). DataKeeper.get 은 실패를 [] 로 돌려주므로
# 출력을 쓰는 쪽은 이 목록으로 '행 0건' 과 '읽기 실패' 를 가른다.
FAILED_READS: list[tuple[str, str]] = []

VALID_TABLES = [
    "shopify_orders_daily", "shopify_orders_sku_daily",
    "amazon_sales_daily", "amazon_sales_sku_daily",
    "amazon_ads_daily", "amazon_ads_search_terms", "amazon_ads_keywords",
    "amazon_campaigns", "amazon_brand_analytics", "amazon_sqp_brand",
    "amazon_autocomplete_daily", "amazon_search_ranking",
    "meta_ads_daily", "meta_campaigns",
    "google_ads_daily", "google_ads_search_terms",
    "ga4_daily", "klaviyo_daily",
    "gsc_daily", "dataforseo_keywords",
    "content_posts", "content_metrics_daily", "influencer_orders",
    "rakuten_orders_daily",
    "rakuten_ads_daily",
]


class DataKeeper:
    """Client to read Data Keeper DB (primary) or cache (fallback).

    Fallback chain: PG API -> NAS shared cache -> local .tmp cache
    """

    def __init__(self, prefer_cache=False):
        """
        Args:
            prefer_cache: If True, read NAS/local cache first. If False (default), query PG first.
        """
        self.prefer_cache = prefer_cache

    def get(self, table: str, days: int = None,
            date_from: str = None, date_to: str = None,
            brand: str = None, campaign_id: str = None,
            channel: str = None, limit: int | None = None) -> list[dict]:
        """Get rows from Data Keeper.

        Default: PG API first, NAS cache fallback, local cache last resort.
        If prefer_cache=True: NAS cache first, local cache, PG last.
        limit = 최대 행 수. None 이면 서버 한도(장당 10,000행)를 넘어도 끝까지 이어 읽는다.
        """
        if table not in VALID_TABLES:
            raise ValueError(f"Unknown table: {table}. Valid: {VALID_TABLES}")

        # Calculate date range
        if days and not date_from:
            today = datetime.now(PST).date()
            date_from = (today - timedelta(days=days)).isoformat()
            date_to = date_to or today.isoformat()

        if self.prefer_cache:
            # Cache-first mode: NAS -> local -> PG
            for reader in [self._read_nas_cache, self._read_cache]:
                rows = reader(table)
                if rows:
                    filtered = self._filter(rows, date_from, date_to, brand,
                                            campaign_id, channel, limit)
                    if filtered:
                        return filtered

            rows = self._read_pg(table, date_from, date_to, brand,
                                 campaign_id, channel, limit)
            return rows if rows else []

        # Default: PG first, NAS fallback, local last
        rows = self._read_pg(table, date_from, date_to, brand,
                             campaign_id, channel, limit)
        if rows:
            return rows

        # PG unreachable -- try NAS cache, then local cache
        for reader in [self._read_nas_cache, self._read_cache]:
            rows = reader(table)
            if rows:
                filtered = self._filter(rows, date_from, date_to, brand,
                                        campaign_id, channel, limit)
                if filtered:
                    return filtered

        return []

    def _read_nas_cache(self, table: str) -> list[dict]:
        """Read from NAS shared JSON cache (Shared/datakeeper/latest/)."""
        path = os.path.join(NAS_CACHE_DIR, f"{table}.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _read_cache(self, table: str) -> list[dict]:
        """Read from local JSON cache (.tmp/datakeeper/)."""
        path = os.path.join(CACHE_DIR, f"{table}.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _read_pg(self, table, date_from, date_to, brand,
                 campaign_id, channel, limit) -> list[dict]:
        """Query from PostgreSQL via orbitools API."""
        params = {"table": table}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if brand:
            params["brand"] = brand
        if campaign_id:
            params["campaign_id"] = campaign_id
        if channel:
            params["channel"] = channel

        try:
            return query_rows(params, max_rows=limit)
        except Exception as e:
            # 401(자격증명 없음)도 빈 결과와 구분 안 되면 호출부가 "데이터 없음"으로 오진한다
            print(f"[DataKeeper] PG query failed ({table}): {e}", file=sys.stderr)
            return []

    def _filter(self, rows, date_from, date_to, brand,
                campaign_id, channel, limit):
        """Client-side filtering for cache data."""
        result = rows
        if date_from:
            result = [r for r in result if r.get("date", "") >= date_from]
        if date_to:
            result = [r for r in result if r.get("date", "") <= date_to]
        if brand:
            result = [r for r in result if r.get("brand") == brand]
        if campaign_id:
            result = [r for r in result if r.get("campaign_id") == campaign_id]
        if channel:
            result = [r for r in result if r.get("channel") == channel]
        return result[:limit]

    def last_updated(self, table: str) -> str | None:
        """Get last update time (checks NAS first, then local)."""
        for cache_dir in [NAS_CACHE_DIR, CACHE_DIR]:
            path = os.path.join(cache_dir, f"{table}.json")
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                return datetime.fromtimestamp(mtime).isoformat()
        return None

    def is_fresh(self, table: str, max_age_hours: int = 14) -> bool:
        """Check if any cache is fresh enough (default: within 14 hours for 2x/day)."""
        for cache_dir in [NAS_CACHE_DIR, CACHE_DIR]:
            path = os.path.join(cache_dir, f"{table}.json")
            if os.path.exists(path):
                age = time.time() - os.path.getmtime(path)
                if age < max_age_hours * 3600:
                    return True
        return False

    def status(self) -> dict:
        """Get status of all tables (checks NAS and local)."""
        result = {}
        for table in VALID_TABLES:
            found = False
            for label, cache_dir in [("nas", NAS_CACHE_DIR), ("local", CACHE_DIR)]:
                path = os.path.join(cache_dir, f"{table}.json")
                if os.path.exists(path):
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    try:
                        with open(path, "r") as f:
                            rows = json.load(f)
                        dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
                        result[table] = {
                            "rows": len(rows),
                            "date_range": f"{dates[0]}~{dates[-1]}" if dates else "?",
                            "updated": mtime.isoformat(),
                            "source": label,
                        }
                        found = True
                        break
                    except Exception:
                        pass
            if not found:
                result[table] = {"rows": 0, "cached": False}
        return result


def query_rows(params: dict, max_rows: int | None = None, *,
               token: str | None = None, timeout: int = 60) -> list[dict]:
    """GET /query/ 를 next_offset 이 null 이 될 때까지 이어 읽는다.

    max_rows 가 있으면 그 수까지만 읽고, 행이 더 남았으면 stderr 에 남긴다.
    429·503 은 기다렸다 다시 묻고, 그 밖의 실패는 예외로 올린다 — 일부 장만 받은 결과는 돌려주지 않는다.
    올리는 실패는 FAILED_READS 에도 남긴다 — 호출부가 예외를 삼켜도 출력 관문이 본다.
    장 사이에 새 행이 앞에 끼면 offset 이 밀려 같은 행이 다시 오므로 id 로 한 번만 담는다.
    """
    tok = token or DK_TOKEN
    auth = ({"headers": {"Authorization": f"Bearer {tok}"}} if tok
            else {"auth": (ORBITOOLS_USER, ORBITOOLS_PASS)})
    rows, seen, offset = [], set(), 0
    while True:
        want = PAGE_ROWS if max_rows is None else min(PAGE_ROWS, max_rows - len(rows))
        try:
            body = _query_page({**params, "limit": want, "offset": offset}, auth, timeout)
        except Exception as e:
            FAILED_READS.append((params.get("table"), str(e)))
            raise
        for r in body.get("rows", []):
            rid = r.get("id")
            if rid is not None:
                if rid in seen:
                    continue
                seen.add(rid)
            rows.append(r)
        nxt = body.get("next_offset")
        if nxt is None:
            return rows
        if max_rows is not None and len(rows) >= max_rows:
            print(f"[DataKeeper] {params.get('table')}: limit {max_rows} 에서 멈췄다 — 행이 더 있다",
                  file=sys.stderr)
            return rows
        offset = nxt
        time.sleep(PAGE_GAP_SEC)


def table_counts(*, token: str | None = None, timeout: int = 60) -> dict[str, int]:
    """GET /tables/ 한 번으로 표마다 전체 행 수 — 행을 읽어 세면 한도(1만)에서 멈춰 큰 표가 1만으로 보인다."""
    tok = token or DK_TOKEN
    auth = ({"headers": {"Authorization": f"Bearer {tok}"}} if tok
            else {"auth": (ORBITOOLS_USER, ORBITOOLS_PASS)})
    body = _query_page({}, auth, timeout, path="/tables/")
    tables = body.get("tables") or (body.get("data") or {}).get("tables") or {}
    return {name: (meta or {}).get("count") for name, meta in tables.items()}


def _query_page(params: dict, auth: dict, timeout: int, path: str = "/query/") -> dict:
    for attempt in range(1, MAX_TRIES + 1):
        r = requests.get(f"{ORBITOOLS_BASE}{path}", params=params, timeout=timeout, **auth)
        if r.status_code not in RETRY_STATUS or attempt == MAX_TRIES:
            r.raise_for_status()
            return r.json()
        try:
            wait = int(r.headers.get("Retry-After", ""))
        except ValueError:
            wait = PAGE_GAP_SEC * 2 ** attempt
        print(f"[DataKeeper] {params.get('table', path)} offset={params.get('offset')}: HTTP {r.status_code}, "
              f"{wait}s 뒤 다시 묻는다 ({attempt}/{MAX_TRIES - 1})", file=sys.stderr)
        time.sleep(wait)
