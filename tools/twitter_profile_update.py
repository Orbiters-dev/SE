"""
@grosmimi_jp 프로필(bio·URL) 브랜드 계정 기조로 갱신 — 일회성 실행 도구.
GitHub Actions (profile_update.yml) 에서 dispatch로 실행.

성공 시 = GH 시크릿 트위터 키 생존 확인 겸용.
NEW_URL 은 2026-08-10 HEAD 요청 200 확인 (자사 라쿠텐 스토어, 5/15 자사 트윗과 동일).
"""

import os
import sys

import tweepy

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NEW_BIO = (
    "韓国生まれのベビーストローマグブランド「グロミミ」日本公式アカウントです🍼 "
    "6ヶ月からのマグ選び・育児のヒントをお届けします"
)
NEW_URL = "https://www.rakuten.co.jp/littlefingerusa/"

REQUIRED_ENV = [
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
]


def main() -> int:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"CONFIG ERROR: missing env {missing}")
        return 1

    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
    )
    api = tweepy.API(auth)

    try:
        me = api.verify_credentials()
    except tweepy.errors.TweepyException as e:
        print(f"AUTH FAILED (GH 트위터 키 사망 판정): {type(e).__name__}: {e}")
        return 2

    print(f"AUTH OK: @{me.screen_name} (followers: {me.followers_count})")
    print(f"BEFORE bio: {me.description}")

    try:
        api.update_profile(description=NEW_BIO, url=NEW_URL)
    except tweepy.errors.TweepyException as e:
        print(f"UPDATE FAILED (인증은 통과, update_profile 권한/티어 문제 가능): {type(e).__name__}: {e}")
        return 3

    after = api.verify_credentials()
    print(f"AFTER  bio: {after.description}")
    print(f"AFTER  url: {after.url}")

    # X는 bio를 160자로 자를 수 있음 — 완전 일치 또는 원문의 앞부분 절단만 성공으로 판정
    applied = after.description or ""
    ok = applied == NEW_BIO or (len(applied) > 0 and NEW_BIO.startswith(applied))
    if not ok:
        print(f"VERIFY FAILED: applied bio mismatch\n expected: {NEW_BIO}\n actual:   {applied}")
        return 4

    print("PROFILE UPDATE: SUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
