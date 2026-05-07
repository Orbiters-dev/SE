"""
WAT Tool: Scrape Twitter/X trending topics and parenting hashtags for Japan.
Uses Firecrawl for web scraping (no API read access needed on Free tier).
Supplements the existing scrape_jp_trends.py with Twitter-specific sources.

Output: .tmp/twitter_trends.json

Usage:
    py -3 tools/twitter_trends.py                        # scrape all sources
    py -3 tools/twitter_trends.py --hashtags-only        # parenting hashtags only
    py -3 tools/twitter_trends.py --trending-only        # Japan trending topics only
    py -3 tools/twitter_trends.py --merge                # merge into jp_trends_raw.json
    py -3 tools/twitter_trends.py --dry-run              # show URLs only
"""

import os
import sys
import re
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import requests
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

from twitter_utils import TWITTER_TRENDS_PATH, TMP_DIR

FIRECRAWL_API = "https://api.firecrawl.dev/v1/scrape"
RATE_LIMIT_DELAY = 3  # seconds between requests

# ── Sources ──────────────────────────────────────────────────────────────

TRENDING_SOURCES = [
    {
        "name": "trends24_japan",
        "url": "https://trends24.in/japan/",
        "description": "Japan trending topics (real-time)",
    },
    {
        "name": "twittrend",
        "url": "https://twittrend.jp/",
        "description": "Japanese Twitter trend rankings",
    },
]

HASHTAG_SOURCES = [
    {
        "name": "twitter_ikuji",
        "url": "https://xcancel.com/search?q=%23育児&f=tweets",
        "description": "#育児 (parenting)",
    },
    {
        "name": "twitter_kosodate",
        "url": "https://xcancel.com/search?q=%23子育て&f=tweets",
        "description": "#子育て (childcare)",
    },
    {
        "name": "twitter_mama",
        "url": "https://xcancel.com/search?q=%23ママ+赤ちゃん&f=tweets",
        "description": "#ママ 赤ちゃん (mom + baby)",
    },
    {
        "name": "twitter_straw_mag",
        "url": "https://xcancel.com/search?q=%23ストローマグ&f=tweets",
        "description": "#ストローマグ (straw mug)",
    },
    {
        "name": "twitter_ikuji_goods",
        "url": "https://xcancel.com/search?q=%23育児グッズ+おすすめ&f=tweets",
        "description": "#育児グッズ おすすめ (baby goods recommend)",
    },
]

PARENTING_ACCOUNTS = [
    {
        "name": "mamasta_select",
        "url": "https://xcancel.com/mamastar_select",
        "description": "ママスタセレクト (parenting media)",
    },
]


# ── Scraping ─────────────────────────────────────────────────────────────

