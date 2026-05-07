"""[SE] Rakuten 주문 파이프라인 — n8n 워크플로우 생성 (v2).

로컬 PC에서 파이프라인 실행 후 결과를 n8n webhook으로 POST하면,
n8n이 성공/실패 분기 → Teams 알림 + Google Sheets 기록을 담당한다.
매일 아침 9시(KST) 리마인더도 자동 전송.

워크플로우 구조:
  1. Webhook (POST /se-rakuten-pipeline) ← run_rakuten_pipeline.py
  2. Code: 결과 요약 + 성공/실패 판별
  3. If: 전부 성공?
     ├─ [true]  → 초록 Teams 카드 전송
     └─ [false] → If: 일부 성공?
          ├─ [true]  → 주황 Teams 카드 전송 (경고)
          └─ [false] → 빨강 Teams 카드 전송 (긴급)
  4. Prepare Log → Google Sheets 기록 (옵션)
  5. Respond to Webhook: 200 OK
  6. Schedule (매일 9am KST) → 리마인더 Teams 전송

Usage:
    python tools/setup_n8n_rakuten_pipeline.py
    python tools/setup_n8n_rakuten_pipeline.py --dry-run
"""
import os
import sys
import json
import uuid
import urllib.request
import urllib.error
import argparse

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env

load_env()

from n8n_api_client import n8n_request

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
TEAMS_WEBHOOK_SEEUN = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")

WORKFLOW_NAME = "[SE] Rakuten 주문 파이프라인"



def find_existing_workflow():
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf.get("id")
    return None


# ============================================================
# JavaScript: 파이프라인 결과 요약 + 성공/실패 판별
# ============================================================
RESULT_SUMMARY_CODE = r"""// run_rakuten_pipeline.py 결과 → 요약 + 성공/실패 분류
const body = $input.first().json.body || $input.first().json;
const steps = body.steps || [];
const totalOrders = body.totalOrders || 0;

if (!steps.length) {
  return [{ json: {
    summary: '(파이프라인 결과 데이터 없음)',
    stepCount: 0, allSuccess: false, someSuccess: false,
    successCount: 0, failCount: 0, failedSteps: [], totalOrders: 0
  } }];
}

const lines = [];
const failedSteps = [];

for (const step of steps) {
  const icon = step.success ? '✅' : '❌';
  const name = step.name || '';
  const detail = step.detail || '';
  lines.push(`${icon} ${name}`);
  if (detail) lines.push(`   ${detail}`);
  if (!step.success) failedSteps.push(name);
}

lines.push('');
if (totalOrders > 0) {
  lines.push(`총 ${totalOrders}건 처리 완료.`);
} else {
  lines.push('주문 처리 결과를 확인해 주세요.');
}
lines.push('주문 들어온 것 공유드립니다.');

const successCount = steps.filter(s => s.success).length;
const failCount = steps.filter(s => !s.success).length;
const allSuccess = failCount === 0;
const someSuccess = successCount > 0 && failCount > 0;

return [{ json: {
  summary: lines.join('\n'),
  stepCount: steps.length,
  allSuccess,
  someSuccess,
  successCount,
  failCount,
  failedSteps,
  totalOrders
} }];
"""

# ============================================================
# JavaScript: 성공 Teams Card (초록)
# ============================================================
SUCCESS_CARD_CODE = r"""const { summary, stepCount, totalOrders } = $input.first().json;
const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const dateStr = `${today.getFullYear()}-${mm}-${dd}`;

const card = {
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "00CC00",
  "summary": `✅ Rakuten 파이프라인 성공: ${dateStr}`,
  "sections": [{
    "activityTitle": `✅ ${dateStr} Rakuten 주문 파이프라인 완료`,
    "activitySubtitle": `${stepCount} steps 전체 성공`,
    "text": summary.replace(/\n/g, '<br/>'),
    "markdown": false
  }]
};
return [{ json: { card, ...($input.first().json) } }];
"""

