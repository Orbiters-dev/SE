"""
ga4_oauth_setup.py - One-time OAuth setup for GA4 Data API

Generates a refresh token with Google Analytics readonly scope.
Opens browser for auth, captures code via local HTTP server.

Usage:
    python tools/no_polar/ga4_oauth_setup.py
"""

import os
import sys
import json
import http.server
import webbrowser
import urllib.parse
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

PORT = 8085
REDIRECT_URI = f"http://localhost:{PORT}"


def main():
    client_id = os.getenv("GA4_CLIENT_ID")
    client_secret = os.getenv("GA4_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("[ERROR] GA4_CLIENT_ID and GA4_CLIENT_SECRET required in .wat_secrets")
        sys.exit(1)

    scope = "https://www.googleapis.com/auth/analytics.readonly"

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(scope)}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print("=" * 60)
    print("GA4 OAuth Setup")
    print("=" * 60)
    print()
    print("Opening browser for authorization...")
    webbrowser.open(auth_url)

    # Capture the auth code via local server
    auth_code = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            auth_code = params.get("code", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if auth_code:
                self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
            else:
                error = params.get("error", ["unknown"])[0]
                self.wfile.write(f"<h2>Authorization failed: {error}</h2>".encode())

        def log_message(self, format, *args):
            pass  # Suppress log output

    server = http.server.HTTPServer(("localhost", PORT), Handler)
    print(f"Waiting for authorization on port {PORT}...")
    server.handle_request()
    server.server_close()

    if not auth_code:
        print("[ERROR] No authorization code received")
        sys.exit(1)

    print("Got authorization code, exchanging for tokens...")

    # Exchange code for refresh token
    import requests
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })

    if resp.status_code != 200:
        print(f"[ERROR] Token exchange failed: {resp.text}")
        sys.exit(1)

    data = resp.json()
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        print(f"[ERROR] No refresh token in response: {data}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print()
    print(f"GA4_REFRESH_TOKEN={refresh_token}")
    print()
    print(f"Add this line to {os.path.expanduser('~/.wat_secrets')}")
    print()


if __name__ == "__main__":
    main()
