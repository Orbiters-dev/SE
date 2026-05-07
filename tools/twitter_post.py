"""
WAT Tool: Post tweets to Twitter/X (text + images, single + thread).
Supports posting from content plan or ad-hoc text input.
Includes budget tracking for Free tier (1,500 tweets/month).

Output: .tmp/twitter_log.json

Usage:
    py -3 tools/twitter_post.py                              # post next planned tweet
    py -3 tools/twitter_post.py --post-id 20260225_T001      # specific tweet from plan
    py -3 tools/twitter_post.py --text "テスト投稿🍼"          # quick manual tweet
    py -3 tools/twitter_post.py --text "..." --image path.jpg # tweet with image
    py -3 tools/twitter_post.py --dry-run                    # validate without posting
    py -3 tools/twitter_post.py --budget                     # show budget status
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

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

# Add tools/ to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from twitter_utils import (
    BudgetTracker,
    RateLimiter,
    create_twitter_clients,
    append_to_log,
    update_plan_status,
    validate_tweet_text,
    count_weighted_chars,
    TWITTER_LOG_PATH,
    TWITTER_PLAN_PATH,
    TMP_DIR,
)

# Rate limiter: max 50 write requests per 15 min window (conservative)
write_limiter = RateLimiter(max_calls=40, period_seconds=900)


# ── Media Upload ─────────────────────────────────────────────────────────

def upload_media(api_v1, image_path: Path) -> str | None:
    """Upload image via Twitter v1.1 media upload endpoint.

    Args:
        api_v1: tweepy.API instance (OAuth 1.0a)
        image_path: Path to image file (JPEG, PNG, GIF; max 5MB)

    Returns:
        media_id string, or None on failure
    """
    if not image_path.exists():
        logger.error(f"Image not found: {image_path}")
        return None

    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > 5:
        logger.error(f"Image too large: {size_mb:.1f}MB (max 5MB)")
        return None

    try:
        media = api_v1.media_upload(filename=str(image_path))
        logger.info(f"Media uploaded: {media.media_id} ({image_path.name})")
        return str(media.media_id)
    except Exception as e:
        logger.error(f"Media upload failed: {e}")
        return None


# ── Single Tweet ─────────────────────────────────────────────────────────

def post_single_tweet(
    client,
    api_v1,
    text: str,
    image_paths: list[Path] | None = None,
    reply_to: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Post a single tweet with optional images.

    Args:
        client: tweepy.Client (v2)
        api_v1: tweepy.API (v1.1, for media)
        text: Tweet text (max 280 chars)
        image_paths: List of image paths (max 4)
        reply_to: tweet_id to reply to (for threads)
        dry_run: If True, validate only

    Returns:
        dict with tweet_id, status, etc.
    """
    # Validate text
    is_valid, msg = validate_tweet_text(text)
    if not is_valid:
        logger.error(msg)
        return {"status": "failed", "error": msg}

    weighted = count_weighted_chars(text)
    logger.info(f"Tweet ({weighted}/280 weighted, {len(text)} raw): {text[:80]}...")

    # Upload media if provided
    media_ids = []
    if image_paths:
        if len(image_paths) > 4:
            logger.warning("Max 4 images per tweet. Using first 4.")
            image_paths = image_paths[:4]

        for img_path in image_paths:
            mid = upload_media(api_v1, img_path) if not dry_run else f"dry_run_{img_path.name}"
            if mid:
                media_ids.append(mid)

    if dry_run:
        print(f"[DRY RUN] Would post tweet:")
        print(f"  Text: {text}")
        print(f"  Weighted: {weighted}/280 ({len(text)} raw chars)")
        if media_ids:
            print(f"  Images: {len(media_ids)}")
        if reply_to:
            print(f"  Reply to: {reply_to}")
        return {"status": "dry_run", "text": text, "weighted_chars": weighted, "char_count": len(text)}

    # Post tweet
    write_limiter.wait_if_needed()

    try:
        kwargs = {"text": text}
        if media_ids:
            kwargs["media_ids"] = media_ids
        if reply_to:
            kwargs["in_reply_to_tweet_id"] = reply_to

        response = client.create_tweet(**kwargs)
        tweet_id = response.data["id"]

        logger.info(f"Tweet posted: {tweet_id}")
        return {
            "tweet_id": tweet_id,
            "status": "published",
            "text": text,
            "char_count": len(text),
            "media_count": len(media_ids),
        }

    except Exception as e:
        logger.error(f"Tweet failed: {e}")
        return {"status": "failed", "error": str(e)}


