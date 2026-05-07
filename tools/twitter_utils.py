"""
WAT Tool: Shared utilities for all Twitter/X tools.
Provides rate limiting, budget tracking, client creation, and logging.

Imported by: twitter_auth.py, twitter_post.py, twitter_reply.py,
             twitter_analytics.py, twitter_trends.py, plan_twitter_content.py
"""

import os
import sys
import json
import time
import logging
import re
from pathlib import Path
from datetime import datetime, date

from dotenv import load_dotenv

# ── Environment ──────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ── Windows encoding fix ─────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Free Tier Limits ─────────────────────────────────────────────────────
MONTHLY_TWEET_LIMIT = 1500
DAILY_TWEET_LIMIT = 50       # self-imposed safety limit
READ_INTERVAL_SECONDS = 900  # 15 minutes between read requests
REPLY_DAILY_LIMIT = 5        # self-imposed to preserve budget

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
TWITTER_LOG_PATH = TMP_DIR / "twitter_log.json"
TWITTER_PLAN_PATH = TMP_DIR / "twitter_plan.json"
TWITTER_TRENDS_PATH = TMP_DIR / "twitter_trends.json"
TWITTER_ANALYTICS_PATH = TMP_DIR / "twitter_analytics.json"
TWITTER_MENTION_STATE_PATH = TMP_DIR / "twitter_mention_state.json"
TWITTER_REPLY_LOG_PATH = TMP_DIR / "twitter_reply_log.json"

# ── Required env keys ───────────────────────────────────────────────────
TWITTER_REQUIRED_KEYS = [
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
]


# ── Rate Limiter ─────────────────────────────────────────────────────────
class RateLimiter:
    """Token-bucket style rate limiter for Twitter API calls."""

    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: list[float] = []

    def wait_if_needed(self):
        """Block until a call is allowed."""
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.period]
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0]) + 1
            logger.warning(f"Rate limit reached. Sleeping {sleep_time:.0f}s...")
            time.sleep(sleep_time)
        self.calls.append(time.time())


# ── Budget Tracker ───────────────────────────────────────────────────────
class BudgetTracker:
    """Track daily/monthly tweet budget against Free tier limits."""

    def __init__(self, log_path: Path = TWITTER_LOG_PATH):
        self.log_path = log_path

    def get_counts(self) -> dict:
        """Return today's and this month's tweet counts."""
        if not self.log_path.exists():
            return {
                "today": 0,
                "month": 0,
                "remaining_today": DAILY_TWEET_LIMIT,
                "remaining_month": MONTHLY_TWEET_LIMIT,
            }

        with open(self.log_path, "r", encoding="utf-8") as f:
            log = json.load(f)

        today_str = date.today().isoformat()
        month_str = today_str[:7]  # "2026-02"
        tweets = log.get("tweets", [])

        today_count = sum(
            1 for t in tweets
            if t.get("posted_at", "").startswith(today_str)
            and t.get("status") == "published"
        )
        month_count = sum(
            1 for t in tweets
            if t.get("posted_at", "").startswith(month_str)
            and t.get("status") == "published"
        )

        return {
            "today": today_count,
            "month": month_count,
            "remaining_today": max(0, DAILY_TWEET_LIMIT - today_count),
            "remaining_month": max(0, MONTHLY_TWEET_LIMIT - month_count),
        }

    def can_post(self, count: int = 1) -> bool:
        """Check if we can post `count` more tweets."""
        counts = self.get_counts()
        return (
            counts["remaining_today"] >= count
            and counts["remaining_month"] >= count
        )

    def print_budget(self):
        """Print budget status to stdout."""
        c = self.get_counts()
        print(f"=== Twitter Budget (Free Tier) ===")
        print(f"Today:  {c['today']}/{DAILY_TWEET_LIMIT}  (remaining: {c['remaining_today']})")
        print(f"Month:  {c['month']}/{MONTHLY_TWEET_LIMIT}  (remaining: {c['remaining_month']})")
        if c["remaining_month"] < 100:
            print("⚠️  WARNING: Monthly budget running low!")


# ── Client Creation ──────────────────────────────────────────────────────
def check_credentials() -> list[str]:
    """Check for missing Twitter credentials. Returns list of missing keys."""
    missing = [k for k in TWITTER_REQUIRED_KEYS if not os.getenv(k)]
    return missing


def create_twitter_clients():
    """Create both Tweepy v2 Client and v1.1 API.

    Returns:
        tuple: (tweepy.Client, tweepy.API)

    Raises:
        EnvironmentError: if required credentials are missing
    """
    import tweepy

    missing = check_credentials()
    if missing:
        raise EnvironmentError(
            f"Missing Twitter credentials in .env: {', '.join(missing)}\n"
            f"See workflows/twitter_setup_guide.md for setup instructions."
        )

    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

    # v2 Client (tweet creation, mentions, etc.)
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    # v1.1 API (media upload)
    auth = tweepy.OAuth1UserHandler(
        api_key, api_secret, access_token, access_token_secret
    )
    api_v1 = tweepy.API(auth)

    return client, api_v1


