"""
Email Viewer Server — 자율주행 테스터용 실시간 이메일 뷰어
===========================================================
로컬 HTTP 서버 (기본 포트 5556).
Playwright 자율주행 테스터의 오른쪽 창에서 열어서
hello@zezebaebae.com ↔ affiliates@onzenna.com 이메일을 화면에 표시.

Endpoints:
  GET  /                          HTML 뷰어 페이지
  GET  /api/inbox/{account}       최신 10개 이메일 JSON (account: zeze | onzenna)
  GET  /api/thread/{account}/{id} 특정 이메일 본문
  POST /api/send                  이메일 발송 (body: {from, to, subject, body, reply_to_id})
  GET  /api/status                양쪽 계정 연결 상태
  GET  /events                    SSE 스트림 (새 이메일 push)
"""

import os
import sys
import json
import time
import base64
import threading
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass

# ─── Gmail API setup ──────────────────────────────────────────────────────────
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GMAIL_OK = True
except ImportError:
    GMAIL_OK = False

ACCOUNTS = {
    "zeze":    {
        "token":   os.path.join(ROOT, "credentials", "zezebaebae_gmail_token.json"),
        "email":   "hello@zezebaebae.com",
        "display": "인플루언서 (zezebaebae)",
        "color":   "#7c3aed",
    },
    "onzenna": {
        "token":   os.path.join(ROOT, "credentials", "onzenna_gmail_token.json"),
        "email":   "affiliates@onzenna.com",
        "display": "마케터 (Onzenna)",
        "color":   "#0ea5e9",
    },
}

_services   = {}   # account -> gmail service
_inbox_cache = {}  # account -> [{id, subject, from, date, snippet, body}]
_sse_clients = []  # list of response write fns

def _get_service(account):
    if account in _services:
        return _services[account]
    if not GMAIL_OK:
        return None
    info = ACCOUNTS.get(account)
    if not info:
        return None
    try:
        creds = Credentials.from_authorized_user_file(info["token"])
        svc   = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _services[account] = svc
        return svc
    except Exception as e:
        print(f"[EmailViewer] Gmail auth failed for {account}: {e}")
        return None

