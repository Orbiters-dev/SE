"""
WAT Tool: Twitter/X Community Engagement via Firecrawl + API.
Finds relevant parenting tweets via web search, generates contextual replies,
and posts them via Twitter API (Free tier workaround).

Flow: Firecrawl search → extract tweet IDs → Claude generates reply → API posts reply

Usage:
    py -3 tools/twitter_engage.py                          # find & reply to parenting tweets
    py -3 tools/twitter_engage.py --query "ストローマグ"     # custom search query
    py -3 tools/twitter_engage.py --limit 5                 # max replies per session
    py -3 tools/twitter_engage.py --dry-run                 # preview without posting
    py -3 tools/twitter_engage.py --history                 # show reply history

Output: .tmp/twitter_engage_log.json
"""

import os
import sys
import json
import re
import time
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from twitter_utils import (
    create_twitter_clients,
    validate_tweet_text,
    count_weighted_chars,
    TMP_DIR,
    PROJECT_ROOT,
)

# ── Constants ────────────────────────────────────────────────────────────

JST = timezone(timedelta(hours=9))
ENGAGE_LOG_PATH = TMP_DIR / "twitter_engage_log.json"
FIRECRAWL_DIR = PROJECT_ROOT / ".firecrawl"
DAILY_REPLY_LIMIT = 10  # max replies per day
MODEL = "claude-sonnet-4-20250514"
MIN_FOLLOWERS = 100  # minimum follower count

TWITTER_EPOCH_MS = 1288834974657  # Nov 4, 2010 UTC
MIN_TWEET_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)  # 2026年以降のみ


def get_tweet_date(tweet_id: str) -> datetime | None:
    """ツイートIDからタイムスタンプを取得（Snowflake ID）。"""
    try:
        ts_ms = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except Exception:
        return None

# Keywords indicating manga/anime/otaku accounts — skip regardless of tweet content
BLOCKED_KEYWORDS = {
    # 漫画・アニメ・オタク系
    "漫画", "マンガ", "まんが", "アニメ", "声優", "コスプレ", "オタク", "ヲタク",
    "推し活", "推し", "二次元", "同人", "コミケ", "萌え", "ガチャ", "聖地巡礼",
    "キャラ", "フィギュア", "ゲーム実況", "vtuber", "にじさんじ", "ホロライブ",
    # イラストレーター・絵師系
    "イラスト", "イラストレーター", "絵師", "お絵描き", "絵描き", "創作",
    "illust", "illustration", "illustrator", "drawing", "artist",
    # 男性・パパ系
    "パパ", "ぱぱ", "父", "おとうさん", "お父さん", "夫", "パパ活",
    "dad", "father", "papa",
}

# Competitor / brand accounts to skip (lowercase)
BLOCKED_ACCOUNTS = {
    "pigeon", "pigeon_jp", "combi_jp", "combi", "richell_jp", "richell",
    "nuk_japan", "nuk", "boon_jp", "munchkin_japan", "munchkin",
    "thermos_jp", "thermos", "zojirushi", "tiger_jp", "skater_jp",
    "babybjorn", "ergobaby", "aprica", "aprica_jp", "leapfrog",
    "fisherprice", "graco_jp", "joie_jp", "cybex_jp",
    "grosmimi", "grosmimi_jp", "grosmimi_japan",
}

# Search queries to find relevant tweets (rotated)
DEFAULT_QUERIES = [
    "1歳 育児 ママ site:x.com",
    "1歳10ヶ月 ママ site:x.com",
    "イヤイヤ期 ママ site:x.com",
    "幼児食 育児ママ site:x.com",
    "1歳 育児あるある ママ site:x.com",
    "ストローマグ ママ site:x.com",
    "PPSU マグ ママ site:x.com",
    "1歳 コップ飲み ママ site:x.com",
    "育児 ママあるある site:x.com",
    "赤ちゃん ストロー ママ site:x.com",
]

# ── Reply Persona Prompt ─────────────────────────────────────────────────

