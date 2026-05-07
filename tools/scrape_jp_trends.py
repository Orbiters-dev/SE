"""
WAT Tool: Scrape Japanese parenting trends from social media and communities.
Approach: Firecrawl markdown scraping + regex extraction (fast, no LLM).
Sources: Twitter/X hashtags, Instagram hashtags, ママスタ, アメブロ
Output: .tmp/jp_trends_raw.json

Usage:
    python tools/scrape_jp_trends.py                    # scrape all sources
    python tools/scrape_jp_trends.py --source twitter   # single source
    python tools/scrape_jp_trends.py --source mamasta   # single source
    python tools/scrape_jp_trends.py --max-pages 2      # limit pages per source
    python tools/scrape_jp_trends.py --dry-run           # show URLs only
"""

import os
import re
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from firecrawl import FirecrawlApp

OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "jp_trends_raw.json"
RATE_LIMIT_DELAY = 3  # seconds between requests (conservative for JP sites)

# Japanese parenting hashtags for each platform
TWITTER_HASHTAGS = ["育児", "ママ", "子育て", "赤ちゃん", "ベビー用品", "育児グッズ"]
INSTAGRAM_HASHTAGS = ["育児ママ", "子育てグラム", "ベビー用品レビュー", "赤ちゃんのいる生活", "育児記録"]

