"""
WAT Tool: Scrape competitor Instagram profiles via public viewers (FREE).
Uses requests + BeautifulSoup to scrape picuki.com (no login, no API cost).
Downloads images locally so Claude can view them directly.
Output: .tmp/competitor_refs/<account>/ (images + metadata JSON)

Usage:
    python tools/scrape_ig_competitor.py bboxforkidsjapan              # single account
    python tools/scrape_ig_competitor.py bboxforkidsjapan pigeon_official.jp  # multiple
    python tools/scrape_ig_competitor.py bboxforkidsjapan --max 5      # limit posts
    python tools/scrape_ig_competitor.py --accounts-file accounts.txt  # from file
    python tools/scrape_ig_competitor.py bboxforkidsjapan --dry-run    # preview only
"""

import os
import re
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "competitor_refs"
RATE_LIMIT_DELAY = 2  # seconds between requests
MAX_POSTS_DEFAULT = 12
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

# Competitor accounts to track
DEFAULT_ACCOUNTS = [
    "bboxforkidsjapan",
    "pigeon_official.jp",
    "richell_official",
    "thermos_k.k",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_profile(account: str, max_posts: int) -> dict:
    """Scrape an Instagram profile via picnob.com (picuki.com is dead since 2026-03)."""
    url = f"https://www.picnob.com/profile/{account}/"
    logger.info(f"Scraping {account} from {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {account}: {e}")
        return {"account": account, "error": str(e), "posts": []}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract profile info
    profile = _extract_profile_info(soup, account)

    # Extract posts
    posts = _extract_posts(soup, account, max_posts)
    profile["posts"] = posts
    profile["scraped_at"] = datetime.now().isoformat()

    logger.info(f"  Found {len(posts)} posts for @{account}")
    return profile


def _extract_profile_info(soup: BeautifulSoup, account: str) -> dict:
    """Extract profile-level info (followers, bio, etc.)."""
    info = {"account": account}

    # Profile name (picnob selectors)
    name_el = soup.select_one(".profile-name-bottom, .info h1, .user-name")
    if name_el:
        info["display_name"] = name_el.get_text(strip=True)

    # Stats (posts, followers, following) — picnob uses .num or .count
    stat_els = soup.select(".total_count, .num, .count")
    labels = ["posts_count", "followers", "following"]
    for i, el in enumerate(stat_els):
        if i < len(labels):
            text = el.get_text(strip=True).replace(",", "")
            info[labels[i]] = text

    # Bio
    bio_el = soup.select_one(".profile-description, .biography, .user-bio")
    if bio_el:
        info["bio"] = bio_el.get_text(strip=True)

    return info


def _extract_posts(soup: BeautifulSoup, account: str, max_posts: int) -> list[dict]:
    """Extract post data from profile page."""
    posts = []
    # picnob uses .box-photo or .post-item or div[class*="post"]
    post_items = soup.select(".box-photo, .post-item, .photo-item, article")

    for item in post_items[:max_posts]:
        post = {}

        # Image URL
        img_el = item.select_one("img")
        if img_el:
            post["image_url"] = img_el.get("src", "") or img_el.get("data-src", "") or img_el.get("data-lazy-src", "")

        # Post link
        link_el = item.select_one("a")
        if link_el:
            href = link_el.get("href", "")
            post["post_url"] = urljoin("https://www.picnob.com", href) if href else ""

        # Caption / description
        desc_el = item.select_one(".photo-description, .desc, .caption, p")
        if desc_el:
            post["caption"] = desc_el.get_text(strip=True)[:500]
            post["hashtags"] = re.findall(r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+",
                                          desc_el.get_text())

        # Engagement
        likes_el = item.select_one(".likes_count, .like-count, .likes, [class*='like']")
        if likes_el:
            likes_text = likes_el.get_text(strip=True).replace(",", "")
            post["likes"] = likes_text

        comments_el = item.select_one(".comments_count, .comment-count, .comments, [class*='comment']")
        if comments_el:
            comments_text = comments_el.get_text(strip=True).replace(",", "")
            post["comments"] = comments_text

        # Video indicator
        video_el = item.select_one(".video-icon, .icon-video, [class*='video']")
        post["is_video"] = video_el is not None

        if post.get("image_url"):
            posts.append(post)

    return posts


# ── Image download ────────────────────────────────────────────────────────────

def download_images(profile_data: dict, output_dir: Path) -> list[str]:
    """Download post images to local folder. Returns list of saved paths."""
    account = profile_data["account"]
    account_dir = output_dir / account
    account_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for i, post in enumerate(profile_data.get("posts", [])):
        img_url = post.get("image_url", "")
        if not img_url or not img_url.startswith("http"):
            continue

        filename = f"{account}_{i+1:03d}.jpg"
        filepath = account_dir / filename

        try:
            resp = requests.get(img_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            post["local_image"] = str(filepath)
            saved_paths.append(str(filepath))
            logger.info(f"  Saved {filename}")
        except requests.RequestException as e:
            logger.warning(f"  Failed to download image {i+1}: {e}")

        time.sleep(0.5)  # polite delay

    return saved_paths


# ── Output ────────────────────────────────────────────────────────────────────

def save_metadata(profile_data: dict, output_dir: Path) -> Path:
    """Save profile + post metadata as JSON."""
    account = profile_data["account"]
    account_dir = output_dir / account
    account_dir.mkdir(parents=True, exist_ok=True)

    json_path = account_dir / "metadata.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

    logger.info(f"  Metadata saved -> {json_path}")
    return json_path


def save_summary(all_profiles: list[dict], output_dir: Path) -> Path:
    """Save a combined summary for quick reference."""
    summary = {
        "scraped_at": datetime.now().isoformat(),
        "accounts": [],
    }

    for profile in all_profiles:
        account_summary = {
            "account": profile.get("account"),
            "display_name": profile.get("display_name", ""),
            "followers": profile.get("followers", ""),
            "posts_scraped": len(profile.get("posts", [])),
            "top_posts": [],
        }

        # Sort posts by likes (descending)
        posts = profile.get("posts", [])
        for post in sorted(posts, key=lambda p: _parse_likes(p.get("likes", "0")), reverse=True)[:3]:
            account_summary["top_posts"].append({
                "likes": post.get("likes", ""),
                "caption": (post.get("caption", "") or "")[:100],
                "hashtags": post.get("hashtags", [])[:5],
                "is_video": post.get("is_video", False),
                "local_image": post.get("local_image", ""),
            })

        summary["accounts"].append(account_summary)

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"Summary saved -> {summary_path}")
    return summary_path


def _parse_likes(likes_str: str) -> int:
    """Parse likes string to int for sorting."""
    cleaned = re.sub(r"[^\d]", "", str(likes_str))
    return int(cleaned) if cleaned else 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape competitor Instagram profiles (free)")
    parser.add_argument("accounts", nargs="*", help="Instagram account handles to scrape")
    parser.add_argument("--accounts-file", type=str, help="File with account handles (one per line)")
    parser.add_argument("--max", type=int, default=MAX_POSTS_DEFAULT,
                        help=f"Max posts per account (default {MAX_POSTS_DEFAULT})")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--no-images", action="store_true", help="Skip image download")
    parser.add_argument("--dry-run", action="store_true", help="Show URLs without scraping")
    args = parser.parse_args()

    # Collect accounts
    accounts = list(args.accounts)
    if args.accounts_file:
        with open(args.accounts_file) as f:
            accounts.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))
    if not accounts:
        accounts = DEFAULT_ACCOUNTS
        logger.info(f"No accounts specified, using defaults: {accounts}")

    output_dir = Path(args.output)

    if args.dry_run:
        print("\nWould scrape these profiles:")
        for acc in accounts:
            print(f"  https://www.picnob.com/profile/{acc}/")
        print(f"\nMax posts per account: {args.max}")
        print(f"Output dir: {output_dir}")
        print(f"Download images: {not args.no_images}")
        return

    # Scrape each account
    all_profiles = []
    for i, account in enumerate(accounts):
        profile = scrape_profile(account, args.max)

        if not profile.get("error"):
            save_metadata(profile, output_dir)

            if not args.no_images:
                saved = download_images(profile, output_dir)
                logger.info(f"  Downloaded {len(saved)} images for @{account}")

        all_profiles.append(profile)

        if i < len(accounts) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    # Save combined summary
    save_summary(all_profiles, output_dir)

    # Print results
    print(f"\nDone. Scraped {len(accounts)} accounts -> {output_dir}")
    for p in all_profiles:
        status = f"{len(p.get('posts', []))} posts" if not p.get("error") else f"ERROR: {p['error']}"
        print(f"  @{p['account']}: {status}")


if __name__ == "__main__":
    main()