REPLY_SYSTEM_PROMPT = """あなたはグロミミ（Grosmimi）ジャパンの公式Twitter/X中の人です。
他のママのツイートに返信します。

## ペルソナ
- 1歳10ヶ月の娘のママ（固定）。韓国出身、グロミミで開発者として働いてる
- 温かくて共感力が高い。同じママとして話す
- 相手のツイートの内容に本当に共感して返信する

## 返信ルール（超重要）
1. 絶対に宣伝しない。製品名を出さない。リンクを貼らない
2. 同じママとして共感する返信だけ
3. 短く（50〜80文字くらい）
4. 絵文字は1個まで
5. ハッシュタグなし（返信にタグは不自然）
6. 「うちも」「わかります」「同じです」系の共感ワード必須

## 良い返信例
- "わかります〜！うちも最初全然飲んでくれなくて😂 でもある日急にできるようになりますよ！"
- "うちもです！カバンの中びしょびしょ事件、何回やったことか…"
- "それ最高ですね！子どもが自分で飲める瞬間、感動しますよね✨"

## ダメな返信例
- "グロミミのマグなら漏れませんよ！" ← 宣伝。絶対NG
- "プロフィールのリンクから見てください" ← 営業。絶対NG
- "おすすめです！" ← 押し売り。絶対NG

返信テキストだけを出力してください。「」や引用符は不要です。"""


# ── Helper Functions ─────────────────────────────────────────────────────

def extract_tweet_ids(search_results) -> list[dict]:
    """Extract tweet IDs and metadata from Firecrawl search results."""
    tweets = []
    seen_ids = set()

    # Handle both dict response and SearchData object (newer SDK)
    if hasattr(search_results, "web"):
        raw = search_results.web or []
    elif hasattr(search_results, "data"):
        raw = search_results.data or []
    elif isinstance(search_results, dict):
        raw = search_results.get("data", search_results.get("web", []))
    else:
        raw = []
    items = raw if isinstance(raw, list) else []
    for item in items:
        # Support both dict and object (SearchResult)
        if isinstance(item, dict):
            url = item.get("url", "")
            title = item.get("title", "")
            description = item.get("description", "")
        else:
            url = getattr(item, "url", "") or ""
            title = getattr(item, "title", "") or ""
            description = getattr(item, "description", "") or ""
        # Match x.com/username/status/tweet_id pattern
        match = re.search(r'x\.com/(\w+)/status/(\d+)', url)
        if match:
            username = match.group(1)
            tweet_id = match.group(2)
            if tweet_id not in seen_ids:
                seen_ids.add(tweet_id)
                tweets.append({
                    "tweet_id": tweet_id,
                    "username": username,
                    "url": url,
                    "title": title,
                    "description": description,
                })

    return tweets


def load_engage_log() -> dict:
    """Load engagement log."""
    if ENGAGE_LOG_PATH.exists():
        with open(ENGAGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"replies": []}


def save_engage_log(log: dict) -> None:
    """Save engagement log."""
    ENGAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENGAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def get_today_reply_count() -> int:
    """Count replies posted today."""
    log = load_engage_log()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    return sum(
        1 for r in log.get("replies", [])
        if r.get("replied_at", "").startswith(today)
    )


def get_replied_tweet_ids() -> set[str]:
    """Get set of tweet IDs we've already replied to."""
    log = load_engage_log()
    return {r.get("target_tweet_id") for r in log.get("replies", [])}


def get_replied_usernames() -> set[str]:
    """Get set of usernames we've already replied to (don't repeat)."""
    log = load_engage_log()
    return {r.get("target_username", "").lower() for r in log.get("replies", [])}


def get_user_info(api, username: str, tweet_info: dict = None) -> dict | None:
    """Build user info from available search data (Free tier: user lookup API not available)."""
    tweet_info = tweet_info or {}
    return {
        "username": username,
        "name": username,
        "description": tweet_info.get("description", "") or tweet_info.get("title", ""),
        "followers": MIN_FOLLOWERS,  # assume OK — follower check not available on Free tier
    }