def scrape_page(url: str, retries: int = 3) -> str | None:
    """Scrape a page via Firecrawl and return markdown."""
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    if not firecrawl_key:
        raise EnvironmentError("FIRECRAWL_API_KEY not found in .env")

    for attempt in range(retries):
        try:
            resp = requests.post(
                FIRECRAWL_API,
                headers={"Authorization": f"Bearer {firecrawl_key}"},
                json={"url": url, "formats": ["markdown"]},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                md = data.get("data", {}).get("markdown", "")
                if md:
                    logger.info(f"Scraped {url} ({len(md)} chars)")
                    return md
                logger.warning(f"Empty markdown from {url}")
            else:
                logger.warning(f"Scrape {url} returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Scrape attempt {attempt + 1}/{retries} failed: {e}")

        if attempt < retries - 1:
            time.sleep(RATE_LIMIT_DELAY * (attempt + 1))

    return None


# ── Parsers ──────────────────────────────────────────────────────────────

def parse_trending_topics(md: str, source_name: str) -> list[dict]:
    """Extract trending topics from trends24/twittrend markdown."""
    items = []

    # Match hashtag-like patterns and trending keywords
    # trends24 format: often lists as "1. #keyword" or just "#keyword"
    hashtag_pattern = re.compile(r"#([\w\u3000-\u9fff\uff00-\uffef]+)")
    matches = hashtag_pattern.findall(md)

    seen = set()
    for tag in matches:
        if tag not in seen and len(tag) > 1:
            seen.add(tag)
            items.append({
                "source": source_name,
                "content_snippet": f"#{tag}",
                "hashtags": [f"#{tag}"],
                "content_type": "trending_topic",
                "scraped_at": datetime.now().isoformat(),
            })

    # Also extract plain text trending items (lines that look like ranked items)
    for line in md.split("\n"):
        line = line.strip()
        # Match numbered items: "1. keyword" or "・keyword"
        rank_match = re.match(r"(?:\d+[\.\)]\s*|[・▸►]\s*)(.{2,30})$", line)
        if rank_match:
            topic = rank_match.group(1).strip()
            if topic not in seen and not topic.startswith("http"):
                seen.add(topic)
                items.append({
                    "source": source_name,
                    "content_snippet": topic,
                    "hashtags": [],
                    "content_type": "trending_topic",
                    "scraped_at": datetime.now().isoformat(),
                })

    return items


def parse_twitter_posts(md: str, source_name: str) -> list[dict]:
    """Extract tweet content from nitter/xcancel markdown."""
    items = []
    seen_snippets = set()

    # Split by common tweet separators
    blocks = re.split(r"\n---\n|\n\n\n+", md)

    for block in blocks:
        block = block.strip()
        if len(block) < 20:
            continue

        # Extract text content (remove URLs, usernames at start)
        text = re.sub(r"https?://\S+", "", block)
        text = re.sub(r"^@\w+\s*", "", text, flags=re.MULTILINE)
        text = text.strip()

        if len(text) < 15:
            continue

        # Dedup by first 80 chars
        key = text[:80]
        if key in seen_snippets:
            continue
        seen_snippets.add(key)

        # Extract hashtags
        hashtags = re.findall(r"#([\w\u3000-\u9fff\uff00-\uffef]+)", block)
        hashtags = [f"#{h}" for h in hashtags[:5]]

        # Extract engagement signals
        engagement = _extract_engagement(block)

        items.append({
            "source": source_name,
            "content_snippet": text[:200],
            "hashtags": hashtags,
            "engagement_signals": engagement,
            "content_type": "tweet",
            "scraped_at": datetime.now().isoformat(),
        })

    return items


def _extract_engagement(text: str) -> str:
    """Extract engagement metrics from text."""
    signals = []
    patterns = [
        (r"(\d[\d,]*)\s*(?:likes?|いいね)", "likes"),
        (r"(\d[\d,]*)\s*(?:retweets?|RT|リツイート)", "rt"),
        (r"(\d[\d,]*)\s*(?:replies?|返信)", "replies"),
        (r"(\d[\d,]*)\s*(?:quotes?|引用)", "quotes"),
    ]
    for pat, label in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            signals.append(f"{label}:{match.group(1)}")
    return ", ".join(signals) if signals else ""


def _is_japanese(text: str) -> bool:
    """Check if text contains Japanese characters."""
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", text))


# ── Main Pipeline ────────────────────────────────────────────────────────

def scrape_all(
    include_trending: bool = True,
    include_hashtags: bool = True,
    include_accounts: bool = True,
) -> dict:
    """Scrape all Twitter sources."""
    all_items = []
    sources_scraped = []

    sources = []
    if include_trending:
        sources.extend(TRENDING_SOURCES)
    if include_hashtags:
        sources.extend(HASHTAG_SOURCES)
    if include_accounts:
        sources.extend(PARENTING_ACCOUNTS)

    for source in sources:
        logger.info(f"Scraping: {source['description']} ({source['url']})")
        md = scrape_page(source["url"])
        if not md:
            continue

        sources_scraped.append(source["name"])

        if source["name"].startswith("trends"):
            items = parse_trending_topics(md, source["name"])
        else:
            items = parse_twitter_posts(md, source["name"])

        all_items.extend(items)
        logger.info(f"  → {len(items)} items extracted")
        time.sleep(RATE_LIMIT_DELAY)

    # Deduplicate by content_snippet
    seen = set()
    deduped = []
    for item in all_items:
        key = item["content_snippet"][:80]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    result = {
        "scraped_at": datetime.now().isoformat(),
        "sources_scraped": sources_scraped,
        "total_items": len(deduped),
        "items": deduped,
    }

    return result


def save_trends(data: dict, path: Path):
    """Save trends to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {data['total_items']} trends to {path}")


def merge_with_existing(new_data: dict):
    """Merge new Twitter trends into existing jp_trends_raw.json."""
    existing_path = TMP_DIR / "jp_trends_raw.json"
    if not existing_path.exists():
        logger.info("No existing jp_trends_raw.json, saving as new file")
        save_trends(new_data, existing_path)
        return

    with open(existing_path, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # Deduplicate
    existing_snippets = {item["content_snippet"][:80] for item in existing.get("items", [])}
    new_items = [
        item for item in new_data.get("items", [])
        if item["content_snippet"][:80] not in existing_snippets
    ]

    existing["items"].extend(new_items)
    existing["total_items"] = len(existing["items"])
    existing["sources_scraped"] = list(set(
        existing.get("sources_scraped", []) + new_data.get("sources_scraped", [])
    ))

    with open(existing_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"Merged {len(new_items)} new items into jp_trends_raw.json")


def main():
    parser = argparse.ArgumentParser(description="Scrape Twitter trends for Japan parenting")
    parser.add_argument("--hashtags-only", action="store_true", help="Hashtag trends only")
    parser.add_argument("--trending-only", action="store_true", help="Japan trending topics only")
    parser.add_argument("--merge", action="store_true", help="Merge into jp_trends_raw.json")
    parser.add_argument("--dry-run", action="store_true", help="Show URLs only")
    parser.add_argument("--output", type=str, default=str(TWITTER_TRENDS_PATH))
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] Would scrape these sources:")
        all_sources = TRENDING_SOURCES + HASHTAG_SOURCES + PARENTING_ACCOUNTS
        for s in all_sources:
            print(f"  {s['name']}: {s['url']}")
            print(f"    → {s['description']}")
        return

    include_trending = not args.hashtags_only
    include_hashtags = not args.trending_only

    data = scrape_all(
        include_trending=include_trending,
        include_hashtags=include_hashtags,
    )

    # Save
    output_path = Path(args.output)
    save_trends(data, output_path)

    if args.merge:
        merge_with_existing(data)

    # Summary
    print(f"\nScraped {data['total_items']} items from {len(data['sources_scraped'])} sources:")
    by_type = {}
    for item in data["items"]:
        ct = item.get("content_type", "unknown")
        by_type[ct] = by_type.get(ct, 0) + 1
    for ct, count in by_type.items():
        print(f"  {ct}: {count}")

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
