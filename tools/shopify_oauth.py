"""
Shopify OAuth 토큰 발급 스크립트
- 로컬 서버를 열어서 OAuth 콜백을 캡처
- 자동으로 access token 발급 후 .wat_secrets에 저장
"""

import os
import json
import hashlib
import secrets
import webbrowser
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from env_loader import load_env

load_env()

def _load_oauth_secrets():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "credentials", "secrets.json")
    try:
        with open(p) as f:
            return json.load(f).get("shopify_oauth", {})
    except FileNotFoundError:
        return {}

_oauth = _load_oauth_secrets()
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID") or _oauth.get("client_id")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET") or _oauth.get("client_secret")
if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("SHOPIFY_CLIENT_ID / CLIENT_SECRET not found in env or credentials/secrets.json")
SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
REDIRECT_URI = "http://localhost:3456/callback"
SCOPES = "read_orders,read_all_orders,read_products,read_customers,write_customers,read_inventory,write_themes,write_content,write_draft_orders,read_discounts,write_discounts,read_price_rules,write_price_rules,write_gift_cards"

STATE = secrets.token_urlsafe(16)
SECRETS_PATH = os.path.expanduser("~/.wat_secrets")
received_token = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if "code" not in params:
            # Install app flow might hit root path with hmac/shop params but no code
            # Check if this is an install redirect that needs the OAuth authorize step
            if "shop" in params:
                shop = params["shop"]
                print(f"\n[INFO] Install redirect from shop: {shop}")
                print(f"[INFO] Redirecting to OAuth authorize...")
                auth_url = (
                    f"https://{shop}/admin/oauth/authorize"
                    f"?client_id={CLIENT_ID}"
                    f"&scope={SCOPES}"
                    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
                    f"&state={STATE}"
                )
                self.send_response(302)
                self.send_header("Location", auth_url)
                self.end_headers()
                return
            self._respond(400, "code parameter missing")
            return

        # Use shop from callback params if available
        shop = params.get("shop", SHOP)
        code = params["code"]
        print(f"\n[OK] Auth code received: {code[:10]}...")
        print(f"[OK] Shop: {shop}")

        # code -> access token exchange
        token_url = f"https://{shop}/admin/oauth/access_token"
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
                    received_token["shop"] = shop
                    print(f"[SUCCESS] Access Token issued!")
                    print(f"   Scope: {scope}")
                    self._respond(200, "Token issued! Close this tab.")
                else:
                    self._respond(500, f"No token: {data}")
        except Exception as e:
            self._respond(500, f"Error: {e}")

        self.server.token_received = True

    def _respond(self, code, msg):
        body = f"<h2>{msg}</h2>".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def save_to_secrets(token, shop=None):
    """Save access token to ~/.wat_secrets"""
    shop = shop or SHOP
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    # Update SHOPIFY_ACCESS_TOKEN
    lines = content.split("\n")
    new_lines = []
    updated_token = False
    updated_shop = False

    for line in lines:
        if line.startswith("SHOPIFY_ACCESS_TOKEN="):
            new_lines.append(f"SHOPIFY_ACCESS_TOKEN={token}")
            updated_token = True
        elif line.startswith("SHOPIFY_SHOP="):
            new_lines.append(f"SHOPIFY_SHOP={shop}")
            updated_shop = True
        else:
            new_lines.append(line)

    if not updated_token:
        new_lines.append(f"SHOPIFY_ACCESS_TOKEN={token}")
    if not updated_shop:
        new_lines.append(f"SHOPIFY_SHOP={shop}")

    with open(SECRETS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print(f"[SAVED] Token saved to {SECRETS_PATH}")


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
    print(f"(If using Partners Dashboard 'Install app', the callback will be auto-captured)\n")

    server = HTTPServer(("localhost", 3456), CallbackHandler)
    server.token_received = False

    while not server.token_received:
        server.handle_request()

    if received_token.get("token"):
        token = received_token["token"]
        shop = received_token.get("shop", SHOP)
        print(f"\n[TOKEN] {token[:20]}...")
        save_to_secrets(token, shop)
        print(f"[DONE] SHOPIFY_ACCESS_TOKEN saved to {SECRETS_PATH}")
    else:
        print("[FAIL] Token not received")


if __name__ == "__main__":
    main()
