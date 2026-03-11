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

import os, json, re, httpx, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

app = FastAPI()

# ─── Debounce (메시지 묶음 처리) ─────────────────────────────────────────────
DEBOUNCE_SECS = 8
_timers: dict = {}
_msg_buffer: dict = {}

async def _debounced_process(subscriber_id: str):
    await asyncio.sleep(DEBOUNCE_SECS)
    if subscriber_id not in _msg_buffer:
        return
    buf = _msg_buffer.pop(subscriber_id)
    _timers.pop(subscriber_id, None)
    name = buf["name"]
    combined = "\n".join(buf["messages"])
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, process_dm, subscriber_id, name, combined)

ANTHROPIC_API_KEY     = os.getenv("ANTHROPIC_API_KEY")
MANYCHAT_API_KEY      = os.getenv("MANYCHAT_API_KEY_JP", "")
TEAMS_WEBHOOK_URL     = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")
BASE_URL              = os.getenv("WEBHOOK_BASE_URL", "https://your-app.railway.app")
UPSTASH_REDIS_URL     = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_TOKEN   = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY             = "jp_dm_data"

# ─── Name helper ─────────────────────────────────────────────────────────────

def _clean_name(val: str) -> str:
    """Return val only if it's an actual name (not an unresolved ManyChat template variable)."""
    if not val:
        return ""
    if re.search(r"\{\{.*?\}\}", val):  # e.g. {{full_name}}
        return ""
    return val.strip()

# ─── Storage (Upstash Redis REST API) ───────────────────────────────────────

def _redis_headers():
    return {"Authorization": f"Bearer {UPSTASH_REDIS_TOKEN}"}

def load_data() -> dict:
    if not UPSTASH_REDIS_URL:
        return {}
    try:
        r = httpx.get(f"{UPSTASH_REDIS_URL}/get/{REDIS_KEY}", headers=_redis_headers(), timeout=5)
        val = r.json().get("result")
        if val:
            return json.loads(val)
    except Exception as e:
        print(f"Redis load error: {e}")
    return {}

def save_data(data: dict):
    if not UPSTASH_REDIS_URL:
        print("UPSTASH_REDIS_REST_URL not set, skipping save")
        return
    try:
        encoded = json.dumps(data, ensure_ascii=False)
        httpx.get(
            f"{UPSTASH_REDIS_URL}/set/{REDIS_KEY}",
            params={"value": encoded},
            headers=_redis_headers(),
            timeout=5,
        )
    except Exception as e:
        print(f"Redis save error: {e}")

# ─── Claude ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI assistant managing Instagram DM conversations for GROSMIMI JAPAN (グロミミ), a Korean baby straw cup brand entering the Japanese market.
Your role: draft DM replies to influencers in professional Japanese, strictly following the brand's SOP templates.

CRITICAL RULES:
- Use the templates below as your BASE. Adapt only the [bracketed] parts.
- Replace [○○様] with the actual subscriber name provided.
- NEVER improvise expressions not in the templates.
- NEVER mention competitor brands (Richell, Pigeon, Combi, Bbox).
- NEVER confirm contract amounts or policies not listed here.

=== TONE RULES ===
- Formal keigo (敬語), business tone only
- Always start with 「[name]様」
- After 「○○様」, always add a polite greeting line (e.g. 「ご返信いただき、誠にありがとうございます。」「お世話になっております。」)
- Minimal emoji: max 1 per message, at the end only
- PROHIBITED: 「もちろんです！」「ぴったりかと思います」「投稿楽しみにしています」and any casual expressions
- Do NOT repeat the same emoji twice in one DM
- Long messages are not read — keep it concise

=== PRODUCTS (Japan) ===
- PPSU Straw Cup 200ml/300ml | ¥3,190/¥3,600 | White/Charcoal/Pink/Sky Blue | 6mo+
- PPSU One-touch 300ml | ¥4,200 | Pink Unicorn/Green Dinosaur | 12mo+
- Stainless Straw Cup 200ml/300ml | ¥5,800/¥6,200 | Bear Butter/Olive Pistachio/Cherry Peach | 12mo+