# Source URL templates
SOURCES = {
    "twitter": {
        "name": "Twitter/X",
        "urls": [
            f"https://nitter.poast.org/search?f=tweets&q=%23{quote(tag)}&since=&until=&near="
            for tag in TWITTER_HASHTAGS
        ],
        "fallback_urls": [
            f"https://xcancel.com/search?q=%23{quote(tag)}"
            for tag in TWITTER_HASHTAGS
        ],
    },
    "mamasta": {
        "name": "ママスタ",
        "urls": [
            "https://mamastar.jp/bbs/ranking",
            "https://mamastar.jp/bbs/search?q=%E8%82%B2%E5%85%90",  # 育児
            "https://mamastar.jp/bbs/search?q=%E3%83%99%E3%83%93%E3%83%BC%E7%94%A8%E5%93%81",  # ベビー用品
        ],
    },
    "ameblo": {
        "name": "アメブロ",
        "urls": [
            "https://blogger.ameba.jp/genres/baby",
            "https://blogger.ameba.jp/genres/kids",
            "https://ranking.ameba.jp/gr_baby",
        ],
    },
    "instagram": {
        "name": "Instagram",
        "urls": [
            f"https://www.picuki.com/tag/{quote(tag)}"
            for tag in INSTAGRAM_HASHTAGS
        ],
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Parsing helpers ──────────────────────────────────────────────────────────

def extract_items_from_markdown(markdown: str, source: str, url: str) -> list[dict]:
    """Extract trend items from scraped markdown content."""
    items = []

    if source == "twitter":
        items = _parse_twitter(markdown, url)
    elif source == "mamasta":
        items = _parse_mamasta(markdown, url)
    elif source == "ameblo":
        items = _parse_ameblo(markdown, url)
    elif source == "instagram":
        items = _parse_instagram(markdown, url)

    return items


def _parse_twitter(markdown: str, url: str) -> list[dict]:
    """Parse tweets from Nitter/xcancel markdown."""
    items = []
    # Split by tweet boundaries — look for username patterns
    tweet_blocks = re.split(r'\n(?=[@\[])', markdown)

    for block in tweet_blocks:
        if len(block.strip()) < 20:
            continue

        # Extract text content (skip very short blocks)
        content = _clean_text(block)
        if len(content) < 30:
            continue

        # Extract hashtags
        hashtags = re.findall(r'#(\w+)', block)
        jp_hashtags = [f"#{h}" for h in hashtags if _is_japanese(h)]

        # Extract URLs
        urls_found = re.findall(r'https?://[^\s\)]+', block)

        # Extract engagement signals
        engagement = _extract_engagement(block)

        items.append({
            "source": "twitter",
            "url": urls_found[0] if urls_found else url,
            "content_snippet": content[:500],
            "hashtags": jp_hashtags if jp_hashtags else [f"#{h}" for h in hashtags[:5]],
            "engagement_signals": engagement,
            "content_type": "image" if re.search(r'\!\[', block) else "text",
            "scraped_at": datetime.now().isoformat(),
        })

    return items


def _parse_mamasta(markdown: str, url: str) -> list[dict]:
    """Parse ママスタ community posts from markdown."""
    items = []

    # Look for topic/thread patterns: links with Japanese titles
    link_pattern = re.compile(r'\[([^\]]{10,})\]\((https?://[^\)]+mamastar[^\)]+)\)')
    matches = link_pattern.findall(markdown)

    for title, link_url in matches:
        if _is_navigation(title):
            continue

        items.append({
            "source": "mamasta",
            "url": link_url,
            "content_snippet": title.strip(),
            "hashtags": _infer_hashtags(title),
            "engagement_signals": "",
            "content_type": "text",
            "scraped_at": datetime.now().isoformat(),
        })

    # Also capture standalone headings with Japanese text
    heading_pattern = re.compile(r'^#{1,3}\s+(.{10,})$', re.MULTILINE)
    for match in heading_pattern.finditer(markdown):
        title = match.group(1).strip()
        if _is_navigation(title) or any(item["content_snippet"] == title for item in items):
            continue
        if _has_japanese(title):
            items.append({
                "source": "mamasta",
                "url": url,
                "content_snippet": title,
                "hashtags": _infer_hashtags(title),
                "engagement_signals": "",
                "content_type": "text",
                "scraped_at": datetime.now().isoformat(),
            })

    return items


def _parse_ameblo(markdown: str, url: str) -> list[dict]:
    """Parse アメブロ blog ranking/listing from markdown."""
    items = []

    # Ameblo posts typically have title links
    link_pattern = re.compile(r'\[([^\]]{5,})\]\((https?://ameblo\.jp/[^\)]+)\)')
    matches = link_pattern.findall(markdown)

    for title, link_url in matches:
        if _is_navigation(title):
            continue

        items.append({
            "source": "ameblo",
            "url": link_url,
            "content_snippet": title.strip(),
            "hashtags": _infer_hashtags(title),
            "engagement_signals": "",
            "content_type": "text",
            "scraped_at": datetime.now().isoformat(),
        })

    # Also capture ranking entries
    ranking_pattern = re.compile(r'(\d+)\s*位?\s*[\.:\-]?\s*(.{5,})', re.MULTILINE)
    for match in ranking_pattern.finditer(markdown):
        rank = match.group(1)
        title = match.group(2).strip()
        if int(rank) > 50 or not _has_japanese(title) or _is_navigation(title):
            continue
        if any(item["content_snippet"] == title for item in items):
            continue

        items.append({
            "source": "ameblo",
            "url": url,
            "content_snippet": title,
            "hashtags": _infer_hashtags(title),
            "engagement_signals": f"rank:{rank}",
            "content_type": "text",
            "scraped_at": datetime.now().isoformat(),
        })

    return items


def _parse_instagram(markdown: str, url: str) -> list[dict]:
    """Parse Instagram hashtag explore pages from picuki."""
    items = []

    # Picuki shows post cards with descriptions and image links
    # Look for image links and surrounding text
    img_pattern = re.compile(r'\!\[([^\]]*)\]\((https?://[^\)]+)\)')
    img_matches = img_pattern.findall(markdown)

    # Also look for post description text blocks
    desc_pattern = re.compile(r'([^\n]{20,}(?:#\w+[^\n]*))', re.MULTILINE)
    descriptions = desc_pattern.findall(markdown)

    for desc in descriptions:
        hashtags = re.findall(r'#(\w+)', desc)
        jp_hashtags = [f"#{h}" for h in hashtags if _is_japanese(h)]
        if not jp_hashtags and not _has_japanese(desc):
            continue

        items.append({
            "source": "instagram",
            "url": url,
            "content_snippet": _clean_text(desc)[:500],
            "hashtags": jp_hashtags[:10],
            "engagement_signals": "",
            "content_type": "image",
            "scraped_at": datetime.now().isoformat(),
        })

    # If no descriptions found, extract from image alt texts
    if not items and img_matches:
        for alt_text, img_url in img_matches[:20]:
            if len(alt_text) < 10:
                continue
            items.append({
                "source": "instagram",
                "url": url,
                "content_snippet": alt_text.strip()[:500],
                "hashtags": _infer_hashtags(alt_text),
                "engagement_signals": "",
                "content_type": "image",
                "scraped_at": datetime.now().isoformat(),
            })

    return items


# ── Utility helpers ──────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Clean markdown artifacts from text."""
    text = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', text)  # remove links, keep text
    text = re.sub(r'\!\[[^\]]*\]\([^\)]+\)', '', text)      # remove images
    text = re.sub(r'[#*_`>]+', '', text)                     # remove markdown formatting
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_japanese(text: str) -> bool:
    """Check if text contains Japanese characters."""
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))


def _has_japanese(text: str) -> bool:
    """Alias for _is_japanese."""
    return _is_japanese(text)


def _is_navigation(text: str) -> bool:
    """Check if text is a navigation/UI element rather than content."""
    nav_patterns = [
        r'^(ホーム|ログイン|登録|メニュー|検索|設定|プロフィール|次へ|前へ|もっと見る)$',
        r'^(Home|Login|Sign|Menu|Search|Settings|Profile|Next|Prev|More)$',
        r'^[\d\s\.\-]+$',  # pure numbers
        r'cookie|privacy|terms|copyright',
    ]
    for pattern in nav_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return len(text.strip()) < 5