# ============================================================
# JavaScript: 경고 Teams Card (주황)
# ============================================================
WARNING_CARD_CODE = r"""const { summary, stepCount, failedSteps, successCount, failCount } = $input.first().json;
const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const dateStr = `${today.getFullYear()}-${mm}-${dd}`;

const card = {
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "FF6A00",
  "summary": `⚠️ Rakuten 파이프라인 부분 실패: ${dateStr}`,
  "sections": [{
    "activityTitle": `⚠️ ${dateStr} Rakuten 주문 파이프라인 (${successCount}/${stepCount} 성공)`,
    "activitySubtitle": `실패: ${(failedSteps || []).join(', ')}`,
    "text": summary.replace(/\n/g, '<br/>'),
    "markdown": false
  }]
};
return [{ json: { card, ...($input.first().json) } }];
"""

# ============================================================
# JavaScript: 에러 Teams Card (빨강)
# ============================================================
ERROR_CARD_CODE = r"""const { summary, stepCount, failedSteps } = $input.first().json;
const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const dateStr = `${today.getFullYear()}-${mm}-${dd}`;

const card = {
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "CC0000",
  "summary": `🚨 Rakuten 파이프라인 전체 실패: ${dateStr}`,
  "sections": [{
    "activityTitle": `🚨 ${dateStr} Rakuten 주문 파이프라인 전체 실패`,
    "activitySubtitle": `${stepCount} steps 모두 실패 — 즉시 확인 필요`,
    "text": summary.replace(/\n/g, '<br/>'),
    "markdown": false
  }]
};
return [{ json: { card, ...($input.first().json) } }];
"""

# ============================================================
# JavaScript: Google Sheets 로그 데이터 준비
# ============================================================
PREPARE_LOG_CODE = r"""const data = $input.first().json;
const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const hh = String(today.getHours()).padStart(2, '0');
const mi = String(today.getMinutes()).padStart(2, '0');

let result;
if (data.allSuccess !== undefined) {
  // 파이프라인 결과 로그
  result = data.allSuccess ? '전체 성공' : (data.someSuccess ? '부분 실패' : '전체 실패');
} else {
  result = '알 수 없음';
}

return [{ json: {
  날짜: `${today.getFullYear()}-${mm}-${dd}`,
  시간: `${hh}:${mi}`,
  채널: 'Rakuten',
  성공: data.successCount || 0,
  실패: data.failCount || 0,
  총건수: data.totalOrders || 0,
  결과: result,
  실패_Step: (data.failedSteps || []).join(', '),
} }];
"""

# ============================================================
# JavaScript: 아침 리마인더 Teams Card (파랑)
# ============================================================
REMINDER_CARD_CODE = r"""const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const dateStr = `${today.getFullYear()}-${mm}-${dd}`;
const weekday = today.getDay();
const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
const dayName = dayNames[weekday];

const card = {
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "0078D7",
  "summary": `📋 ${dateStr} 주문 처리 리마인더`,
  "sections": [{
    "activityTitle": `📋 ${dateStr} (${dayName}) Rakuten 주문 처리`,
    "activitySubtitle": "아침 리마인더",
    "text": "오늘도 주문 확인할 시간입니다!<br/><br/>파이프라인 실행:<br/>python tools/run_rakuten_pipeline.py --headed",
    "markdown": false
  }]
};
return [{ json: { card } }];
"""


def _uid():
    return str(uuid.uuid4())