Age rule: 6–11 months → PPSU only. 12mo+ → all 3 available. NEVER recommend PPSU to 12mo+.
Rakuten store: https://www.rakuten.co.jp/littlefingerusa/

=== COLLABORATION CONDITIONS ===
- Basic: gifting only (no payment)
- Paid (10k+ followers): ask desired amount → report to human, NEVER decide on your own
- Content: Instagram Reel post
- Whitelisting required (Instagram + Facebook linked) — if refused → set needs_human_review: true

=== DM FLOW TEMPLATES ===

[STAGE: recommendation] — influencer shows interest / asks about conditions
---
[name]様

ご連絡いただき、誠にありがとうございます😊

GROSMIMIの最大の特長は、「成長に合わせて選べるストローステージシステム」です。生後6〜10ヶ月のストローデビュー期はやわらかいStage 1ストロー、噛みぐせが出てくる10ヶ月頃からはかためのStage 2ストローへ交換可能です✨

また、PPSUストローカップからステンレスストローカップまですべてパーツの互換性がある設計のため、1本のボトルでパーツだけを交換しながら長くご使用いただけるメリットがあります。

まだ弊社は日本市場に参入したばかりのため、まずはアメリカでのインフルエンサー様とのコラボ実績をもとにガイドラインを作成いたしました。

もしよろしければ、ご確認のうえお気軽にご意見をいただけますと幸いです。

いただいた内容をもとに改めてご返信いたします🥹❤️

GROSMIMI JAPAN
---
※ Send guideline link separately: https://orbiters-my.sharepoint.com/:w:/g/personal/k_yamaguchi_orbiters_co_kr/IQCx4NnjvM54SoYfnpacH_J1Aa3XWgfCSVw-HrHw1LmOHmY?e=lLPxhl

[STAGE: age_check] — influencer mentions baby age
→ 6–11 months: recommend PPSU only
→ 12mo+: recommend One-touch and/or Stainless
---
商品の選定をさせていただきたいのですが、お子様が[月齢]とのことですので

・[推薦製品1]
・[推薦製品2]

がよろしいかと思っております🍼

ご希望のタイプやカラーがございましたら、ぜひお知らせください。お子様にぴったりのものをご用意できればと思います。

どうぞよろしくお願いいたします。

GROSMIMI JAPAN
---
※ Attach product links for recommended items

[STAGE: timing_mismatch] — baby too young, timing doesn't work
---
[name]様

ご丁寧にご返信いただき、ありがとうございます😊

[사정] とのこと、承知いたしました。

弊社のストローマグは生後6ヶ月頃からご使用いただける商品となっておりますので、お子様がそのご月齢になられましたら、改めてこちらよりご連絡させていただきます。

引き続きよろしくお願いいたします✨

GROSMIMI JAPAN
---

[STAGE: terms] — conditions confirmed, collect DocuSign info
---
[name]様

この度はご丁寧なご返信をいただき、誠にありがとうございます🙇‍♀️

また、ご提示いただいた内容にて、ぜひ進めさせていただければと存じます😊

――――――――――
【実施内容】
・商品：[製品名] [容量]（[カラー]）
・投稿内容：リール投稿 1本

【報酬】
・商品提供
――――――――――

上記内容で問題なさそうでしたら、契約書の作成に進めさせていただきます📝

なお、契約書のご署名には「DocuSign」というアプリのアカウント作成が必要となります。お手数をおかけいたしますが、あらかじめご準備をお願いいたします🙇‍♀️

また、契約書に記載するため、以下の情報をお知らせいただけますでしょうか✨

【フルネーム】
【メールアドレス】
【Instagramハンドル】

GROSMIMI JAPAN
---

[STAGE: shipping] — DocuSign signed, collect shipping address
---
[name]様

契約書のご送付、ありがとうございます😊内容につきまして、問題なく確認させていただきました。