def is_likely_female_japanese(user_info: dict) -> bool:
    """Use Claude to judge if the account is likely a Japanese mama."""
    import anthropic
    name = user_info.get("name", "")
    bio = user_info.get("description", "")
    username = user_info.get("username", "")
    tweet_text = user_info.get("tweet_text", "")

    prompt = f"""以下のTwitterアカウントが「日本人ママ（子育て中の女性）」かどうか判定してください。
名前: {name}
ユーザー名: @{username}
プロフィール: {bio}
ツイート内容: {tweet_text}

YES（送る）条件:
- ママ・母・育児・子供・赤ちゃん・妊娠などの言及がある
- 女性らしい名前＋育児系ツイート

NO（送らない）条件:
- 男性・パパ・父・男性っぽい名前やプロフィール
- 漫画・アニメ・ゲーム・声優・コスプレ関連のアカウント
- 企業・ブランド・bot・ショップ系
- イラストレーター・絵師・創作系
- 不明・判断できない（確信がない場合は送らない）

YESまたはNOだけ答えてください。"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.content[0].text.strip().upper()
        return answer.startswith("YES")
    except Exception:
        return False  # 判定できない場合は送らない


def has_blocked_keywords(user_info: dict) -> bool:
    """ユーザー名・ツイート内容に漫画・アニメ系キーワードが含まれるか確認。"""
    username = user_info.get("username", "").lower()
    text = (user_info.get("description", "") + " " + user_info.get("tweet_text", "")).lower()

    for kw in BLOCKED_KEYWORDS:
        if kw in username or kw in text:
            return True
    return False


def should_engage(user_info: dict, replied_usernames: set[str]) -> tuple[bool, str]:
    """エンゲージするかどうかを判定する。理由も返す。"""
    username = user_info.get("username", "").lower()
    followers = user_info.get("followers", 0)

    # 同じ人に送らない
    if username in replied_usernames:
        return False, "already replied"

    # 競合・自社アカウントはスキップ
    if username in BLOCKED_ACCOUNTS:
        return False, "blocked account"

    # 漫画・アニメ系キーワードが含まれる場合はスキップ（Claude判定より前に弾く）
    if has_blocked_keywords(user_info):
        return False, "manga/anime keyword detected"

    # フォロワー100人未満はスキップ
    if followers < MIN_FOLLOWERS:
        return False, f"too few followers ({followers})"

    # 男性・企業はスキップ
    if not is_likely_female_japanese(user_info):
        return False, "not female/Japanese"

    return True, "ok"


def search_tweets(query: str) -> list[dict]:
    """Search for tweets using Firecrawl."""
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.error("FIRECRAWL_API_KEY not set")
        return []

    logger.info(f"Searching: {query}")
    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.search(query, limit=10)
        return extract_tweet_ids(result)
    except Exception as e:
        logger.error(f"Search failed: {e}")

    return []


def generate_reply(tweet_info: dict) -> str | None:
    """Generate a contextual reply using Claude."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found")
        return None

    tweet_context = f"""相手のツイート:
@{tweet_info['username']}
「{tweet_info.get('description', tweet_info.get('title', ''))}」

このツイートに対して、同じママとして共感する短い返信を1つ作成してください。
宣伝は絶対にしないでください。製品名も出さないでください。"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": tweet_context}],
        )
        reply = response.content[0].text.strip()

        # Clean up quotes
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        if reply.startswith("「") and reply.endswith("」"):
            reply = reply[1:-1]

        # Validate length
        is_valid, msg = validate_tweet_text(reply)
        if not is_valid:
            logger.warning(f"Reply too long: {msg}")
            return None

        return reply

    except Exception as e:
        logger.error(f"Reply generation failed: {e}")
        return None


def translate_to_korean(text: str) -> str:
    """Quick Korean translation for operator."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"다음 일본어를 한국어로 번역. 번역만 출력:\n{text}"
            }],
        )
        return response.content[0].text.strip()
    except Exception:
        return "(번역 불가)"


