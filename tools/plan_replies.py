"""
WAT Tool: Plan specific reply targets for each slot.

Searches for relevant parenting tweets via Firecrawl, generates contextual
reply drafts using Claude, and returns structured plans for team review.

Usage:
    python tools/plan_replies.py --slot 11              # plan replies for slot 11
    python tools/plan_replies.py --slots 11,13,15       # plan for multiple slots
    python tools/plan_replies.py --am                   # plan AM slots (9,11,13,15)
    python tools/plan_replies.py --pm                   # plan PM slots (17,19,21,23)
    python tools/plan_replies.py --dry-run              # preview without saving
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

from twitter_agent import SLOT_CONFIG
from twitter_engage import (
    search_tweets,
    generate_reply,
    translate_to_korean,
    get_replied_tweet_ids,
    REPLY_SYSTEM_PROMPT,
)
from twitter_utils import count_weighted_chars

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
def _plan_path(date_str: str = None) -> Path:
    """Get date-specific plan file path."""
    if not date_str:
        date_str = datetime.now(JST).strftime("%Y-%m-%d")
    return TMP_DIR / f"daily_tweet_plan_{date_str}.json"

JST = timezone(timedelta(hours=9))

AM_SLOTS = [9, 11, 13, 15]
PM_SLOTS = [17, 19, 21, 23]
# Slots that don't get replies (no engage_count or 0)
NO_REPLY_SLOTS = {9, 23}


def plan_slot_replies(slot: int, count: int = None) -> list[dict]:
    """Plan specific reply targets for a slot.

    1. Get engage_hashtags from SLOT_CONFIG
    2. Search tweets via Firecrawl
    3. Generate reply drafts via Claude
    4. Translate to Korean

    Returns: list of reply plan dicts
    """
    config = SLOT_CONFIG.get(slot)
    if not config:
        logger.warning(f"No config for slot {slot}")
        return []

    if count is None:
        count = config.get("engage_count", 0)
    if count == 0:
        logger.info(f"Slot {slot}: no replies planned (engage_count=0)")
        return []

    hashtags = config.get("engage_hashtags", [])
    if not hashtags:
        logger.warning(f"Slot {slot}: no engage_hashtags configured")
        return []

    # Build search queries from hashtags
    replied_ids = get_replied_tweet_ids()
    all_candidates = []

    for tag in hashtags[:3]:  # search max 3 hashtags per slot
        query = f"{tag} site:x.com"
        tweets = search_tweets(query)
        for t in tweets:
            if t["tweet_id"] not in replied_ids:
                all_candidates.append(t)

    if not all_candidates:
        logger.warning(f"Slot {slot}: no reply targets found")
        return []

    # Deduplicate by tweet_id
    seen = set()
    unique = []
    for t in all_candidates:
        if t["tweet_id"] not in seen:
            seen.add(t["tweet_id"])
            unique.append(t)

    logger.info(f"Slot {slot}: found {len(unique)} candidates, planning {count} replies")

    # Generate reply drafts for top candidates
    replies = []
    for tweet in unique[:count * 2]:  # search more, use fewer
        if len(replies) >= count:
            break

        reply_jp = generate_reply(tweet)
        if not reply_jp:
            continue

        reply_ko = translate_to_korean(reply_jp)
        chars = count_weighted_chars(reply_jp)

        replies.append({
            "target_username": tweet["username"],
            "target_text": tweet.get("description", tweet.get("title", ""))[:200],
            "target_url": tweet["url"],
            "target_tweet_id": tweet["tweet_id"],
            "reply_jp": reply_jp,
            "reply_ko": reply_ko,
            "reply_chars": chars,
        })

        logger.info(f"  Reply to @{tweet['username']}: {reply_jp[:50]}...")

    return replies


def plan_daily_replies(slots: list[int]) -> dict:
    """Plan replies for multiple slots.

    Returns: {slot: [reply_plan, ...], ...}
    """
    result = {}
    for slot in slots:
        if slot in NO_REPLY_SLOTS:
            result[slot] = []
            continue
        logger.info(f"=== Planning replies for slot {slot}:00 ===")
        result[slot] = plan_slot_replies(slot)

    return result


def merge_replies_into_plan(reply_plans: dict, plan_file: str = None) -> dict:
    """Merge reply plans into the daily tweet plan JSON.

    Args:
        reply_plans: {slot: [reply_plan, ...]}
        plan_file: path to plan JSON (default: PLAN_FILE)

    Returns: updated plan dict
    """
    path = Path(plan_file) if plan_file else PLAN_FILE

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = {"date": datetime.now(JST).strftime("%Y-%m-%d"), "slots": {}}

    for slot, replies in reply_plans.items():
        slot_key = str(slot)
        if slot_key not in plan.get("slots", {}):
            plan["slots"][slot_key] = {}
        plan["slots"][slot_key]["replies"] = replies

    # Save
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    logger.info(f"Reply plans merged into {path}")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plan reply targets for Twitter slots")
    parser.add_argument("--slot", type=int, help="Plan replies for a single slot")
    parser.add_argument("--slots", type=str, help="Comma-separated slots (e.g., 11,13,15)")
    parser.add_argument("--am", action="store_true", help="Plan AM slots (9,11,13,15)")
    parser.add_argument("--pm", action="store_true", help="Plan PM slots (17,19,21,23)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    if args.slot:
        target_slots = [args.slot]
    elif args.slots:
        target_slots = [int(s.strip()) for s in args.slots.split(",")]
    elif args.am:
        target_slots = AM_SLOTS
    elif args.pm:
        target_slots = PM_SLOTS
    else:
        target_slots = AM_SLOTS + PM_SLOTS

    reply_plans = plan_daily_replies(target_slots)

    # Print summary
    total = sum(len(r) for r in reply_plans.values())
    print(f"\n{'='*60}")
    print(f"Reply Plan Summary: {total} replies across {len(target_slots)} slots")
    print(f"{'='*60}")
    for slot, replies in reply_plans.items():
        if replies:
            print(f"\n[{slot}:00] {len(replies)} replies:")
            for r in replies:
                print(f"  → @{r['target_username']}: {r['reply_jp'][:50]}...")
                print(f"    KR: {r['reply_ko'][:50]}...")
        else:
            print(f"\n[{slot}:00] (no replies)")

    if not args.dry_run:
        merge_replies_into_plan(reply_plans)
        print(f"\nSaved to {PLAN_FILE}")
    else:
        print(f"\n[DRY RUN] Not saved")
