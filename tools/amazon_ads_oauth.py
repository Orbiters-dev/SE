"""
Amazon Ads API - OAuth 토큰 발급 도구
=====================================
Fleeters Inc 등 새 계정에 대한 refresh token을 발급받을 때 사용.

사용법:
    # Step 1: 브라우저에서 인증 URL 열기
    python tools/amazon_ads_oauth.py --auth-url

    # Step 2: 리다이렉트된 URL에서 code를 복사한 후 토큰 교환
    python tools/amazon_ads_oauth.py --exchange CODE_HERE

    # Step 3: 발급된 refresh_token을 GitHub Secrets에 저장
"""

import argparse
import os
import sys
import urllib.parse
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

CLIENT_ID = os.getenv("AMZ_ADS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET", "")

# Must match "Allowed Return URLs" in LWA Security Profile
REDIRECT_URI = "https://zezebaebae.com"

SCOPES = "advertising::campaign_management"


def print_auth_url():
    if not CLIENT_ID:
        print("[ERROR] AMZ_ADS_CLIENT_ID not set. Check ~/.wat_secrets")
        sys.exit(1)

    params = {
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
    }
    url = f"https://www.amazon.com/ap/oa?{urllib.parse.urlencode(params)}"

    print()
    print("=" * 70)
    print("Amazon Ads OAuth - Step 1: 브라우저에서 아래 URL 열기")
    print("=" * 70)
    print()
    print("중요: 시크릿/프라이빗 모드에서 열고,")
    print("Fleeters Inc 계정 (official@fleeters.us)으로 로그인하세요!")
    print()
    print(url)
    print()
    print("=" * 70)
    print("로그인 후 'Allow' 클릭하면 리다이렉트됩니다.")
    print("리다이렉트된 URL에서 'code=' 파라미터 값을 복사하세요.")
    print()
    print("예시: https://www.amazon.com/ap/oa?code=ANdNAVhyhqBKVoys&scope=...")
    print("                                         ^^^^^^^^^^^^^^^^ 이 부분")
    print()
    print("Step 2: python tools/amazon_ads_oauth.py --exchange YOUR_CODE")
    print("=" * 70)


def exchange_code(code: str):
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[ERROR] AMZ_ADS_CLIENT_ID / AMZ_ADS_CLIENT_SECRET not set")
        sys.exit(1)

    import requests

    print(f"\n[Step 2] Authorization code -> Refresh token 교환 중...")
    print(f"  Code: {code[:10]}...")

    resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"\n[ERROR] Token exchange failed: {resp.status_code}")
        print(resp.json())
        sys.exit(1)

    data = resp.json()
    refresh_token = data.get("refresh_token", "")
    access_token = data.get("access_token", "")

    print()
    print("=" * 70)
    print("SUCCESS! Refresh token 발급 완료")
    print("=" * 70)
    print()
    print(f"  Refresh Token: {refresh_token[:20]}...{refresh_token[-10:]}")
    print(f"  Access Token:  {access_token[:20]}... (1시간 유효)")
    print()

    # Test: list profiles with new token
    print("[검증] 새 토큰으로 프로필 조회...")
    resp2 = requests.get(
        "https://advertising-api.amazon.com/v2/profiles",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Amazon-Advertising-API-ClientId": CLIENT_ID,
        },
        timeout=30,
    )
    if resp2.status_code == 200:
        profiles = resp2.json()
        us_sellers = [p for p in profiles
                      if p.get("countryCode") == "US"
                      and p.get("accountInfo", {}).get("type") == "seller"]
        print(f"  전체 프로필: {len(profiles)}개")
        print(f"  US Seller: {len(us_sellers)}개")
        for p in us_sellers:
            name = p.get("accountInfo", {}).get("name", "?")
            print(f"    - {name} (profile_id: {p['profileId']})")
    else:
        print(f"  [WARN] 프로필 조회 실패: {resp2.status_code}")

    print()
    print("=" * 70)
    print("다음 단계:")
    print(f"  1. GitHub Secrets에 추가:")
    print(f"     AMZ_ADS_REFRESH_TOKEN_FLEETERS = {refresh_token[:20]}...")
    print(f"  2. 코드에서 프로필별 토큰 매핑 적용")
    print("=" * 70)
    print()
    print(f"전체 Refresh Token (복사용):")
    print(refresh_token)


def main():
    parser = argparse.ArgumentParser(description="Amazon Ads OAuth 토큰 발급")
    parser.add_argument("--auth-url", action="store_true",
                        help="Step 1: 인증 URL 출력")
    parser.add_argument("--exchange", type=str, default=None,
                        help="Step 2: authorization code로 refresh token 교환")
    args = parser.parse_args()

    if args.auth_url:
        print_auth_url()
    elif args.exchange:
        exchange_code(args.exchange)
    else:
        parser.print_help()
        print("\n사용 예시:")
        print("  python tools/amazon_ads_oauth.py --auth-url")
        print("  python tools/amazon_ads_oauth.py --exchange ANdNAVhyhqBKVoys")


if __name__ == "__main__":
    main()