# ── Logging ──────────────────────────────────────────────────────────────
def append_to_log(log_path: Path, entry: dict) -> None:
    """Append an entry to a JSON log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = {"tweets": []}
    log["tweets"].append(entry)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def update_plan_status(plan_path: Path, post_id: str, status: str) -> None:
    """Update status of a post in the content plan."""
    if not plan_path.exists():
        return
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    for post in plan.get("posts", []):
        if post.get("post_id") == post_id:
            post["status"] = status
            break
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


# ── .env update ──────────────────────────────────────────────────────────
def update_env_file(key: str, new_value: str) -> None:
    """Update a key in the .env file. Reuses pattern from refresh_ig_token.py."""
    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{key}={new_value}", content)
    else:
        content += f"\n{key}={new_value}\n"
    env_path.write_text(content, encoding="utf-8")
    logger.info(f"Updated {key} in .env")


# ── Tweet validation ─────────────────────────────────────────────────────
def count_weighted_chars(text: str) -> int:
    """Count Twitter weighted characters.

    Twitter rules (from twitter-text library config):
    - U+0000–U+10FF: weight 1 (Latin, basic symbols)
    - U+1100–U+10FFFF: weight 2 (CJK, Hangul, emojis, etc.)
    - URLs are normalized to 23 chars (not handled here)
    """
    weight = 0
    for ch in text:
        if ord(ch) >= 0x1100:
            weight += 2
        else:
            weight += 1
    return weight


def is_test_or_spam(text: str) -> tuple[bool, str]:
    """Detect test/spam/debug content that should NEVER be posted to production.

    Returns:
        tuple: (is_spam, reason)
    """
    import re
    clean = text.strip()

    # Block: single character repeated (e.g. "AAAAAA", "ああああ", "テストテスト...")
    if len(clean) >= 10:
        # Check if text is just 1-2 unique chars repeated
        unique_chars = set(clean.replace(" ", "").replace("\n", ""))
        if len(unique_chars) <= 2:
            return True, f"Repetitive content (only {len(unique_chars)} unique chars)"

    # Block: very short text (< 15 raw chars, likely test)
    no_space = clean.replace(" ", "").replace("\n", "")
    if len(no_space) < 15 and not any(tag in clean for tag in ["#", "@", "http"]):
        return True, f"Too short to be a real tweet ({len(no_space)} chars without spaces)"

    # Block: common test patterns
    test_patterns = [
        r'^テスト[\s\nテスト]*',             # starts with テスト repeated
        r'^test[\s\ntest]*$',              # only "test" repeated
        r'^[Aa]+\s*#?\d*$',               # "AAAA..." with optional number
        r'^[あ]+\s*$',                     # "ああああ..."
        r'^ライン\d',                       # "ライン1\nライン2..."
        r'^\s*테스트\s*$',                  # Korean "test"
        r'^ストローマグ\s*$',               # bare product name only
    ]
    for pattern in test_patterns:
        if re.match(pattern, clean, re.IGNORECASE | re.DOTALL):
            return True, f"Test/debug content detected: matches '{pattern}'"

    # Block: extremely repetitive (same 2-4 char substring repeated 5+ times)
    for chunk_size in range(2, 5):
        if len(clean) >= chunk_size * 5:
            chunk = clean[:chunk_size]
            if chunk * 5 in clean:
                ratio = clean.count(chunk) / (len(clean) / chunk_size)
                if ratio > 0.7:
                    return True, f"Repetitive substring '{chunk}' detected ({ratio:.0%} of text)"

    return False, "OK"


def validate_tweet_text(text: str) -> tuple[bool, str]:
    """Validate tweet text using Twitter's weighted character counting.

    CJK/Hangul/emoji = 2 weighted chars each. Limit is 280 weighted.
    Also blocks test/spam content from being posted.

    Returns:
        tuple: (is_valid, message)
    """
    if not text:
        return False, "Tweet text is empty"

    # Safety: block test/spam content
    is_spam, spam_reason = is_test_or_spam(text)
    if is_spam:
        return False, f"BLOCKED: {spam_reason}. This looks like test content, not a real tweet."

    weighted = count_weighted_chars(text)
    raw = len(text)
    if weighted > 280:
        return False, f"Tweet too long: {weighted}/280 weighted ({raw} raw chars, over by {weighted - 280})"
    return True, f"OK: {weighted}/280 weighted ({raw} raw chars)"


def split_body_and_hashtags(text: str) -> tuple[str, list[str]]:
    """Split tweet text into body (no hashtags) and hashtag list.

    Hashtags are detected by '#' followed by non-space chars. Both leading and
    trailing/inline hashtags are extracted; the body is what remains after
    removing them, with whitespace normalized.

    Returns:
        tuple: (body_text, [hashtags])
    """
    import re
    if not text:
        return "", []
    tags = re.findall(r"#[^\s#]+", text)
    body = re.sub(r"#[^\s#]+", "", text)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, tags


def count_body_chars(text: str) -> int:
    """Count raw body characters excluding hashtags.

    Used to enforce the 60-80 char body rule from feedback_twitter_weekly_flow.md
    (rule: 본문 60~80자 + 해시태그로 280加重 맞춤).
    """
    body, _ = split_body_and_hashtags(text)
    return len(body)


def validate_body_length(text: str, min_chars: int = 60, max_chars: int = 80) -> tuple[bool, str]:
    """Validate that the tweet body (excluding hashtags) is within target range.

    Per feedback_twitter_weekly_flow.md: body should be 60-80 raw chars (not
    weighted), with hashtags filling the rest of the 280 weighted budget.

    Returns:
        tuple: (is_valid, message)
    """
    body_len = count_body_chars(text)
    if body_len < min_chars:
        return False, f"Body too short: {body_len} chars (min {min_chars})"
    if body_len > max_chars:
        return False, f"Body too long: {body_len} chars (max {max_chars})"
    return True, f"OK: body {body_len} chars (target {min_chars}-{max_chars})"
