"""
Influencer Collaboration E2E Flow Tester
=========================================
n8n 기반 인플루언서 협업 파이프라인 전체 플로우를 자율주행 스타일로 테스트.

3개 플로우:
  Flow 1: Influencer Gifting Application (메인 신청)
  Flow 2: Creator Profile Signup (크리에이터 프로필)
  Flow 3: Sample Request (수락 후 샘플 요청)

매 스텝마다 request/response 전체를 flight recorder에 기록하고,
스텝 간 변수 캡처 & 전달, HTML 리포트 자동 생성, 테스트 데이터 cleanup.

Usage:
    python tools/test_influencer_flow.py --run                  # 전체 3개 플로우
    python tools/test_influencer_flow.py --run --flow gifting   # 특정 플로우만
    python tools/test_influencer_flow.py --dry-run              # API 호출 없이 미리보기
    python tools/test_influencer_flow.py --run --no-cleanup     # 데이터 보존
    python tools/test_influencer_flow.py --status               # 환경변수 체크
    python tools/test_influencer_flow.py --results              # 마지막 결과 보기
"""

import os
import sys
import json
import time
import random
import string
import re
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# ─── Paths ──────────────────────────────────────────────────────────────────
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP = os.path.join(ROOT, ".tmp")
LOG_FILE = os.path.join(TMP, "influencer_flow_log.json")
REPORT_FILE = os.path.join(TMP, "influencer_flow_report.html")

os.makedirs(TMP, exist_ok=True)

# ─── Env loading ────────────────────────────────────────────────────────────
sys.path.insert(0, DIR)
try:
    from env_loader import load_env
    load_env()
except ImportError:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))

# ─── Config ─────────────────────────────────────────────────────────────────
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "appT2gLRR0PqMFgII")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_INBOUND_TABLE_ID", "tbloYjIEr5OtEppT0")
SHOPIFY_STORE = os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

REQUIRED_ENVS = {
    "N8N_INFLUENCER_WEBHOOK": "Flow 1 webhook",
    "N8N_CREATOR_AIRTABLE_WEBHOOK": "Flow 2 webhook",
    "N8N_GIFTING2_WEBHOOK": "Flow 3 webhook",
    "AIRTABLE_API_KEY": "Airtable verification",
    "SHOPIFY_SHOP": "Shopify Admin API",
    "SHOPIFY_ACCESS_TOKEN": "Shopify Admin API",
    "ORBITOOLS_URL": "PostgreSQL verification",
    "ORBITOOLS_USER": "Orbitools auth",
    "ORBITOOLS_PASS": "Orbitools auth",
}

TEST_EMAIL_DOMAIN = "test.orbiters.co.kr"

# ─── Output helpers ─────────────────────────────────────────────────────────
def log(msg):  print(msg)
def ok(msg):   print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def sep():     print("=" * 70)
def sep2():    print("-" * 70)


# ─── HTTP utility ───────────────────────────────────────────────────────────
def http_request(method, url, payload=None, headers=None, basic_auth=None, timeout=30):
    """urllib-based HTTP request. Returns (status_code, body_dict_or_str)."""
    _headers = {"Content-Type": "application/json"}
    if headers:
        _headers.update(headers)
    if basic_auth:
        import base64
        creds = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode()
        _headers["Authorization"] = f"Basic {creds}"

    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except urllib.error.URLError as e:
        return 0, str(e.reason)


# ═══════════════════════════════════════════════════════════════════════════
# FlowContext — State machine with variable capture & interpolation
# ═══════════════════════════════════════════════════════════════════════════

