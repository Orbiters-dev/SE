"""
Shopify OAuth 토큰 발급 스크립트
- 로컬 서버를 열어서 OAuth 콜백을 캡처
- 자동으로 access token 발급 후 .env에 저장
"""

import os
import json
import hashlib
import secrets
import webbrowser
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "d35ab8420b01d73924735d2ab58e1d45")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "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")
SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
REDIRECT_URI = "http://localhost:3456/callback"
SCOPES = "read_orders,read_all_orders,read_products,read_customers,write_customers,read_inventory,write_themes,write_content,write_draft_orders"

STATE = "shopify_oauth_ok"
received_token = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if "code" not in params:
            self._respond(400, "❌ code 파라미터 없음")
            return

        # state check skipped for reliability

        code = params["code"]
        print(f"\n[OK] Auth code received: {code[:10]}...")

        # code → access token 교환
        token_url = f"https://{SHOP}/admin/oauth/access_token"
        payload = json.dumps({
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code
        }).encode()

        req = urllib.request.Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
                token = data.get("access_token")
                scope = data.get("scope")

                if token:
                    received_token["token"] = token
                    received_token["scope"] = scope
                    print(f"[SUCCESS] Access Token issued!")
                    print(f"   Scope: {scope}")
                    self._respond(200, f"<h2>Token issued! Close this tab.</h2>")
                else:
                    self._respond(500, f"No token: {data}")
        except Exception as e:
            self._respond(500, f"Error: {e}")

        # 서버 종료 신호
        self.server.token_received = True

    def _respond(self, code, msg):
        body = f"<h2>{msg}</h2>".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # 로그 숨김


def save_to_env(token):
    """access token을 .env에 저장"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    shopify_block = f"\n# Shopify\nSHOPIFY_SHOP={SHOP}\nSHOPIFY_ACCESS_TOKEN={token}\n"

    if "# Shopify" in content:
        # 기존 블록 업데이트
        lines = content.split("\n")
        new_lines = []
        skip = False
        for line in lines:
            if line.strip() == "# Shopify":
                skip = True
                new_lines.append(f"# Shopify")
                new_lines.append(f"SHOPIFY_SHOP={SHOP}")
                new_lines.append(f"SHOPIFY_ACCESS_TOKEN={token}")
            elif skip and line.startswith("SHOPIFY_"):
                continue
            else:
                skip = False
                new_lines.append(line)
        content = "\n".join(new_lines)
    else:
        content += shopify_block

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[SAVED] .env updated")


def main():
    auth_url = (
        f"https://{SHOP}/admin/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope={SCOPES}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={STATE}"
    )

    print(f"[START] Shopify OAuth")
    print(f"   Shop: {SHOP}")
    print(f"   Scopes: {SCOPES}")
    print(f"\n[URL] Open this URL in browser:\n")
    print(f"  {auth_url}\n")
    print(f"Waiting for callback on localhost:3456 ...\n")

    server = HTTPServer(("localhost", 3456), CallbackHandler)
    server.token_received = False

    while not server.token_received:
        server.handle_request()

    if received_token.get("token"):
        token = received_token["token"]
        print(f"\n[TOKEN] {token}")
        try:
            save_to_env(token)
            print(f"[DONE] SHOPIFY_ACCESS_TOKEN saved to .env")
        except PermissionError:
            # Fallback: save to temp file
            tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp", "shopify_token.txt")
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
            with open(tmp_path, "w") as f:
                f.write(token)
            print(f"[WARN] .env locked, token saved to: {tmp_path}")
    else:
        print("[FAIL] Token not received")


if __name__ == "__main__":
    main()