def notify_supervisor(tweet_info: dict, reply_text: str, reply_url: str) -> None:
    """コメント投稿をTeamsに報告する（監督）。"""
    import requests

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
    if not webhook_url:
        return

    now = datetime.now(JST).strftime("%H:%M")
    target_url = tweet_info.get("url", "")
    target_text = (tweet_info.get("description", "") or tweet_info.get("title", ""))[:80]
    username = tweet_info.get("username", "")

    message = (
        f"💬 **コメンター報告** {now} JST\n\n"
        f"**送信先:** [@{username}]({target_url})\n"
        f"> {target_text}\n\n"
        f"**送ったコメント:**\n> {reply_text}\n\n"
        f"[投稿を確認]({reply_url})"
    )

    try:
        requests.post(webhook_url, json={"text": message}, timeout=10)
        logger.info("Supervisor notified via Teams")
    except Exception as e:
        logger.warning(f"Teams notify failed: {e}")


def post_reply(tweet_id: str, reply_text: str, username: str = "", dry_run: bool = False) -> dict:
    """Post engagement to a tweet. Tries reply → mention fallback.

    Strategy:
    1. Try in_reply_to (direct reply) — fails if user restricts replies
    2. Fallback to @mention tweet (new tweet mentioning user) — always works
    """
    if dry_run:
        return {"status": "dry_run", "text": reply_text}

    try:
        client, _ = create_twitter_clients()

        # Attempt 1: Direct reply
        try:
            response = client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id,
            )
            reply_id = response.data["id"]
            logger.info(f"Direct reply posted: {reply_id}")
            return {
                "status": "published",
                "reply_id": reply_id,
                "text": reply_text,
                "method": "reply",
            }
        except Exception as e:
            if "403" in str(e):
                logger.info(f"Reply restricted, falling back to @mention")
            else:
                raise

        # Attempt 2: @mention tweet (always works)
        if username:
            mention_text = f"@{username} {reply_text}"
            # Validate length with mention
            is_valid, msg = validate_tweet_text(mention_text)
            if not is_valid:
                # Trim reply to fit
                mention_text = f"@{username} {reply_text[:100]}"

            response = client.create_tweet(text=mention_text)
            reply_id = response.data["id"]
            logger.info(f"Mention tweet posted: {reply_id}")
            return {
                "status": "published",
                "reply_id": reply_id,
                "text": mention_text,
                "method": "mention",
            }

        return {"status": "failed", "error": "Reply restricted, no username for mention"}

    except Exception as e:
        logger.error(f"Reply failed: {e}")
        return {"status": "failed", "error": str(e)}


# ── Main Engagement Flow ─────────────────────────────────────────────────

