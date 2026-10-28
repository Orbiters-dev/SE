"""TikTok Marketing API OAuth — 인증 URL 생성 + auth_code→access_token 교환.

tiktok_ads_jp.py 의 짝. 개발자 앱이 승인(Verification Approved)되어 App ID/Secret 이
발급된 뒤 한 번 실행해 long-lived access_token 과 advertiser_id 를 확보한다.

흐름:
  1) python tools/tiktok_oauth.py auth-url --app-id <APP_ID>
       → 출력된 URL 을 브라우저에서 열고 JP 광고계정으로 승인
       → redirect 주소창(...grosmimijapan.com/tiktok/callback?auth_code=XXX)의 auth_code 복사
  2) python tools/tiktok_oauth.py exchange --app-id <APP_ID> --secret <SECRET> --auth-code <CODE>
       → access_token + advertiser_ids 출력 → 안내대로 .env 에 저장

엔드포인트/파라미터는 TikTok Marketing API v1.3 표준이며, 최종 정합성은 실호출 응답
(code≠0 이면 즉시 중단·메시지 표시)으로 확정한다 — 공식 문서는 SPA/로그인 게이트라
전량 노출되지 않으므로 실호출을 검증 기준으로 삼는다.
"""
from __future__ import annotations
import sys
import json
import argparse
import urllib.request
import urllib.error
from urllib.parse import urlencode

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # dotenv 없으면 프로세스 환경변수만 사용 (실제 에러는 마스킹하지 않음)

AUTH_PORTAL = "https://business-api.tiktok.com/portal/auth"
TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
DEFAULT_REDIRECT = "https://grosmimijapan.com/tiktok/callback"


def build_auth_url(app_id: str, redirect_uri: str = DEFAULT_REDIRECT,
                   state: str = "grosmimi_jp") -> str:
    """광고계정 소유자가 열어 승인할 OAuth 인증 URL."""
    q = urlencode({"app_id": app_id, "redirect_uri": redirect_uri, "state": state})
    return f"{AUTH_PORTAL}?{q}"


def exchange(app_id: str, secret: str, auth_code: str) -> dict:
    """auth_code → access_token + advertiser_ids. 실패 시 스택트레이스 대신 명확한 메시지."""
    body = json.dumps({
        "app_id": app_id,
        "secret": secret,
        "auth_code": auth_code,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[HTTP {e.code}] {e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"[NETWORK] {e.reason}")
    if res.get("code") != 0:
        sys.exit(f"[API ERROR] code={res.get('code')} msg={res.get('message')}")
    return res.get("data", {})


def main() -> None:
    ap = argparse.ArgumentParser(description="TikTok Marketing API OAuth helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("auth-url", help="인증 URL 생성")
    p_url.add_argument("--app-id", required=True)
    p_url.add_argument("--redirect", default=DEFAULT_REDIRECT)

    p_ex = sub.add_parser("exchange", help="auth_code → access_token")
    p_ex.add_argument("--app-id", required=True)
    p_ex.add_argument("--secret", required=True)
    p_ex.add_argument("--auth-code", required=True)

    a = ap.parse_args()

    if a.cmd == "auth-url":
        print(build_auth_url(a.app_id, a.redirect))
        print("\n위 URL 을 브라우저에서 열고 JP 광고계정으로 승인하세요.")
        print("승인 후 redirect 주소창에 붙는 auth_code 를 복사해 exchange 에 넣으면 됩니다.")
    elif a.cmd == "exchange":
        data = exchange(a.app_id, a.secret, a.auth_code)
        token = data.get("access_token", "")
        advs = data.get("advertiser_ids", []) or []
        print(f"ACCESS_TOKEN : {token}")
        print(f"ADVERTISER_IDS: {advs}")
        print("\n--- .env 에 아래 추가 ---")
        print(f"TIKTOK_ACCESS_TOKEN={token}")
        if advs:
            print(f"TIKTOK_ADVERTISER_ID_JP={advs[0]}")
            if len(advs) > 1:
                print(f"# 광고계정이 여러 개입니다. JP 계정 id 를 골라 위 값에 넣으세요: {advs}")
        else:
            print("# advertiser_ids 가 비었습니다 — 앱에 광고계정 인증이 안 됐을 수 있습니다.")


if __name__ == "__main__":
    main()