class FlowContext:
    def __init__(self, flow_id):
        self.flow_id = flow_id
        self.variables = {}
        self.flight_log = []
        self.step_results = []
        self.started_at = None
        self.finished_at = None
        self.status = "PENDING"

    def set(self, key, value):
        self.variables[key] = value

    def get(self, key, default=None):
        return self.variables.get(key, default)

    def interpolate(self, obj):
        """Recursively replace {{var}} in any nested dict/list/str."""
        if isinstance(obj, str):
            # Full-token replacement (preserves type: int, dict, etc.)
            m = re.fullmatch(r"\{\{(\w+)\}\}", obj.strip())
            if m:
                key = m.group(1)
                if key in self.variables:
                    return self.variables[key]
                env_val = os.getenv(key)
                if env_val is not None:
                    return env_val
                return obj  # leave as-is if not found
            # Partial replacement (always returns string)
            def _replace(match):
                key = match.group(1)
                if key in self.variables:
                    return str(self.variables[key])
                env_val = os.getenv(key)
                if env_val is not None:
                    return env_val
                return match.group(0)
            return re.sub(r"\{\{(\w+)\}\}", _replace, obj)
        elif isinstance(obj, dict):
            return {k: self.interpolate(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.interpolate(v) for v in obj]
        return obj

    def log_entry(self, entry):
        self.flight_log.append(entry)

    def summary(self):
        passed = sum(1 for r in self.step_results if r.get("status") == "PASS")
        failed = sum(1 for r in self.step_results if r.get("status") == "FAIL")
        skipped = sum(1 for r in self.step_results if r.get("status") == "SKIP")
        total = len(self.step_results)
        return {"passed": passed, "failed": failed, "skipped": skipped, "total": total}


def extract_value(data, path):
    """Extract value from response using dot-notation JSONPath-like syntax.

    Examples:
        "$"                         -> entire data
        "$.customers[0].id"         -> data["customers"][0]["id"]
        "$.records[0].fields.Status" -> nested access
    """
    if path == "$":
        return data
    if not path.startswith("$."):
        return data

    parts = path[2:].split(".")
    current = data
    for part in parts:
        # Handle array index: key[N]
        m = re.match(r"(\w+)\[(\d+)\]", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(current, dict):
                current = current.get(key, [])
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        if current is None:
            return None
    return current


# ═══════════════════════════════════════════════════════════════════════════
# Step Runners — Enhanced with flight recording
# ═══════════════════════════════════════════════════════════════════════════

def run_http_post(step, ctx):
    url = ctx.interpolate(step["url"])
    payload = ctx.interpolate(step.get("payload", {}))
    expect_status = step.get("expect_status", 200)

    log(f"  POST {url}")
    entry = {"request": {"method": "POST", "url": url, "body": payload}, "response": {}, "assertions": []}

    status, body = http_request("POST", url, payload=payload)
    entry["response"] = {"status": status, "body": body if isinstance(body, (dict, list)) else str(body)[:2000]}

    passed = True
    if status != expect_status:
        fail(f"Status {status} (expected {expect_status})")
        entry["assertions"].append({"check": "status_code", "expected": expect_status, "actual": status, "pass": False})
        passed = False
    else:
        ok(f"Status {status}")
        entry["assertions"].append({"check": "status_code", "expected": expect_status, "actual": status, "pass": True})

    # Capture values from response
    _do_captures(step, body, ctx, entry)

    return passed, entry


def run_http_get(step, ctx):
    url = ctx.interpolate(step["url"])
    expect_status = step.get("expect_status", 200)
    headers = ctx.interpolate(step.get("headers", {}))

    log(f"  GET {url}")
    entry = {"request": {"method": "GET", "url": url}, "response": {}, "assertions": []}

    status, body = http_request("GET", url, headers=headers if headers else None)
    entry["response"] = {"status": status, "body": body if isinstance(body, (dict, list)) else str(body)[:2000]}

    passed = True
    if status != expect_status:
        fail(f"Status {status} (expected {expect_status})")
        entry["assertions"].append({"check": "status_code", "expected": expect_status, "actual": status, "pass": False})
        passed = False
    else:
        ok(f"Status {status}")
        entry["assertions"].append({"check": "status_code", "expected": expect_status, "actual": status, "pass": True})

    _do_captures(step, body, ctx, entry)
    return passed, entry


def run_verify_airtable(step, ctx):
    base_id = ctx.interpolate(step.get("base_id", AIRTABLE_BASE_ID))
    table_id = ctx.interpolate(step.get("table_id", AIRTABLE_TABLE_ID))
    filter_field = step.get("filter_field", "Email")
    filter_value = ctx.interpolate(step.get("filter_value", ""))
    expect_exists = step.get("expect_exists", True)
    expect_fields = ctx.interpolate(step.get("expect_fields", {}))

    if not AIRTABLE_API_KEY:
        warn("AIRTABLE_API_KEY not set -- skipping")
        return None, {"skipped": "no AIRTABLE_API_KEY"}

    safe_value = filter_value.replace("'", "\\'")
    formula = urllib.parse.quote(f"{{{filter_field}}}='{safe_value}'")
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?filterByFormula={formula}&maxRecords=5"

    log(f"  Airtable: {base_id}/{table_id} where {filter_field}='{filter_value}'")
    entry = {"request": {"method": "GET", "url": url}, "response": {}, "assertions": []}

    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:300]
        fail(f"Airtable API error {e.code}: {err_body}")
        entry["response"] = {"status": e.code, "body": err_body}
        return False, entry

    records = data.get("records", [])
    entry["response"] = {"status": 200, "record_count": len(records),
                         "body": data if len(json.dumps(data)) < 5000 else {"records_count": len(records), "truncated": True}}

    passed = True
    if expect_exists and not records:
        fail(f"No record found in Airtable (expected exists)")
        entry["assertions"].append({"check": "record_exists", "expected": True, "actual": False, "pass": False})
        return False, entry
    elif not expect_exists and records:
        fail(f"Record found in Airtable (expected NOT exists)")
        entry["assertions"].append({"check": "record_not_exists", "expected": True, "actual": False, "pass": False})
        return False, entry
    elif expect_exists:
        ok(f"Record found ({len(records)} match)")
        entry["assertions"].append({"check": "record_exists", "expected": True, "actual": True, "pass": True})
        fields = records[0].get("fields", {})
        for field, expected in expect_fields.items():
            actual = fields.get(field)
            if actual == expected:
                ok(f"  Field '{field}' = {expected!r}")
                entry["assertions"].append({"check": f"field_{field}", "expected": expected, "actual": actual, "pass": True})
            else:
                fail(f"  Field '{field}': expected {expected!r}, got {actual!r}")
                entry["assertions"].append({"check": f"field_{field}", "expected": expected, "actual": actual, "pass": False})
                passed = False
    else:
        ok("No record in Airtable (as expected)")

    # Capture: always provide record data for capture
    capture_data = {"records": records}
    _do_captures(step, capture_data, ctx, entry)

    return passed, entry


def run_verify_shopify(step, ctx):
    resource = step.get("resource", "customer")
    filter_params = ctx.interpolate(step.get("filter", {}))
    expect_exists = step.get("expect_exists", True)
    expect_fields = ctx.interpolate(step.get("expect_fields", {}))

    if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
        warn("Shopify credentials not set -- skipping")
        return None, {"skipped": "no Shopify credentials"}

    entry = {"request": {}, "response": {}, "assertions": []}
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

    if resource == "customer":
        query = " ".join(f"{k}:{v}" for k, v in filter_params.items())
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/search.json?query={urllib.parse.quote(query)}"
        log(f"  Shopify customer search: {filter_params}")
        entry["request"] = {"method": "GET", "url": url}
        status, body = http_request("GET", url, headers=headers)
        entry["response"] = {"status": status, "body": body if isinstance(body, (dict, list)) else str(body)[:2000]}

        if status != 200:
            fail(f"Shopify API returned {status}")
            return False, entry

        customers = body.get("customers", []) if isinstance(body, dict) else []
        passed = True

        if expect_exists and not customers:
            fail("No Shopify customer found")
            entry["assertions"].append({"check": "customer_exists", "expected": True, "actual": False, "pass": False})
            passed = False
        elif not expect_exists and customers:
            fail("Shopify customer found (expected NOT exists)")
            entry["assertions"].append({"check": "customer_not_exists", "expected": True, "actual": False, "pass": False})
            passed = False
        elif expect_exists:
            ok(f"Shopify customer found (id={customers[0].get('id')})")
            entry["assertions"].append({"check": "customer_exists", "expected": True, "actual": True, "pass": True})
            c = customers[0]
            for field, expected in expect_fields.items():
                actual = c.get(field)
                if actual == expected:
                    ok(f"  Field '{field}' = {expected!r}")
                    entry["assertions"].append({"check": f"field_{field}", "expected": expected, "actual": actual, "pass": True})
                else:
                    fail(f"  Field '{field}': expected {expected!r}, got {actual!r}")
                    entry["assertions"].append({"check": f"field_{field}", "expected": expected, "actual": actual, "pass": False})
                    passed = False
        else:
            ok("No Shopify customer (as expected)")

        _do_captures(step, body, ctx, entry)
        return passed, entry

    elif resource == "metafield":
        customer_id = ctx.interpolate(step.get("customer_id", ""))
        if not customer_id:
            warn("No customer_id for metafield check")
            return None, {"skipped": "no customer_id"}

        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/{customer_id}/metafields.json"
        log(f"  Shopify metafields for customer {customer_id}")
        entry["request"] = {"method": "GET", "url": url}

        time.sleep(0.5)  # Shopify rate limit
        status, body = http_request("GET", url, headers=headers)
        entry["response"] = {"status": status, "body": body if isinstance(body, (dict, list)) else str(body)[:2000]}

        if status != 200:
            fail(f"Shopify metafields API returned {status}")
            return False, entry

        metafields = body.get("metafields", []) if isinstance(body, dict) else []
        expect_mf = step.get("expect_metafields", {})
        passed = True

        for ns_key, expected_val in expect_mf.items():
            parts = ns_key.split(".", 1)
            if len(parts) != 2:
                continue
            ns, key = parts
            found = None
            for mf in metafields:
                if mf.get("namespace") == ns and mf.get("key") == key:
                    found = mf.get("value")
                    break
            if found == expected_val:
                ok(f"  Metafield {ns_key} = {expected_val!r}")
                entry["assertions"].append({"check": f"metafield_{ns_key}", "expected": expected_val, "actual": found, "pass": True})
            else:
                fail(f"  Metafield {ns_key}: expected {expected_val!r}, got {found!r}")
                entry["assertions"].append({"check": f"metafield_{ns_key}", "expected": expected_val, "actual": found, "pass": False})
                passed = False

        _do_captures(step, body, ctx, entry)
        return passed, entry

    elif resource == "draft_order":
        customer_id = ctx.interpolate(step.get("customer_id", ""))
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/draft_orders.json?status=open&limit=10"
        log(f"  Shopify draft orders (searching for customer {customer_id})")
        entry["request"] = {"method": "GET", "url": url}

        time.sleep(0.5)
        status, body = http_request("GET", url, headers=headers)
        entry["response"] = {"status": status, "body": {"draft_orders_count": len(body.get("draft_orders", [])) if isinstance(body, dict) else 0}}

        if status != 200:
            fail(f"Shopify draft orders API returned {status}")
            return False, entry

        draft_orders = body.get("draft_orders", []) if isinstance(body, dict) else []
        # Find draft order for this customer
        matching = [d for d in draft_orders
                    if d.get("customer", {}).get("id") == customer_id
                    or str(d.get("customer", {}).get("id")) == str(customer_id)]

        passed = True
        expect_exists_do = step.get("expect_exists", True)
        if expect_exists_do and not matching:
            fail(f"No draft order found for customer {customer_id}")
            entry["assertions"].append({"check": "draft_order_exists", "expected": True, "actual": False, "pass": False})
            passed = False
        elif expect_exists_do and matching:
            do = matching[0]
            ok(f"Draft order found (id={do.get('id')})")
            entry["assertions"].append({"check": "draft_order_exists", "expected": True, "actual": True, "pass": True})
            # Check for pr/influencer-gifting tags
            tags = do.get("tags", "")
            if "pr" in tags and "influencer-gifting" in tags:
                ok(f"  Tags contain 'pr' and 'influencer-gifting'")
                entry["assertions"].append({"check": "tags", "expected": "pr,influencer-gifting", "actual": tags, "pass": True})
            else:
                fail(f"  Tags missing: got '{tags}'")
                entry["assertions"].append({"check": "tags", "expected": "pr,influencer-gifting", "actual": tags, "pass": False})
                passed = False

            # Provide body for captures
            _do_captures(step, {"draft_orders": matching}, ctx, entry)
        return passed, entry

    else:
        warn(f"Unknown resource type: {resource}")
        return None, {"skipped": f"unknown resource {resource}"}


def run_verify_postgres(step, ctx):
    endpoint = ctx.interpolate(step.get("endpoint", ""))
    filter_params = ctx.interpolate(step.get("filter", {}))
    expect_exists = step.get("expect_exists", True)

    if not ORBITOOLS_URL:
        warn("ORBITOOLS_URL not set -- skipping")
        return None, {"skipped": "no ORBITOOLS_URL"}

    qs = urllib.parse.urlencode(filter_params)
    url = f"{ORBITOOLS_URL}{endpoint}?{qs}"
    log(f"  PostgreSQL (via orbitools): {endpoint} filter={filter_params}")
    entry = {"request": {"method": "GET", "url": url}, "response": {}, "assertions": []}

    auth = (ORBITOOLS_USER, ORBITOOLS_PASS) if ORBITOOLS_USER else None
    status, body = http_request("GET", url, basic_auth=auth)
    entry["response"] = {"status": status, "body": body if isinstance(body, (dict, list)) else str(body)[:2000]}

    if status not in (200, 201):
        fail(f"orbitools API returned {status}")
        entry["assertions"].append({"check": "api_status", "expected": "200", "actual": str(status), "pass": False})
        return False, entry

    results = body if isinstance(body, list) else body.get("results", body.get("data", []))
    count = len(results) if isinstance(results, list) else 0

    passed = True
    if expect_exists and not results:
        fail("No record found in PostgreSQL")
        entry["assertions"].append({"check": "record_exists", "expected": True, "actual": False, "pass": False})
        passed = False
    elif expect_exists:
        ok(f"Record found in PostgreSQL ({count} rows)")
        entry["assertions"].append({"check": "record_exists", "expected": True, "actual": True, "pass": True})

    _do_captures(step, body, ctx, entry)
    return passed, entry


def run_wait(step, ctx):
    seconds = step.get("seconds", 5)
    log(f"  Waiting {seconds}s for async processing...")
    time.sleep(seconds)
    ok(f"Waited {seconds}s")
    return True, {"waited_seconds": seconds, "assertions": []}


def _do_captures(step, body, ctx, entry):
    """Extract capture values from response body into context."""
    captures = step.get("capture", {})
    if not captures or not isinstance(body, (dict, list)):
        return
    captured = {}
    for var_name, json_path in captures.items():
        try:
            value = extract_value(body, json_path)
            ctx.set(var_name, value)
            captured[var_name] = value
            info(f"  Captured {var_name} = {str(value)[:80]}")
        except Exception as e:
            captured[var_name] = f"CAPTURE_ERROR: {e}"
    entry["captures"] = captured


STEP_RUNNERS = {
    "http_post":        run_http_post,
    "http_get":         run_http_get,
    "verify_airtable":  run_verify_airtable,
    "verify_shopify":   run_verify_shopify,
    "verify_postgres":  run_verify_postgres,
    "wait":             run_wait,
}


# ═══════════════════════════════════════════════════════════════════════════
# Flow Definitions — Built-in 3 flows
# ═══════════════════════════════════════════════════════════════════════════

def _make_test_email():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"flow_test_{ts}_{rand}@{TEST_EMAIL_DOMAIN}"


def flow_gifting():
    """Flow 1: Influencer Gifting Application (Main Entry)."""
    test_email = _make_test_email()
    return {
        "flow_id": "influencer_gifting",
        "flow_name": "Flow 1: Influencer Gifting Application",
        "description": "Form submit -> n8n -> Airtable + Shopify Customer + Metafields + PostgreSQL",
        "test_email": test_email,
        "steps": [
            {
                "step_id": "submit_gifting_form",
                "type": "http_post",
                "name": "POST to n8n influencer-gifting webhook",
                "url": "{{N8N_INFLUENCER_WEBHOOK}}",
                "payload": {
                    "form_type": "influencer_gifting",
                    "submitted_at": "{{now_iso}}",
                    "personal_info": {
                        "full_name": "FlowTest Runner",
                        "email": test_email,
                        "phone": "+12025551234",
                        "instagram": "@flowtest_ig",
                        "tiktok": "@flowtest_tk",
                    },
                    "baby_info": {
                        "child_1": {"birthday": "2025-06-15", "age_months": 9},
                        "child_2": None,
                    },
                    "selected_products": [
                        {
                            "product_key": "ppsu_straw",
                            "product_id": 8288579256642,
                            "variant_id": 45018985431362,
                            "title": "Grosmimi PPSU Straw Cup 10oz",
                            "color": "White",
                            "price": "$24.90",
                        }
                    ],
                    "shipping_address": {
                        "street": "123 FlowTest St",
                        "apt": "",
                        "city": "Los Angeles",
                        "state": "CA",
                        "zip": "90001",
                        "country": "US",
                    },
                    "terms_accepted": True,
                    "shopify_customer_id": None,
                },
                "expect_status": 200,
                "capture": {"webhook_response": "$"},
            },
            {
                "step_id": "wait_n8n_gifting",
                "type": "wait",
                "name": "Wait for n8n async processing",
                "seconds": 8,
            },
            {
                "step_id": "verify_airtable_gifting",
                "type": "verify_airtable",
                "name": "Verify Airtable record created",
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {"Status": "New"},
                "capture": {
                    "airtable_record_id": "$.records[0].id",
                    "airtable_name": "$.records[0].fields.Name",
                },
            },
            {
                "step_id": "verify_shopify_customer_gifting",
                "type": "verify_shopify",
                "name": "Verify Shopify customer exists",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
            },
            {
                "step_id": "verify_metafields_gifting",
                "type": "verify_shopify",
                "name": "Verify influencer metafields (instagram/tiktok)",
                "resource": "metafield",
                "customer_id": "{{shopify_customer_id}}",
                "expect_metafields": {
                    "influencer.instagram": "@flowtest_ig",
                    "influencer.tiktok": "@flowtest_tk",
                },
            },
            {
                "step_id": "verify_postgres_gifting",
                "type": "verify_postgres",
                "name": "Verify PostgreSQL record (orbitools)",
                "endpoint": "/api/onzenna/creators/",
                "filter": {"email": test_email},
                "expect_exists": True,
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_creator():
    """Flow 2: Creator Profile Signup."""
    test_email = _make_test_email()
    return {
        "flow_id": "creator_profile",
        "flow_name": "Flow 2: Creator Profile Signup",
        "description": "Creator profile form -> n8n -> Airtable + Shopify Metafields(onzenna_creator) + PostgreSQL",
        "test_email": test_email,
        "steps": [
            {
                "step_id": "submit_creator_profile",
                "type": "http_post",
                "name": "POST to n8n creator-to-airtable webhook",
                "url": "{{N8N_CREATOR_AIRTABLE_WEBHOOK}}",
                "payload": {
                    "customer_name": "FlowTest Creator",
                    "customer_email": test_email,
                    "customer_id": None,
                    "submitted_at": "{{now_iso}}",
                    "survey_data": {
                        "primary_platform": "instagram",
                        "primary_handle": "@flowtest_creator",
                        "following_size": "1k_10k",
                        "content_type": ["product_reviews", "lifestyle"],
                        "hashtags": "#flowtest #grosmimi",
                        "other_platforms": ["tiktok"],
                        "other_handles": ["@flowtest_tk"],
                        "has_brand_partnerships": "no_but_interested",
                        "brand_names": "",
                    },
                    "core_signup_data": {
                        "journey_stage": "new_mom_0_12m",
                        "baby_birth_month": "2025-06",
                        "has_other_children": False,
                        "other_child_birth": None,
                        "third_child_birth": None,
                    },
                    "contact": {"phone": "+12025559876"},
                    "shipping_address": {
                        "address1": "456 Creator Ave",
                        "address2": "",
                        "city": "San Francisco",
                        "province": "CA",
                        "zip": "94102",
                        "country": "US",
                    },
                },
                "expect_status": 200,
                "capture": {"webhook_response": "$"},
            },
            {
                "step_id": "wait_n8n_creator",
                "type": "wait",
                "name": "Wait for n8n async processing (includes IG scrape)",
                "seconds": 10,
            },
            {
                "step_id": "verify_airtable_creator",
                "type": "verify_airtable",
                "name": "Verify Airtable Applicants record",
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {
                    "Name": "FlowTest Creator",
                    "Primary Platform": "instagram",
                    "Status": "New",
                },
                "capture": {
                    "airtable_record_id": "$.records[0].id",
                    "airtable_ig_handle": "$.records[0].fields.Instagram Handle",
                },
            },
            {
                "step_id": "verify_shopify_customer_creator",
                "type": "verify_shopify",
                "name": "Verify Shopify customer created/found",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
            },
            {
                "step_id": "verify_metafields_creator",
                "type": "verify_shopify",
                "name": "Verify onzenna_creator metafields",
                "resource": "metafield",
                "customer_id": "{{shopify_customer_id}}",
                "expect_metafields": {
                    "onzenna_creator.primary_platform": "instagram",
                    "onzenna_creator.primary_handle": "@flowtest_creator",
                    "onzenna_creator.following_size": "1k_10k",
                },
            },
            {
                "step_id": "verify_postgres_creator",
                "type": "verify_postgres",
                "name": "Verify PostgreSQL creator record",
                "endpoint": "/api/onzenna/creators/",
                "filter": {"email": test_email},
                "expect_exists": True,
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_sample():
    """Flow 3: Sample Request (after acceptance)."""
    test_email = _make_test_email()
    return {
        "flow_id": "sample_request",
        "flow_name": "Flow 3: Sample Request (Gifting2)",
        "description": "Accepted creator submits sample form -> n8n -> Shopify Customer + Draft Order + Airtable update",
        "test_email": test_email,
        "steps": [
            {
                "step_id": "submit_gifting2_form",
                "type": "http_post",
                "name": "POST to n8n gifting2-submit webhook",
                "url": "{{N8N_GIFTING2_WEBHOOK}}",
                "payload": {
                    "form_type": "influencer_gifting2",
                    "submitted_at": "{{now_iso}}",
                    "source": "inbound_pipeline",
                    "personal_info": {
                        "full_name": "FlowTest Sample",
                        "email": test_email,
                        "phone": "+12025557777",
                        "instagram": "@flowtest_sample",
                        "tiktok": "None",
                    },
                    "baby_info": {
                        "child_1": {"birthday": "2025-03-01", "age_months": 12},
                        "child_2": None,
                    },
                    "selected_products": [
                        {
                            "product_key": "ppsu_straw",
                            "product_id": 8288579256642,
                            "variant_id": 45018985431362,
                            "title": "Grosmimi PPSU Straw Cup 10oz",
                            "color": "White",
                            "price": "$24.90",
                        }
                    ],
                    "shipping_address": {
                        "street": "789 Sample Blvd",
                        "apt": "Unit 3",
                        "city": "Austin",
                        "state": "TX",
                        "zip": "73301",
                        "country": "US",
                    },
                    "terms_accepted": True,
                    "shopify_customer_id": None,
                    "airtable_email": test_email,
                },
                "expect_status": 200,
                "capture": {"webhook_response": "$"},
            },
            {
                "step_id": "wait_n8n_sample",
                "type": "wait",
                "name": "Wait for n8n async processing",
                "seconds": 10,
            },
            {
                "step_id": "verify_shopify_customer_sample",
                "type": "verify_shopify",
                "name": "Verify Shopify customer created",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
            },
            {
                "step_id": "verify_draft_order",
                "type": "verify_shopify",
                "name": "Verify draft order created (100% discount)",
                "resource": "draft_order",
                "customer_id": "{{shopify_customer_id}}",
                "expect_exists": True,
                "capture": {"draft_order_id": "$.draft_orders[0].id"},
            },
            {
                "step_id": "verify_airtable_updated",
                "type": "verify_airtable",
                "name": "Verify Airtable record updated (Sample Form Completed)",
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {},
                "capture": {
                    "airtable_record_id": "$.records[0].id",
                    "airtable_sample_completed": "$.records[0].fields.Sample Form Completed",
                },
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


FLOW_REGISTRY = {
    "gifting": flow_gifting,
    "creator": flow_creator,
    "sample": flow_sample,
}


# ═══════════════════════════════════════════════════════════════════════════
# Flow Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_flow(flow_spec, dry_run=False, wait_multiplier=1.0):
    """Execute an entire flow with full flight recording."""
    flow_id = flow_spec["flow_id"]
    ctx = FlowContext(flow_id)
    ctx.started_at = datetime.now().isoformat()
    ctx.set("now_iso", datetime.now().isoformat())
    ctx.set("test_email", flow_spec["test_email"])

    sep()
    log(f"FLOW: {flow_spec['flow_name']}")
    log(f"Test email: {flow_spec['test_email']}")
    log(f"Description: {flow_spec['description']}")
    sep()

    overall_pass = True
    steps = flow_spec["steps"]

    for i, step in enumerate(steps, 1):
        step_type = step.get("type")
        step_name = step.get("name", step_type)
        step_id = step.get("step_id", f"step_{i}")

        sep2()
        log(f"Step {i}/{len(steps)}: [{step_type}] {step_name}")

        if dry_run:
            resolved = ctx.interpolate(step)
            info(f"  DRY-RUN: would execute {step_type}")
            if step_type == "http_post":
                info(f"  URL: {resolved.get('url', '?')}")
                info(f"  Payload keys: {list(resolved.get('payload', {}).keys())}")
            elif step_type in ("verify_airtable", "verify_shopify", "verify_postgres"):
                info(f"  Config: {json.dumps({k: v for k, v in resolved.items() if k not in ('type', 'name', 'step_id', 'capture')}, default=str)[:200]}")
            elif step_type == "wait":
                adjusted = int(step.get("seconds", 5) * wait_multiplier)
                info(f"  Would wait {adjusted}s")
            ctx.step_results.append({"step_id": step_id, "name": step_name, "type": step_type, "status": "DRY-RUN"})
            continue

        # Apply wait multiplier
        if step_type == "wait":
            step = dict(step)
            step["seconds"] = int(step.get("seconds", 5) * wait_multiplier)

        runner = STEP_RUNNERS.get(step_type)
        if not runner:
            warn(f"Unknown step type: {step_type}")
            ctx.step_results.append({"step_id": step_id, "name": step_name, "type": step_type, "status": "SKIP"})
            continue

        start_time = time.monotonic()
        try:
            passed, entry = runner(step, ctx)
        except Exception as e:
            fail(f"Exception: {e}")
            passed = False
            entry = {"exception": str(e), "assertions": []}

        duration_ms = int((time.monotonic() - start_time) * 1000)
        status_str = "PASS" if passed else ("SKIP" if passed is None else "FAIL")

        result = {
            "step_id": step_id,
            "name": step_name,
            "type": step_type,
            "status": status_str,
            "started_at": datetime.now().isoformat(),
            "duration_ms": duration_ms,
        }
        result.update(entry)
        ctx.step_results.append(result)
        ctx.log_entry(result)

        if passed is False:
            overall_pass = False
            # Stop on failure by default
            if step.get("critical", True):
                warn(f"Critical step failed. Stopping flow.")
                break

        # Shopify rate limiting
        if step_type == "verify_shopify":
            time.sleep(0.5)

    ctx.finished_at = datetime.now().isoformat()
    ctx.status = "PASS" if overall_pass else ("DRY-RUN" if dry_run else "FAIL")

    sep()
    s = ctx.summary()
    log(f"FLOW RESULT: {ctx.status}  ({s['passed']}/{s['total']} passed, {s['failed']} failed, {s['skipped']} skipped)")
    sep()

    return ctx


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

def run_cleanup(cleanup_spec, ctx):
    """Delete test data created during the flow."""
    resolved = ctx.interpolate(cleanup_spec)
    test_email = resolved.get("test_email", "")

    # Safety: only delete test data
    if test_email and TEST_EMAIL_DOMAIN not in test_email:
        warn(f"SAFETY: Refusing to cleanup non-test email '{test_email}'")
        return

    log("\n  [CLEANUP]")

    # 1. Delete Airtable record
    record_id = resolved.get("airtable_record_id")
    if record_id and AIRTABLE_API_KEY and isinstance(record_id, str) and record_id.startswith("rec"):
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}/{record_id}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok(f"Airtable record {record_id} deleted")
        except Exception as e:
            warn(f"Airtable cleanup failed: {e}")
    else:
        info("  No Airtable record to clean up")

    # 2. Delete Shopify customer
    customer_id = resolved.get("shopify_customer_id")
    if customer_id and SHOPIFY_STORE and SHOPIFY_TOKEN:
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/{customer_id}.json"
        headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ok(f"Shopify customer {customer_id} deleted")
        except urllib.error.HTTPError as e:
            if e.code == 200 or e.code == 204:
                ok(f"Shopify customer {customer_id} deleted")
            else:
                warn(f"Shopify cleanup failed (HTTP {e.code}): {e.read().decode()[:200]}")
        except Exception as e:
            warn(f"Shopify cleanup failed: {e}")
    else:
        info("  No Shopify customer to clean up")

    # 3. PostgreSQL - log warning (no DELETE endpoint)
    if test_email:
        warn(f"PostgreSQL: manual cleanup needed for email '{test_email}' (no DELETE endpoint)")


# ═══════════════════════════════════════════════════════════════════════════
# HTML Report Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_html_report(all_contexts):
    """Generate a visual HTML report from all flow contexts."""
    total_duration = 0
    for ctx in all_contexts:
        for step in ctx.step_results:
            total_duration += step.get("duration_ms", 0)

    overall_pass = sum(1 for c in all_contexts if c.status == "PASS")
    overall_total = len(all_contexts)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Influencer Flow E2E Test Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1419; color: #e7e9ea; padding: 24px; }}
  .header {{ background: linear-gradient(135deg, #1a1f2e, #2d3748); border-radius: 12px; padding: 28px; margin-bottom: 24px; border: 1px solid #374151; }}
  .header h1 {{ font-size: 24px; color: #f0f6fc; margin-bottom: 8px; }}
  .header .meta {{ color: #8b949e; font-size: 14px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-left: 8px; }}
  .badge-pass {{ background: #1a3d2a; color: #3fb950; border: 1px solid #238636; }}
  .badge-fail {{ background: #3d1a1a; color: #f85149; border: 1px solid #da3633; }}
  .badge-skip {{ background: #3d3a1a; color: #d29922; border: 1px solid #9e6a03; }}
  .badge-dry {{ background: #1a2d3d; color: #58a6ff; border: 1px solid #1f6feb; }}
  .flow-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; margin-bottom: 20px; overflow: hidden; }}
  .flow-header {{ padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; cursor: pointer; background: #1c2128; }}
  .flow-header:hover {{ background: #21262d; }}
  .flow-title {{ font-size: 16px; font-weight: 600; }}
  .flow-body {{ padding: 0 20px 20px; }}
  .step {{ border: 1px solid #21262d; border-radius: 8px; margin-top: 12px; overflow: hidden; }}
  .step-header {{ padding: 10px 14px; display: flex; align-items: center; gap: 10px; font-size: 14px; background: #0d1117; }}
  .step-num {{ color: #8b949e; font-size: 12px; min-width: 50px; }}
  .step-type {{ background: #21262d; padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #8b949e; }}
  .duration {{ color: #8b949e; font-size: 12px; margin-left: auto; }}
  details {{ margin-top: 4px; }}
  summary {{ cursor: pointer; padding: 6px 14px; font-size: 13px; color: #58a6ff; }}
  summary:hover {{ color: #79c0ff; }}
  .detail-block {{ padding: 8px 14px; font-size: 13px; }}
  pre {{ background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; overflow-x: auto; font-size: 12px; color: #c9d1d9; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }}
  .assertion {{ padding: 4px 14px; font-size: 13px; }}
  .assertion-pass {{ color: #3fb950; }}
  .assertion-fail {{ color: #f85149; }}
  .timeline-bar {{ height: 6px; border-radius: 3px; margin-top: 4px; min-width: 4px; }}
  .timeline-pass {{ background: #238636; }}
  .timeline-fail {{ background: #da3633; }}
  .timeline-skip {{ background: #9e6a03; }}
  .captures {{ background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 14px; margin-top: 16px; }}
  .captures h3 {{ font-size: 14px; color: #8b949e; margin-bottom: 8px; }}
  .capture-row {{ display: flex; padding: 3px 0; font-size: 13px; }}
  .capture-key {{ color: #d2a8ff; min-width: 200px; }}
  .capture-val {{ color: #c9d1d9; word-break: break-all; }}
  .footer {{ text-align: center; color: #484f58; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="header">
  <h1>Influencer Flow E2E Test Report</h1>
  <div class="meta">
    Generated: {now_str} &nbsp;|&nbsp; Duration: {total_duration/1000:.1f}s &nbsp;|&nbsp;
    Flows: {overall_pass}/{overall_total} passed
    <span class="badge {'badge-pass' if overall_pass == overall_total else 'badge-fail'}">
      {'ALL PASS' if overall_pass == overall_total else f'{overall_total - overall_pass} FAILED'}
    </span>
  </div>
</div>
"""]

    for ctx in all_contexts:
        s = ctx.summary()
        status_class = "badge-pass" if ctx.status == "PASS" else ("badge-dry" if ctx.status == "DRY-RUN" else "badge-fail")

        html_parts.append(f"""
<div class="flow-card">
  <details open>
    <summary class="flow-header">
      <span class="flow-title">{ctx.flow_id}</span>
      <span class="badge {status_class}">{ctx.status}</span>
      <span class="duration">{s['passed']}/{s['total']} steps | {sum(r.get('duration_ms',0) for r in ctx.step_results)/1000:.1f}s</span>
    </summary>
    <div class="flow-body">
""")

        # Max duration for timeline scaling
        max_dur = max((r.get("duration_ms", 1) for r in ctx.step_results), default=1)

        for i, result in enumerate(ctx.step_results, 1):
            st = result.get("status", "?")
            st_class = "badge-pass" if st == "PASS" else ("badge-skip" if st in ("SKIP", "DRY-RUN") else "badge-fail")
            tl_class = "timeline-pass" if st == "PASS" else ("timeline-skip" if st in ("SKIP", "DRY-RUN") else "timeline-fail")
            dur = result.get("duration_ms", 0)
            bar_width = max(4, int(dur / max(max_dur, 1) * 200))

            html_parts.append(f"""
      <div class="step">
        <div class="step-header">
          <span class="step-num">Step {i}</span>
          <span class="step-type">{result.get('type', '?')}</span>
          <span>{result.get('name', '?')}</span>
          <span class="badge {st_class}" style="font-size:11px;padding:2px 8px;">{st}</span>
          <span class="duration">{dur}ms</span>
        </div>
        <div class="timeline-bar {tl_class}" style="width:{bar_width}px;margin-left:14px;"></div>
""")

            # Assertions
            for a in result.get("assertions", []):
                a_class = "assertion-pass" if a.get("pass") else "assertion-fail"
                mark = "PASS" if a.get("pass") else "FAIL"
                html_parts.append(f"""        <div class="assertion {a_class}">[{mark}] {a.get('check','?')}: expected={a.get('expected','?')}, actual={a.get('actual','?')}</div>\n""")

            # Request/Response expandable
            req = result.get("request", {})
            resp = result.get("response", {})
            captures = result.get("captures", {})

            if req:
                html_parts.append(f"""        <details><summary>Request</summary><div class="detail-block"><pre>{json.dumps(req, indent=2, ensure_ascii=False, default=str)[:3000]}</pre></div></details>\n""")
            if resp:
                html_parts.append(f"""        <details><summary>Response</summary><div class="detail-block"><pre>{json.dumps(resp, indent=2, ensure_ascii=False, default=str)[:3000]}</pre></div></details>\n""")
            if captures:
                html_parts.append(f"""        <details><summary>Captures</summary><div class="detail-block"><pre>{json.dumps(captures, indent=2, ensure_ascii=False, default=str)[:2000]}</pre></div></details>\n""")

            html_parts.append("      </div>\n")

        # Context variables
        if ctx.variables:
            html_parts.append("""      <div class="captures"><h3>Context Variables (Final State)</h3>\n""")
            for k, v in ctx.variables.items():
                val_str = json.dumps(v, default=str)[:120] if not isinstance(v, str) else v[:120]
                html_parts.append(f"""        <div class="capture-row"><span class="capture-key">{k}</span><span class="capture-val">{val_str}</span></div>\n""")
            html_parts.append("      </div>\n")

        html_parts.append("    </div>\n  </details>\n</div>\n")

    html_parts.append(f"""
<div class="footer">
  Influencer Flow E2E Tester | Generated {now_str}
</div>
</body>
</html>""")

    html = "".join(html_parts)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"\nHTML Report: {REPORT_FILE}")
    return REPORT_FILE


# ═══════════════════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════════════════

def cmd_status():
    """Check environment readiness."""
    sep()
    log("ENVIRONMENT STATUS")
    sep()
    all_ok = True
    for key, desc in REQUIRED_ENVS.items():
        val = os.getenv(key, "")
        if val:
            ok(f"{key:40s} ({desc})")
        else:
            fail(f"{key:40s} ({desc}) -- NOT SET")
            all_ok = False

    sep2()
    if all_ok:
        log("All environment variables are set. Ready to run.")
    else:
        log("Missing environment variables. Check ~/.wat_secrets")
    return all_ok


def cmd_run(flow_names, dry_run=False, no_cleanup=False, wait_multiplier=1.0, verbose=False):
    """Run specified flows."""
    all_contexts = []

    for name in flow_names:
        builder = FLOW_REGISTRY.get(name)
        if not builder:
            warn(f"Unknown flow: {name}. Available: {', '.join(FLOW_REGISTRY.keys())}")
            continue

        flow_spec = builder()
        ctx = run_flow(flow_spec, dry_run=dry_run, wait_multiplier=wait_multiplier)
        all_contexts.append(ctx)

        # Cleanup
        if not dry_run and not no_cleanup and "cleanup" in flow_spec:
            run_cleanup(flow_spec["cleanup"], ctx)

    # Save flight log
    log_data = {
        "ran_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "flows": []
    }
    for ctx in all_contexts:
        log_data["flows"].append({
            "flow_id": ctx.flow_id,
            "status": ctx.status,
            "started_at": ctx.started_at,
            "finished_at": ctx.finished_at,
            "variables": {k: str(v)[:200] for k, v in ctx.variables.items()},
            "steps": ctx.step_results,
            "summary": ctx.summary(),
        })

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)
    log(f"\nFlight log: {LOG_FILE}")

    # Generate HTML report
    generate_html_report(all_contexts)

    # Final summary
    sep()
    log("FINAL SUMMARY")
    sep()
    for ctx in all_contexts:
        s = ctx.summary()
        mark = "OK" if ctx.status == "PASS" else ("--" if ctx.status == "DRY-RUN" else "!!")
        log(f"  [{mark}] {ctx.flow_id:30s}  {ctx.status}  ({s['passed']}/{s['total']} steps)")

    return all_contexts


def cmd_results():
    """Show last test results from flight log."""
    if not os.path.exists(LOG_FILE):
        log("No results yet. Run --run first.")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    log(f"Last run: {data.get('ran_at', '?')}")
    log(f"Dry run: {data.get('dry_run', False)}")
    sep()

    for flow in data.get("flows", []):
        log(f"\nFLOW: {flow['flow_id']}  [{flow['status']}]")
        sep2()
        for step in flow.get("steps", []):
            mark = "OK" if step.get("status") == "PASS" else ("--" if step.get("status") in ("SKIP", "DRY-RUN") else "!!")
            dur = step.get("duration_ms", 0)
            log(f"  [{mark}] {step.get('name', '?'):50s}  {step.get('status','?'):8s}  {dur}ms")
            for a in step.get("assertions", []):
                a_mark = "  " if a.get("pass") else "!!"
                log(f"       [{a_mark}] {a.get('check','?')}: expected={a.get('expected','?')}, actual={a.get('actual','?')}")

        # Variables
        variables = flow.get("variables", {})
        if variables:
            log(f"\n  Context Variables:")
            for k, v in variables.items():
                log(f"    {k}: {v}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Influencer Flow E2E Tester")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true", help="Run flow tests")
    group.add_argument("--dry-run", action="store_true", dest="dry_run_cmd", help="Preview without API calls")
    group.add_argument("--status", action="store_true", help="Check environment readiness")
    group.add_argument("--results", action="store_true", help="Show last test results")

    parser.add_argument("--flow", type=str, default="all",
                        help="Flow to run: gifting|creator|sample|all (default: all)")
    parser.add_argument("--no-cleanup", action="store_true", dest="no_cleanup",
                        help="Skip cleanup (keep test data)")
    parser.add_argument("--wait-multiplier", type=float, default=1.0, dest="wait_multiplier",
                        help="Multiply wait times (e.g. 1.5 for slow environments)")
    parser.add_argument("--verbose", action="store_true", help="Print full payloads to console")

    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.results:
        cmd_results()
    elif args.run or args.dry_run_cmd:
        # Determine which flows to run
        if args.flow == "all":
            flow_names = ["gifting", "creator", "sample"]
        else:
            flow_names = [f.strip() for f in args.flow.split(",")]

        is_dry = args.dry_run_cmd
        cmd_run(flow_names, dry_run=is_dry, no_cleanup=args.no_cleanup,
                wait_multiplier=args.wait_multiplier, verbose=args.verbose)
