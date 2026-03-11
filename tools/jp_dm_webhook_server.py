"""
GROSMIMI Japan Instagram DM Webhook Server
ManyChat → Claude → Teams notification → Approve/Edit → ManyChat send DM

Replaces n8n workflow: b2WeE6ZPkaTjTvu2
Endpoints:
  POST /webhook/jp-ig-dm-v1         - receives DM from ManyChat
  GET  /webhook/jp-ig-dm-approve-v1 - approve & send DM
  GET  /webhook/jp-ig-dm-edit       - show edit form
  POST /webhook/jp-ig-dm-edit       - submit edited reply
"""

import os, json, re, httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

app = FastAPI()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MANYCHAT_API_KEY  = os.getenv("MANYCHAT_API_KEY_JP", "")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")
DATA_FILE = ".tmp/jp_dm_data.json"
BASE_URL   = os.getenv("WEBHOOK_BASE_URL", "https://your-app.railway.app")  # update after deploy

# ─── Storage ────────────────────────────────────────────────────────────────

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_data(data: dict):
    os.makedirs(".tmp", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Claude ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an AI assistant managing Instagram DM conversations for GROSMIMI JAPAN (グロミミ), a Korean baby straw cup brand entering the Japanese market.
Your role: draft DM replies to influencers in professional Japanese, following the brand's SOP.

BRAND INFO:
- Brand: GROSMIMI JAPAN (グロミミ)
- Product: PPSU/Stainless straw cups for babies
- Rakuten: https://www.rakuten.co.jp/littlefingerusa/
- Account: @grosmimi_japan

TONE RULES:
- Formal keigo (敬語), business tone
- Always start with 「○○様」(use subscriber name)
- Minimal emoji (1 per message max at end)
- No overly casual expressions (「もちろん！」NG)
- Recommended: 「喜んでご用意させていただきます」「何なりとお申し付けください」

COLLABORATION CONDITIONS:
- Basic: gifting only (no payment)
- Paid: 10k+ followers → confirm desired amount with user first
- Content: Instagram Reel post
- Whitelisting required (Instagram + Facebook linked) — if refused, no contract

DM FLOW STAGES:
- greeting: First contact, ask about baby age
- recommendation: Recommend products based on age
- terms: Explain gifted collaboration terms
- shipping: Collect shipping address
- contract: DocuSign info collection
- content_review: Draft review
- posting: Confirm post link
- other: Doesn't fit above stages

NEEDS_HUMAN_REVIEW triggers (set needs_human_review: true):
- Influencer insists on paid collaboration
- Influencer shares Google Drive link
- Influencer shares video/draft content for review
- Any situation requiring judgment beyond the SOP

IMPORTANT RULES:
- NEVER make up contract amounts, policies, or conditions not in this prompt
- If unsure → set needs_human_review: true with alert_reason
- Output reply in Japanese + Korean translation separated by \\n\\n---한국어---\\n\\n

Respond in this exact JSON format (no markdown):
{
  "reply": "Japanese DM text here\\n\\n---한국어---\\n\\n Korean translation here",
  "stage": "one of: greeting/recommendation/terms/shipping/contract/content_review/posting/other",
  "needs_human_review": false,
  "alert_reason": "",
  "alert_note": ""
}
"""

def call_claude(history: list, subscriber_name: str, message: str) -> dict:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msgs = history + [{"role": "user", "content": f"[인플루언서 이름: {subscriber_name}]\n메시지: {message}"}]
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=msgs,
    )
    raw = response.content[0].text.strip()
    # extract JSON block if wrapped in ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        return {"reply": raw, "stage": "other", "needs_human_review": True,
                "alert_reason": "Claude 응답 JSON 파싱 실패", "alert_note": raw[:200]}

# ─── Teams notification ──────────────────────────────────────────────────────

def send_teams(subscriber_id: str, subscriber_name: str, message: str, result: dict):
    if not TEAMS_WEBHOOK_URL:
        print("TEAMS_WEBHOOK_URL not set, skipping Teams notification")
        return
    review_flag = " ⚠️ 확인필요: " + result.get("alert_reason", "") if result.get("needs_human_review") else ""
    reply_preview = result.get("reply", "")[:500]
    text = (
        f"[JP DM] @{subscriber_name}{review_flag}\n\n"
        f"📩 받은 메시지:\n{message or '(메시지 없음)'}\n\n"
        f"🤖 Claude 답장:\n{reply_preview}\n\n"
        f"Stage: {result.get('stage', '?')}"
        + (f"\n\n📝 메모: {result['alert_note']}" if result.get("alert_note") else "")
        + f"\n\n✅ 승인: {BASE_URL}/webhook/jp-ig-dm-approve-v1?id={subscriber_id}"
        + f"\n✏️ 수정: {BASE_URL}/webhook/jp-ig-dm-edit?id={subscriber_id}"
    )
    try:
        httpx.post(TEAMS_WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"Teams send error: {e}")

# ─── ManyChat send DM ────────────────────────────────────────────────────────

def send_manychat_dm(subscriber_id: str, message: str) -> bool:
    # Extract only Japanese part (before ---한국어--- separator)
    jp_text = message.split("---한국어---")[0].strip()
    url = "https://api.manychat.com/fb/sending/sendContent"
    headers = {"Authorization": f"Bearer {MANYCHAT_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "subscriber_id": subscriber_id,
        "data": {
            "version": "v2",
            "content": {
                "type": "instagram",
                "messages": [{"type": "text", "text": jp_text}]
            }
        },
        "message_tag": "ACCOUNT_UPDATE"
    }
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=15)
        print(f"ManyChat response: {r.status_code} {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"ManyChat send error: {e}")
        return False

# ─── Background task ─────────────────────────────────────────────────────────

def process_dm(subscriber_id: str, subscriber_name: str, message: str):
    data = load_data()
    history = data.get(f"history_{subscriber_id}", [])

    result = call_claude(history, subscriber_name, message)

    # Update history
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result.get("reply", "")})
    data[f"history_{subscriber_id}"] = history[-20:]  # keep last 20 turns

    # Store pending reply
    data[f"pending_{subscriber_id}"] = {
        "subscriber_id": subscriber_id,
        "subscriber_name": subscriber_name,
        "message": message,
        "reply": result.get("reply", ""),
        "stage": result.get("stage", "other"),
        "needs_human_review": result.get("needs_human_review", False),
        "alert_reason": result.get("alert_reason", ""),
        "alert_note": result.get("alert_note", ""),
    }
    save_data(data)

    send_teams(subscriber_id, subscriber_name, message, result)

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/webhook/jp-ig-dm-v1")
async def receive_dm(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    subscriber_id   = str(body.get("subscriber_id", ""))
    subscriber_name = body.get("subscriber_name", "名前不明")
    message         = body.get("message", "")

    if not subscriber_id:
        return JSONResponse({"error": "subscriber_id required"}, status_code=400)

    background_tasks.add_task(process_dm, subscriber_id, subscriber_name, message)
    return {"ok": True}


@app.get("/webhook/jp-ig-dm-approve-v1")
async def approve_dm(id: str):
    data = load_data()
    pending = data.get(f"pending_{id}")
    if not pending:
        return PlainTextResponse("❌ Pending reply not found (already sent or expired)", status_code=404)

    ok = send_manychat_dm(id, pending["reply"])
    if ok:
        del data[f"pending_{id}"]
        save_data(data)
        return PlainTextResponse(f"✅ DM sent to @{pending['subscriber_name']}")
    else:
        return PlainTextResponse("❌ ManyChat send failed — check logs", status_code=500)


@app.get("/webhook/jp-ig-dm-edit", response_class=HTMLResponse)
async def edit_form(id: str):
    data = load_data()
    pending = data.get(f"pending_{id}")
    if not pending:
        return HTMLResponse("<h2>❌ Not found</h2>", status_code=404)

    reply_escaped = pending["reply"].replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>DM 수정</title>
<style>body{{font-family:sans-serif;max-width:600px;margin:40px auto;padding:0 20px}}
textarea{{width:100%;height:300px;font-size:14px;padding:10px;border:1px solid #ccc;border-radius:6px}}
button{{margin-top:12px;padding:10px 24px;background:#0078d4;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:15px}}
h2{{color:#333}}.meta{{color:#888;font-size:13px;margin-bottom:12px}}</style></head>
<body>
<h2>✏️ DM 수정 — @{pending['subscriber_name']}</h2>
<div class="meta">받은 메시지: {pending['message']}</div>
<form method="POST" action="/webhook/jp-ig-dm-edit">
  <input type="hidden" name="id" value="{id}">
  <textarea name="reply">{reply_escaped}</textarea>
  <br><button type="submit">📤 수정 후 전송</button>
</form>
</body></html>"""
    return HTMLResponse(html)


@app.post("/webhook/jp-ig-dm-edit")
async def submit_edit(request: Request):
    form = await request.form()
    sub_id = form.get("id", "")
    new_reply = form.get("reply", "")

    data = load_data()
    pending = data.get(f"pending_{sub_id}")
    if not pending:
        return PlainTextResponse("❌ Not found", status_code=404)

    ok = send_manychat_dm(sub_id, new_reply)
    if ok:
        # Update history with edited reply
        history = data.get(f"history_{sub_id}", [])
        if history and history[-1]["role"] == "assistant":
            history[-1]["content"] = new_reply  # replace Claude's reply with edited
        data[f"history_{sub_id}"] = history
        del data[f"pending_{sub_id}"]
        save_data(data)
        return HTMLResponse(f"<h2>✅ 전송 완료!</h2><p>@{pending['subscriber_name']}에게 DM이 발송되었습니다.</p>")
    else:
        return PlainTextResponse("❌ ManyChat send failed", status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}
