"""[SE] Amazon JP 주문 파이프라인 n8n 워크플로우 생성.

KSE OMS 배송접수 후 팩킹리스트 데이터를 받아 주문 요약을 생성하고
Teams로 자동 전송하는 n8n 워크플로우를 생성/업데이트한다.

워크플로우 구조:
  1. Webhook (POST /se-mazonee-summary) ← kse_order_summary.py가 호출
  2. Code: 상품 분류 + 주문 요약 텍스트 생성
  3. HTTP Request: Teams 웹훅으로 전송
  4. Respond to Webhook: 200 OK

Usage:
    python tools/setup_n8n_amazon_pipeline.py
    python tools/setup_n8n_amazon_pipeline.py --dry-run
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

WORKFLOW_NAME = "[SE] Amazon JP 주문 파이프라인"



def find_existing_workflow():
    """Find existing workflow by name."""
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf.get("id")
    return None


# ============================================================
# JavaScript: 상품 분류 + 주문 요약 생성
# ============================================================
ORDER_SUMMARY_CODE = r"""// 팩킹리스트 데이터 → 채널별 주문 요약 텍스트 생성
const body = $input.first().json.body || $input.first().json;
const rows = body.rows || [];

if (!rows.length) {
  return [{ json: { summary: '(주문 데이터 없음)', rowCount: 0 } }];
}

// 상품 분류
function classifyProduct(titleKr) {
  const t = (titleKr || '').toLowerCase();
  const sizeMatch = t.match(/(\d+)\s*ml/);
  const size = sizeMatch ? sizeMatch[1] + 'ml' : '';

  if (t.includes('replacement straw')) return { cat: 'replacement straw', size: '' };
  if (t.includes('silicone') && t.includes('nipple')) return { cat: 'silicone nipple', size: '' };
  if (['dino', 'unicorn', 'flip'].some(kw => t.includes(kw))) return { cat: 'PPSU', size };
  if (t.includes('stainless')) return { cat: '스테인리스', size };
  if (t.includes('ppsu')) return { cat: 'PPSU', size };
  return { cat: '기타', size };
}

// 채널 매핑
const channelMap = {
  amazonjp: '아마존', amazon: '아마존',
  rakuten: '라쿠텐', rakutenjp: '라쿠텐'
};

// {채널: {카테고리: {사이즈: 수량}}}
const summary = {};

for (const row of rows) {
  const market = (row.market || '').toLowerCase();
  const channel = channelMap[market] || market;
  const titleKr = row.itemTitleKr || '';
  const qty = parseInt(row.orderQty || '1', 10);
  const { cat, size } = classifyProduct(titleKr);

  if (!summary[channel]) summary[channel] = {};
  if (!summary[channel][cat]) summary[channel][cat] = {};
  summary[channel][cat][size] = (summary[channel][cat][size] || 0) + qty;
}

// 정렬된 출력
const channelOrder = ['아마존', '라쿠텐'];
const catOrder = ['PPSU', '스테인리스', 'replacement straw', 'silicone nipple', '기타'];

const lines = [];
for (const ch of channelOrder) {
  if (!summary[ch]) continue;
  const cats = summary[ch];
  let first = true;
  for (const cat of catOrder) {
    if (!cats[cat]) continue;
    const sizes = cats[cat];
    let sizeStr;
    if ('' in sizes) {
      sizeStr = `x ${sizes['']}`;
    } else {
      const parts = [];
      for (const s of Object.keys(sizes).sort()) {
        if (s) parts.push(`${s} x ${sizes[s]}`);
      }
      sizeStr = parts.join('/ ');
    }
    const prefix = first ? `${ch}: ` : '            ';
    lines.push(`${prefix}(${cat}) ${sizeStr}`);
    first = false;
  }
}

lines.push('');
lines.push('주문 들어온 것 공유드립니다.');
const summaryText = lines.join('\n');

return [{ json: { summary: summaryText, rowCount: rows.length } }];
"""

# ============================================================
# JavaScript: Teams MessageCard 생성
# ============================================================
TEAMS_CARD_CODE = r"""// Teams MessageCard 포맷으로 변환
const { summary, rowCount } = $input.first().json;

const today = new Date();
const mm = String(today.getMonth() + 1).padStart(2, '0');
const dd = String(today.getDate()).padStart(2, '0');
const dateStr = `${today.getFullYear()}-${mm}-${dd}`;

const card = {
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "themeColor": "FF6A00",
  "summary": `Amazon JP: ${dateStr} 주문 요약`,
  "sections": [
    {
      "activityTitle": `📦 ${dateStr} 주문 요약 (${rowCount}건)`,
      "activitySubtitle": "Amazon JP 주문 파이프라인",
      "text": summary.replace(/\n/g, '<br/>'),
      "markdown": false
    }
  ]
};

