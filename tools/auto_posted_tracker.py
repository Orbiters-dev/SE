#!/usr/bin/env python3
"""Auto-detect posted content and transition JP CRM pipeline to `posted`.

Scans each candidate influencer (CRM status = sample_delivered or guidelines_sent)
via Meta Graph business_discovery and matches recent posts that satisfy ALL:

  - Caption contains BOTH `#グロミミ` AND `#grosmimi`
  - media_type == VIDEO (Reel)
  - Posted after creator's sample_shipped_date (if available), else last 60 days

On match, transitions CRM status to `posted` with posted_date + content_url.

Usage:
  python tools/auto_posted_tracker.py --dry-run
  python tools/auto_posted_tracker.py
  python tools/auto_posted_tracker.py --handle specific_user --dry-run

Env:
  META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_USER_ID (Meta Graph)
  N8N_BASE_URL, N8N_API_KEY (n8n API for CRM read + update)
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# Also try .wat_secrets for META creds (check_influencer_hashtag.py convention)
try:
    sys.path.insert(0, DIR)
    from env_loader import load_env  # type: ignore
    load_env()
except Exception:
    pass

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("INSTAGRAM_BUSINESS_USER_ID", "")
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_IG_SCRAPER = "apify/instagram-scraper"

N8N_BASE = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_KEY = os.getenv("N8N_API_KEY", "")
WF_ID = "ynMO08sqdUEDk4Rc"

# Required hashtags (both must be present, case-insensitive)
REQUIRED_HASHTAGS = ["#グロミミ", "#grosmimi"]

# Candidate CRM statuses
CANDIDATE_STATUSES = ["sample_delivered", "guidelines_sent"]

# Fallback lookback window if no sample_shipped_date available
FALLBACK_LOOKBACK_DAYS = 60

# Posts per handle to scan
MAX_POSTS_PER_HANDLE = 10

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def n8n_api(method, path, body=None):
    url = f"{N8N_BASE}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", N8N_KEY)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def graph_request(url):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [META API ERROR {e.code}] {body[:300]}")
        return None


def build_url(path, params):
    qs = urllib.parse.urlencode(params)
    return f"{GRAPH_API_BASE}{path}?{qs}"


def fetch_via_meta(handle, max_posts):
    """Meta business_discovery. Returns list or None on API error."""
    if not IG_USER_ID or not META_ACCESS_TOKEN:
        return None
    fields = (
        f"business_discovery.username({handle}){{"
        f"id,username,"
        f"media.limit({max_posts}){{id,timestamp,media_type,caption,permalink}}"
        f"}}"
    )
    url = build_url(f"/{IG_USER_ID}", {
        "fields": fields,
        "access_token": META_ACCESS_TOKEN,
    })
    result = graph_request(url)
    if not result:
        return None
    bd = result.get("business_discovery")
    if not bd:
        return []
    return (bd.get("media", {}) or {}).get("data", []) or []


def fetch_via_apify(handle, max_posts):
    """Fallback: Apify Instagram Scraper. Returns list of posts in Meta-like shape or None."""
    if not APIFY_TOKEN:
        print("    [APIFY] APIFY_API_TOKEN missing, skipping fallback")
        return None
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("    [APIFY] apify_client not installed, skipping fallback")
        return None

    try:
        client = ApifyClient(APIFY_TOKEN)
        run = client.actor(APIFY_IG_SCRAPER).call(
            run_input={
                "directUrls": [f"https://www.instagram.com/{handle}/"],
                "resultsType": "posts",
                "resultsLimit": max_posts,
                "searchType": "user",
                "addParentData": False,
            },
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    except Exception as e:
        print(f"    [APIFY ERROR] {str(e)[:200]}")
        return None

    normalized = []
    for it in items:
        product_type = (it.get("productType") or "").lower()
        post_type = (it.get("type") or "").lower()
        is_video = (
            product_type in ("clips", "feed", "igtv")
            or post_type == "video"
            or bool(it.get("videoUrl"))
        )
        # Map to Meta-like media_type
        if is_video:
            media_type = "VIDEO"
        elif post_type == "sidecar":
            media_type = "CAROUSEL_ALBUM"
        else:
            media_type = "IMAGE"

        normalized.append({
            "id": it.get("id") or it.get("shortCode") or "",
            "timestamp": it.get("timestamp") or "",
            "media_type": media_type,
            "caption": it.get("caption") or "",
            "permalink": it.get("url") or "",
        })
    return normalized


def fetch_recent_posts(handle, max_posts=MAX_POSTS_PER_HANDLE):
    """Try Meta first, then Apify as fallback. Returns (posts, source)."""
    handle = handle.lstrip("@").strip()
    posts = fetch_via_meta(handle, max_posts)
    if posts is not None and len(posts) > 0:
        return posts, "meta"
    if posts is None:
        print(f"    [META API failed for @{handle}, trying Apify fallback...]")
    else:
        print(f"    [META returned empty for @{handle}, trying Apify fallback...]")
    apify_posts = fetch_via_apify(handle, max_posts)
    if apify_posts is not None:
        return apify_posts, "apify"
    return None, "none"


def match_post(post, cutoff_dt):
    """Check if a post satisfies all matching criteria."""
    caption = (post.get("caption") or "")
    caption_lower = caption.lower()

    # All required hashtags present (case-insensitive)
    for tag in REQUIRED_HASHTAGS:
        if tag.lower() not in caption_lower:
            return False

    # Must be a video (Reel)
    if post.get("media_type") != "VIDEO":
        return False

    # Timestamp check
    ts = post.get("timestamp") or ""
    if cutoff_dt and ts:
        try:
            post_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if post_dt < cutoff_dt:
                return False
        except ValueError:
            pass

    return True


def parse_sample_shipped_date(creator):
    """Try to derive a cutoff datetime from sample_shipped info. Returns tz-aware datetime or None."""
    for key in ("sample_shipped_date", "shipped_date", "shipped_at", "sample_shipped_at"):
        val = creator.get(key)
        if val:
            try:
                if len(str(val)) == 10:
                    return datetime.fromisoformat(str(val)).replace(tzinfo=timezone.utc)
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def load_candidates():
    """Read CRM and return list of creators in candidate statuses."""
    wf = n8n_api("GET", f"/workflows/{WF_ID}")
    sd = wf.get("staticData", {})
    if isinstance(sd, str):
        sd = json.loads(sd)
    creators = sd.get("global", {}).get("creators", []) or []
    return [c for c in creators if c.get("status") in CANDIDATE_STATUSES]


def apply_posted_transition(handle, posted_date, content_url, dry_run):
    """Call update_crm_status.py to transition to posted."""
    cmd = [
        sys.executable, os.path.join(DIR, "update_crm_status.py"),
        "--handle", handle,
        "--status", "posted",
        "--posted-date", posted_date,
        "--content-url", content_url,
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(f"    -> {' '.join(cmd[1:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"    [STATUS UPDATE FAILED] {result.stderr[:300]}")
            return False
        for line in result.stdout.splitlines():
            print(f"    | {line}")
        return True
    except subprocess.TimeoutExpired:
        print("    [TIMEOUT]")
        return False


def run(dry_run=False, only_handle=None):
    candidates = load_candidates()
    if only_handle:
        candidates = [c for c in candidates if c.get("username") == only_handle]
    print(f"\nCandidates (status in {CANDIDATE_STATUSES}): {len(candidates)}")

    now_utc = datetime.now(timezone.utc)
    fallback_cutoff = now_utc - timedelta(days=FALLBACK_LOOKBACK_DAYS)

    matched_count = 0
    transitioned_count = 0

    for c in candidates:
        handle = c.get("username", "")
        status = c.get("status", "?")
        print(f"\n[{handle}] status={status}")

        cutoff = parse_sample_shipped_date(c) or fallback_cutoff
        print(f"  cutoff: {cutoff.date()} ({'sample_shipped' if parse_sample_shipped_date(c) else 'fallback 60d'})")

        posts, source = fetch_recent_posts(handle, MAX_POSTS_PER_HANDLE)
        if posts is None:
            print("  skip (all sources failed)")
            continue
        if not posts:
            print("  no posts returned (both sources empty)")
            continue
        print(f"  source={source}, posts={len(posts)}")

        match = None
        for p in posts:
            if match_post(p, cutoff):
                match = p
                break

        if not match:
            print(f"  no match in {len(posts)} recent posts")
            continue

        matched_count += 1
        ts = match.get("timestamp", "")
        posted_date = ts[:10] if ts else now_utc.date().isoformat()
        content_url = match.get("permalink", "")
        print(f"  MATCH: {posted_date} | {content_url}")

        ok = apply_posted_transition(handle, posted_date, content_url, dry_run)
        if ok:
            transitioned_count += 1

    print(f"\n=== Summary ===")
    print(f"Candidates scanned : {len(candidates)}")
    print(f"Matches found      : {matched_count}")
    print(f"Transitions applied: {transitioned_count}{' (DRY RUN)' if dry_run else ''}")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Auto-detect posted content and update CRM")
    parser.add_argument("--dry-run", action="store_true", help="Preview transitions without applying")
    parser.add_argument("--handle", help="Limit to a specific handle (for testing)")
    args = parser.parse_args()

    if not META_ACCESS_TOKEN or not IG_USER_ID:
        print("[FATAL] META_ACCESS_TOKEN / INSTAGRAM_BUSINESS_USER_ID missing")
        sys.exit(1)
    if not N8N_KEY:
        print("[FATAL] N8N_API_KEY missing")
        sys.exit(1)

    run(dry_run=args.dry_run, only_handle=args.handle)


if __name__ == "__main__":
    main()
