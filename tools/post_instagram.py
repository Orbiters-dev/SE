"""
WAT Tool: Post content to Instagram via Graph API.
Uploads images to Google Cloud Storage for public URL, then publishes via Instagram Graph API.
Supports single images and carousel posts.
Output: .tmp/posting_log.json

Usage:
    python tools/post_instagram.py                              # post next ready item
    python tools/post_instagram.py --post-id 20260219_001       # specific post
    python tools/post_instagram.py --dry-run                    # validate without posting
"""

import os
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from google.cloud import storage

PLAN_PATH = Path(__file__).parent.parent / ".tmp" / "content_plan.json"
IMAGES_DIR = Path(__file__).parent.parent / ".tmp" / "content_images"
LOG_PATH = Path(__file__).parent.parent / ".tmp" / "posting_log.json"

IG_API_BASE = "https://graph.facebook.com/v21.0"

# Polling config for Instagram container status
CONTAINER_POLL_INTERVAL = 5   # seconds
CONTAINER_POLL_TIMEOUT = 60   # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Google Cloud Storage Upload ──────────────────────────────────────────────

def upload_to_gcs(image_path: Path, bucket_name: str) -> str | None:
    """Upload an image to Google Cloud Storage and return the public URL."""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        # Use date-based path to organize uploads
        today = datetime.now().strftime("%Y/%m/%d")
        blob_name = f"instagram/{today}/{image_path.parent.name}/{image_path.name}"
        blob = bucket.blob(blob_name)

        blob.upload_from_filename(str(image_path), content_type="image/jpeg")
        blob.make_public()

        public_url = blob.public_url
        logger.info(f"  GCS upload OK: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"  GCS upload error: {e}")
        return None


# ── Instagram Graph API ──────────────────────────────────────────────────────

def create_media_container(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str = "",
    is_carousel_item: bool = False,
) -> str | None:
    """Create a single media container on Instagram."""
    url = f"{IG_API_BASE}/{ig_user_id}/media"
    params = {
        "image_url": image_url,
        "access_token": access_token,
    }

    if is_carousel_item:
        params["is_carousel_item"] = "true"
    else:
        params["caption"] = caption

    try:
        resp = requests.post(url, data=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        container_id = data.get("id")
        logger.info(f"  Container created: {container_id}")
        return container_id
    except Exception as e:
        logger.error(f"  Container creation failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  Response: {e.response.text}")
        return None


def create_carousel_container(
    ig_user_id: str,
    access_token: str,
    children_ids: list[str],
    caption: str,
) -> str | None:
    """Create a carousel container from child media items."""
    url = f"{IG_API_BASE}/{ig_user_id}/media"
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": access_token,
    }

    try:
        resp = requests.post(url, data=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        container_id = data.get("id")
        logger.info(f"  Carousel container created: {container_id}")
        return container_id
    except Exception as e:
        logger.error(f"  Carousel container creation failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  Response: {e.response.text}")
        return None


def check_container_status(container_id: str, access_token: str) -> str:
    """Check the status of a media container."""
    url = f"{IG_API_BASE}/{container_id}"
    params = {"fields": "status_code", "access_token": access_token}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("status_code", "UNKNOWN")
    except Exception as e:
        logger.error(f"  Status check failed: {e}")
        return "ERROR"


def wait_for_container(container_id: str, access_token: str) -> bool:
    """Poll container status until FINISHED or timeout."""
    elapsed = 0
    while elapsed < CONTAINER_POLL_TIMEOUT:
        status = check_container_status(container_id, access_token)
        if status == "FINISHED":
            return True
        if status == "ERROR":
            logger.error(f"  Container {container_id} has ERROR status")
            return False
        logger.info(f"  Container status: {status}, waiting...")
        time.sleep(CONTAINER_POLL_INTERVAL)
        elapsed += CONTAINER_POLL_INTERVAL

    logger.error(f"  Container {container_id} timed out after {CONTAINER_POLL_TIMEOUT}s")
    return False


def publish_container(ig_user_id: str, access_token: str, container_id: str) -> str | None:
    """Publish a media container to Instagram feed."""
    url = f"{IG_API_BASE}/{ig_user_id}/media_publish"
    params = {
        "creation_id": container_id,
        "access_token": access_token,
    }

    try:
        resp = requests.post(url, data=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        media_id = data.get("id")
        logger.info(f"  Published! Media ID: {media_id}")
        return media_id
    except Exception as e:
        logger.error(f"  Publishing failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  Response: {e.response.text}")
        return None


# ── Posting Logic ────────────────────────────────────────────────────────────

def post_single_image(
    ig_user_id: str,
    access_token: str,
    bucket_name: str,
    image_path: Path,
    caption: str,
) -> dict:
    """Upload and post a single image."""
    result = {"status": "failed", "errors": []}

    # Upload to GCS
    image_url = upload_to_gcs(image_path, bucket_name)
    if not image_url:
        result["errors"].append("GCS upload failed")
        return result

    # Create container
    container_id = create_media_container(ig_user_id, access_token, image_url, caption)
    if not container_id:
        result["errors"].append("Container creation failed")
        return result

    # Wait for processing
    if not wait_for_container(container_id, access_token):
        result["errors"].append("Container processing failed/timed out")
        return result

    # Publish
    media_id = publish_container(ig_user_id, access_token, container_id)
    if media_id:
        result["status"] = "published"
        result["ig_media_id"] = media_id
        result["container_id"] = container_id
    else:
        result["errors"].append("Publishing failed")

    return result


def post_carousel(
    ig_user_id: str,
    access_token: str,
    bucket_name: str,
    image_paths: list[Path],
    caption: str,
) -> dict:
    """Upload and post a carousel of images."""
    result = {"status": "failed", "errors": []}

    # Upload all images to GCS
    image_urls = []
    for path in image_paths:
        url = upload_to_gcs(path, bucket_name)
        if url:
            image_urls.append(url)
        else:
            result["errors"].append(f"GCS upload failed for {path.name}")

    if len(image_urls) < 2:
        result["errors"].append("Need at least 2 images for carousel")
        return result

    # Create child containers
    children_ids = []
    for url in image_urls:
        child_id = create_media_container(
            ig_user_id, access_token, url, is_carousel_item=True
        )
        if child_id:
            children_ids.append(child_id)
        else:
            result["errors"].append("Child container creation failed")
        time.sleep(1)

    if len(children_ids) < 2:
        result["errors"].append("Need at least 2 child containers for carousel")
        return result

    # Create carousel container
    carousel_id = create_carousel_container(
        ig_user_id, access_token, children_ids, caption
    )
    if not carousel_id:
        result["errors"].append("Carousel container creation failed")
        return result

    # Wait for processing
    if not wait_for_container(carousel_id, access_token):
        result["errors"].append("Carousel processing failed/timed out")
        return result

    # Publish
    media_id = publish_container(ig_user_id, access_token, carousel_id)
    if media_id:
        result["status"] = "published"
        result["ig_media_id"] = media_id
        result["container_id"] = carousel_id
        result["image_count"] = len(image_urls)
    else:
        result["errors"].append("Publishing failed")

    return result


# ── Logging ──────────────────────────────────────────────────────────────────

def append_to_log(log_path: Path, entry: dict) -> None:
    """Append a posting result to the log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = {"posts": []}

    log["posts"].append(entry)

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def update_plan_status(plan_path: Path, post_id: str, status: str) -> None:
    """Update post status in content plan."""
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    for post in plan.get("posts", []):
        if post.get("post_id") == post_id:
            post["status"] = status
            break

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post content to Instagram via Graph API")
    parser.add_argument("--post-id", type=str, help="Post specific content by ID")
    parser.add_argument("--plan-file", type=str, default=str(PLAN_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Validate without posting")
    args = parser.parse_args()

    # Load credentials
    ig_user_id = os.getenv("IG_USER_ID")
    ig_access_token = os.getenv("IG_ACCESS_TOKEN")
    bucket_name = os.getenv("GCS_BUCKET_NAME")

    if not args.dry_run:
        missing = []
        if not ig_user_id:
            missing.append("IG_USER_ID")
        if not ig_access_token:
            missing.append("IG_ACCESS_TOKEN")
        if not bucket_name:
            missing.append("GCS_BUCKET_NAME")
        if missing:
            raise EnvironmentError(
                f"Missing credentials in .env: {', '.join(missing)}\n"
                f"See workflows/jp_parenting_content.md for setup instructions."
            )

    # Load content plan
    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        raise FileNotFoundError(f"Content plan not found: {plan_path}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    # Filter posts to publish
    posts = plan.get("posts", [])
    if args.post_id:
        posts = [p for p in posts if p.get("post_id") == args.post_id]
        if not posts:
            raise ValueError(f"Post ID '{args.post_id}' not found in plan")
    else:
        # Only post items with status "images_ready"
        posts = [p for p in posts if p.get("status") == "images_ready"]

    if not posts:
        print("No posts ready to publish. Run generate_content.py first.")
        return

    # Check for duplicate posting today
    today = datetime.now().strftime("%Y-%m-%d")
    if LOG_PATH.exists():
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            existing_log = json.load(f)
        today_posts = [
            p for p in existing_log.get("posts", [])
            if p.get("posted_at", "").startswith(today) and p.get("status") == "published"
        ]
        if today_posts and not args.post_id:
            print(f"Already posted {len(today_posts)} time(s) today. Use --post-id to force.")
            return

    for post in posts:
        post_id = post["post_id"]
        content_format = post.get("content_format", "single_image")
        caption = post.get("caption_ja", "")
        hashtags = post.get("hashtags", [])

        # Append hashtags to caption
        if hashtags:
            caption += "\n\n" + " ".join(hashtags)

        # Find images
        post_dir = IMAGES_DIR / post_id
        if not post_dir.exists():
            logger.error(f"Image directory not found: {post_dir}")
            continue

        image_paths = sorted(post_dir.glob("slide_*.jpg"))
        if not image_paths:
            logger.error(f"No images found in {post_dir}")
            continue

        # Dry run
        if args.dry_run:
            print(f"\n{'='*60}")
            print(f"[DRY RUN] Post: {post_id}")
            print(f"Format: {content_format}")
            print(f"Images: {len(image_paths)}")
            for p in image_paths:
                print(f"  - {p.name}")
            print(f"Caption ({len(caption)} chars):")
            print(f"  {caption[:200]}...")
            print(f"{'='*60}")
            continue

        # Post
        logger.info(f"Publishing post {post_id} ({content_format}, {len(image_paths)} images)")

        if content_format == "carousel" and len(image_paths) >= 2:
            result = post_carousel(
                ig_user_id, ig_access_token, bucket_name, image_paths, caption
            )
        else:
            result = post_single_image(
                ig_user_id, ig_access_token, bucket_name, image_paths[0], caption
            )

        # Log result
        log_entry = {
            "post_id": post_id,
            "posted_at": datetime.now().isoformat(),
            "platform": "instagram",
            "content_format": content_format,
            "image_count": len(image_paths),
            "dry_run": False,
            **result,
        }
        append_to_log(LOG_PATH, log_entry)

        # Update plan status
        new_status = "published" if result["status"] == "published" else "publish_failed"
        update_plan_status(plan_path, post_id, new_status)

        if result["status"] == "published":
            print(f"Post {post_id} published! Media ID: {result.get('ig_media_id')}")
        else:
            print(f"Post {post_id} failed: {result.get('errors')}")

    if args.dry_run:
        print(f"\nDry run complete. No posts were published.")
    else:
        print(f"\nDone. See posting log: {LOG_PATH}")


if __name__ == "__main__":
    main()