def run_engagement(
    query: str | None = None,
    max_replies: int = 3,
    dry_run: bool = False,
) -> dict:
    """Run a full engagement session."""

    # Check daily limit
    today_count = get_today_reply_count()
    remaining = DAILY_REPLY_LIMIT - today_count
    if remaining <= 0 and not dry_run:
        print(f"Daily reply limit reached ({DAILY_REPLY_LIMIT})")
        return {"status": "limit_reached", "today_count": today_count}

    max_replies = min(max_replies, remaining)
    replied_ids = get_replied_tweet_ids()

    # Search for tweets
    if query:
        queries = [f"{query} site:x.com"]
    else:
        # Rotate through default queries based on day
        day_index = datetime.now(JST).timetuple().tm_yday
        q1 = DEFAULT_QUERIES[day_index % len(DEFAULT_QUERIES)]
        q2 = DEFAULT_QUERIES[(day_index + 1) % len(DEFAULT_QUERIES)]
        queries = [q1, q2]

    all_tweets = []
    for q in queries:
        tweets = search_tweets(q)
        all_tweets.extend(tweets)
        time.sleep(2)

    # Filter already replied tweets
    new_tweets = [t for t in all_tweets if t["tweet_id"] not in replied_ids]

    if not new_tweets:
        print("No new tweets found to reply to")
        session_result = {"status": "no_targets", "searched": len(queries), "queries": queries, "results": []}
        _save_engage_excel(session_result)
        return session_result

    print(f"\nFound {len(new_tweets)} new tweets to engage with")
    print(f"Will reply to max {max_replies}")
    print(f"{'='*60}")

    # Load Twitter API for user info filtering
    _, api = create_twitter_clients()
    replied_usernames = get_replied_usernames()

    results = []
    reply_count = 0

    for tweet in new_tweets:  # Check all candidates
        if reply_count >= max_replies:
            break

        # 直近30日以内のツイートのみ
        tweet_date = get_tweet_date(tweet["tweet_id"])
        if not tweet_date or (datetime.now(timezone.utc) - tweet_date).total_seconds() > 86400 * 30:
            continue  # 30日超えはスキップ

        print(f"\n--- Target Tweet ---")
        print(f"  @{tweet['username']}: {tweet['description'][:80]}...")
        print(f"  URL: {tweet['url']}")
        print(f"  Date: {tweet_date.strftime('%Y-%m-%d') if tweet_date else '?'}")

        # Fetch user info and apply filters
        user_info = get_user_info(api, tweet["username"], tweet_info=tweet)
        if user_info:
            user_info["tweet_text"] = tweet.get("description", tweet.get("title", ""))
        if not user_info:
            print("  (skipped: could not fetch user info)")
            continue

        ok, reason = should_engage(user_info, replied_usernames)
        if not ok:
            print(f"  (skipped: {reason})")
            continue

        print(f"  Followers: {user_info['followers']} ✅")

        # Generate reply
        reply_text = generate_reply(tweet)
        if not reply_text:
            print("  (skipped: generation failed)")
            continue

        ko = translate_to_korean(reply_text) if not dry_run else ""
        weighted = count_weighted_chars(reply_text)

        print(f"  Reply JP: {reply_text}")
        if ko:
            print(f"  Reply KO: {ko}")
        print(f"  Weighted: {weighted}/280")

        # Post reply (with mention fallback)
        result = post_reply(tweet["tweet_id"], reply_text, username=tweet["username"], dry_run=dry_run)

        if result["status"] in ("published", "dry_run"):
            reply_count += 1

            # Notify supervisor via Teams
            if result["status"] == "published" and result.get("reply_id"):
                reply_url = f"https://x.com/grosmimi_jp/status/{result['reply_id']}"
                notify_supervisor(tweet, reply_text, reply_url)

            # Log
            log_entry = {
                "replied_at": datetime.now(JST).isoformat(),
                "target_tweet_id": tweet["tweet_id"],
                "target_username": tweet["username"],
                "target_url": tweet["url"],
                "target_text": tweet["description"][:200],
                "reply_text": reply_text,
                "reply_ko": ko,
                "reply_id": result.get("reply_id"),
                "status": result["status"],
            }

            # セッション内でも同じ人に送らないようにリアルタイム更新
            replied_usernames.add(tweet["username"].lower())

            if not dry_run:
                log = load_engage_log()
                log["replies"].append(log_entry)
                save_engage_log(log)

            results.append(log_entry)
            print(f"  Status: {result['status']}")

            if result.get("reply_id"):
                print(f"  Reply URL: https://x.com/grosmimi_jp/status/{result['reply_id']}")

        else:
            print(f"  Failed: {result.get('error', 'unknown')}")

        time.sleep(3)  # Rate limit between replies

    print(f"\n{'='*60}")
    print(f"Session complete: {reply_count} replies posted")
    print(f"Today total: {today_count + reply_count}/{DAILY_REPLY_LIMIT}")

    session_result = {
        "status": "ok",
        "replies_posted": reply_count,
        "today_total": today_count + reply_count,
        "queries": queries,
        "results": results,
    }
    _save_engage_excel(session_result)
    _save_engagement_intel(results)
    return session_result