return [{ json: { card } }];
"""


def build_workflow_nodes():
    """Build all nodes for the Amazon JP pipeline workflow."""
    nodes = []

    # ── Sticky Notes (파이프라인 단계 시각화) ──
    pipeline_steps = """## Amazon JP 주문 파이프라인 전체 흐름

1️⃣ KSE OMS 로그인
2️⃣ /orders → 주문등록(Excel) 탭
3️⃣ Amazon 주문 Excel 업로드 (TXT→Excel 변환)
4️⃣ 주문 목록에서 옵션코드 입력
5️⃣ 최상단 체크박스 → 전체 선택
6️⃣ 배송접수(국제) 클릭
7️⃣ 팩킹리스트(/shipping2) 이동 확인
8️⃣ 다운로드▼ → 아마존 엑셀 다운로드
9️⃣ 파일 저장: {MMDD}_amazon_주문서.xlsx
🔟 주문 요약 생성 + Teams 전송 ← 이 워크플로우"""

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Sticky Note - Pipeline",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [-200, -200],
        "parameters": {
            "content": pipeline_steps,
            "height": 420,
            "width": 380,
            "color": 4,
        },
    })

    webhook_note = """## Webhook 사용법

kse_order_summary.py 에서 자동 호출:
```
POST /webhook/se-mazonee-summary
Body: { "rows": [...팩킹리스트 데이터...] }
```

또는 수동 테스트:
```
curl -X POST {webhook_url} \\
  -H "Content-Type: application/json" \\
  -d '{"rows": [...]}'
```"""

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Sticky Note - Webhook",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [200, -200],
        "parameters": {
            "content": webhook_note,
            "height": 320,
            "width": 360,
            "color": 6,
        },
    })

    # ── 1. Webhook Trigger ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Order Data Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 200],
        "parameters": {
            "path": "se-mazonee-summary",
            "httpMethod": "POST",
            "responseMode": "responseNode",
            "options": {},
        },
        "webhookId": str(uuid.uuid4()),
    })

    # ── 2. Code: 주문 요약 생성 ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Generate Order Summary",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [480, 200],
        "parameters": {
            "jsCode": ORDER_SUMMARY_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # ── 3. Code: Teams MessageCard 생성 ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Build Teams Card",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [740, 200],
        "parameters": {
            "jsCode": TEAMS_CARD_CODE,
            "mode": "runOnceForAllItems",
        },
    })

    # ── 4. HTTP Request: Teams 웹훅 전송 ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Send to Teams",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1000, 200],
        "parameters": {
            "method": "POST",
            "url": TEAMS_WEBHOOK_SEEUN,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.card) }}",
            "options": {},
        },
    })

    # ── 5. Respond to Webhook ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Respond OK",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": [1260, 200],
        "parameters": {
            "respondWith": "json",
            "responseBody": '={{ JSON.stringify({ ok: true, summary: $("Generate Order Summary").first().json.summary }) }}',
            "options": {},
        },
    })

    return nodes


def build_connections():
    """Build node connections."""
    return {
        "Order Data Webhook": {
            "main": [[{"node": "Generate Order Summary", "type": "main", "index": 0}]]
        },
        "Generate Order Summary": {
            "main": [[{"node": "Build Teams Card", "type": "main", "index": 0}]]
        },
        "Build Teams Card": {
            "main": [[{"node": "Send to Teams", "type": "main", "index": 0}]]
        },
        "Send to Teams": {
            "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
        },
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Amazon JP n8n 워크플로우 생성")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (생성하지 않음)")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  [SE] Amazon JP 주문 파이프라인")
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

    print(f"  노드 {len(nodes)}개:")
    for n in nodes:
        ntype = n["type"].replace("n8n-nodes-base.", "")
        print(f"    - {n['name']} ({ntype})")

    print(f"\n  연결:")
    for src, targets in connections.items():
        for outputs in targets.get("main", []):
            for t in outputs:
                print(f"    {src} → {t['node']}")

    if args.dry_run:
        print(f"\n  [DRY RUN] 실제 생성하지 않았습니다.")

        # Save preview JSON
        preview = {
            "name": WORKFLOW_NAME,
            "nodes": nodes,
            "connections": connections,
        }
        preview_path = os.path.join(DIR, "..", ".tmp", "n8n_mazonee_pipeline_preview.json")
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        with open(preview_path, "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
        print(f"  미리보기 저장: {preview_path}")
        return

    # 기존 워크플로우 확인
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

    # Activate
    print(f"\n  워크플로우 활성화...")
    try:
        n8n_request("PATCH", f"/workflows/{wf_id}", {"active": True})
        print(f"  [OK] 활성화 완료")
    except Exception as e:
        print(f"  [WARN] 활성화 실패: {e}")
        print(f"  n8n UI에서 수동 활성화 필요")

    # Print webhook URL
    print(f"\n  Webhook URL:")
    print(f"  POST {N8N_BASE_URL}/webhook/se-mazonee-summary")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