def _infer_hashtags(text: str) -> list[str]:
    """Infer relevant hashtags from content text."""
    keyword_to_hashtag = {
        "育児": "#育児",
        "子育て": "#子育て",
        "赤ちゃん": "#赤ちゃん",
        "ベビー": "#ベビー用品",
        "ママ": "#ママ",
        "離乳食": "#離乳食",
        "夜泣き": "#夜泣き",
        "おむつ": "#おむつ",
        "抱っこ": "#抱っこ紐",
        "ミルク": "#ミルク育児",
        "保育園": "#保育園",
        "幼稚園": "#幼稚園",
    }
    found = []
    for keyword, hashtag in keyword_to_hashtag.items():
        if keyword in text and hashtag not in found:
            found.append(hashtag)
    return found if found else ["#育児"]


def _extract_engagement(text: str) -> str:
    """Extract engagement metrics from text."""
    metrics = []
    like_match = re.search(r'(\d[\d,]*)\s*(?:likes?|いいね|♡|❤)', text, re.IGNORECASE)
    rt_match = re.search(r'(\d[\d,]*)\s*(?:retweets?|RT|リツイート)', text, re.IGNORECASE)
    reply_match = re.search(r'(\d[\d,]*)\s*(?:replies|返信|コメント)', text, re.IGNORECASE)

    if like_match:
        metrics.append(f"likes:{like_match.group(1)}")
    if rt_match:
        metrics.append(f"rt:{rt_match.group(1)}")
    if reply_match:
        metrics.append(f"replies:{reply_match.group(1)}")

    return ", ".join(metrics)


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_page(app: FirecrawlApp, url: str, retries: int = 3) -> str:
    """Scrape a page and return its markdown content."""
    for attempt in range(retries):
        try:
            result = app.scrape(
                url,
                formats=['markdown'],
                wait_for=3000,
                only_main_content=True,
                timeout=60000,
            )
            md = ""
            if hasattr(result, 'markdown'):
                md = result.markdown or ""
            elif isinstance(result, dict):
                md = result.get('markdown', '')
            logger.info(f"  -> {len(md)} chars from {url[:80]}")
            return md
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} for {url[:80]}: {e}")
            if attempt < retries - 1:
                time.sleep(RATE_LIMIT_DELAY * (attempt + 1))

    logger.error(f"All retries failed for {url[:80]}")
    return ""


def scrape_source(app: FirecrawlApp, source_key: str, max_pages: int) -> list[dict]:
    """Scrape a single source and return extracted items."""
    source = SOURCES[source_key]
    urls = source["urls"][:max_pages]
    all_items = []

    logger.info(f"Scraping {source['name']} ({len(urls)} URLs)")

    for i, url in enumerate(urls):
        md = scrape_page(app, url)
        if md:
            items = extract_items_from_markdown(md, source_key, url)
            logger.info(f"  Extracted {len(items)} items from page {i + 1}")
            all_items.extend(items)
        else:
            # Try fallback URLs if available
            fallbacks = source.get("fallback_urls", [])
            if i < len(fallbacks):
                logger.info(f"  Trying fallback URL...")
                md = scrape_page(app, fallbacks[i])
                if md:
                    items = extract_items_from_markdown(md, source_key, fallbacks[i])
                    logger.info(f"  Extracted {len(items)} items from fallback")
                    all_items.extend(items)

        if i < len(urls) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    return all_items


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove duplicate items by content snippet."""
    seen = set()
    unique = []
    for item in items:
        key = item.get("content_snippet", "")[:100]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def save_output(items: list[dict], sources_scraped: list[str], output_path: Path) -> None:
    """Save scraped items to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scraped_at": datetime.now().isoformat(),
        "sources_scraped": sources_scraped,
        "total_items": len(items),
        "items": items,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(items)} items -> {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape Japanese parenting trends")
    parser.add_argument("--source", type=str, choices=list(SOURCES.keys()),
                        help="Scrape a single source only")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Max pages/URLs per source (default 5)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="Show URLs to scrape without making requests")
    args = parser.parse_args()

    if args.dry_run:
        sources = [args.source] if args.source else list(SOURCES.keys())
        for src in sources:
            print(f"\n{SOURCES[src]['name']}:")
            for url in SOURCES[src]["urls"][:args.max_pages]:
                print(f"  {url}")
            fallbacks = SOURCES[src].get("fallback_urls", [])
            if fallbacks:
                print(f"  Fallbacks:")
                for url in fallbacks[:args.max_pages]:
                    print(f"    {url}")
        return

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise EnvironmentError("FIRECRAWL_API_KEY not found. Check .env file.")

    app = FirecrawlApp(api_key=api_key)

    sources_to_scrape = [args.source] if args.source else list(SOURCES.keys())
    all_items = []

    for source_key in sources_to_scrape:
        items = scrape_source(app, source_key, args.max_pages)
        all_items.extend(items)
        logger.info(f"{SOURCES[source_key]['name']}: {len(items)} items")

        if source_key != sources_to_scrape[-1]:
            time.sleep(RATE_LIMIT_DELAY)

    unique_items = deduplicate(all_items)
    logger.info(f"Total: {len(all_items)} | Unique: {len(unique_items)}")

    save_output(unique_items, sources_to_scrape, Path(args.output))
    print(f"\nDone. {len(unique_items)} trend items -> {args.output}")


if __name__ == "__main__":
    main()