def _decode_body(payload):
    """Extract plain text from Gmail message payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            # strip tags roughly
            import re
            return re.sub(r"<[^>]+>", "", raw).strip()
    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result
    return ""

def fetch_inbox(account, max_results=10):
    """Fetch recent emails for account."""
    svc = _get_service(account)
    if not svc:
        return []
    try:
        result = svc.users().messages().list(
            userId="me", maxResults=max_results,
            labelIds=["INBOX"],
        ).execute()
        msgs = result.get("messages", [])
        inbox = []
        for m in msgs[:max_results]:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=m["id"], format="full"
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
                body    = _decode_body(msg["payload"])
                inbox.append({
                    "id":      m["id"],
                    "subject": headers.get("Subject", "(no subject)"),
                    "from":    headers.get("From", ""),
                    "to":      headers.get("To", ""),
                    "date":    headers.get("Date", ""),
                    "snippet": msg.get("snippet", "")[:120],
                    "body":    body[:2000],
                })
            except Exception:
                pass
        _inbox_cache[account] = inbox
        return inbox
    except Exception as e:
        print(f"[EmailViewer] fetch_inbox {account}: {e}")
        return _inbox_cache.get(account, [])

def send_email(from_account, to_addr, subject, body_text, reply_to_id=None):
    """Send email from account."""
    svc = _get_service(from_account)
    if not svc:
        return False, "Gmail service not available"
    try:
        msg = MIMEText(body_text, "plain")
        msg["To"]      = to_addr
        msg["From"]    = ACCOUNTS[from_account]["email"]
        msg["Subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        body = {"raw": raw}
        if reply_to_id:
            body["threadId"] = reply_to_id
        svc.users().messages().send(userId="me", body=body).execute()
        return True, "sent"
    except Exception as e:
        return False, str(e)

def _push_sse(event_data):
    """Push SSE event to all connected clients."""
    msg = f"data: {json.dumps(event_data)}\n\n"
    dead = []
    for wfile in _sse_clients:
        try:
            wfile.write(msg.encode())
            wfile.flush()
        except Exception:
            dead.append(wfile)
    for d in dead:
        _sse_clients.remove(d)

def _poll_loop():
    """Background: poll Gmail every 15s and push SSE if new mail."""
    last_ids = {acc: set() for acc in ACCOUNTS}
    while True:
        for acc in ACCOUNTS:
            try:
                inbox = fetch_inbox(acc, max_results=5)
                current_ids = {m["id"] for m in inbox}
                new_ids = current_ids - last_ids[acc]
                if new_ids and last_ids[acc]:  # not first poll
                    for m in inbox:
                        if m["id"] in new_ids:
                            _push_sse({"type": "new_email", "account": acc,
                                       "subject": m["subject"], "from": m["from"]})
                last_ids[acc] = current_ids
            except Exception:
                pass
        time.sleep(15)


# ─── HTML template ────────────────────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>이메일 뷰어 — 자율주행 테스터</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;height:100vh;display:flex;flex-direction:column}
.header{background:#1a1d2e;border-bottom:1px solid #2d3148;padding:10px 16px;display:flex;align-items:center;gap:12px}
.header h1{font-size:14px;font-weight:700;color:#fff}
.header .badge{font-size:10px;padding:2px 8px;border-radius:10px;background:#7c3aed22;color:#a78bfa;border:1px solid #7c3aed44}
.status-dot{width:7px;height:7px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.panels{display:grid;grid-template-columns:1fr 1fr;flex:1;overflow:hidden;gap:1px;background:#2d3148}
.panel{background:#0f1117;display:flex;flex-direction:column;overflow:hidden}
.panel-header{padding:10px 14px;border-bottom:1px solid #1e2235;display:flex;align-items:center;justify-content:space-between}
.panel-header h2{font-size:12px;font-weight:700}
.panel-header .email-addr{font-size:10px;color:#64748b}
.refresh-btn{font-size:10px;padding:3px 8px;border-radius:4px;border:1px solid #2d3148;background:#1a1d2e;color:#94a3b8;cursor:pointer}
.refresh-btn:hover{background:#2d3148}
.inbox{flex:1;overflow-y:auto;padding:8px}
.email-item{background:#141620;border:1px solid #1e2235;border-radius:6px;padding:10px 12px;margin-bottom:6px;cursor:pointer;transition:border-color .15s}
.email-item:hover,.email-item.active{border-color:#7c3aed}
.email-item .from{font-size:11px;font-weight:700;color:#e2e8f0;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.email-item .subject{font-size:11px;color:#94a3b8;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.email-item .snippet{font-size:10px;color:#4b5563;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.email-item .date{font-size:9px;color:#374151;float:right;margin-top:-22px}
.detail-panel{background:#0f1117;border-top:1px solid #1e2235;padding:12px;display:none;max-height:240px;overflow-y:auto}
.detail-panel.open{display:block}
.detail-panel .d-subject{font-size:13px;font-weight:700;margin-bottom:6px}
.detail-panel .d-meta{font-size:10px;color:#64748b;margin-bottom:10px}
.detail-panel .d-body{font-size:12px;color:#cbd5e1;white-space:pre-wrap;line-height:1.6}
.compose{background:#141620;border-top:1px solid #1e2235;padding:10px 12px;flex-shrink:0}
.compose textarea{width:100%;background:#0f1117;border:1px solid #2d3148;border-radius:4px;padding:8px;font-size:11px;color:#e2e8f0;resize:vertical;min-height:60px;font-family:inherit}
.compose-row{display:flex;gap:6px;margin-bottom:6px;align-items:center}
.compose-row input{flex:1;background:#0f1117;border:1px solid #2d3148;border-radius:4px;padding:5px 8px;font-size:11px;color:#e2e8f0}
.compose-row label{font-size:10px;color:#64748b;white-space:nowrap}
.send-btn{padding:5px 14px;border-radius:4px;border:none;font-size:11px;font-weight:700;cursor:pointer;color:#fff}
.send-btn.zeze{background:#7c3aed} .send-btn.onzenna{background:#0ea5e9}
.new-badge{background:#22c55e;color:#000;font-size:9px;padding:1px 5px;border-radius:8px;margin-left:6px;animation:pop .3s ease}
@keyframes pop{0%{transform:scale(0)}100%{transform:scale(1)}}
::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-track{background:#0f1117} ::-webkit-scrollbar-thumb{background:#2d3148;border-radius:2px}
</style>
</head>
<body>
<div class="header">
  <div class="status-dot" id="dot"></div>
  <h1>📧 이메일 뷰어 — 자율주행 테스터</h1>
  <span class="badge">LIVE</span>
  <span style="font-size:10px;color:#4b5563;margin-left:auto" id="last-updated"></span>
</div>

<div class="panels">
  <!-- ZEZE panel -->
  <div class="panel" id="panel-zeze">
    <div class="panel-header" style="border-left:3px solid #7c3aed">
      <div>
        <h2 style="color:#a78bfa">🧑‍🎤 인플루언서</h2>
        <div class="email-addr">hello@zezebaebae.com</div>
      </div>
      <button class="refresh-btn" onclick="loadInbox('zeze')">⟳ 새로고침</button>
    </div>
    <div class="inbox" id="inbox-zeze"><div style="padding:20px;text-align:center;color:#374151;font-size:12px">로딩 중...</div></div>
    <div class="detail-panel" id="detail-zeze"></div>
    <div class="compose">
      <div class="compose-row">
        <label>To:</label>
        <input id="zeze-to" value="affiliates@onzenna.com" placeholder="수신자">
        <label>제목:</label>
        <input id="zeze-subject" value="" placeholder="제목">
      </div>
      <textarea id="zeze-body" placeholder="Reply 메시지 입력...&#10;&#10;여기에 인플루언서 답장 작성"></textarea>
      <div style="text-align:right;margin-top:6px">
        <button class="send-btn zeze" onclick="sendEmail('zeze')">📤 발송 (zezebaebae)</button>
      </div>
    </div>
  </div>

  <!-- ONZENNA panel -->
  <div class="panel" id="panel-onzenna">
    <div class="panel-header" style="border-left:3px solid #0ea5e9">
      <div>
        <h2 style="color:#38bdf8">🏢 마케터</h2>
        <div class="email-addr">affiliates@onzenna.com</div>
      </div>
      <button class="refresh-btn" onclick="loadInbox('onzenna')">⟳ 새로고침</button>
    </div>
    <div class="inbox" id="inbox-onzenna"><div style="padding:20px;text-align:center;color:#374151;font-size:12px">로딩 중...</div></div>
    <div class="detail-panel" id="detail-onzenna"></div>
    <div class="compose">
      <div class="compose-row">
        <label>To:</label>
        <input id="onzenna-to" value="hello@zezebaebae.com" placeholder="수신자">
        <label>제목:</label>
        <input id="onzenna-subject" value="Grosmimi x 콜라보 제안 🌿" placeholder="제목">
      </div>
      <textarea id="onzenna-body" placeholder="아웃리치 이메일 내용...&#10;&#10;Hi! We'd love to collaborate..."></textarea>
      <div style="text-align:right;margin-top:6px">
        <button class="send-btn onzenna" onclick="sendEmail('onzenna')">📤 발송 (onzenna)</button>
      </div>
    </div>
  </div>
</div>

<script>
var _selected = {zeze: null, onzenna: null};
var _replyThreadId = {zeze: null, onzenna: null};

async function loadInbox(account) {
  var box = document.getElementById('inbox-' + account);
  try {
    var r = await fetch('/api/inbox/' + account);
    var emails = await r.json();
    if(!emails.length){box.innerHTML='<div style="padding:20px;text-align:center;color:#374151;font-size:12px">이메일 없음</div>';return}
    box.innerHTML = emails.map(function(e,i){
      return '<div class="email-item" id="ei-'+account+'-'+e.id+'" onclick="openEmail(\''+account+'\',\''+e.id+'\')">'
        +'<div class="from">'+esc(e.from.split('<')[0].trim().slice(0,40))+'</div>'
        +'<div class="subject">'+esc(e.subject.slice(0,60))+'</div>'
        +'<div class="snippet">'+esc(e.snippet)+'</div>'
        +'<div class="date">'+esc(e.date.slice(0,16))+'</div>'
        +'</div>';
    }).join('');
    document.getElementById('last-updated').textContent = '업데이트: ' + new Date().toLocaleTimeString('ko');
  } catch(err) {
    box.innerHTML = '<div style="padding:20px;text-align:center;color:#dc2626;font-size:12px">오류: '+err.message+'</div>';
  }
}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

async function openEmail(account, id) {
  var prev = document.getElementById('ei-'+account+'-'+_selected[account]);
  if(prev) prev.classList.remove('active');
  _selected[account] = id;
  var el = document.getElementById('ei-'+account+'-'+id);
  if(el) el.classList.add('active');

  var detail = document.getElementById('detail-'+account);
  detail.innerHTML = '<div style="font-size:11px;color:#64748b">로딩 중...</div>';
  detail.classList.add('open');
  try {
    var r = await fetch('/api/thread/'+account+'/'+id);
    var msg = await r.json();
    _replyThreadId[account] = msg.thread_id || id;
    // Pre-fill reply
    var subj = document.getElementById(account+'-subject');
    if(subj && !subj.value.startsWith('Re:')) subj.value = 'Re: '+msg.subject;
    detail.innerHTML = '<div class="d-subject">'+esc(msg.subject)+'</div>'
      +'<div class="d-meta">From: '+esc(msg.from)+' | '+esc(msg.date)+'</div>'
      +'<div class="d-body">'+esc(msg.body)+'</div>';
  } catch(err) {
    detail.innerHTML = '<div style="font-size:11px;color:#dc2626">오류: '+err.message+'</div>';
  }
}

async function sendEmail(account) {
  var to      = document.getElementById(account+'-to').value.trim();
  var subject = document.getElementById(account+'-subject').value.trim();
  var body    = document.getElementById(account+'-body').value.trim();
  if(!to||!body){alert('수신자와 내용을 입력하세요');return}
  var btn = event.target;
  btn.disabled = true; btn.textContent = '발송 중...';
  try {
    var r = await fetch('/api/send', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({from_account:account, to, subject, body,
                            reply_to_id: _replyThreadId[account]})
    });
    var res = await r.json();
    if(res.ok){
      btn.textContent = '✅ 발송 완료!';
      document.getElementById(account+'-body').value = '';
      setTimeout(function(){loadInbox('onzenna');loadInbox('zeze')}, 3000);
    } else {
      btn.textContent = '❌ 실패: '+res.error;
    }
  } catch(err){
    btn.textContent = '❌ 오류: '+err.message;
  }
  setTimeout(function(){btn.disabled=false;btn.textContent=account==='zeze'?'📤 발송 (zezebaebae)':'📤 발송 (onzenna)'},3000);
}

// SSE: real-time push when new email arrives
var evtSource = new EventSource('/events');
evtSource.onmessage = function(e) {
  var data = JSON.parse(e.data);
  if(data.type === 'new_email') {
    var box = document.getElementById('inbox-' + data.account);
    if(box) {
      // add new badge
      var badge = document.createElement('div');
      badge.style.cssText='padding:8px 12px;background:#22c55e22;border:1px solid #22c55e44;border-radius:6px;margin-bottom:6px;font-size:11px;color:#22c55e';
      badge.innerHTML = '🔔 새 이메일: '+esc(data.subject)+' (from: '+esc(data.from)+')';
      box.prepend(badge);
      document.getElementById('dot').style.background='#f59e0b';
      setTimeout(function(){document.getElementById('dot').style.background='#22c55e'},2000);
    }
    loadInbox(data.account);
  }
};

// Initial load
loadInbox('zeze');
loadInbox('onzenna');
</script>
</body>
</html>"""