# ── Thread ───────────────────────────────────────────────────────────────

def post_thread(
    client,
    api_v1,
    tweets: list[dict],
    dry_run: bool = False,
) -> dict:
    """Post a thread (chain of reply tweets).

    Args:
        client: tweepy.Client
        api_v1: tweepy.API
        tweets: List of {"text": str, "image_path": str|None}
        dry_run: If True, validate only

    Returns:
        dict with thread_id, tweet_ids, status
    """
    if not tweets:
        return {"status": "failed", "error": "No tweets in thread"}

    # Validate all tweets first
    errors = []
    for i, tweet in enumerate(tweets):
        is_valid, msg = validate_tweet_text(tweet["text"])
        if not is_valid:
            errors.append(f"Tweet {i + 1}: {msg}")

    if errors:
        for err in errors:
            logger.error(err)
        return {"status": "failed", "errors": errors}

    if dry_run:
        print(f"[DRY RUN] Would post thread ({len(tweets)} tweets):")
        for i, tweet in enumerate(tweets):
            img = " + image" if tweet.get("image_path") else ""
            print(f"  [{i + 1}] ({len(tweet['text'])}/280){img}: {tweet['text'][:60]}...")
        return {"status": "dry_run", "tweet_count": len(tweets)}

    # Post thread
    tweet_ids = []
    reply_to = None

    for i, tweet in enumerate(tweets):
        image_paths = []
        if tweet.get("image_path"):
            img_path = Path(tweet["image_path"])
            if img_path.exists():
                image_paths = [img_path]

        result = post_single_tweet(
            client, api_v1,
            text=tweet["text"],
            image_paths=image_paths or None,
            reply_to=reply_to,
        )

        if result["status"] != "published":
            logger.error(f"Thread broken at tweet {i + 1}: {result.get('error')}")
            return {
                "status": "partial",
                "thread_id": tweet_ids[0] if tweet_ids else None,
                "tweet_ids": tweet_ids,
                "failed_at": i + 1,
                "error": result.get("error"),
            }

        tweet_ids.append(result["tweet_id"])
        reply_to = result["tweet_id"]

        # Pause between thread tweets to avoid rate limits
        if i < len(tweets) - 1:
            time.sleep(2)

    logger.info(f"Thread posted: {len(tweet_ids)} tweets")
    return {
        "status": "published",
        "thread_id": tweet_ids[0],
        "tweet_ids": tweet_ids,
        "tweet_count": len(tweet_ids),
    }


# ── Plan-based Posting ───────────────────────────────────────────────────

def load_plan(plan_path: Path) -> dict | None:
    """Load twitter content plan."""
    if not plan_path.exists():
        logger.error(f"Plan not found: {plan_path}")
        return None
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_next_post(plan: dict) -> dict | None:
    """Get next planned (unposted) post from plan."""
    for post in plan.get("posts", []):
        if post.get("status") == "planned":
            return post
    return None


