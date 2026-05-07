#!/usr/bin/env python3
"""
Rakuten RMS API client for Order Management API v2.

Auth: ESA Base64(serviceSecret:licenseKey)
Content-Type: application/json;charset=UTF-8

Flow:
  1. searchOrder  -> returns orderNumberList
  2. getOrder     -> takes orderNumberList, returns full order details
"""
import json
import requests
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


JST = timezone(timedelta(hours=9))


class RakutenRMSClient:
    def __init__(self, config_path: str):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"RMS config not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg: Dict[str, Any] = json.load(f)
        self.base = self.cfg.get("base_url", "").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json;charset=UTF-8"})
        auth = self.cfg.get("auth") or {}
        if auth.get("type") == "header":
            self.session.headers.update({auth.get("header_name"): auth.get("value")})

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base}{path}"

    def search_order_numbers(self, days: int = 30, order_progress: List[int] = None) -> List[str]:
        """Call searchOrder in 7-day chunks to get all order numbers (API returns max 30 per call)."""
        now = datetime.now(JST)
        all_numbers: List[str] = []
        seen: set = set()
        chunk_days = 7
        for offset in range(0, days, chunk_days):
            chunk_end = now - timedelta(days=offset)
            chunk_start = now - timedelta(days=min(offset + chunk_days, days))
            body: Dict[str, Any] = {
                "dateType": 1,
                "startDatetime": chunk_start.strftime("%Y-%m-%dT%H:%M:%S+0900"),
                "endDatetime": chunk_end.strftime("%Y-%m-%dT%H:%M:%S+0900"),
            }
            if order_progress:
                body["orderProgressList"] = order_progress
            resp = self.session.post(self._url("/es/2.0/order/searchOrder"), json=body)
            resp.raise_for_status()
            data = resp.json()
            for num in (data.get("orderNumberList") or []):
                if num not in seen:
                    seen.add(num)
                    all_numbers.append(num)
        return all_numbers

    def get_orders(self, order_numbers: List[str]) -> List[Dict[str, Any]]:
        """Call getOrder for a batch of order numbers (max 100 per request)."""
        orders = []
        for i in range(0, len(order_numbers), 100):
            batch = order_numbers[i:i + 100]
            body = {"orderNumberList": batch, "version": 3}
            resp = self.session.post(self._url("/es/2.0/order/getOrder"), json=body)
            resp.raise_for_status()
            data = resp.json()
            orders.extend(data.get("OrderModelList") or [])
        return orders

    def list_orders(self, days: int = 30, order_progress: List[int] = None) -> List[Dict[str, Any]]:
        """Convenience: search + fetch full order details."""
        numbers = self.search_order_numbers(days=days, order_progress=order_progress)
        if not numbers:
            return []
        return self.get_orders(numbers)

    def update_order_status(self, order_number: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        body = payload or self.cfg.get("delivered_payload") or {"orderProgress": 5}
        body = dict(body)
        body["orderNumber"] = order_number
        resp = self.session.post(self._url("/es/2.0/order/updateOrderProgress"), json=body)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code}
