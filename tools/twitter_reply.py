"""
WAT Tool: Monitor Twitter/X mentions and auto-reply with templates.
Uses keyword-based classification (no LLM needed) + predefined Japanese responses.
Budget-aware: max 5 replies per day on Free tier.

Output: .tmp/twitter_reply_log.json

Usage:
    py -3 tools/twitter_reply.py                    # check mentions and reply
    py -3 tools/twitter_reply.py --check-only       # show mentions without replying
    py -3 tools/twitter_reply.py --dry-run          # show what replies would be sent
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, date

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
    append_to_log,
    RateLimiter,
    TWITTER_REPLY_LOG_PATH,
    TWITTER_MENTION_STATE_PATH,
    REPLY_DAILY_LIMIT,
    TMP_DIR,
)

# Read rate limiter: 1 request per 15 minutes on Free tier
read_limiter = RateLimiter(max_calls=1, period_seconds=900)


# ── Mention Classification ───────────────────────────────────────────────

PRODUCT_KEYWORDS = [
    "漏れ", "こぼれ", "洗い", "サイズ", "いつから", "ストロー",
    "PPSU", "ppsu", "マグ", "ステンレス", "温度", "保温", "保冷",
    "何ヶ月", "何歳", "使い方", "パーツ", "交換", "価格", "値段",
    "どこで買", "グロミミ", "grosmimi",
]

POSITIVE_KEYWORDS = [
    "最高", "大好き", "ありがとう", "買ってよかった", "おすすめ",
    "気に入", "可愛い", "かわいい", "良い", "いい", "素敵",
    "助かっ", "便利", "神", "推し",
]

COMPLAINT_KEYWORDS = [
    "壊れ", "使えな", "返品", "交換して", "不良", "ひどい",
    "最悪", "がっかり", "割れ", "漏れた", "こぼれた",
]


def classify_mention(text: str) -> str:
    """Classify mention into categories using keyword matching.

    Returns:
        One of: 'product_question', 'positive_feedback', 'complaint', 'general'
    """
    text_lower = text.lower()

    # Check complaints first (highest priority)
    if any(kw in text_lower for kw in COMPLAINT_KEYWORDS):
        return "complaint"

    # Product questions
    if any(kw in text_lower for kw in PRODUCT_KEYWORDS) and "?" in text or "？" in text:
        return "product_question"
    if any(kw in text_lower for kw in PRODUCT_KEYWORDS):
        return "product_question"

    # Positive feedback
    if any(kw in text_lower for kw in POSITIVE_KEYWORDS):
        return "positive_feedback"

    return "general"


# ── Reply Templates ──────────────────────────────────────────────────────

REPLY_TEMPLATES = {
    "product_question": [
        "ご質問ありがとうございます！✨\nグロミミのストローマグについて、詳しくはプロフィールのリンクからご確認いただけます🍼\nご不明な点がございましたら、お気軽にDMくださいね！",
        "お問い合わせありがとうございます！🍼\n詳しい製品情報はプロフィールリンクからご覧いただけます✨\nDMでも承っておりますのでお気軽にどうぞ！",
    ],
    "positive_feedback": [
        "嬉しいお言葉ありがとうございます！💕\nこれからもお子様の成長を応援させてください✨",
        "ありがとうございます！とても嬉しいです🥰\nグロミミを選んでくださり感謝です🍼✨",
        "素敵なお言葉、ありがとうございます💕\nお子様との毎日がもっと楽しくなりますように✨",
    ],
    "complaint": [
        "ご不便をおかけして大変申し訳ございません🙇\nお手数ですが、DMにて詳しい状況をお聞かせいただけますでしょうか？早急にご対応させていただきます。",
    ],
    "general": [
        "コメントありがとうございます✨",
    ],
}


def pick_reply(category: str, mention_id: str) -> str:
    """Pick a reply template (rotates based on mention_id hash)."""
    templates = REPLY_TEMPLATES.get(category, REPLY_TEMPLATES["general"])
    idx = hash(mention_id) % len(templates)
    return templates[idx]


# ── Mention State ────────────────────────────────────────────────────────

def load_mention_state() -> dict:
    """Load last processed mention ID."""
    if TWITTER_MENTION_STATE_PATH.exists():
        with open(TWITTER_MENTION_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_mention_id": None, "last_checked": None}


def save_mention_state(state: dict):
    """Save mention state."""
    TWITTER_MENTION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_checked"] = datetime.now().isoformat()
    with open(TWITTER_MENTION_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_today_reply_count() -> int:
    """Count replies sent today."""
    if not TWITTER_REPLY_LOG_PATH.exists():
        return 0
    with open(TWITTER_REPLY_LOG_PATH, "r", encoding="utf-8") as f:
        log = json.load(f)
    today = date.today().isoformat()
    return sum(
        1 for t in log.get("tweets", [])
        if t.get("replied_at", "").startswith(today)
        and t.get("status") == "replied"
    )


# ── Fetch & Reply ────────────────────────────────────────────────────────

def fetch_mentions(client, since_id: str | None = None) -> list[dict]:
    """Fetch recent mentions via Twitter API v2."""
    read_limiter.wait_if_needed()

    try:
        me = client.get_me()
        user_id = me.data.id

        kwargs = {
            "id": user_id,
            "max_results": 10,
            "tweet_fields": ["created_at", "author_id", "conversation_id"],
        }
        if since_id:
            kwargs["since_id"] = since_id

        mentions = client.get_users_mentions(**kwargs)

        if not mentions.data:
            logger.info("No new mentions found")
            return []

        results = []
        for tweet in mentions.data:
            results.append({
                "tweet_id": str(tweet.id),
                "text": tweet.text,
                "author_id": str(tweet.author_id),
                "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
            })

        logger.info(f"Found {len(results)} mentions")
        return results

    except Exception as e:
        logger.error(f"Failed to fetch mentions: {e}")
        if "429" in str(e):
            logger.warning("Rate limit hit. Try again in 15 minutes.")
        return []


def process_mentions(client, mentions: list[dict], dry_run: bool = False) -> list[dict]:
    """Process mentions: classify and reply."""
    replies_sent = get_today_reply_count()
    remaining = REPLY_DAILY_LIMIT - replies_sent

    if remaining <= 0 and not dry_run:
        logger.warning(f"Daily reply limit reached ({REPLY_DAILY_LIMIT}). Skipping replies.")
        for m in mentions:
            m["action"] = "skipped_budget"
        return mentions

    results = []
    for mention in mentions:
        category = classify_mention(mention["text"])
        reply_text = pick_reply(category, mention["tweet_id"])

        mention["category"] = category
        mention["reply_text"] = reply_text

        if dry_run:
            mention["action"] = "dry_run"
            print(f"\n--- Mention {mention['tweet_id']} ---")
            print(f"  Text: {mention['text'][:100]}")
            print(f"  Category: {category}")
            print(f"  Reply: {reply_text[:80]}...")
            results.append(mention)
            continue

        if remaining <= 0:
            mention["action"] = "skipped_budget"
            results.append(mention)
            continue

        # Send reply
        try:
            response = client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=mention["tweet_id"],
            )
            mention["action"] = "replied"
            mention["reply_tweet_id"] = response.data["id"]
            remaining -= 1

            # Log reply
            append_to_log(TWITTER_REPLY_LOG_PATH, {
                "mention_id": mention["tweet_id"],
                "author_id": mention["author_id"],
                "category": category,
                "reply_tweet_id": response.data["id"],
                "reply_text": reply_text,
                "replied_at": datetime.now().isoformat(),
                "status": "replied",
            })

            logger.info(f"Replied to {mention['tweet_id']} ({category})")

        except Exception as e:
            logger.error(f"Reply failed: {e}")
            mention["action"] = "failed"
            mention["error"] = str(e)

        results.append(mention)

    return results


def main():
    parser = argparse.ArgumentParser(description="Monitor Twitter mentions and auto-reply")
    parser.add_argument("--check-only", action="store_true", help="Show mentions without replying")
    parser.add_argument("--dry-run", action="store_true", help="Show replies without sending")
    parser.add_argument("--since-id", type=str, help="Only mentions after this tweet ID")
    args = parser.parse_args()

    # Load state
    state = load_mention_state()
    since_id = args.since_id or state.get("last_mention_id")

    # Show reply budget
    replies_today = get_today_reply_count()
    print(f"Reply budget: {replies_today}/{REPLY_DAILY_LIMIT} used today")

    # Fetch mentions
    client, api_v1 = create_twitter_clients()
    mentions = fetch_mentions(client, since_id=since_id)

    if not mentions:
        print("No new mentions.")
        save_mention_state(state)
        return

    print(f"\nFound {len(mentions)} new mention(s):")

    if args.check_only:
        for m in mentions:
            category = classify_mention(m["text"])
            print(f"\n  [{category}] @{m['author_id']} ({m['created_at']})")
            print(f"  {m['text'][:120]}")
        # Update last seen ID
        state["last_mention_id"] = mentions[0]["tweet_id"]
        save_mention_state(state)
        return

    # Process and reply
    results = process_mentions(client, mentions, dry_run=args.dry_run)

    # Update state
    if mentions and not args.dry_run:
        state["last_mention_id"] = mentions[0]["tweet_id"]
        save_mention_state(state)

    # Summary
    replied = sum(1 for r in results if r.get("action") == "replied")
    skipped = sum(1 for r in results if r.get("action") == "skipped_budget")
    failed = sum(1 for r in results if r.get("action") == "failed")

    print(f"\nSummary: {replied} replied, {skipped} skipped (budget), {failed} failed")


if __name__ == "__main__":
    main()
