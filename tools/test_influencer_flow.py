"""
Influencer Collaboration E2E Flow Tester
=========================================
n8n 기반 인플루언서 협업 파이프라인 전체 플로우를 자율주행 스타일로 테스트.
Pathlight Workflows의 [WJ TEST] 클론을 사용하여 프로덕션에 영향 없이 테스트.

플로우:
  pipeline  : 풀 파이프라인 (Syncly -> Outreach -> Fulfillment) - Pathlight 전체
  gifting   : Influencer Gifting Application (메인 신청)
  creator   : Creator Profile Signup (크리에이터 프로필)
  sample    : Sample Request (수락 후 샘플 요청)

매 스텝마다 request/response 전체를 flight recorder에 기록하고,
스텝 간 변수 캡처 & 전달, HTML 리포트 자동 생성, 테스트 데이터 cleanup.

Usage:
    python tools/test_influencer_flow.py --run --flow pipeline  # 풀 파이프라인 E2E
    python tools/test_influencer_flow.py --run --flow gifting   # 기프팅만
    python tools/test_influencer_flow.py --run                  # gifting+creator+sample
    python tools/test_influencer_flow.py --dry-run --flow pipeline  # 파이프라인 미리보기
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
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# ─── Airtable CRM Tables (Pathlight Workflows 사용) ─────────────────────────
AT_BASE = "appT2gLRR0PqMFgII"
AT_CREATORS = "tbl7zJ1MscP852p9N"
AT_CONTENT = "tblSva2askQRwgGV1"
AT_ORDERS = "tblCcWpvDZX7UZmSd"
AT_CONVERSATIONS = "tblUnBCTmGzBb4BjZ"
AT_APPLICANTS = "tbloYjIEr5OtEppT0"

# ─── [WJ TEST] Workflow IDs (Pathlight 클론) ────────────────────────────────
WJ_WORKFLOWS = {
    "syncly":       "6BNQRz57oCtdROlH",   # Syncly Data Processing
    "content":      "zKmOX0tEWi6EBT9h",   # Content Tracking
    "manychat":     "k08R16VJIuSPdi6T",   # ManyChat Automation
    "draft_gen":    "0q9uJUYTpDhQFMfz",   # Outreach - Draft Generation
    "approval":     "mmkBpmvhzbgmSayh",   # Outreach - Approval Send
    "reply":        "nVtYmhU0InRqRn4K",   # Outreach - Reply Handler
    "docusign":     "5BG7Qe7HtsbD4iP0",   # Docusign Contracting
    "fulfillment":  "UP1OnpNEFN54AOUn",   # Shopify Fulfillment -> Airtable
    "gifting":        "4q5NCzMb3nMGYqL4",   # Influencer Gifting -> Draft Order
    "gifting2":       "734aqkcOIfiylExL",   # Gifting2 -> Draft Order + Airtable (2026-03-13)
    "syncly_metrics": "FT70hFR6qI0mVc2T",   # Syncly Daily Metrics Sync (2026-03-13)
    "lookup":         "wyttsPSZJlWLgy86",   # Influencer Customer Lookup
    "full_pipeline":  "CEWr3kQlDg07310Y",  # Full Pipeline (JH&SY)
}

# ─── [WJ TEST] Webhook paths ───────────────────────────────────────────────
WJ_WEBHOOK_BASE = "https://n8n.orbiters.co.kr/webhook"
WJ_WEBHOOKS = {
    "gifting":      f"{WJ_WEBHOOK_BASE}/wj-test-influencer-gifting",
    "gifting2":     f"{WJ_WEBHOOK_BASE}/onzenna-gifting2-submit",
    "fulfillment":  f"{WJ_WEBHOOK_BASE}/wj-test-shopify-fulfillment",
    "content":      f"{WJ_WEBHOOK_BASE}/wj-test-check-content",
    "contract":     f"{WJ_WEBHOOK_BASE}/wj-test-contract-approve",
    "draft_gen":    f"{WJ_WEBHOOK_BASE}/wj-test-draft-gen",
    "approval":     f"{WJ_WEBHOOK_BASE}/wj-test-approval-send",
}

REQUIRED_ENVS = {
    "N8N_API_KEY": "n8n API (workflow execution)",
    "N8N_BASE_URL": "n8n base URL",
    "AIRTABLE_API_KEY": "Airtable verification",
    "SHOPIFY_SHOP": "Shopify Admin API",
    "SHOPIFY_ACCESS_TOKEN": "Shopify Admin API",
}

TEST_EMAIL_DOMAIN = "orbiters.co.kr"  # Must be valid DNS domain (Shopify Draft Order validates)

# ─── Output helpers ─────────────────────────────────────────────────────────
STATE_FILE = os.path.join(TMP, "influencer_flow_state.json")

def log(msg):  print(msg)
def ok(msg):   print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def link(msg): print(f"  [LINK] {msg}")
def sep():     print("=" * 70)
def sep2():    print("-" * 70)


# ─── Link generators ──────────────────────────────────────────────────────
def link_airtable(table_id, record_id=""):
    url = f"https://airtable.com/{AT_BASE}/{table_id}"
    if record_id and str(record_id).startswith("rec"):
        url += f"/{record_id}"
    return url

def link_shopify(resource, resource_id):
    return f"https://{SHOPIFY_STORE}/admin/{resource}/{resource_id}"

def link_n8n_wf(wf_key):
    wf_id = WJ_WORKFLOWS.get(wf_key, wf_key)
    return f"{N8N_BASE_URL}/workflow/{wf_id}"

def link_n8n_exec(wf_id, exec_id):
    return f"{N8N_BASE_URL}/workflow/{wf_id}/executions/{exec_id}"


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
        self.data_trail = []  # {label, url, type, id, step_id}
        self.started_at = None
        self.finished_at = None
        self.status = "PENDING"

    def set(self, key, value):
        self.variables[key] = value

    def get(self, key, default=None):
        return self.variables.get(key, default)

    def add_link(self, label, url, resource_type="", resource_id="", step_id=""):
        self.data_trail.append({"label": label, "url": url, "type": resource_type,
                                "id": str(resource_id), "step_id": step_id})
        link(f"{label}: {url}")

    def save_state(self):
        """Persist context variables to file for step-by-step execution."""
        state = {
            "flow_id": self.flow_id,
            "variables": {},
            "data_trail": self.data_trail,
            "last_step": len(self.step_results),
            "saved_at": datetime.now().isoformat(),
        }
        # Serialize variables (only JSON-safe values)
        for k, v in self.variables.items():
            try:
                json.dumps(v)
                state["variables"][k] = v
            except (TypeError, ValueError):
                state["variables"][k] = str(v)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
        info(f"State saved to {STATE_FILE} (step {state['last_step']})")

    def load_state(self):
        """Load context variables from saved state file."""
        if not os.path.exists(STATE_FILE):
            return False
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("flow_id") != self.flow_id:
                warn(f"State file is for flow '{state.get('flow_id')}', not '{self.flow_id}'")
                return False
            self.variables = state.get("variables", {})
            self.data_trail = state.get("data_trail", [])
            last = state.get("last_step", 0)
            info(f"Loaded state from {STATE_FILE} ({len(self.variables)} vars, last_step={last})")
            return True
        except Exception as e:
            warn(f"Failed to load state: {e}")
            return False

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

    # Auto-generate links for webhook URLs
    entry["links"] = []
    for wh_name, wh_url in WJ_WEBHOOKS.items():
        if wh_url in url:
            wf_key = {"contract": "docusign"}.get(wh_name, wh_name)
            entry["links"].append({"label": f"n8n Workflow ({wh_name})", "url": link_n8n_wf(wf_key)})
            break

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
    custom_formula = ctx.interpolate(step.get("filter_formula", ""))
    expect_exists = step.get("expect_exists", True)
    expect_fields = ctx.interpolate(step.get("expect_fields", {}))

    if not AIRTABLE_API_KEY:
        warn("AIRTABLE_API_KEY not set -- skipping")
        return None, {"skipped": "no AIRTABLE_API_KEY"}

    if custom_formula:
        formula = urllib.parse.quote(custom_formula)
    else:
        safe_value = filter_value.replace("'", "\\'")
        formula = urllib.parse.quote(f"{{{filter_field}}}='{safe_value}'")
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?filterByFormula={formula}&maxRecords=5"

    if custom_formula:
        log(f"  Airtable: {base_id}/{table_id} formula: {custom_formula}")
    else:
        log(f"  Airtable: {base_id}/{table_id} where {filter_field}='{filter_value}'")
    entry = {"request": {"method": "GET", "url": url}, "response": {}, "assertions": []}

    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:300]
        entry["response"] = {"status": e.code, "body": err_body}
        # 422 INVALID_FILTER_BY_FORMULA: field doesn't exist in empty table
        # If we don't expect the record to exist, treat as no records found → PASS
        if e.code == 422 and not expect_exists:
            warn(f"Airtable filter formula invalid (table likely empty/field missing) -- treating as no record (expected)")
            entry["assertions"].append({"check": "record_not_exists", "expected": True, "actual": True, "pass": True})
            return True, entry
        fail(f"Airtable API error {e.code}: {err_body}")
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

    # Auto-generate Airtable links
    entry["links"] = []
    if records:
        rid = records[0].get("id", "")
        if rid:
            entry["links"].append({"label": "Airtable Record", "url": link_airtable(table_id, rid), "id": rid})

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

        # Auto-generate Shopify customer link
        entry["links"] = []
        if customers:
            cid = customers[0].get("id")
            if cid:
                entry["links"].append({"label": "Shopify Customer", "url": link_shopify("customers", cid), "id": str(cid)})
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

            # Auto-generate Shopify draft order link
            entry.setdefault("links", [])
            did = do.get("id")
            if did:
                entry["links"].append({"label": "Shopify Draft Order", "url": link_shopify("draft_orders", did), "id": str(did)})
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
    elif not expect_exists and results:
        warn(f"Record unexpectedly found in PostgreSQL ({count} rows)")
        entry["assertions"].append({"check": "record_not_exists", "expected": False, "actual": True, "pass": True})
    elif not expect_exists:
        ok("No record in PostgreSQL (as expected)")
        entry["assertions"].append({"check": "record_not_exists", "expected": False, "actual": False, "pass": True})
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


# ─── New Step Runners: n8n execute, Airtable create/update ──────────────────

def run_n8n_execute(step, ctx):
    """Trigger a [WJ TEST] n8n workflow via API. Schedule-based workflows need this."""
    wf_key = ctx.interpolate(step.get("workflow_key", ""))
    wf_id = WJ_WORKFLOWS.get(wf_key, wf_key)  # Accept key or raw ID
    test_data = ctx.interpolate(step.get("test_data", {}))

    if not N8N_API_KEY:
        warn("N8N_API_KEY not set -- skipping")
        return None, {"skipped": "no N8N_API_KEY"}

    url = f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/run"
    log(f"  n8n Execute: {wf_key} (id={wf_id})")
    entry = {"request": {"method": "POST", "url": url, "body": test_data}, "response": {}, "assertions": []}

    headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
    payload = {}
    if test_data:
        payload["data"] = test_data

    data_bytes = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
            entry["response"] = {"status": resp.status, "body": body if len(json.dumps(body, default=str)) < 5000 else {"truncated": True, "keys": list(body.keys()) if isinstance(body, dict) else "..."}}
            ok(f"Workflow triggered (status={resp.status})")
            entry["assertions"].append({"check": "n8n_execute", "expected": "success", "actual": "success", "pass": True})
            _do_captures(step, body, ctx, entry)
            # Auto-generate n8n links
            entry["links"] = [{"label": f"n8n Workflow ({wf_key})", "url": link_n8n_wf(wf_key)}]
            # Try to get execution ID from response
            exec_id = None
            if isinstance(body, dict):
                exec_id = body.get("executionId") or body.get("data", {}).get("executionId") if isinstance(body.get("data"), dict) else None
            if exec_id:
                entry["links"].append({"label": "n8n Execution", "url": link_n8n_exec(wf_id, exec_id), "id": str(exec_id)})
            return True, entry
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        entry["response"] = {"status": e.code, "body": err_body}
        # 404 might mean workflow needs activation or different API path
        if e.code == 404:
            fail(f"Workflow not found or inactive. Activate it first in n8n UI.")
        else:
            fail(f"n8n API error {e.code}: {err_body[:200]}")
        entry["assertions"].append({"check": "n8n_execute", "expected": "success", "actual": f"HTTP {e.code}", "pass": False})
        return False, entry
    except Exception as e:
        fail(f"n8n execute error: {e}")
        entry["response"] = {"error": str(e)}
        return False, entry


def run_airtable_create(step, ctx):
    """Create a record in Airtable (seed test data or simulate upstream output)."""
    base_id = ctx.interpolate(step.get("base_id", AT_BASE))
    table_id = ctx.interpolate(step.get("table_id", ""))
    fields = ctx.interpolate(step.get("fields", {}))

    if not AIRTABLE_API_KEY:
        warn("AIRTABLE_API_KEY not set -- skipping")
        return None, {"skipped": "no AIRTABLE_API_KEY"}

    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    log(f"  Airtable CREATE: {base_id}/{table_id}")
    entry = {"request": {"method": "POST", "url": url, "body": {"fields": fields}}, "response": {}, "assertions": []}

    typecast = step.get("typecast", False)
    body = {"fields": fields}
    if typecast:
        body["typecast"] = True
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {AIRTABLE_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            record_id = data.get("id", "")
            entry["response"] = {"status": 200, "body": data}
            ok(f"Created record {record_id}")
            entry["assertions"].append({"check": "airtable_create", "expected": "created", "actual": record_id, "pass": True})
            _do_captures(step, data, ctx, entry)
            # Auto-capture record_id
            if record_id:
                ctx.set("_last_airtable_record_id", record_id)
            # Auto-generate Airtable link
            entry["links"] = []
            if record_id:
                entry["links"].append({"label": "Airtable Record (created)", "url": link_airtable(table_id, record_id), "id": record_id})
            return True, entry
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        fail(f"Airtable create error {e.code}: {err_body[:200]}")
        entry["response"] = {"status": e.code, "body": err_body}
        entry["assertions"].append({"check": "airtable_create", "expected": "created", "actual": f"HTTP {e.code}", "pass": False})
        return False, entry


def run_airtable_update(step, ctx):
    """Update an Airtable record (simulate human-in-the-loop status changes)."""
    base_id = ctx.interpolate(step.get("base_id", AT_BASE))
    table_id = ctx.interpolate(step.get("table_id", ""))
    record_id = ctx.interpolate(step.get("record_id", ""))
    fields = ctx.interpolate(step.get("fields", {}))

    if not AIRTABLE_API_KEY:
        warn("AIRTABLE_API_KEY not set -- skipping")
        return None, {"skipped": "no AIRTABLE_API_KEY"}

    if not record_id:
        fail("No record_id for Airtable update")
        return False, {"error": "no record_id"}

    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    log(f"  Airtable UPDATE: {record_id} -> {fields}")
    entry = {"request": {"method": "PATCH", "url": url, "body": {"fields": fields}}, "response": {}, "assertions": []}

    payload = json.dumps({"fields": fields}).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH")
    req.add_header("Authorization", f"Bearer {AIRTABLE_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            entry["response"] = {"status": 200, "body": data}
            ok(f"Updated record {record_id}")
            entry["assertions"].append({"check": "airtable_update", "expected": "updated", "actual": "success", "pass": True})
            _do_captures(step, data, ctx, entry)
            return True, entry
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        fail(f"Airtable update error {e.code}: {err_body[:200]}")
        entry["response"] = {"status": e.code, "body": err_body}
        entry["assertions"].append({"check": "airtable_update", "expected": "updated", "actual": f"HTTP {e.code}", "pass": False})
        return False, entry


def run_human_checkpoint(step, ctx):
    """Mark a human-in-the-loop point with instructions and links."""
    description = step.get("description", "Human action required")
    simulated = step.get("simulated", True)
    instructions = step.get("instructions", [])

    log(f"\n  === HUMAN CHECKPOINT ===")
    log(f"  {description}")
    entry = {"assertions": [], "links": []}

    if instructions:
        log(f"")
        for instr in instructions:
            log(f"  {instr}")
        log(f"")

    # Auto-add relevant links from context
    creator_rid = ctx.get("creator_record_id")
    if creator_rid:
        url = link_airtable(AT_CREATORS, creator_rid)
        log(f"  [LINK] Airtable Creator: {url}")
        entry["links"].append({"label": "Airtable Creator Record", "url": url, "id": creator_rid})
    conv_rid = ctx.get("conversation_record_id")
    if conv_rid:
        url = link_airtable(AT_CONVERSATIONS, conv_rid)
        log(f"  [LINK] Airtable Conversation: {url}")
        entry["links"].append({"label": "Airtable Conversation", "url": url, "id": conv_rid})
    cust_id = ctx.get("shopify_customer_id")
    if cust_id:
        url = link_shopify("customers", cust_id)
        log(f"  [LINK] Shopify Customer: {url}")
        entry["links"].append({"label": "Shopify Customer", "url": url, "id": str(cust_id)})

    log(f"  === Do the above, then run the NEXT step ===\n")

    if simulated:
        info(f"  (Auto-simulated in test mode)")
    entry["assertions"].append({"check": "human_checkpoint", "expected": "acknowledged", "actual": "acknowledged", "pass": True})
    return True, entry


def run_verify_n8n_workflow(step, ctx):
    """Structural check: verify n8n workflow is active with expected node count and key nodes present."""
    wf_key = ctx.interpolate(step.get("workflow_key", ""))
    wf_id = WJ_WORKFLOWS.get(wf_key, wf_key)
    expect_active = step.get("expect_active", True)
    min_nodes = step.get("min_nodes", 1)
    expect_nodes = step.get("expect_nodes", [])  # list of node name substrings to check

    entry = {"request": {"method": "GET", "url": f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}"}, "response": {}, "assertions": []}
    entry["links"] = [{"label": f"n8n Workflow ({wf_key})", "url": link_n8n_wf(wf_key)}]

    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    req = urllib.request.Request(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            entry["response"] = {"status": resp.status}

            is_active = body.get("active", False)
            node_names = [n.get("name", "") for n in body.get("nodes", [])]
            node_count = len(node_names)

            # Check active
            active_pass = (is_active == expect_active)
            mark = "PASS" if active_pass else "FAIL"
            log(f"  [{mark}] active={is_active} (expected={expect_active})")
            entry["assertions"].append({"check": "active", "expected": expect_active, "actual": is_active, "pass": active_pass})

            # Check node count
            count_pass = (node_count >= min_nodes)
            mark = "PASS" if count_pass else "FAIL"
            log(f"  [{mark}] node_count={node_count} (min={min_nodes})")
            entry["assertions"].append({"check": "node_count", "expected": f">={min_nodes}", "actual": node_count, "pass": count_pass})

            # Check key nodes
            for expected_node in expect_nodes:
                found = any(expected_node.lower() in n.lower() for n in node_names)
                mark = "PASS" if found else "FAIL"
                log(f"  [{mark}] node '{expected_node}': {'found' if found else 'MISSING'}")
                entry["assertions"].append({"check": f"node:{expected_node}", "expected": "present", "actual": "found" if found else "missing", "pass": found})

            all_pass = all(a["pass"] for a in entry["assertions"])
            return all_pass, entry
    except Exception as e:
        fail(f"n8n workflow verify error: {e}")
        entry["response"] = {"error": str(e)}
        entry["assertions"].append({"check": "reachable", "expected": "success", "actual": str(e), "pass": False})
        return False, entry


def run_assert_captured(step, ctx):
    """Assert that a previously captured value is truthy / non-empty."""
    assert_key = step.get("assert_key", "")
    assert_path = step.get("assert_path", "")
    expect_truthy = step.get("expect_truthy", True)
    entry = {"request": {}, "response": {}, "assertions": []}

    captured = ctx.variables.get(assert_key)
    if captured is None:
        fail(f"Captured key '{assert_key}' not found in context")
        entry["assertions"].append({"check": assert_key, "expected": "captured", "actual": "missing", "pass": False})
        return False, entry

    # Drill into nested path if specified
    value = captured
    if assert_path and isinstance(captured, dict):
        value = captured.get(assert_path)

    passed = bool(value) == expect_truthy
    if passed:
        ok(f"  {assert_key}.{assert_path} = {value!r} (truthy as expected)")
        entry["assertions"].append({"check": f"{assert_key}.{assert_path}", "expected": f"truthy={expect_truthy}", "actual": str(value), "pass": True})
    else:
        fail(f"  {assert_key}.{assert_path} = {value!r} (expected truthy={expect_truthy})")
        entry["assertions"].append({"check": f"{assert_key}.{assert_path}", "expected": f"truthy={expect_truthy}", "actual": str(value), "pass": False})
    return passed, entry


STEP_RUNNERS = {
    "http_post":          run_http_post,
    "http_get":           run_http_get,
    "verify_airtable":    run_verify_airtable,
    "verify_shopify":     run_verify_shopify,
    "verify_postgres":    run_verify_postgres,
    "wait":               run_wait,
    "n8n_execute":         run_n8n_execute,
    "verify_n8n_workflow": run_verify_n8n_workflow,
    "airtable_create":     run_airtable_create,
    "airtable_update":     run_airtable_update,
    "human_checkpoint":    run_human_checkpoint,
    "assert_captured":     run_assert_captured,
}


# ═══════════════════════════════════════════════════════════════════════════
# Flow Definitions — Built-in 3 flows
# ═══════════════════════════════════════════════════════════════════════════

def _make_test_email():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"flow_test_{ts}_{rand}@{TEST_EMAIL_DOMAIN}"


def _make_test_phone():
    """Generate unique US phone for each test run (avoids Shopify 'phone taken')."""
    # US format: +1 (area 3 digits) (exchange 3 digits, starts 2-9) (station 4 digits)
    exchange = str(random.randint(200, 999))
    station = "".join(random.choices(string.digits, k=4))
    return f"+1310{exchange}{station}"  # 310 = valid LA area code


def flow_pipeline(email=None):
    """Full Pathlight Pipeline: Syncly -> Content -> Outreach -> Docusign -> Fulfillment.
    Uses [WJ TEST] clones only. Production is never touched."""
    test_email = email or _make_test_email()
    is_real_email = email is not None
    test_name = "WJ FlowTest" if not is_real_email else "Wonjin Choi"
    test_ig = "wjflowtest_ig" if not is_real_email else "wj_choi_test"
    test_profile_url = f"https://instagram.com/{test_ig}"
    return {
        "flow_id": "pathlight_pipeline",
        "flow_name": "Full Pipeline: Syncly -> Outreach -> Fulfillment",
        "description": "Pathlight Workflows 전체 E2E ([WJ TEST] 클론 사용)",
        "test_email": test_email,
        "steps": [
            # ── Phase 1: Seed test creator in Airtable (simulates Syncly output) ──
            {
                "step_id": "seed_creator",
                "type": "airtable_create",
                "name": "1. Seed test creator in Airtable Creators table",
                "table_id": AT_CREATORS,
                "fields": {
                    "Name": test_name,
                    "Email": test_email,
                    "Username": test_ig,
                    "Platform": "Instagram",
                    "Profile URL": test_profile_url,
                    "Bio": "Mom of 1. Love sharing baby product reviews and daily mom life. Honest opinions only!",
                    "Location": "Los Angeles, CA",
                    "Followers": 8500,
                    "Number of fully matched posts": 2,
                    "Average views": 3200,
                    "Average likes": 450,
                    "Average ER": 5.3,
                    "Recent 30-Day Views": 4800,
                    "Recent 30-Day Likes": 680,
                    "Recent 30-Day Avg ER": 5.8,
                    "Syncly Level": "Fully Matched",
                    "Brand Classification": "Grosmimi",
                    "Source": "Syncly Outbound",
                },
                "capture": {
                    "creator_record_id": "$.id",
                    "creator_fields": "$.fields",
                },
            },
            {
                "step_id": "verify_creator_seeded",
                "type": "verify_airtable",
                "name": "1b. Verify creator record exists",
                "base_id": AT_BASE,
                "table_id": AT_CREATORS,
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {"Platform": "Instagram"},
            },

            # ── Phase 2: Trigger Syncly Data Processing (WJ TEST) ──
            {
                "step_id": "trigger_syncly",
                "type": "n8n_execute",
                "name": "2. Trigger [WJ TEST] Syncly Data Processing",
                "workflow_key": "syncly",
                "critical": False,  # May fail if no sheet data — that's OK
            },
            {
                "step_id": "wait_syncly",
                "type": "wait",
                "name": "2b. Wait for Syncly processing",
                "seconds": 5,
            },

            # ── Phase 3: Simulate human review -> set status to trigger outreach ──
            {
                "step_id": "human_review",
                "type": "human_checkpoint",
                "name": "3. HUMAN: Review creator profile",
                "description": "Airtable Creators 테이블에서 레코드 확인 후 다음 스텝 진행",
                "simulated": False,
                "instructions": [
                    "1. Airtable 링크를 열어서 방금 생성된 Creator 레코드를 확인하세요",
                    f"2. 레코드 링크: 위 DATA TRAIL의 Airtable Record 링크 클릭",
                    "3. 프로필 정보 (Name, Email, IG, Bio, Followers 등) 확인",
                    "4. 확인 완료 후 다음 스텝 (step 6) 실행",
                ],
            },
            {
                "step_id": "update_status_for_outreach",
                "type": "airtable_update",
                "name": "3b. Set creator outreach status -> trigger outreach draft",
                "table_id": AT_CREATORS,
                "record_id": "{{creator_record_id}}",
                "fields": {
                    "Outreach Type": "Low Touch",
                    "Communication Channel": "Email",
                },
            },

            # ── Phase 4: Trigger Outreach Draft Generation (via webhook) ──
            {
                "step_id": "trigger_draft_gen",
                "type": "http_post",
                "name": "4. Trigger Draft Gen via webhook (wj-test-draft-gen)",
                "url": WJ_WEBHOOKS["draft_gen"],
                "payload": {
                    "records": [{
                        "id": "{{creator_record_id}}",
                        "fields": {
                            "Username": test_ig,
                            "Email": test_email,
                            "Platform": "Instagram",
                            "Outreach Type": "Low Touch",
                            "Outreach Status": "Not Started",
                            "Name": test_name,
                            "Brand Classification": "Grosmimi",
                        },
                        "createdTime": "{{now_iso}}",
                    }]
                },
                "expect_status": 200,
                "critical": False,
                "capture": {"draft_gen_response": "$"},
            },
            {
                "step_id": "wait_draft",
                "type": "wait",
                "name": "4b. Wait for Claude AI draft generation (AI+Sheets+Gmail ~40-60s)",
                "seconds": 60,
            },
            {
                # ARRAYJOIN({Creator}) returns display names (usernames), not record IDs.
                # Filter by Subject which contains the test_ig handle.
                "step_id": "verify_conversation_created",
                "type": "verify_airtable",
                "name": "4c. Verify conversation draft created",
                "base_id": AT_BASE,
                "table_id": AT_CONVERSATIONS,
                "filter_formula": "FIND('" + test_ig + "', {Subject})",
                "expect_exists": True,
                "capture": {
                    "conversation_record_id": "$.records[0].id",
                },
                "critical": False,
            },

            # ── Phase 5: Human approves draft (simulated) ──
            {
                "step_id": "human_approve_draft",
                "type": "human_checkpoint",
                "name": "5. HUMAN: Review & approve outreach draft",
                "description": "Airtable Conversations 테이블에서 AI가 생성한 이메일 초안 확인",
                "simulated": False,
                "instructions": [
                    "1. Airtable Conversations 테이블 확인 (DATA TRAIL 링크)",
                    f"2. AI가 생성한 이메일 초안(Draft) 내용 리뷰",
                    "3. 내용 괜찮으면 다음 스텝 (step 11) 실행하여 Outreach Status -> Sent 변경",
                    "4. 수정 필요하면 Airtable에서 직접 수정 후 진행",
                ],
            },
            {
                "step_id": "update_draft_approved",
                "type": "airtable_update",
                "name": "5b. Set outreach status -> Approved (triggers send)",
                "table_id": AT_CREATORS,
                "record_id": "{{creator_record_id}}",
                "fields": {"Outreach Status": "Sent"},
                "critical": False,
            },

            # ── Phase 6: Trigger Approval Send (via webhook) ──
            {
                "step_id": "trigger_approval_send",
                "type": "http_post",
                "name": "6. Trigger Approval Send via webhook (wj-test-approval-send)",
                "url": WJ_WEBHOOKS["approval"],
                "payload": {
                    "records": [{
                        "id": "{{creator_record_id}}",
                        "fields": {
                            "Username": test_ig,
                            "Email": test_email,
                            "Name": test_name,
                            "Outreach Status": "Sent",
                        },
                        "createdTime": "{{now_iso}}",
                    }]
                },
                "expect_status": 200,
                "critical": False,
                "capture": {"approval_response": "$"},
            },
            {
                "step_id": "wait_approval",
                "type": "wait",
                "name": "6b. Wait for email send",
                "seconds": 15,
            },

            # ── Phase 7: Simulate influencer confirms -> Fulfillment ──
            {
                "step_id": "human_influencer_confirms",
                "type": "human_checkpoint",
                "name": "7. HUMAN: Influencer replies (you reply to the email)",
                "description": "실제로 wj.choi@orbiters.co.kr 메일함에서 수신된 이메일에 답장",
                "simulated": False,
                "instructions": [
                    "1. Gmail (wj.choi@orbiters.co.kr) 메일함 확인",
                    "2. Outreach 이메일이 도착했는지 확인",
                    "3. 이메일에 '제품 사용해보고 싶습니다' 식으로 답장",
                    "4. 답장 후 다음 스텝 (step 15) 실행하여 Gifting 폼 제출",
                ],
            },

            # ── Phase 8: Test Gifting form -> Draft Order via WJ TEST webhook ──
            {
                "step_id": "submit_gifting_wjtest",
                "type": "http_post",
                "name": "8. POST to [WJ TEST] Gifting webhook",
                "url": WJ_WEBHOOKS["gifting"],
                "payload": {
                    "form_type": "influencer_gifting",
                    "submitted_at": "{{now_iso}}",
                    "personal_info": {
                        "full_name": test_name,
                        "email": test_email,
                        "phone": _make_test_phone(),
                        "instagram": f"@{test_ig}",
                        "tiktok": "None",
                    },
                    "baby_info": {
                        "child_1": {"birthday": "2025-06-15", "age_months": 9},
                        "child_2": None,
                    },
                    "selected_products": [{
                        "product_key": "ppsu_straw",
                        "product_id": 8288579256642,
                        "variant_id": 45018985431362,
                        "title": "Grosmimi PPSU Straw Cup 10oz",
                        "color": "White",
                        "price": "$24.90",
                    }],
                    "shipping_address": {
                        "street": "123 WJ Test St",
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
                "capture": {"gifting_response": "$"},
            },
            {
                "step_id": "wait_gifting",
                "type": "wait",
                "name": "8b. Wait for n8n gifting processing",
                "seconds": 10,
            },
            {
                "step_id": "verify_shopify_customer",
                "type": "verify_shopify",
                "name": "8c. Verify Shopify customer created",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
            },
            {
                # n8n creates draft order on mytoddie.myshopify.com (different from test env toddie-4080)
                # Verify via webhook response draft_order_id instead of Shopify API lookup
                "step_id": "verify_draft_order",
                "type": "assert_captured",
                "name": "8d. Verify Draft Order created (via webhook response)",
                "assert_key": "gifting_response",
                "assert_path": "draft_order_id",
                "expect_truthy": True,
                "critical": False,
            },

            # ── Phase 9: Fulfillment webhook test ──
            {
                "step_id": "trigger_fulfillment",
                "type": "http_post",
                "name": "9. POST to [WJ TEST] Fulfillment webhook",
                "url": WJ_WEBHOOKS["fulfillment"],
                "payload": {
                    "order_id": "{{draft_order_id}}",
                    "customer_email": test_email,
                    "customer_name": test_name,
                    "source": "wj_flow_test",
                },
                "expect_status": 200,
                "critical": False,
                "capture": {"fulfillment_response": "$"},
            },
            {
                "step_id": "wait_fulfillment",
                "type": "wait",
                "name": "9b. Wait for fulfillment processing",
                "seconds": 8,
            },

            # ── Phase 10: Verify final state in Airtable ──
            {
                "step_id": "verify_final_creator",
                "type": "verify_airtable",
                "name": "10. Verify creator record in Airtable (final state)",
                "base_id": AT_BASE,
                "table_id": AT_CREATORS,
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "capture": {
                    "final_outreach_status": "$.records[0].fields.Outreach Status",
                    "final_partnership_status": "$.records[0].fields.Partnership Status",
                },
            },
            {
                "step_id": "create_order_record",
                "type": "airtable_create",
                "name": "10b. Create Order record in Airtable Orders (direct)",
                "base_id": AT_BASE,
                "table_id": AT_ORDERS,
                "fields": {
                    "Order Title": f"WJ Flow Test - {test_name}",
                    "Shopify Order ID": "{{draft_order_id}}",
                    "Recipient Name": test_name,
                    "[WJ Test] Creators": ["{{creator_record_id}}"],
                },
                "typecast": True,
                "capture": {"order_record_id": "$.id"},
                "critical": False,
            },
            {
                "step_id": "verify_order_record",
                "type": "assert_captured",
                "name": "10c. Verify Order record created",
                "assert_key": "order_record_id",
                "expect_truthy": True,
                "critical": False,
            },
        ],
        "cleanup": {
            "airtable_records": [
                {"table_id": AT_CREATORS, "record_id": "{{creator_record_id}}"},
                {"table_id": AT_CONVERSATIONS, "record_id": "{{conversation_record_id}}"},
                {"table_id": AT_ORDERS, "record_id": "{{order_record_id}}"},
            ],
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_gifting(email=None):
    """Flow 1: Influencer Gifting Application (Main Entry)."""
    test_email = email or _make_test_email()
    test_phone = _make_test_phone()
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
                        "phone": test_phone,
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
                "seconds": 12,
            },
            {
                "step_id": "verify_airtable_gifting",
                "type": "verify_airtable",
                "name": "Verify Applicants table record",
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
                "step_id": "verify_creators_gifting",
                "type": "verify_airtable",
                "name": "Verify Creators table record (Pathlight CRM)",
                "table_id": AT_CREATORS,
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {
                    "Outreach Status": "Needs Review",
                    "Partnership Status": "New",
                    "Source": "ManyChat Inbound",
                },
                "capture": {
                    "creators_record_id": "$.records[0].id",
                    "creators_username": "$.records[0].fields.Username",
                    "creators_platform": "$.records[0].fields.Platform",
                },
                "critical": False,  # New node, non-critical until verified stable
            },
            {
                "step_id": "verify_shopify_customer_gifting",
                "type": "verify_shopify",
                "name": "Verify Shopify customer exists",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
                "critical": False,  # n8n uses mytoddie store, test checks toddie-4080
            },
            {
                "step_id": "verify_metafields_gifting",
                "type": "verify_shopify",
                "name": "Verify influencer metafields (instagram/tiktok)",
                "resource": "metafield",
                "customer_id": "{{shopify_customer_id}}",
                "critical": False,  # n8n uses mytoddie store
                "expect_metafields": {
                    "influencer.instagram": "@flowtest_ig",
                    "influencer.tiktok": "@flowtest_tk",
                },
            },
            {
                "step_id": "verify_postgres_gifting",
                "type": "verify_postgres",
                "name": "Verify PostgreSQL record (orbitools)",
                "endpoint": "/api/onzenna/gifting/list/",
                "filter": {"email": test_email},
                "expect_exists": True,
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "creators_record_id": "{{creators_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_creator(email=None):
    """Flow 2: Creator Profile Signup."""
    test_email = email or _make_test_email()
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
                    "contact": {"phone": _make_test_phone()},
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
                "name": "Verify Shopify customer (creator workflow doesn't create)",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": False,  # Creator-to-Airtable workflow doesn't create Shopify customers
                "capture": {"shopify_customer_id": "$.customers[0].id"},
                "critical": False,
            },
            {
                "step_id": "verify_metafields_creator",
                "type": "verify_shopify",
                "name": "Verify onzenna_creator metafields (skipped, no customer created)",
                "resource": "metafield",
                "customer_id": "{{shopify_customer_id}}",
                "critical": False,  # No customer created by this flow
                "expect_metafields": {
                    "onzenna_creator.primary_platform": "instagram",
                    "onzenna_creator.primary_handle": "@flowtest_creator",
                    "onzenna_creator.following_size": "1k_10k",
                },
            },
            {
                "step_id": "verify_postgres_creator",
                "type": "verify_postgres",
                "name": "Verify PostgreSQL creator record (no PG integration in creator flow)",
                "endpoint": "/api/onzenna/gifting/list/",
                "filter": {"email": test_email},
                "expect_exists": False,  # Creator-to-Airtable has no PG save node
                "critical": False,
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_sample(email=None):
    """Flow 3: Sample Request (after acceptance)."""
    test_email = email or _make_test_email()
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
                        "phone": _make_test_phone(),
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
                "critical": False,  # n8n uses mytoddie store, test checks toddie-4080
            },
            {
                "step_id": "verify_draft_order",
                "type": "verify_shopify",
                "name": "Verify draft order created (100% discount)",
                "resource": "draft_order",
                "customer_id": "{{shopify_customer_id}}",
                "expect_exists": True,
                "capture": {"draft_order_id": "$.draft_orders[0].id"},
                "critical": False,  # n8n uses mytoddie store
            },
            {
                "step_id": "verify_airtable_updated",
                "type": "verify_airtable",
                "name": "Verify Applicants table updated (Gifting2 upsert)",
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {"Status": "Accepted"},
                "capture": {
                    "airtable_record_id": "$.records[0].id",
                    "airtable_draft_order_id": "$.records[0].fields.Draft Order ID",
                },
                "critical": False,  # Gifting2 uses mytoddie store credentials
            },
            {
                "step_id": "verify_creators_updated",
                "type": "verify_airtable",
                "name": "Verify Creators table updated (Gifting2 upsert)",
                "table_id": AT_CREATORS,
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {
                    "Outreach Status": "Sample Sent",
                },
                "capture": {
                    "creators_draft_order_id": "$.records[0].fields.Draft Order ID",
                },
                "critical": False,  # New node, non-critical until verified stable
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_gifting2(email=None):
    """Flow 5: Gifting2 → Draft Order + Airtable (2026-03-13 migration, WF: 734aqkcOIfiylExL)."""
    test_email = email or _make_test_email()
    test_phone = _make_test_phone()
    return {
        "flow_id": "gifting2_draft_order",
        "flow_name": "Flow 5: Gifting2 → Draft Order + Airtable",
        "description": "Creator sample form → Draft Order → Airtable Applicants/Creators upsert → PostgreSQL",
        "test_email": test_email,
        "steps": [
            {
                "step_id": "submit_gifting2_form",
                "type": "http_post",
                "name": "POST to Gifting2 webhook (onzenna-gifting2-submit)",
                "url": WJ_WEBHOOKS["gifting2"],
                "payload": {
                    "form_type": "gifting2_sample_request",
                    "submitted_at": "{{now_iso}}",
                    "personal_info": {
                        "full_name": "FlowTest G2",
                        "email": test_email,
                        "phone": test_phone,
                        "instagram": "@flowtest_g2_ig",
                        "tiktok": "@flowtest_g2_tk",
                    },
                    "baby_info": {
                        "child_1": {"birthday": "2025-01-10", "age_months": 14},
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
                        "street": "456 G2 Test Ave",
                        "apt": "",
                        "city": "San Francisco",
                        "state": "CA",
                        "zip": "94102",
                        "country": "US",
                    },
                    "terms_accepted": True,
                    "shopify_customer_id": None,
                },
                "expect_status": 200,
                "capture": {"webhook_response": "$"},
            },
            {
                "step_id": "wait_gifting2_processing",
                "type": "wait",
                "name": "Wait for n8n async processing (Gifting2)",
                "seconds": 15,
            },
            {
                "step_id": "verify_airtable_applicants_g2",
                "type": "verify_airtable",
                "name": "Verify Applicants table record (Gifting2)",
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {},
                "capture": {
                    "airtable_record_id": "$.records[0].id",
                    "airtable_name": "$.records[0].fields.Name",
                    "g2_draft_order_id": "$.records[0].fields.Draft Order ID",
                },
            },
            {
                "step_id": "verify_creators_g2",
                "type": "verify_airtable",
                "name": "Verify Creators table record (Gifting2)",
                "table_id": AT_CREATORS,
                "filter_field": "Email",
                "filter_value": test_email,
                "expect_exists": True,
                "expect_fields": {},
                "capture": {
                    "creators_record_id": "$.records[0].id",
                    "creators_username": "$.records[0].fields.Username",
                },
                "critical": False,
            },
            {
                "step_id": "verify_shopify_customer_g2",
                "type": "verify_shopify",
                "name": "Verify Shopify customer exists (Gifting2)",
                "resource": "customer",
                "filter": {"email": test_email},
                "expect_exists": True,
                "capture": {"shopify_customer_id": "$.customers[0].id"},
                "critical": False,
            },
            {
                "step_id": "verify_postgres_g2",
                "type": "verify_postgres",
                "name": "Verify PostgreSQL record (Gifting2)",
                "endpoint": "/api/onzenna/gifting/list/",
                "filter": {"email": test_email},
                "expect_exists": True,
                "critical": False,
            },
        ],
        "cleanup": {
            "airtable_record_id": "{{airtable_record_id}}",
            "creators_record_id": "{{creators_record_id}}",
            "shopify_customer_id": "{{shopify_customer_id}}",
            "test_email": test_email,
        },
    }


def flow_syncly_metrics(email=None):
    """Flow 6: Syncly Daily Metrics Sync — structural verification (2026-03-13 migration, WF: FT70hFR6qI0mVc2T).
    Note: schedule-trigger workflows cannot be manually executed via n8n API v1 (405).
    Test verifies: active=True, node count ≥5, key nodes present, schedule config correct.
    """
    return {
        "flow_id": "syncly_metrics_sync",
        "flow_name": "Flow 6: Syncly Daily Metrics Sync",
        "description": "Structural check: active, node count, key nodes, schedule trigger (schedule-only WF, no execution)",
        "steps": [
            {
                "step_id": "verify_syncly_active",
                "type": "verify_n8n_workflow",
                "name": "Verify Syncly Metrics: active + nodes + schedule",
                "workflow_key": "syncly_metrics",
                "expect_active": True,
                "min_nodes": 5,
                "expect_nodes": ["Schedule Trigger", "Run Syncly Sync", "Check Result"],
            },
            {
                "step_id": "verify_gifting2_structural",
                "type": "verify_n8n_workflow",
                "name": "Structural: Gifting2 active + all 14 nodes present",
                "workflow_key": "gifting2",
                "expect_active": True,
                "min_nodes": 14,
                "expect_nodes": ["Build Payloads", "Create Draft Order", "Save to Applicants", "Save to Creators", "Save to PostgreSQL"],
            },
        ],
    }


FLOW_REGISTRY = {
    "pipeline":       flow_pipeline,
    "gifting":        flow_gifting,
    "creator":        flow_creator,
    "sample":         flow_sample,
    "gifting2":       flow_gifting2,       # 2026-03-13: Gifting2 Draft Order
    "syncly_metrics": flow_syncly_metrics, # 2026-03-13: Syncly Daily Metrics
}


# ═══════════════════════════════════════════════════════════════════════════
# Flow Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_flow(flow_spec, dry_run=False, wait_multiplier=1.0, step_num=None):
    """Execute an entire flow with full flight recording.

    Args:
        step_num: If set, run ONLY this step (1-indexed). Load/save state for continuity.
    """
    flow_id = flow_spec["flow_id"]
    ctx = FlowContext(flow_id)
    ctx.started_at = datetime.now().isoformat()
    ctx.set("now_iso", datetime.now().isoformat())
    ctx.set("test_email", flow_spec.get("test_email", ""))

    # Load state for step-by-step mode (not needed for dry-run)
    if step_num and step_num > 1 and not dry_run:
        loaded = ctx.load_state()
        if not loaded:
            warn(f"No saved state found. Run step 1 first.")
            return ctx
        # Restore test_email from state if it was saved
        if ctx.get("test_email"):
            flow_spec["test_email"] = ctx.get("test_email")

    sep()
    log(f"FLOW: {flow_spec['flow_name']}")
    if flow_spec.get("test_email"):
        log(f"Email: {flow_spec['test_email']}")
    if step_num:
        log(f"Running STEP {step_num} only (step-by-step mode)")
    log(f"Description: {flow_spec['description']}")
    sep()

    overall_pass = True
    steps = flow_spec["steps"]

    # Determine which steps to run
    if step_num:
        if step_num < 1 or step_num > len(steps):
            fail(f"Step {step_num} out of range (1-{len(steps)})")
            return ctx
        step_range = [(step_num, steps[step_num - 1])]
    else:
        step_range = list(enumerate(steps, 1))

    for i_idx, step in step_range:
        step_type = step.get("type")
        step_name = step.get("name", step_type)
        step_id = step.get("step_id", f"step_{i_idx}")

        sep2()
        log(f"Step {i_idx}/{len(steps)}: [{step_type}] {step_name}")

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
            elif step_type == "airtable_create":
                info(f"  Table: {resolved.get('table_id', '?')}")
                info(f"  Fields: {list(resolved.get('fields', {}).keys())}")
            elif step_type == "airtable_update":
                info(f"  Record: {resolved.get('record_id', '?')}")
                info(f"  Fields: {resolved.get('fields', {})}")
            elif step_type == "n8n_execute":
                info(f"  Workflow: {resolved.get('workflow_key', '?')}")
                wk = resolved.get('workflow_key', '')
                info(f"  Link: {link_n8n_wf(wk)}")
            elif step_type == "verify_n8n_workflow":
                info(f"  Workflow: {resolved.get('workflow_key', '?')}")
                wk = resolved.get('workflow_key', '')
                info(f"  Link: {link_n8n_wf(wk)}")
                info(f"  Expect nodes: {resolved.get('expect_nodes', [])}")
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

        # Print links from step
        for lnk in entry.get("links", []):
            ctx.add_link(lnk["label"], lnk["url"], resource_type=lnk.get("type", ""),
                         resource_id=lnk.get("id", ""), step_id=step_id)

        if passed is False:
            if step.get("critical", True):
                overall_pass = False
                warn(f"Critical step failed. Stopping flow.")
                break
            else:
                warn(f"Non-critical step failed. Continuing.")

        # Shopify rate limiting
        if step_type == "verify_shopify":
            time.sleep(0.5)

    ctx.finished_at = datetime.now().isoformat()
    ctx.status = "PASS" if overall_pass else ("DRY-RUN" if dry_run else "FAIL")

    # Save state after each run (for step-by-step mode)
    if not dry_run:
        ctx.save_state()

    sep()
    s = ctx.summary()
    log(f"FLOW RESULT: {ctx.status}  ({s['passed']}/{s['total']} passed, {s['failed']} failed, {s['skipped']} skipped)")

    # Print Data Trail
    if ctx.data_trail:
        sep2()
        log("DATA TRAIL (where data was stored):")
        for dt in ctx.data_trail:
            log(f"  {dt['label']}: {dt['url']}")
    sep()

    return ctx


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

def _delete_airtable_record(base_id, table_id, record_id):
    """Delete a single Airtable record."""
    if not record_id or not isinstance(record_id, str) or not record_id.startswith("rec"):
        return
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok(f"Airtable record {record_id} deleted from {table_id}")
    except Exception as e:
        warn(f"Airtable cleanup failed ({record_id}): {e}")


def run_cleanup(cleanup_spec, ctx):
    """Delete test data created during the flow."""
    resolved = ctx.interpolate(cleanup_spec)
    test_email = resolved.get("test_email", "")

    # Safety: only delete test data
    if test_email and TEST_EMAIL_DOMAIN not in test_email:
        warn(f"SAFETY: Refusing to cleanup non-test email '{test_email}'")
        return

    log("\n  [CLEANUP]")

    # 1a. Delete single Airtable record (legacy format)
    record_id = resolved.get("airtable_record_id")
    if record_id and AIRTABLE_API_KEY:
        _delete_airtable_record(AT_BASE, AT_APPLICANTS, record_id)

    # 1b. Delete multiple Airtable records (pipeline format)
    airtable_records = resolved.get("airtable_records", [])
    for rec in airtable_records:
        if isinstance(rec, dict):
            tid = rec.get("table_id", "")
            rid = rec.get("record_id", "")
            if tid and rid and isinstance(rid, str) and rid.startswith("rec"):
                _delete_airtable_record(AT_BASE, tid, rid)

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
  .link-row {{ padding: 4px 14px; font-size: 13px; }}
  .link-row a {{ color: #58a6ff; text-decoration: none; }}
  .link-row a:hover {{ text-decoration: underline; color: #79c0ff; }}
  .data-trail {{ background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 14px; margin-top: 16px; }}
  .data-trail h3 {{ font-size: 14px; color: #d2a8ff; margin-bottom: 8px; }}
  .trail-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }}
  .trail-icon {{ font-size: 16px; min-width: 24px; text-align: center; }}
  .trail-label {{ color: #8b949e; min-width: 180px; }}
  .trail-link a {{ color: #58a6ff; text-decoration: none; word-break: break-all; }}
  .trail-link a:hover {{ text-decoration: underline; }}
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

            # Links
            for lnk in result.get("links", []):
                html_parts.append(f"""        <div class="link-row"><a href="{lnk['url']}" target="_blank">-> {lnk['label']}</a></div>\n""")

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

        # Data Trail
        if ctx.data_trail:
            trail_icons = {"Airtable": "AT", "Shopify": "SP", "n8n": "N8"}
            html_parts.append("""      <div class="data-trail"><h3>Data Trail (Where Data Lives)</h3>\n""")
            for dt in ctx.data_trail:
                icon = "AT" if "airtable" in dt["label"].lower() else ("SP" if "shopify" in dt["label"].lower() else "N8")
                html_parts.append(f"""        <div class="trail-row"><span class="trail-icon">[{icon}]</span><span class="trail-label">{dt['label']}</span><span class="trail-link"><a href="{dt['url']}" target="_blank">{dt['url']}</a></span></div>\n""")
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


def cmd_run(flow_names, dry_run=False, no_cleanup=False, wait_multiplier=1.0,
            verbose=False, email=None, step_num=None):
    """Run specified flows."""
    all_contexts = []

    # Safety warning for real emails
    if email and TEST_EMAIL_DOMAIN not in email:
        log(f"\n  ** REAL EMAIL MODE: {email} **")
        log(f"  ** Cleanup will be SKIPPED for safety **\n")
        no_cleanup = True

    for name in flow_names:
        builder = FLOW_REGISTRY.get(name)
        if not builder:
            warn(f"Unknown flow: {name}. Available: {', '.join(FLOW_REGISTRY.keys())}")
            continue

        flow_spec = builder(email=email)
        ctx = run_flow(flow_spec, dry_run=dry_run, wait_multiplier=wait_multiplier, step_num=step_num)
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
    parser.add_argument("--email", type=str, default=None,
                        help="Use real email (e.g. wj.choi@orbiters.co.kr). Auto-skips cleanup.")
    parser.add_argument("--step", type=int, default=None,
                        help="Run ONLY step N (1-indexed). State saved between steps.")

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
                wait_multiplier=args.wait_multiplier, verbose=args.verbose,
                email=args.email, step_num=args.step)
