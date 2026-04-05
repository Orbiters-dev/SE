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

VALID_TABLES = [
    "shopify_orders_daily", "shopify_orders_sku_daily",
    "amazon_sales_daily", "amazon_sales_sku_daily",
    "amazon_ads_daily", "amazon_ads_search_terms", "amazon_ads_keywords",
    "amazon_campaigns", "amazon_brand_analytics", "amazon_sqp_brand", "amazon_autocomplete_daily",
    "meta_ads_daily", "meta_campaigns",
    "google_ads_daily", "google_ads_search_terms",
    "ga4_daily", "klaviyo_daily",
    "gsc_daily", "dataforseo_keywords",
    "content_posts", "content_metrics_daily", "influencer_orders",
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
            channel: str = None, limit: int = 10000) -> list[dict]:
        """Get rows from Data Keeper.

        Default: PG API first, NAS cache fallback, local cache last resort.
        If prefer_cache=True: NAS cache first, local cache, PG last.
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
        params = {"table": table, "limit": limit}
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
            r = requests.get(
                f"{ORBITOOLS_BASE}/query/",
                params=params,
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("rows", [])
        except Exception:
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