# ─── HTTP Handler ─────────────────────────────────────────────────────────────
class EmailViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access log

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "" or path == "/":
            self._send_html(HTML_PAGE)

        elif path == "/api/status":
            status = {}
            for acc, info in ACCOUNTS.items():
                svc = _get_service(acc)
                status[acc] = {"email": info["email"], "connected": svc is not None}
            self._send_json(status)

        elif path.startswith("/api/inbox/"):
            account = path.split("/")[-1]
            if account not in ACCOUNTS:
                self._send_json({"error": "unknown account"}, 404)
                return
            inbox = fetch_inbox(account)
            self._send_json(inbox)

        elif path.startswith("/api/thread/"):
            parts   = path.split("/")
            account = parts[-2] if len(parts) >= 3 else ""
            msg_id  = parts[-1]
            if account not in ACCOUNTS:
                self._send_json({"error": "unknown account"}, 404)
                return
            svc = _get_service(account)
            if not svc:
                self._send_json({"error": "no service"}, 503)
                return
            try:
                msg = svc.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
                body    = _decode_body(msg["payload"])
                self._send_json({
                    "id":        msg_id,
                    "thread_id": msg.get("threadId", msg_id),
                    "subject":   headers.get("Subject", ""),
                    "from":      headers.get("From", ""),
                    "to":        headers.get("To", ""),
                    "date":      headers.get("Date", ""),
                    "body":      body[:3000],
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/events":
            # SSE
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            _sse_clients.append(self.wfile)
            try:
                # Keep alive
                while True:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    time.sleep(20)
            except Exception:
                pass
            finally:
                if self.wfile in _sse_clients:
                    _sse_clients.remove(self.wfile)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "/api/send":
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            try:
                data         = json.loads(raw)
                from_account = data.get("from_account", "")
                to_addr      = data.get("to", "")
                subject      = data.get("subject", "(no subject)")
                body_text    = data.get("body", "")
                reply_id     = data.get("reply_to_id")
                ok, msg      = send_email(from_account, to_addr, subject, body_text, reply_id)
                self._send_json({"ok": ok, "msg": msg})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ─── Server start ─────────────────────────────────────────────────────────────
_server = None

def start(port=5556, background=True):
    global _server
    _server = HTTPServer(("127.0.0.1", port), EmailViewerHandler)
    print(f"[EmailViewer] http://localhost:{port} 에서 이메일 뷰어 시작")

    # Start SSE poll thread
    t_poll = threading.Thread(target=_poll_loop, daemon=True)
    t_poll.start()

    if background:
        t = threading.Thread(target=_server.serve_forever, daemon=True)
        t.start()
        return port
    else:
        _server.serve_forever()

def stop():
    global _server
    if _server:
        _server.shutdown()
        _server = None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5556)
    args = parser.parse_args()
    print(f"[EmailViewer] Starting on http://localhost:{args.port}")
    print(f"  zeze  : hello@zezebaebae.com")
    print(f"  onzenna: affiliates@onzenna.com")
    print(f"  Press Ctrl+C to stop")
    start(port=args.port, background=False)