それでは、下記商品の発送を進めさせていただきます✨

――――――――――
■ 発送商品
[製品名]
[容量]（[カラー]）
――――――――――

商品発送のため、恐れ入りますが、下記情報をお知らせいただけますでしょうか🙇‍♀️

・ご住所
・お名前
・お電話番号
・お受け取り希望日時

GROSMIMI JAPAN
---

=== NEEDS_HUMAN_REVIEW triggers (set needs_human_review: true) ===
- Influencer insists on paid collaboration (report exact amount in alert_note)
- Influencer shares Google Drive link or video/draft for review
- Influencer refuses whitelisting
- Any situation outside the SOP above

=== OUTPUT FORMAT ===
Output reply in Japanese + Korean translation separated by \\n\\n---한국어---\\n\\n

Respond in this EXACT JSON format (no markdown wrapper):
{
  "reply": "Japanese DM text here\\n\\n---한국어---\\n\\nKorean translation here",
  "stage": "one of: greeting/recommendation/age_check/timing_mismatch/terms/shipping/contract/content_review/posting/other",
  "needs_human_review": false,
  "alert_reason": "",
  "alert_note": ""
}"""

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

    approve_url = f"{BASE_URL}/webhook/jp-ig-dm-approve-v1?id={subscriber_id}"
    edit_url    = f"{BASE_URL}/webhook/jp-ig-dm-edit?id={subscriber_id}"

    reply_full = result.get("reply", "")
    parts      = reply_full.split("---한국어---")
    reply_jp   = parts[0].strip()[:600]
    reply_kr   = parts[1].strip()[:400] if len(parts) > 1 else ""

    review_flag = f"  ⚠️ 확인필요: {result.get('alert_reason', '')}" if result.get("needs_human_review") else ""
    title       = f"[JP DM] @{subscriber_name}{review_flag}"
    color       = "FF0000" if result.get("needs_human_review") else "0078D4"

    facts = [
        {"name": "Stage", "value": result.get("stage", "?")},
        {"name": "📩 받은 메시지", "value": message or "(메시지 없음)"},
        {"name": "🤖 Claude 답장 (일본어)", "value": reply_jp},
    ]
    if reply_kr:
        facts.append({"name": "🇰🇷 한국어 번역", "value": reply_kr})
    if result.get("alert_note"):
        facts.append({"name": "📝 메모", "value": result["alert_note"]})

    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": color,
        "title": title,
        "sections": [{"facts": facts}],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "✅ 승인 후 전송",
                "targets": [{"os": "default", "uri": approve_url}],
            },
            {
                "@type": "OpenUri",
                "name": "✏️ 수정 후 전송",
                "targets": [{"os": "default", "uri": edit_url}],
            },
        ],
    }

    try:
        r = httpx.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        print(f"Teams response: {r.status_code} {r.text[:100]}")
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
async def receive_dm(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    subscriber_id   = str(body.get("subscriber_id", ""))
    # ManyChat sometimes sends unresolved template variables like {{full_name}} — filter them all out
    subscriber_name = (
        _clean_name(body.get("subscriber_name", ""))
        or _clean_name(body.get("name", ""))
        or _clean_name(body.get("first_name", ""))
        or _clean_name(body.get("subscriber_handle", ""))
        or "名前不明"
    )
    message         = body.get("message", "")

    if not subscriber_id:
        return JSONResponse({"error": "subscriber_id required"}, status_code=400)

    # Cancel existing timer and buffer message
    if subscriber_id in _timers and not _timers[subscriber_id].done():
        _timers[subscriber_id].cancel()
    if subscriber_id not in _msg_buffer:
        _msg_buffer[subscriber_id] = {"name": subscriber_name, "messages": []}
    _msg_buffer[subscriber_id]["messages"].append(message)

    # Schedule debounced processing (waits DEBOUNCE_SECS for more messages)
    _timers[subscriber_id] = asyncio.create_task(_debounced_process(subscriber_id))
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