def build_workflow_nodes():
    nodes = []

    # ══════════════════════════════════════════════════════════
    # Sticky Notes (3개)
    # ══════════════════════════════════════════════════════════

    nodes.append({
        "id": _uid(),
        "name": "Sticky Note - Pipeline",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [-200, -200],
        "parameters": {
            "content": """## Rakuten 주문 파이프라인 v2

로컬 PC → webhook POST → 성공/실패 분기 → Teams 알림

**파이프라인 순서:**
1️⃣ RMS 주문확인 (100→300)
2️⃣ RMS 발송메일 (300→500)
3️⃣ KSE 주문수집+옵션코드+배송접수
4️⃣ KSE 옵션코드 보정
5️⃣ RMS 송장번호 입력""",
            "height": 380, "width": 400, "color": 4,
        },
    })

    nodes.append({
        "id": _uid(),
        "name": "Sticky Note - Features",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [700, -200],
        "parameters": {
            "content": """## v2 신규 기능

🔀 **에러 분기**
- 전체 성공 → 초록 알림
- 일부 실패 → 주황 경고
- 전체 실패 → 빨강 긴급

📊 **Google Sheets 로그**
- 매일 처리 결과 자동 기록
- (credential 설정 필요)

⏰ **아침 리마인더**
- 매일 9am KST (평일만)
- "주문 처리 시작하세요!" 알림""",
            "height": 380, "width": 360, "color": 6,
        },
    })

    nodes.append({
        "id": _uid(),
        "name": "Sticky Note - Sheets Setup",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [1600, -200],
        "parameters": {
            "content": """## Google Sheets 설정

1. Google Sheet 생성
2. 시트 이름: "파이프라인 로그"
3. 헤더: 날짜 | 시간 | 채널 | 성공 | 실패 | 총건수 | 결과 | 실패_Step
4. n8n에서 Google Sheets credential 추가
5. "Log to Google Sheets" 노드에 연결

⚠️ credential 없으면 이 노드만 스킵됨
(Teams 알림은 정상 작동)""",
            "height": 300, "width": 380, "color": 3,
        },
    })

    # ══════════════════════════════════════════════════════════
    # Main Flow: Webhook → Summary → Branching
    # ══════════════════════════════════════════════════════════

    # 1. Webhook Trigger
    nodes.append({
        "id": _uid(),
        "name": "Pipeline Result Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 200],
        "parameters": {
            "path": "se-rakuten-pipeline",
            "httpMethod": "POST",
            "responseMode": "responseNode",
            "options": {},
        },
        "webhookId": _uid(),
    })

    # 2. Generate Summary
    nodes.append({
        "id": _uid(),
        "name": "Generate Summary",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [480, 200],
        "parameters": {
            "jsCode": RESULT_SUMMARY_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 3. If: All Success?
    nodes.append({
        "id": _uid(),
        "name": "All Success?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [720, 200],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": ""},
                "conditions": [{
                    "id": _uid(),
                    "leftValue": "={{ $json.allSuccess }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "equals"},
                }],
                "combinator": "and",
            },
            "options": {},
        },
    })

    # ── 성공 경로 (초록) ──

    # 4. Build Success Card
    nodes.append({
        "id": _uid(),
        "name": "Build Success Card",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [980, 60],
        "parameters": {
            "jsCode": SUCCESS_CARD_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 5. Send Success Teams
    nodes.append({
        "id": _uid(),
        "name": "Send Success Teams",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1220, 60],
        "parameters": {
            "method": "POST",
            "url": TEAMS_WEBHOOK_SEEUN,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.card) }}",
            "options": {},
        },
    })

    # ── If: Some Success? (부분 실패 vs 전체 실패) ──

    # 6. If: Some Success?
    nodes.append({
        "id": _uid(),
        "name": "Some Success?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [980, 340],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": ""},
                "conditions": [{
                    "id": _uid(),
                    "leftValue": "={{ $json.someSuccess }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "equals"},
                }],
                "combinator": "and",
            },
            "options": {},
        },
    })

    # ── 경고 경로 (주황) ──

    # 7. Build Warning Card
    nodes.append({
        "id": _uid(),
        "name": "Build Warning Card",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1220, 260],
        "parameters": {
            "jsCode": WARNING_CARD_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 8. Send Warning Teams
    nodes.append({
        "id": _uid(),
        "name": "Send Warning Teams",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1460, 260],
        "parameters": {
            "method": "POST",
            "url": TEAMS_WEBHOOK_SEEUN,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.card) }}",
            "options": {},
        },
    })

    # ── 에러 경로 (빨강) ──

    # 9. Build Error Card
    nodes.append({
        "id": _uid(),
        "name": "Build Error Card",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1220, 440],
        "parameters": {
            "jsCode": ERROR_CARD_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 10. Send Error Teams
    nodes.append({
        "id": _uid(),
        "name": "Send Error Teams",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1460, 440],
        "parameters": {
            "method": "POST",
            "url": TEAMS_WEBHOOK_SEEUN,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.card) }}",
            "options": {},
        },
    })

    # ══════════════════════════════════════════════════════════
    # 로그 + 응답 (3개 경로 합류)
    # ══════════════════════════════════════════════════════════

    # 11. Prepare Log Data
    nodes.append({
        "id": _uid(),
        "name": "Prepare Log Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1700, 200],
        "parameters": {
            "jsCode": PREPARE_LOG_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 12. Log to Google Sheets (continueOnFail)
    nodes.append({
        "id": _uid(),
        "name": "Log to Google Sheets",
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5,
        "position": [1940, 200],
        "parameters": {
            "operation": "append",
            "documentId": {
                "mode": "url",
                "value": "https://docs.google.com/spreadsheets/d/PLACEHOLDER_SPREADSHEET_ID/edit",
            },
            "sheetName": {
                "mode": "name",
                "value": "파이프라인 로그",
            },
            "columns": {
                "mappingMode": "autoMapInputData",
                "value": {},
            },
            "options": {},
        },
        "onError": "continueRegularOutput",
    })

    # 13. Respond OK
    nodes.append({
        "id": _uid(),
        "name": "Respond OK",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": [2180, 200],
        "parameters": {
            "respondWith": "json",
            "responseBody": '={{ JSON.stringify({ ok: true, pipeline: "rakuten", teamsNotified: true }) }}',
            "options": {},
        },
    })

    # ══════════════════════════════════════════════════════════
    # 아침 리마인더 (독립 경로)
    # ══════════════════════════════════════════════════════════

    # 14. Morning Schedule Trigger (9am KST = 0am UTC, 평일만)
    nodes.append({
        "id": _uid(),
        "name": "Morning Schedule",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [200, 640],
        "parameters": {
            "rule": {
                "interval": [{
                    "field": "cronExpression",
                    "expression": "30 23 * * 0-4",
                }],
            },
        },
    })

    # 15. Build Reminder Card
    nodes.append({
        "id": _uid(),
        "name": "Build Reminder Card",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [480, 640],
        "parameters": {
            "jsCode": REMINDER_CARD_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # 16. Send Reminder Teams
    nodes.append({
        "id": _uid(),
        "name": "Send Reminder Teams",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [740, 640],
        "parameters": {
            "method": "POST",
            "url": TEAMS_WEBHOOK_SEEUN,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.card) }}",
            "options": {},
        },
    })

    return nodes


def build_connections():
    return {
        # Webhook → Summary → If
        "Pipeline Result Webhook": {
            "main": [[{"node": "Generate Summary", "type": "main", "index": 0}]]
        },
        "Generate Summary": {
            "main": [[{"node": "All Success?", "type": "main", "index": 0}]]
        },
        # If All Success: true → 초록, false → 2차 분기
        "All Success?": {
            "main": [
                [{"node": "Build Success Card", "type": "main", "index": 0}],
                [{"node": "Some Success?", "type": "main", "index": 0}],
            ]
        },
        # 성공 경로
        "Build Success Card": {
            "main": [[{"node": "Send Success Teams", "type": "main", "index": 0}]]
        },
        "Send Success Teams": {
            "main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]
        },
        # If Some Success: true → 주황, false → 빨강
        "Some Success?": {
            "main": [
                [{"node": "Build Warning Card", "type": "main", "index": 0}],
                [{"node": "Build Error Card", "type": "main", "index": 0}],
            ]
        },
        # 경고 경로
        "Build Warning Card": {
            "main": [[{"node": "Send Warning Teams", "type": "main", "index": 0}]]
        },
        "Send Warning Teams": {
            "main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]
        },
        # 에러 경로
        "Build Error Card": {
            "main": [[{"node": "Send Error Teams", "type": "main", "index": 0}]]
        },
        "Send Error Teams": {
            "main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]
        },
        # 3개 경로 합류 → 로그 → Sheets → 응답
        "Prepare Log Data": {
            "main": [[{"node": "Log to Google Sheets", "type": "main", "index": 0}]]
        },
        "Log to Google Sheets": {
            "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
        },
        # 아침 리마인더 (독립 경로)
        "Morning Schedule": {
            "main": [[{"node": "Build Reminder Card", "type": "main", "index": 0}]]
        },
        "Build Reminder Card": {
            "main": [[{"node": "Send Reminder Teams", "type": "main", "index": 0}]]
        },
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Rakuten 주문 파이프라인 n8n 워크플로우 생성 (v2)")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (생성하지 않음)")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  [SE] Rakuten 주문 파이프라인 v2")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"{'=' * 60}\n")

    if not N8N_API_KEY:
        print("  [ERROR] N8N_API_KEY 없음")
        sys.exit(1)
    if not TEAMS_WEBHOOK_SEEUN:
        print("  [ERROR] TEAMS_WEBHOOK_URL_SEEUN 없음")
        sys.exit(1)

    nodes = build_workflow_nodes()
    connections = build_connections()

    # 노드 카운트 (Sticky Note 제외)
    functional = [n for n in nodes if "stickyNote" not in n["type"]]
    sticky = [n for n in nodes if "stickyNote" in n["type"]]

    print(f"  노드: {len(nodes)}개 (기능 {len(functional)} + 메모 {len(sticky)})")
    print()
    for n in nodes:
        ntype = n["type"].replace("n8n-nodes-base.", "")
        if "stickyNote" in ntype:
            continue
        print(f"    - {n['name']} ({ntype})")

    print(f"\n  연결 ({len(connections)}개):")
    for src, targets in connections.items():
        for i, outputs in enumerate(targets.get("main", [])):
            label = ""
            if src in ("All Success?", "Some Success?"):
                label = " [true]" if i == 0 else " [false]"
            for t in outputs:
                print(f"    {src}{label} → {t['node']}")

    if args.dry_run:
        print(f"\n  [DRY RUN] 실제 생성하지 않았습니다.")
        preview = {"name": WORKFLOW_NAME, "nodes": nodes, "connections": connections}
        preview_path = os.path.join(DIR, "..", ".tmp", "n8n_rakuten_pipeline_v2_preview.json")
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        with open(preview_path, "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
        print(f"  미리보기 저장: {preview_path}")
        return

    # 기존 워크플로우 업데이트
    existing_id = find_existing_workflow()

    payload = {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "callerPolicy": "workflowsFromSameOwner",
        },
    }

    if existing_id:
        print(f"\n  기존 워크플로우 업데이트: {existing_id}")
        result = n8n_request("PUT", f"/workflows/{existing_id}", payload)
    else:
        print(f"\n  새 워크플로우 생성...")
        result = n8n_request("POST", "/workflows", payload)

    wf_id = result.get("id", "")
    print(f"\n  완료!")
    print(f"  ID: {wf_id}")
    print(f"  이름: {result.get('name', '')}")
    print(f"  노드: {len(result.get('nodes', []))}개")
    print(f"  URL: {N8N_BASE_URL}/workflow/{wf_id}")

    print(f"\n  Webhook URL:")
    print(f"  POST {N8N_BASE_URL}/webhook/se-rakuten-pipeline")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
