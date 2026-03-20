"""Pipeline CRM E2E test suite.

Tests all API flows against the live EC2 server and saves results to JSON.
Usage: python tools/run_pipeline_e2e.py
"""
import sys
import json
import urllib.request
import ssl
import base64
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'https://orbitools.orbiters.co.kr/api/onzenna'
CTX = ssl._create_unverified_context()
CREDS = base64.b64encode(b'admin:admin').decode()
RESULTS = []


def api(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header('Authorization', f'Basic {CREDS}')
    req.add_header('Content-Type', 'application/json')
    try:
        resp = urllib.request.urlopen(req, context=CTX, timeout=15)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = str(e)
        return e.code, body
    except Exception as e:
        return 0, str(e)


def add(flow, test, ok, detail):
    status = 'PASS' if ok else 'FAIL'
    RESULTS.append({'flow': flow, 'test': test, 'status': status, 'detail': detail})
    print(f'  [{status}] {test} -- {detail}')


def test_cors():
    print('\n=== Flow 1: CORS Preflight ===')
    req = urllib.request.Request(BASE + '/tables/', method='OPTIONS')
    req.add_header('Origin', 'https://orbiters-dev.github.io')
    req.add_header('Access-Control-Request-Method', 'GET')
    req.add_header('Access-Control-Request-Headers', 'Authorization')
    try:
        resp = urllib.request.urlopen(req, context=CTX, timeout=10)
        cors = resp.headers.get('Access-Control-Allow-Origin', '')
        ok = 'orbiters-dev' in cors and resp.status == 204
        add('CORS', 'OPTIONS preflight', ok, f'status={resp.status}, origin={cors}')
    except Exception as e:
        add('CORS', 'OPTIONS preflight', False, str(e))


def test_creators():
    print('\n=== Flow 2: Creators CRUD ===')

    code, data = api('GET', '/pipeline/creators/stats/')
    ok = code == 200 and 'total' in data
    add('Creators', 'GET /stats/', ok, f'total={data.get("total","?")}' if ok else str(data))

    code, data = api('GET', '/pipeline/creators/?limit=5')
    ok = code == 200 and ('results' in data if isinstance(data, dict) else False)
    count = data.get('count', len(data.get('results', []))) if ok else '?'
    add('Creators', 'GET /creators/?limit=5', ok, f'{count} total')

    cid = None
    if ok and data.get('results'):
        cid = data['results'][0]['id']
        code2, d2 = api('GET', f'/pipeline/creators/{cid}/')
        ok2 = code2 == 200 and isinstance(d2, dict) and d2.get('id') == cid
        handle = d2.get('handle', '?') if isinstance(d2, dict) else '?'
        add('Creators', 'GET /creators/<id>/', ok2, f'handle={handle}')

    if cid:
        code, data = api('POST', '/pipeline/creators/bulk-status/', {'ids': [cid], 'status': 'Not Started'})
        updated = data.get('updated', 0) if isinstance(data, dict) else 0
        ok = code == 200 and updated >= 0  # 0 is ok if already that status
        add('Creators', 'POST /bulk-status/', ok, f'status={code}, updated={updated}')


def test_config():
    print('\n=== Flow 3: Config ===')

    code, data = api('GET', '/pipeline/config/today/')
    ok = code == 200 and 'date' in data
    add('Config', 'GET /config/today/', ok, f'date={data.get("date","?")}' if ok else str(data))

    cfg = {'creators_contacted': 10, 'ht_threshold': 100000, 'human_in_loop': 'on', 'rag_email_dedup': True}
    code, data = api('POST', '/pipeline/config/2026-03-20/', cfg)
    ok = code in (200, 201)
    add('Config', 'POST /config/<date>/', ok, f'status={code}')

    code, data = api('GET', '/pipeline/config/history/')
    ok = code == 200 and isinstance(data, list)
    add('Config', 'GET /config/history/', ok, f'{len(data)} entries' if ok else str(data))


def test_exec_log():
    print('\n=== Flow 4: Execution Log ===')

    code, data = api('POST', '/pipeline/execution/log/', {
        'action_type': 'e2e_test', 'triggered_by': 'run_pipeline_e2e',
        'target_count': 0, 'status': 'completed'
    })
    ok = code == 201 and 'id' in data
    add('Exec Log', 'POST /execution/log/', ok, f'id={data.get("id","?")}')

    code, data = api('GET', '/pipeline/execution/log/')
    ok = code == 200 and data.get('total', 0) >= 1
    add('Exec Log', 'GET /execution/log/', ok, f'{data.get("total","?")} entries')


def test_discovery():
    print('\n=== Flow 5: Syncly Discovery Import ===')
    code, data = api('POST', '/pipeline/creators/import-discovery/', {'min_followers': 500, 'limit': 10})
    ok = code in (200, 201) and isinstance(data, dict) and 'created' in data
    add('Discovery', 'POST /import-discovery/', ok,
        f'created={data.get("created","?")}, skipped={data.get("skipped","?")}')


def test_gmail_rag():
    print('\n=== Flow 6: Gmail RAG ===')
    code, data = api('GET', '/gmail-rag/check-contact/?email=test@example.com')
    ok = code == 200
    detail = f'found={data.get("found","?")}' if isinstance(data, dict) else f'status={code}, data={data}'
    add('Gmail RAG', 'GET /check-contact/', ok, detail)


def test_monitoring():
    print('\n=== Flow 7: Monitoring ===')
    code, data = api('GET', '/tables/')
    ok = code == 200 and isinstance(data, dict) and 'tables' in data
    tbl_count = len(data['tables']) if ok else '?'
    add('Monitoring', 'GET /tables/', ok, f'{tbl_count} tables')


if __name__ == '__main__':
    print(f'Pipeline CRM E2E Test Suite')
    print(f'Target: {BASE}')
    print(f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}')

    test_cors()
    test_creators()
    test_config()
    test_exec_log()
    test_discovery()
    test_gmail_rag()
    test_monitoring()

    passed = sum(1 for r in RESULTS if r['status'] == 'PASS')
    failed = sum(1 for r in RESULTS if r['status'] == 'FAIL')
    print(f'\n{"="*50}')
    print(f'TOTAL: {passed}/{len(RESULTS)} PASS, {failed} FAIL')
    print(f'{"="*50}')

    out = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'base_url': BASE,
        'results': RESULTS,
        'summary': {'passed': passed, 'failed': failed, 'total': len(RESULTS)}
    }
    with open('.tmp/pipeline_e2e_results.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print('Saved: .tmp/pipeline_e2e_results.json')
