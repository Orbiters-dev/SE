"""
Amazon Ads API Guard Rails
===========================
Prevents recurring API mistakes documented in mistakes.md M-021 through M-027.

Usage:
    from amazon_api_guards import (
        validate_report_columns,    # M-021: no 'date' with SUMMARY
        validate_groupby,           # M-022: keyword report groupBy
        ensure_string_ids,          # M-023: campaignId/adGroupId must be str
        wrap_targeting_clauses,     # M-024: targets PUT wrapper
        normalize_state_filter,     # M-025: state filter uppercase
        validate_bulk_response,     # M-027: check individual item status
    )
"""

import logging

logger = logging.getLogger(__name__)


# ── M-021: SUMMARY 리포트에서 date 컬럼 제거 ────────────────────────

def validate_report_columns(time_unit: str, columns: list[str]) -> list[str]:
    """Remove 'date' column when timeUnit is SUMMARY (M-021).

    >>> validate_report_columns("SUMMARY", ["date", "impressions", "clicks"])
    ['impressions', 'clicks']
    >>> validate_report_columns("DAILY", ["date", "impressions"])
    ['date', 'impressions']
    """
    if time_unit.upper() == "SUMMARY" and "date" in columns:
        logger.warning("M-021: Removed 'date' column (not available with timeUnit=SUMMARY)")
        return [c for c in columns if c != "date"]
    return columns


# ── M-022: keyword report groupBy 강제 ──────────────────────────────

VALID_KEYWORD_GROUPBY = ["adGroup"]

def validate_groupby(report_type: str, group_by: list[str]) -> list[str]:
    """Force groupBy to ["adGroup"] for keyword reports (M-022).

    >>> validate_groupby("keywords", ["keyword"])
    ['adGroup']
    >>> validate_groupby("campaigns", ["campaign"])
    ['campaign']
    """
    if report_type.lower() in ("keywords", "keyword"):
        invalid = [g for g in group_by if g not in VALID_KEYWORD_GROUPBY]
        if invalid:
            logger.warning(
                f"M-022: Changed groupBy from {group_by} to {VALID_KEYWORD_GROUPBY} "
                f"(keyword report only supports adGroup)"
            )
            return VALID_KEYWORD_GROUPBY
    return group_by


# ── M-023: ID 필드 string 변환 ──────────────────────────────────────

ID_FIELDS = {"campaignId", "adGroupId", "keywordId", "targetId", "adId"}

def ensure_string_ids(payload: dict) -> dict:
    """Convert int ID fields to str recursively (M-023).

    >>> ensure_string_ids({"campaignId": 123, "bid": 1.5})
    {'campaignId': '123', 'bid': 1.5}
    """
    if isinstance(payload, dict):
        result = {}
        for k, v in payload.items():
            if k in ID_FIELDS and isinstance(v, (int, float)):
                logger.warning(f"M-023: Converted {k}={v} from {type(v).__name__} to str")
                result[k] = str(int(v))
            elif isinstance(v, (dict, list)):
                result[k] = ensure_string_ids(v)
            else:
                result[k] = v
        return result
    elif isinstance(payload, list):
        return [ensure_string_ids(item) for item in payload]
    return payload


# ── M-024: targets PUT wrapper ───────────────────────────────────────

def wrap_targeting_clauses(clauses: list | dict) -> dict:
    """Wrap in {"targetingClauses": [...]} if not already wrapped (M-024).

    >>> wrap_targeting_clauses([{"targetId": "123", "bid": 1.0}])
    {'targetingClauses': [{'targetId': '123', 'bid': 1.0}]}
    >>> wrap_targeting_clauses({"targetingClauses": [{"targetId": "123"}]})
    {'targetingClauses': [{'targetId': '123'}]}
    """
    if isinstance(clauses, dict) and "targetingClauses" in clauses:
        return clauses
    if isinstance(clauses, list):
        logger.warning("M-024: Wrapped clauses in targetingClauses wrapper")
        return {"targetingClauses": clauses}
    if isinstance(clauses, dict):
        logger.warning("M-024: Wrapped single clause in targetingClauses wrapper")
        return {"targetingClauses": [clauses]}
    return {"targetingClauses": clauses}


# ── M-025: state filter 대문자 변환 ──────────────────────────────────

def normalize_state_filter(states: list[str] | str) -> list[str]:
    """Uppercase all state values (M-025).

    >>> normalize_state_filter(["enabled", "paused"])
    ['ENABLED', 'PAUSED']
    >>> normalize_state_filter("enabled")
    ['ENABLED']
    """
    if isinstance(states, str):
        states = [states]
    result = [s.upper() for s in states]
    if result != [s for s in (states if isinstance(states, list) else [states])]:
        logger.warning(f"M-025: Uppercased state filter: {states} -> {result}")
    return result


# ── M-027: bulk response 개별 item 검증 ─────────────────────────────

def validate_bulk_response(
    response: list | dict,
    operation_name: str = "bulk_operation",
) -> tuple[list, list]:
    """Check each item's code/status field in bulk API response (M-027).

    Returns (successes, failures) where each is a list of items.

    >>> resp = [{"code": "SUCCESS", "keywordId": "1"}, {"code": "INVALID", "keywordId": "2"}]
    >>> ok, fail = validate_bulk_response(resp, "add_keyword")
    >>> len(ok), len(fail)
    (1, 1)
    """
    items = response if isinstance(response, list) else response.get("keywords", response.get("targetingClauses", [response]))

    successes = []
    failures = []

    for item in items:
        code = item.get("code", item.get("status", "UNKNOWN"))
        if code.upper() in ("SUCCESS", "OK", "CREATED", "UPDATED"):
            successes.append(item)
        else:
            failures.append(item)

    if failures:
        logger.warning(
            f"M-027: {operation_name} — {len(failures)}/{len(items)} items failed. "
            f"Codes: {[f.get('code', f.get('status', '?')) for f in failures]}"
        )

    return successes, failures


# ── Self-test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # M-021
    assert validate_report_columns("SUMMARY", ["date", "impressions"]) == ["impressions"]
    assert validate_report_columns("DAILY", ["date", "impressions"]) == ["date", "impressions"]

    # M-022
    assert validate_groupby("keywords", ["keyword"]) == ["adGroup"]
    assert validate_groupby("campaigns", ["campaign"]) == ["campaign"]

    # M-023
    assert ensure_string_ids({"campaignId": 123})["campaignId"] == "123"
    assert ensure_string_ids({"bid": 1.5})["bid"] == 1.5

    # M-024
    assert "targetingClauses" in wrap_targeting_clauses([{"targetId": "1"}])
    assert "targetingClauses" in wrap_targeting_clauses({"targetingClauses": [{"targetId": "1"}]})

    # M-025
    assert normalize_state_filter(["enabled"]) == ["ENABLED"]
    assert normalize_state_filter("paused") == ["PAUSED"]

    # M-027
    ok, fail = validate_bulk_response([
        {"code": "SUCCESS", "id": "1"},
        {"code": "INVALID_ARGUMENT", "id": "2"},
    ], "test")
    assert len(ok) == 1 and len(fail) == 1

    print("All amazon_api_guards tests passed.")
