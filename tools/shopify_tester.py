"""
Shopify Tester — Customer Journey Test Runner
=============================================
쇼피파이 고객 저니 자동 테스트 실행기.

두 Claude 대화창이 .tmp/test_queue.json 파일을 통해 핸드오프.
  - 개발 대화창: --push 로 테스트 스펙 등록
  - 테스터 대화창: --run 으로 큐에서 읽어 실행

Usage:
    # 테스트 스펙 큐에 등록 (개발 대화창에서)
    python tools/shopify_tester.py --push --spec path/to/spec.json

    # 큐에 있는 테스트 모두 실행 (테스터 대화창에서)
    python tools/shopify_tester.py --run

    # 인라인 스펙으로 즉시 실행
    python tools/shopify_tester.py --run --spec path/to/spec.json

    # 마지막 결과 보기
    python tools/shopify_tester.py --results

    # 큐 상태 확인
    python tools/shopify_tester.py --status

Supported step types:
    http_post          - HTTP POST 요청 & 응답 검증
    http_get           - HTTP GET 요청 & 응답 검증
    verify_airtable    - Airtable 레코드 존재/필드값 검증
    verify_postgres    - orbitools API 통해 PostgreSQL 검증
    verify_shopify     - Shopify Admin API 고객/메타필드 검증
    wait               - 다음 스텝 전 대기 (비동기 처리 대기용)
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# .tmp 기준 경로
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP = os.path.join(ROOT, ".tmp")
QUEUE_FILE = os.path.join(TMP, "test_queue.json")
RESULTS_FILE = os.path.join(TMP, "test_results.json")

os.makedirs(TMP, exist_ok=True)

# env 로드
try:
    sys.path.insert(0, DIR)
    from env_loader import load_env
    load_env()
except ImportError:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")
SHOPIFY_STORE = os.getenv("SHOPIFY_SHOP", "")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

# ─── 출력 헬퍼 ───────────────────────────────────────────────────────────────

def log(msg): print(msg)
def ok(msg):  print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def sep(): print("-" * 60)


# ─── HTTP 유틸 ───────────────────────────────────────────────────────────────

def http_request(method, url, payload=None, headers=None, basic_auth=None, timeout=30):
    """urllib 기반 HTTP 요청. requests 없이 동작."""
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


# ─── 스텝 실행기들 ───────────────────────────────────────────────────────────

def run_http_post(step):
    url = step["url"]
    payload = step.get("payload", {})
    expect_status = step.get("expect_status", 200)
    expect_fields = step.get("expect_fields", {})

    log(f"  POST {url}")
    status, body = http_request("POST", url, payload=payload)

    passed = True
    details = {}

    if status != expect_status:
        fail(f"Status {status} (expected {expect_status})")
        passed = False
    else:
        ok(f"Status {status}")

    details["status_code"] = status
    details["response"] = body if isinstance(body, dict) else str(body)[:300]

    if expect_fields and isinstance(body, dict):
        for field, expected in expect_fields.items():
            actual = body.get(field)
            if actual == expected:
                ok(f"Response field '{field}' = {expected!r}")
            else:
                fail(f"Response field '{field}': expected {expected!r}, got {actual!r}")
                passed = False
                details[f"field_mismatch_{field}"] = {"expected": expected, "actual": actual}

    return passed, details


def run_http_get(step):
    url = step["url"]
    expect_status = step.get("expect_status", 200)
    expect_fields = step.get("expect_fields", {})

    log(f"  GET {url}")
    status, body = http_request("GET", url)

    passed = True
    details = {"status_code": status}

    if status != expect_status:
        fail(f"Status {status} (expected {expect_status})")
        passed = False
    else:
        ok(f"Status {status}")

    details["response"] = body if isinstance(body, dict) else str(body)[:300]
    return passed, details


def run_verify_airtable(step):
    base_id = step["base_id"]
    table_id = step["table_id"]
    filter_field = step.get("filter_field")
    filter_value = step.get("filter_value")
    expect_fields = step.get("expect_fields", {})
    expect_exists = step.get("expect_exists", True)

    if not AIRTABLE_API_KEY:
        warn("AIRTABLE_API_KEY not set -- skipping")
        return None, {"skipped": "no AIRTABLE_API_KEY"}

    # Airtable filter formula
    safe_value = filter_value.replace("'", "\\'")
    formula = urllib.parse.quote(f"{{{filter_field}}}='{safe_value}'")
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}?filterByFormula={formula}&maxRecords=5"
    log(f"  Airtable: {base_id}/{table_id} where {filter_field}={filter_value!r}")

    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        fail(f"Airtable API error {e.code}: {e.read().decode()[:200]}")
        return False, {"error": f"HTTP {e.code}"}

    records = data.get("records", [])
    passed = True
    details = {"record_count": len(records)}

    if expect_exists and not records:
        fail(f"No record found in Airtable (expected exists)")
        return False, details
    elif not expect_exists and records:
        fail(f"Record found in Airtable (expected NOT exists)")
        return False, details
    elif expect_exists:
        ok(f"Record found in Airtable ({len(records)} match)")
        fields = records[0].get("fields", {})
        details["record"] = fields
        for field, expected in expect_fields.items():
            actual = fields.get(field)
            if actual == expected:
                ok(f"  Field '{field}' = {expected!r}")
            else:
                fail(f"  Field '{field}': expected {expected!r}, got {actual!r}")
                passed = False
    else:
        ok("No record in Airtable (as expected)")

    return passed, details


def run_verify_postgres(step):
    endpoint = step["endpoint"]
    filter_params = step.get("filter", {})
    expect_exists = step.get("expect_exists", True)
    expect_fields = step.get("expect_fields", {})

    if not ORBITOOLS_URL:
        warn("ORBITOOLS_URL not set -- skipping")
        return None, {"skipped": "no ORBITOOLS_URL"}

    qs = urllib.parse.urlencode(filter_params)
    url = f"{ORBITOOLS_URL}{endpoint}?{qs}"
    log(f"  PostgreSQL (via orbitools): {endpoint} filter={filter_params}")

    auth = (ORBITOOLS_USER, ORBITOOLS_PASS) if ORBITOOLS_USER else None
    status, body = http_request("GET", url, basic_auth=auth)

    passed = True
    details = {"status_code": status}

    if status not in (200, 201):
        fail(f"orbitools API returned {status}")
        return False, details

    results = body if isinstance(body, list) else body.get("results", body.get("data", []))
    details["count"] = len(results) if isinstance(results, list) else "N/A"

    if expect_exists:
        if not results:
            fail("No record found in PostgreSQL")
            passed = False
        else:
            ok(f"Record found in PostgreSQL ({details['count']} rows)")
            if expect_fields and isinstance(results, list) and results:
                row = results[0]
                for field, expected in expect_fields.items():
                    actual = row.get(field)
                    if actual == expected:
                        ok(f"  Field '{field}' = {expected!r}")
                    else:
                        fail(f"  Field '{field}': expected {expected!r}, got {actual!r}")
                        passed = False
    else:
        if results:
            fail("Record found in PostgreSQL (expected NOT exists)")
            passed = False
        else:
            ok("No record in PostgreSQL (as expected)")

    return passed, details


def run_verify_shopify(step):
    resource = step.get("resource", "customer")
    filter_params = step.get("filter", {})
    expect_exists = step.get("expect_exists", True)
    expect_fields = step.get("expect_fields", {})

    if not SHOPIFY_STORE or not SHOPIFY_ADMIN_TOKEN:
        warn("SHOPIFY_STORE or SHOPIFY_ADMIN_TOKEN not set -- skipping")
        return None, {"skipped": "no Shopify credentials"}

    if resource == "customer":
        # Shopify search uses "field:value" format, not "field=value"
        query = " ".join(f"{k}:{v}" for k, v in filter_params.items())
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/search.json?query={urllib.parse.quote(query)}"
        log(f"  Shopify customer search: {filter_params}")
        headers = {"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}
        status, body = http_request("GET", url, headers=headers)
    elif resource == "metafield":
        customer_id = step.get("customer_id")
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/{customer_id}/metafields.json"
        log(f"  Shopify metafields for customer {customer_id}")
        headers = {"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}
        status, body = http_request("GET", url, headers=headers)
    else:
        warn(f"Unknown resource type: {resource}")
        return None, {"skipped": f"unknown resource {resource}"}

    passed = True
    details = {"status_code": status}

    if status != 200:
        fail(f"Shopify API returned {status}")
        return False, details

    if resource == "customer":
        customers = body.get("customers", []) if isinstance(body, dict) else []
        details["count"] = len(customers)
        if expect_exists and not customers:
            fail("No Shopify customer found")
            passed = False
        elif not expect_exists and customers:
            fail("Shopify customer found (expected NOT exists)")
            passed = False
        elif expect_exists:
            ok(f"Shopify customer found")
            c = customers[0]
            details["customer_id"] = c.get("id")
            for field, expected in expect_fields.items():
                actual = c.get(field)
                if actual == expected:
                    ok(f"  Field '{field}' = {expected!r}")
                else:
                    fail(f"  Field '{field}': expected {expected!r}, got {actual!r}")
                    passed = False
        else:
            ok("No Shopify customer (as expected)")

    return passed, details


def run_wait(step):
    seconds = step.get("seconds", 3)
    log(f"  Waiting {seconds}s for async processing...")
    time.sleep(seconds)
    ok(f"Waited {seconds}s")
    return True, {"waited_seconds": seconds}


# ─── 테스트 스펙 실행 ─────────────────────────────────────────────────────────

STEP_RUNNERS = {
    "http_post":       run_http_post,
    "http_get":        run_http_get,
    "verify_airtable": run_verify_airtable,
    "verify_postgres": run_verify_postgres,
    "verify_shopify":  run_verify_shopify,
    "wait":            run_wait,
}


def run_spec(spec):
    """테스트 스펙 하나를 실행하고 결과 dict 반환."""
    test_id = spec.get("test_id", "unknown")
    module = spec.get("module", "unknown")
    state = spec.get("state", "GUEST")
    description = spec.get("description", "")
    steps = spec.get("steps", [])

    sep()
    log(f"TEST: {test_id}")
    log(f"Module: {module}  |  State: {state}")
    log(f"Desc: {description}")
    sep()

    all_results = []
    overall_pass = True

    for i, step in enumerate(steps, 1):
        step_type = step.get("type")
        step_name = step.get("name", step_type)
        log(f"\nStep {i}/{len(steps)}: [{step_type}] {step_name}")

        runner = STEP_RUNNERS.get(step_type)
        if not runner:
            warn(f"Unknown step type: {step_type}")
            all_results.append({"step": step_name, "status": "SKIP", "details": {}})
            continue

        try:
            passed, details = runner(step)
        except Exception as e:
            fail(f"Exception: {e}")
            passed = False
            details = {"exception": str(e)}

        status_str = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
        if passed is False:
            overall_pass = False

        all_results.append({
            "step": step_name,
            "type": step_type,
            "status": status_str,
            "details": details,
        })

    sep()
    final = "PASS" if overall_pass else "FAIL"
    log(f"RESULT: {final}  ({sum(1 for r in all_results if r['status']=='PASS')}/{len(steps)} steps passed)")
    sep()

    return {
        "test_id": test_id,
        "module": module,
        "state": state,
        "description": description,
        "status": final,
        "ran_at": datetime.now().isoformat(),
        "steps": all_results,
    }


# ─── 큐 관리 ─────────────────────────────────────────────────────────────────

def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def load_results():
    if not os.path.exists(RESULTS_FILE):
        return []
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def cmd_push(spec_path):
    """테스트 스펙을 큐에 등록."""
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    if not spec.get("test_id"):
        spec["test_id"] = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    spec["queued_at"] = datetime.now().isoformat()
    spec["status"] = "pending"

    queue = load_queue()
    # 같은 test_id 있으면 교체
    queue = [q for q in queue if q.get("test_id") != spec["test_id"]]
    queue.append(spec)
    save_queue(queue)
    log(f"[QUEUED] {spec['test_id']} -> {QUEUE_FILE}")


def cmd_run(spec_path=None):
    """큐 또는 지정 스펙 실행."""
    if spec_path:
        with open(spec_path, "r", encoding="utf-8") as f:
            specs = json.load(f)
        if isinstance(specs, dict):
            specs = [specs]
    else:
        specs = [s for s in load_queue() if s.get("status") == "pending"]
        if not specs:
            log("No pending tests in queue.")
            return

    all_results = load_results()

    for spec in specs:
        result = run_spec(spec)
        all_results.append(result)
        # 큐에서 상태 업데이트
        queue = load_queue()
        for q in queue:
            if q.get("test_id") == result["test_id"]:
                q["status"] = "done"
        save_queue(queue)

    save_results(all_results)
    log(f"\nResults saved: {RESULTS_FILE}")

    # 요약 출력
    sep()
    log("SUMMARY")
    sep()
    for r in all_results[-len(specs):]:
        mark = "OK" if r["status"] == "PASS" else "!!"
        log(f"  [{mark}] {r['test_id']:30s}  {r['status']}  ({r['module']} / {r['state']})")


def cmd_status():
    """큐 및 결과 현황."""
    queue = load_queue()
    results = load_results()
    log(f"Queue ({QUEUE_FILE}): {len(queue)} items")
    for q in queue:
        log(f"  {q.get('test_id', '?'):30s}  status={q.get('status','?')}")
    log(f"\nResults ({RESULTS_FILE}): {len(results)} items")
    for r in results[-10:]:
        mark = "OK" if r["status"] == "PASS" else "!!"
        log(f"  [{mark}] {r.get('test_id','?'):30s}  {r.get('status','?')}  ran={r.get('ran_at','?')[:16]}")


def cmd_results():
    """마지막 결과 상세 출력."""
    results = load_results()
    if not results:
        log("No results yet.")
        return
    for r in results[-5:]:
        sep()
        log(f"TEST: {r['test_id']}  |  {r['status']}  |  {r.get('ran_at','')[:16]}")
        for s in r.get("steps", []):
            mark = "OK" if s["status"] == "PASS" else ("--" if s["status"] == "SKIP" else "!!")
            log(f"  [{mark}] {s['step']}  -> {s['status']}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shopify Tester — Customer Journey QA Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--push",    action="store_true", help="Push spec to queue (requires --spec)")
    group.add_argument("--run",     action="store_true", help="Run pending tests (or --spec for inline)")
    group.add_argument("--status",  action="store_true", help="Show queue and result status")
    group.add_argument("--results", action="store_true", help="Show last test results in detail")
    parser.add_argument("--spec",   type=str, help="Path to test spec JSON file")
    args = parser.parse_args()

    if args.push:
        if not args.spec:
            parser.error("--push requires --spec <path>")
        cmd_push(args.spec)
    elif args.run:
        cmd_run(spec_path=args.spec)
    elif args.status:
        cmd_status()
    elif args.results:
        cmd_results()
