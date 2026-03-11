"""
n8n 워크플로우 생성: Syncly Daily Content Metrics Sync
=======================================================
매일 PST 00:00 (= UTC 08:00) 로컬 웹훅 서버 호출.

워크플로우:
  Schedule Trigger (매일 08:00 UTC)
    → HTTP Request POST /sync
    → IF success
        → ✅ NoOp (성공 로그)
        → ❌ NoOp (실패 — n8n UI에서 확인)

전제 조건:
  - 로컬 PC에서 run_syncly_server.py 상시 실행 중
  - 로컬 서버가 n8n에서 접근 가능한 URL 보유
    (같은 네트워크: 로컬 IP, 외부: Cloudflare Tunnel / ngrok 등)

사용:
  py tools/setup_n8n_syncly_daily.py --webhook-url "http://YOUR_IP:5050/sync"
  py tools/setup_n8n_syncly_daily.py --dry-run
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from env_loader import load_env

load_env()

N8N_API_KEY  = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")

WORKFLOW_NAME    = "Syncly: Daily Content Metrics Sync"
DEFAULT_HOOK_URL = "http://localhost:5050/sync"


# ──── n8n API ────

def n8n_request(method, path, data=None):
    url  = f"{N8N_BASE_URL}/api/v1{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req  = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"  [n8n ERROR] {e.code}: {err[:500]}")
        raise


def find_existing():
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


# ──── 워크플로우 정의 ────

def build_workflow(webhook_url: str) -> dict:
    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            {
                "id": "node-schedule",
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [200, 300],
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "cronExpression",
                                # 매일 UTC 08:00 = PST 00:00
                                "expression": "0 8 * * *",
                            }
                        ]
                    }
                },
            },
            {
                "id": "node-http",
                "name": "Run Syncly Sync",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [440, 300],
                "parameters": {
                    "method": "POST",
                    "url": webhook_url,
                    "options": {
                        "timeout": 360000,    # 6분 타임아웃 (fetch+sync 여유)
                        "response": {"response": {"responseFormat": "json"}},
                    },
                },
            },
            {
                "id": "node-if",
                "name": "Check Result",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [680, 300],
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "strict",
                        },
                        "conditions": [
                            {
                                "id": "cond-success",
                                "leftValue": "={{ $json.success }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "equals",
                                },
                            }
                        ],
                        "combinator": "and",
                    }
                },
            },
            {
                "id": "node-ok",
                "name": "✅ Sync 완료",
                "type": "n8n-nodes-base.noOp",
                "typeVersion": 1,
                "position": [920, 180],
                "parameters": {},
            },
            {
                "id": "node-fail",
                "name": "❌ Sync 실패 (로그 확인)",
                "type": "n8n-nodes-base.noOp",
                "typeVersion": 1,
                "position": [920, 420],
                "parameters": {},
            },
        ],
        "connections": {
            "Schedule Trigger": {
                "main": [[{"node": "Run Syncly Sync", "type": "main", "index": 0}]]
            },
            "Run Syncly Sync": {
                "main": [[{"node": "Check Result", "type": "main", "index": 0}]]
            },
            "Check Result": {
                "main": [
                    [{"node": "✅ Sync 완료",           "type": "main", "index": 0}],
                    [{"node": "❌ Sync 실패 (로그 확인)", "type": "main", "index": 0}],
                ]
            },
        },
        "settings": {"executionOrder": "v1"},
    }


# ──── Main ────

def main():
    parser = argparse.ArgumentParser(description="n8n Syncly Daily Sync 워크플로우 생성")
    parser.add_argument(
        "--webhook-url", default=DEFAULT_HOOK_URL,
        help=f"로컬 웹훅 서버 URL (기본: {DEFAULT_HOOK_URL})",
    )
    parser.add_argument("--dry-run", action="store_true", help="실제 생성 없이 JSON만 출력")
    args = parser.parse_args()

    workflow = build_workflow(args.webhook_url)

    if args.dry_run:
        print("[DRY RUN] 생성할 워크플로우 JSON:")
        print(json.dumps(workflow, indent=2, ensure_ascii=False))
        return

    existing = find_existing()
    if existing:
        wf_id = existing["id"]
        print(f"[n8n] 기존 워크플로우 발견 (id={wf_id}) → 업데이트...")
        n8n_request("PUT", f"/workflows/{wf_id}", workflow)
        print(f"[n8n] 업데이트 완료")
    else:
        result = n8n_request("POST", "/workflows", workflow)
        wf_id  = result["id"]
        print(f"[n8n] 워크플로우 생성 완료 (id={wf_id})")

    # 활성화
    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"[n8n] 활성화 완료")
    except Exception as e:
        print(f"[n8n] 활성화 실패 (n8n UI에서 수동 활성화 필요): {e}")

    print(f"""
[DONE] 워크플로우: {WORKFLOW_NAME}
  스케줄  : 매일 UTC 08:00 (PST 00:00 / KST 17:00)
  웹훅 URL: {args.webhook_url}

⚠️  로컬 PC에서 웹훅 서버를 항상 실행해두세요:
  py tools/run_syncly_server.py

n8n이 외부 서버라면 로컬 PC를 인터넷에 노출해야 합니다:
  [추천] Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
  [간편] ngrok: ngrok http 5050
  그 후: --webhook-url "https://xxxx.trycloudflare.com/sync" 로 재실행
""")


if __name__ == "__main__":
    main()