def _save_engagement_intel(results: list[dict]) -> None:
    """Save engagement target topics to intel file for 企画マン reference."""
    if not results:
        return
    try:
        intel_dir = TMP_DIR / "twitter_intel"
        intel_dir.mkdir(parents=True, exist_ok=True)
        intel_path = intel_dir / "engagement_insights.json"

        # Load existing topics
        existing = []
        if intel_path.exists():
            with open(intel_path, "r", encoding="utf-8") as f:
                existing = json.load(f).get("recent_topics", [])

        # Add today's engagement targets (対象ツイート = 育児現場インサイト)
        new_topics = []
        for reply in results:
            new_topics.append({
                "date": reply.get("replied_at", "")[:10],
                "target_text": reply.get("target_text", "")[:200],
                "username": reply.get("target_username", ""),
            })

        # Keep last 50
        all_topics = (new_topics + existing)[:50]

        intel_data = {
            "source": "コメンター",
            "updated": datetime.now(JST).strftime("%Y-%m-%d"),
            "recent_topics": all_topics,
            "raw_file": str(ENGAGE_LOG_PATH),
        }
        with open(intel_path, "w", encoding="utf-8") as f:
            json.dump(intel_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Engagement intel saved: {intel_path} ({len(all_topics)} topics)")
    except Exception as e:
        logger.warning(f"Engagement intel save failed: {e}")


def _save_engage_excel(session: dict) -> None:
    """コメンター実行結果をExcelにまとめてTeamsにアップロードする。"""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "コメンター実行ログ"

        # ヘッダー
        headers = ["実行日時", "@ユーザー", "対象ツイートURL", "対象テキスト", "返信内容", "ステータス"]
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        results = session.get("results", [])
        now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

        if results:
            fill = PatternFill(start_color="DEEAF1", end_color="DEEAF1", fill_type="solid")
            for r_idx, r in enumerate(results, 2):
                values = [
                    r.get("replied_at", now_str)[:16],
                    r.get("target_username", ""),
                    r.get("target_url", ""),
                    r.get("target_text", "")[:100],
                    r.get("reply_text", ""),
                    r.get("status", ""),
                ]
                for col, v in enumerate(values, 1):
                    cell = ws.cell(row=r_idx, column=col, value=v)
                    cell.fill = fill
                    cell.alignment = Alignment(wrap_text=True)
        else:
            # ツイートなし行
            queries = session.get("queries", [])
            status_text = "ツイートが見つかりませんでした"
            fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            values = [now_str, "—", "—", f"検索クエリ: {', '.join(queries)}", "—", status_text]
            for col, v in enumerate(values, 1):
                cell = ws.cell(row=2, column=col, value=v)
                cell.fill = fill
                cell.alignment = Alignment(wrap_text=True)

        # 列幅
        for col, width in zip(["A", "B", "C", "D", "E", "F"], [18, 18, 45, 50, 60, 16]):
            ws.column_dimensions[col].width = width

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(JST).strftime("%Y-%m-%d")
        path = TMP_DIR / f"twitter_engage_{date_str}.xlsx"
        wb.save(path)
        logger.info(f"Engage Excel saved: {path}")

        # TeamsにアップロードorNotify
        try:
            from teams_upload import upload_file
            reply_count = len(results)
            msg = (
                f"💬 {date_str} コメンター実行完了 — {reply_count}件返信"
                if reply_count else
                f"💬 {date_str} コメンター実行 — 対象ツイートなし（Excelで確認）"
            )
            upload_file(str(path), notify=True, message=msg)
            logger.info("Engage Excel uploaded to Teams")
        except Exception as e:
            logger.warning(f"Teams upload failed: {e}")

    except Exception as e:
        logger.warning(f"Engage Excel creation failed: {e}")


def show_history():
    """Show reply history."""
    log = load_engage_log()
    replies = log.get("replies", [])

    if not replies:
        print("No reply history yet")
        return

    print(f"\n{'='*60}")
    print(f"Reply History ({len(replies)} total)")
    print(f"{'='*60}")

    for r in replies[-10:]:
        print(f"\n  [{r.get('replied_at', '?')[:16]}]")
        print(f"  To: @{r.get('target_username')} — {r.get('target_text', '')[:60]}...")
        print(f"  Reply: {r.get('reply_text', '')}")
        if r.get("reply_ko"):
            print(f"  KO: {r['reply_ko']}")
        print(f"  Status: {r.get('status')}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Twitter engagement via Firecrawl + API"
    )
    parser.add_argument("--query", type=str, help="Custom search query")
    parser.add_argument("--limit", type=int, default=3, help="Max replies (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--history", action="store_true", help="Show reply history")
    args = parser.parse_args()

    if args.history:
        show_history()
        return

    run_engagement(
        query=args.query,
        max_replies=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