def post_from_plan(
    client, api_v1, plan_path: Path, post_id: str | None = None, dry_run: bool = False
) -> dict:
    """Post a tweet from the content plan.

    Args:
        client: tweepy.Client
        api_v1: tweepy.API
        plan_path: Path to twitter_plan.json
        post_id: Specific post_id, or None for next planned
        dry_run: Validate only
    """
    plan = load_plan(plan_path)
    if not plan:
        return {"status": "failed", "error": "No plan found"}

    # Find the post
    if post_id:
        post = next((p for p in plan["posts"] if p["post_id"] == post_id), None)
        if not post:
            return {"status": "failed", "error": f"Post {post_id} not found in plan"}
    else:
        post = get_next_post(plan)
        if not post:
            return {"status": "failed", "error": "No planned posts remaining"}

    logger.info(f"Posting: {post['post_id']} — {post.get('topic', 'no topic')}")

    # Determine tweet type
    tweet_type = post.get("tweet_type", "single")
    tweets_data = post.get("tweets", [])

    if tweet_type == "thread" and len(tweets_data) > 1:
        result = post_thread(client, api_v1, tweets_data, dry_run=dry_run)
    else:
        # Single tweet
        text = tweets_data[0]["text"] if tweets_data else post.get("text", "")
        image_path = tweets_data[0].get("image_path") if tweets_data else post.get("image_path")
        image_paths = [Path(image_path)] if image_path else None
        result = post_single_tweet(client, api_v1, text, image_paths=image_paths, dry_run=dry_run)

    # Update plan status
    if not dry_run and result["status"] in ("published", "partial"):
        update_plan_status(plan_path, post["post_id"], result["status"])

    # Log
    if not dry_run:
        log_entry = {
            "post_id": post["post_id"],
            "posted_at": datetime.now().isoformat(),
            "platform": "twitter",
            "type": tweet_type,
            "tweet_id": result.get("tweet_id") or result.get("thread_id"),
            "tweet_ids": result.get("tweet_ids"),
            "text_preview": (tweets_data[0]["text"][:80] if tweets_data else "")[:80],
            "status": result["status"],
            "errors": result.get("error") or result.get("errors"),
        }
        append_to_log(TWITTER_LOG_PATH, log_entry)

    return result


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post tweets to Twitter/X")
    parser.add_argument("--post-id", type=str, help="Specific post ID from plan")
    parser.add_argument("--text", type=str, help="Ad-hoc tweet text")
    parser.add_argument("--image", type=str, action="append", help="Image path (can repeat, max 4)")
    parser.add_argument("--thread", action="store_true", help="Post as thread from plan")
    parser.add_argument("--plan-file", type=str, default=str(TWITTER_PLAN_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Validate without posting")
    parser.add_argument("--budget", action="store_true", help="Show budget status only")
    args = parser.parse_args()

    # Budget check
    tracker = BudgetTracker()
    if args.budget:
        tracker.print_budget()
        return

    # Ad-hoc tweet
    if args.text:
        if not args.dry_run and not tracker.can_post():
            print("Budget exceeded. Cannot post more tweets today.")
            tracker.print_budget()
            return

        if args.dry_run:
            result = post_single_tweet(None, None, args.text, dry_run=True)
        else:
            client, api_v1 = create_twitter_clients()
            image_paths = [Path(p) for p in args.image] if args.image else None
            result = post_single_tweet(client, api_v1, args.text, image_paths=image_paths, dry_run=False)

            # Log ad-hoc tweet
            if result["status"] == "published":
                log_entry = {
                    "post_id": f"adhoc_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "posted_at": datetime.now().isoformat(),
                    "platform": "twitter",
                    "type": "single",
                    "tweet_id": result.get("tweet_id"),
                    "text_preview": args.text[:80],
                    "status": result["status"],
                }
                append_to_log(TWITTER_LOG_PATH, log_entry)

        print(f"\nResult: {result['status']}")
        if result.get("tweet_id"):
            print(f"Tweet ID: {result['tweet_id']}")
            print(f"URL: https://x.com/i/status/{result['tweet_id']}")
        return

    # Plan-based posting
    if not args.dry_run and not tracker.can_post():
        print("Budget exceeded. Cannot post more tweets today.")
        tracker.print_budget()
        return

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"No content plan found at: {plan_path}")
        print("Run: py -3 tools/plan_twitter_content.py --count 3")
        return

    if args.dry_run:
        result = post_from_plan(None, None, plan_path, post_id=args.post_id, dry_run=True)
    else:
        client, api_v1 = create_twitter_clients()
        result = post_from_plan(client, api_v1, plan_path, post_id=args.post_id, dry_run=False)

    print(f"\nResult: {result['status']}")
    if result.get("tweet_id") or result.get("thread_id"):
        tid = result.get("tweet_id") or result.get("thread_id")
        print(f"Tweet ID: {tid}")
        print(f"URL: https://x.com/i/status/{tid}")

    # Show remaining budget
    print()
    tracker.print_budget()


if __name__ == "__main__":
    main()
