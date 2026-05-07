#!/usr/bin/env python3
"""
Carrier delivery status checker.

Supported carriers:
  1001 - ヤマト運輸 (Yamato)
  1002 - 佐川急便 (Sagawa)
  1003 - 日本郵便 (Japan Post)
"""
import re
import requests

TIMEOUT = 10

# Rakuten carrier codes
CARRIER_JAPANPOST = "1003"
CARRIER_YAMATO = "1001"
CARRIER_SAGAWA = "1002"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})


def _check_japanpost(tracking_number: str) -> tuple[str | None, str | None]:
    """Returns (status, delivery_date_str). status: 'delivered'|'in_transit'|'not_found'|None"""
    url = "https://trackings.post.japanpost.jp/services/srv/search/direct"
    try:
        r = _SESSION.get(url, params={"reqCodeNo1": tracking_number, "locale": "ja"}, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text
        if "お問い合わせ番号が見つかりません" in text:
            return "not_found", None
        # Extract date+status pairs: YYYY/MM/DD HH:MM ... STATUS
        pairs = re.findall(
            r"(\d{4}/\d{2}/\d{2})\s+\d{2}:\d{2}\s*</td>\s*<td[^>]*>\s*([^<]{2,20})",
            text,
        )
        if pairs:
            for date_str, status in reversed(pairs):
                if "配達完了" in status or "お届け済み" in status:
                    return "delivered", date_str
            return "in_transit", None
        return "in_transit", None
    except Exception:
        return None, None


def _check_yamato(tracking_number: str) -> tuple[str | None, str | None]:
    url = "https://jizen.kuronekoyamato.co.jp/jizen/servlet/crjz.b.NQ0010"
    try:
        r = _SESSION.get(url, params={"id": tracking_number}, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text
        if "配達完了" in text or "お届け済み" in text:
            m = re.search(r"(\d{4}/\d{2}/\d{2})", text)
            return "delivered", (m.group(1) if m else None)
        if "該当する荷物" in text or "見つかりません" in text:
            return "not_found", None
        return "in_transit", None
    except Exception:
        return None, None


def _check_sagawa(tracking_number: str) -> tuple[str | None, str | None]:
    url = "https://k2k.sagawa-exp.co.jp/p/web/okurijosearch.do"
    try:
        r = _SESSION.post(url, data={"okurijoNo": tracking_number}, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text
        if "配達完了" in text or "お届け済み" in text:
            m = re.search(r"(\d{4}/\d{2}/\d{2}|\d{4}-\d{2}-\d{2})", text)
            return "delivered", (m.group(1) if m else None)
        if "見つかりません" in text or "存在しません" in text:
            return "not_found", None
        return "in_transit", None
    except Exception:
        return None, None


def check_delivered(carrier_code: str, tracking_number: str) -> bool | None:
    """Returns True if delivered, False if in transit / not found, None if error."""
    result = check_delivered_with_date(carrier_code, tracking_number)
    return result[0]


def check_delivered_with_date(carrier_code: str, tracking_number: str) -> tuple[bool | None, str | None]:
    """Returns (delivered: bool|None, delivery_date: str|None)."""
    if not tracking_number:
        return None, None
    if carrier_code == CARRIER_JAPANPOST:
        status, date = _check_japanpost(tracking_number)
    elif carrier_code == CARRIER_YAMATO:
        status, date = _check_yamato(tracking_number)
    elif carrier_code == CARRIER_SAGAWA:
        status, date = _check_sagawa(tracking_number)
    else:
        return None, None
    if status is None:
        return None, None
    return (status == "delivered"), (date if status == "delivered" else None)


def get_tracking_info(order: dict) -> list[dict]:
    """Extract list of {carrier_code, tracking_number} from an RMS order."""
    result = []
    for pkg in (order.get("PackageModelList") or []):
        for s in (pkg.get("ShippingModelList") or []):
            code = s.get("deliveryCompany") or ""
            number = s.get("shippingNumber") or ""
            if code and number:
                result.append({"carrier_code": code, "tracking_number": number})
    return result
