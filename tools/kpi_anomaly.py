"""
kpi_anomaly.py - Lightweight anomaly detection for KPI metrics.

Phase 1: IQR + Z-score (stdlib only, no PyOD dependency).
Seasonal adjustments for known events (BFCM Nov, Prime Day Jul).

Usage:
    from kpi_anomaly import detect_anomalies, detect_mom_anomalies

    anomalies = detect_anomalies(
        {"2026-01": 45000, "2026-02": 47000, "2026-03": 142000},
        metric_name="amazon_ads_spend"
    )
"""

import math
from typing import Optional


# ── Seasonal Adjustment Factors ──────────────────────────────────────────────
# From kpi-data-taxonomy.md section 8: known seasonal spikes

SEASONAL_MULTIPLIERS = {
    # month_num: allowed_multiplier (how much above normal is OK)
    7: 1.5,   # Prime Day (Amazon spike 30-50%)
    11: 2.0,  # BFCM (50-100% spike is normal)
    12: 1.3,  # Holiday tail
}


# ── Ad Spend Sanity Ranges (from kpi-data-taxonomy.md section 8) ─────────────

SPEND_RANGES = {
    "amazon_ads": {"min": 30_000, "max": 150_000, "label": "Amazon Ads Monthly"},
    "meta_ads": {"min": 5_000, "max": 60_000, "label": "Meta Ads Monthly"},
    "google_ads": {"min": 3_000, "max": 30_000, "label": "Google Ads Monthly"},
}


# ── Core Detection Functions ─────────────────────────────────────────────────

def _iqr_bounds(values: list[float], multiplier: float = 1.5) -> tuple[float, float]:
    """Calculate IQR-based lower/upper bounds."""
    if len(values) < 4:
        return float('-inf'), float('inf')

    sorted_v = sorted(values)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[3 * n // 4]
    iqr = q3 - q1
    return q1 - multiplier * iqr, q3 + multiplier * iqr


def _zscore(value: float, values: list[float]) -> float:
    """Calculate Z-score for a single value against a series."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return (value - mean) / std


def detect_anomalies(
    metric_series: dict[str, float],
    metric_name: str = "",
    iqr_multiplier: float = 1.5,
    zscore_threshold: float = 2.5,
    seasonal: bool = True,
) -> list[dict]:
    """
    Detect anomalies in a monthly metric series.

    Args:
        metric_series: {"2026-01": 45000, "2026-02": 47000, ...}
        metric_name: Name for reporting
        iqr_multiplier: IQR fence multiplier (default 1.5)
        zscore_threshold: Z-score threshold (default 2.5)
        seasonal: Apply seasonal adjustment factors

    Returns:
        List of anomaly dicts:
        [{"month": "2026-03", "value": 142000, "expected_range": [35000, 55000],
          "zscore": 4.2, "type": "spike", "metric": "amazon_ads_spend"}]
    """
    if len(metric_series) < 3:
        return []  # not enough data points

    months = sorted(metric_series.keys())
    values = [metric_series[m] for m in months]

    lower, upper = _iqr_bounds(values, iqr_multiplier)
    anomalies = []

    for month, value in zip(months, values):
        # Apply seasonal adjustment
        adj_upper = upper
        adj_lower = lower
        if seasonal:
            try:
                month_num = int(month.split("-")[1])
                mult = SEASONAL_MULTIPLIERS.get(month_num, 1.0)
                adj_upper *= mult
            except (IndexError, ValueError):
                pass

        z = _zscore(value, values)

        if value > adj_upper or value < adj_lower:
            if abs(z) >= zscore_threshold:
                anomalies.append({
                    "month": month,
                    "value": round(value, 2),
                    "expected_range": [round(lower, 2), round(adj_upper, 2)],
                    "zscore": round(z, 2),
                    "type": "spike" if value > adj_upper else "dip",
                    "metric": metric_name,
                })

    return anomalies


def detect_mom_anomalies(
    metric_series: dict[str, float],
    metric_name: str = "",
    spike_threshold: float = 0.50,   # 50% MoM increase
    dip_threshold: float = -0.30,    # 30% MoM decrease
    seasonal: bool = True,
) -> list[dict]:
    """
    Detect month-over-month growth anomalies.

    Based on kpi-data-taxonomy.md section 8:
    - MoM > 50% or < -30%: Investigate
    - BFCM exception: Nov MoM spike ~50-100% is normal
    - Prime Day exception: Jul Amazon spike ~30-50% is normal
    """
    if len(metric_series) < 2:
        return []

    months = sorted(metric_series.keys())
    anomalies = []

    for i in range(1, len(months)):
        prev_val = metric_series[months[i - 1]]
        curr_val = metric_series[months[i]]

        if prev_val == 0:
            continue

        mom = (curr_val - prev_val) / abs(prev_val)

        # Seasonal exception
        effective_spike = spike_threshold
        effective_dip = dip_threshold
        if seasonal:
            try:
                month_num = int(months[i].split("-")[1])
                if month_num == 11:  # BFCM
                    effective_spike = 1.0  # up to 100% MoM is OK
                elif month_num == 7:  # Prime Day
                    effective_spike = 0.50  # up to 50% is OK
                elif month_num == 1:  # Jan post-holiday dip
                    effective_dip = -0.50  # up to 50% dip is OK
                elif month_num == 12:  # Dec post-BFCM normalization
                    effective_dip = -0.40
            except (IndexError, ValueError):
                pass

        if mom > effective_spike or mom < effective_dip:
            anomalies.append({
                "month": months[i],
                "prev_month": months[i - 1],
                "value": round(curr_val, 2),
                "prev_value": round(prev_val, 2),
                "mom_change": round(mom * 100, 1),
                "type": "spike" if mom > 0 else "dip",
                "metric": metric_name,
            })

    return anomalies


def check_spend_sanity(
    monthly_spend: dict[str, float],
    platform: str,
) -> list[dict]:
    """
    Check if monthly ad spend falls within expected ranges.

    Args:
        monthly_spend: {"2026-01": 85000, ...}
        platform: "amazon_ads" | "meta_ads" | "google_ads"

    Returns:
        List of warnings for out-of-range months.
    """
    if platform not in SPEND_RANGES:
        return []

    bounds = SPEND_RANGES[platform]
    warnings = []

    for month, spend in sorted(monthly_spend.items()):
        if spend < bounds["min"]:
            warnings.append({
                "month": month,
                "value": round(spend, 2),
                "expected_min": bounds["min"],
                "expected_max": bounds["max"],
                "type": "below_minimum",
                "metric": bounds["label"],
            })
        elif spend > bounds["max"]:
            warnings.append({
                "month": month,
                "value": round(spend, 2),
                "expected_min": bounds["min"],
                "expected_max": bounds["max"],
                "type": "above_maximum",
                "metric": bounds["label"],
            })

    return warnings
