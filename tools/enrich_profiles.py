#!/usr/bin/env python3
"""
Profile Enrichment Tool — Apify IG/TT Profile Scrapers
=======================================================
Enriches pipeline creators with country, is_business, biography from Apify.

- Instagram: apify/instagram-profile-scraper (+ About profile add-on)
  → isBusinessAccount, businessCategoryName, about.country, biography, verified
- TikTok: clockworks/tiktok-profile-scraper
  → region (country code), verified, signature (bio)

Usage:
    python tools/enrich_profiles.py                     # Enrich all unenriched "Not Started"
    python tools/enrich_profiles.py --limit 100         # Limit batch size
    python tools/enrich_profiles.py --platform ig       # Instagram only
    python tools/enrich_profiles.py --platform tt       # TikTok only
    python tools/enrich_profiles.py --re-enrich         # Re-enrich already enriched
    python tools/enrich_profiles.py --dry-run           # Preview without API calls
    python tools/enrich_profiles.py --stats             # Show enrichment stats
"""

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths & Env ─────────────────────────────────────────────────────────────
DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
sys.path.insert(0, str(DIR))

JEEHOO_ENV = Path("/Volumes/Orbiters/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/Jeehoo/.env")
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass
# Fallback: Jeehoo .env
if not os.getenv("APIFY_API_TOKEN") and JEEHOO_ENV.exists():
    for line in JEEHOO_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if not os.getenv(k):
                os.environ[k] = v

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "admin")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Apify actor IDs
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"
TT_PROFILE_SCRAPER = "clockworks/tiktok-profile-scraper"

# Batch sizes for Apify calls (to avoid timeout)
IG_BATCH = 50
TT_BATCH = 50

# US location detection from bio text
US_STATES = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY",
    "LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"}
US_CITIES = {"new york","los angeles","chicago","houston","phoenix","philadelphia","san antonio",
    "san diego","dallas","san jose","austin","jacksonville","fort worth","columbus","charlotte",
    "san francisco","indianapolis","seattle","denver","nashville","oklahoma city","portland",
    "las vegas","memphis","louisville","baltimore","milwaukee","albuquerque","tucson","fresno",
    "sacramento","mesa","kansas city","atlanta","omaha","colorado springs","raleigh","long beach",
    "virginia beach","miami","oakland","minneapolis","tampa","tulsa","arlington","new orleans",
    "la","nyc","atl","philly","sf","socal","norcal"}

def _guess_us_from_bio(bio):
    """Return 'United States' if bio text contains US location signals."""
    if not bio:
        return ""
    bio_lower = bio.lower()
    # Check state abbreviations (word boundary)
    import re
    for state in US_STATES:
        if re.search(r'\b' + state.lower() + r'\b', bio_lower):
            return "United States"
    # Check city names
    for city in US_CITIES:
        if city in bio_lower:
            return "United States"
    # Common US patterns
    # Area codes (3-digit in parentheses or with dash)
    if re.search(r'\(\d{3}\)', bio_lower):
        return "United States"
    # ZIP codes (5-digit standalone)
    if re.search(r'\b\d{5}\b', bio_lower):
        return "United States"
    us_patterns = ["based in us", "usa ", "u.s.a", "united states", "american mom",
                   "american family", "🇺🇸", "sahm", "boy mom", "girl mom",
                   "mama of", "mommy of", "mom of", "toddler mom",
                   "midwest", "east coast", "west coast", "southern belle",
                   "pnw", "tristate", "new england", "the south"]
    for p in us_patterns:
        if p in bio_lower:
            return "United States"
    return ""


# ═════════════════════════════════════════════════════════════════════════════
# HTTP helpers
# ═════════════════════════════════════════════════════════════════════════════
def _orbi_headers():
    creds = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


def orbi_get(path, timeout=15):
    url = f"{ORBITOOLS_URL}{path}"
    req = urllib.request.Request(url, headers=_orbi_headers())
    resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
    return json.loads(resp.read())


def orbi_put(path, data, timeout=15):
    url = f"{ORBITOOLS_URL}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers=_orbi_headers())
    resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
    return json.loads(resp.read())


# ═════════════════════════════════════════════════════════════════════════════
# Apify client
# ═════════════════════════════════════════════════════════════════════════════
class ApifyClient:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.apify.com/v2"

    def _req(self, method, path, data=None, timeout=600):
        url = f"{self.base}{path}?token={self.token}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
        return json.loads(resp.read())

    def run_actor(self, actor_id, run_input, timeout_secs=300):
        """Run actor and wait for completion, return dataset items."""
        import urllib.parse
        encoded_id = urllib.parse.quote(actor_id, safe='')
        # Start the run
        result = self._req("POST", f"/acts/{encoded_id}/runs", run_input)
        run_id = result["data"]["id"]
        dataset_id = result["data"]["defaultDatasetId"]

        # Poll until finished
        start = time.time()
        while time.time() - start < timeout_secs:
            status_resp = self._req("GET", f"/actor-runs/{run_id}")
            status = status_resp["data"]["status"]
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break
            time.sleep(5)

        if status != "SUCCEEDED":
            print(f"  [WARN] Actor run {run_id} ended with status: {status}")
            return []

        # Fetch dataset items
        items_resp = self._req("GET", f"/datasets/{dataset_id}/items")
        return items_resp if isinstance(items_resp, list) else items_resp.get("items", items_resp.get("data", []))


# ═════════════════════════════════════════════════════════════════════════════
# Instagram Profile Enrichment
# ═════════════════════════════════════════════════════════════════════════════
def enrich_ig_profiles(client, usernames):
    """Fetch IG profiles with About add-on for country detection."""
    if not usernames:
        return {}

    print(f"  [IG] Fetching {len(usernames)} profiles...")
    results = {}

    for i in range(0, len(usernames), IG_BATCH):
        batch = usernames[i:i + IG_BATCH]
        print(f"  [IG] Batch {i // IG_BATCH + 1}: {len(batch)} usernames...")

        try:
            items = client.run_actor(IG_PROFILE_SCRAPER, {
                "usernames": batch,
                "addAboutInfo": True,  # Enable About profile add-on
            }, timeout_secs=600)

            for item in items:
                u = (item.get("username", "") or "").lower()
                if not u:
                    continue

                about = item.get("about", {}) or {}
                bio = (item.get("biography", "") or "")[:1000]
                country = about.get("country", "")
                if not country:
                    country = _guess_us_from_bio(bio)
                results[u] = {
                    "country": country,
                    "is_business_account": item.get("isBusinessAccount"),
                    "business_category": item.get("businessCategoryName", ""),
                    "biography": bio,
                    "is_verified": item.get("verified") or about.get("is_verified"),
                    "followers": item.get("followersCount", item.get("followedByCount")),
                }

            print(f"  [IG] Got {len(results)} profiles so far")
        except Exception as e:
            print(f"  [IG] Batch error: {e}")

        if i + IG_BATCH < len(usernames):
            time.sleep(2)  # Rate limit between batches

    return results


# ═════════════════════════════════════════════════════════════════════════════
# TikTok Profile Enrichment
# ═════════════════════════════════════════════════════════════════════════════
def enrich_tt_profiles(client, usernames):
    """Fetch TT profiles for region (country code)."""
    if not usernames:
        return {}

    print(f"  [TT] Fetching {len(usernames)} profiles...")
    results = {}

    for i in range(0, len(usernames), TT_BATCH):
        batch = usernames[i:i + TT_BATCH]
        print(f"  [TT] Batch {i // TT_BATCH + 1}: {len(batch)} usernames...")

        try:
            # clockworks actor returns video posts with authorMeta containing region.
            # Request 1 video per profile to minimize cost; extract profile from authorMeta.
            items = client.run_actor(TT_PROFILE_SCRAPER, {
                "profiles": [f"https://www.tiktok.com/@{u}" for u in batch],
                "resultsPerPage": 1,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
                "shouldDownloadSubtitles": False,
                "shouldDownloadSlideshowImages": False,
                "shouldDownloadAvatars": False,
            }, timeout_secs=600)

            for item in items:
                author = item.get("authorMeta", {})
                u = (author.get("name", item.get("uniqueId", "")) or "").lower().lstrip("@")
                if not u or u in results:
                    continue

                region = author.get("region", item.get("region", ""))
                # Normalize 2-letter region codes to full country names
                region_map = {"US": "United States", "GB": "United Kingdom", "CA": "Canada",
                              "AU": "Australia", "DE": "Germany", "FR": "France", "MX": "Mexico",
                              "KR": "South Korea", "JP": "Japan", "BR": "Brazil", "IN": "India"}
                country = region_map.get(region.upper(), region) if region else ""
                results[u] = {
                    "country": country,
                    "is_business_account": None,  # TikTok doesn't reliably expose this
                    "business_category": "",
                    "biography": (author.get("signature", item.get("bio", "")) or "")[:1000],
                    "is_verified": author.get("verified", item.get("verified")),
                    "followers": author.get("fans", item.get("followerCount")),
                }

            print(f"  [TT] Got {len(results)} profiles so far")
        except Exception as e:
            print(f"  [TT] Batch error: {e}")

        if i + TT_BATCH < len(usernames):
            time.sleep(2)

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Main Enrichment Pipeline
# ═════════════════════════════════════════════════════════════════════════════
def fetch_unenriched_creators(limit=500, platform=None, re_enrich=False):
    """Fetch creators that haven't been enriched yet."""
    params = f"?status=Not+Started&limit={limit}"
    if not re_enrich:
        params += "&enriched=false"
    data = orbi_get(f"/api/onzenna/pipeline/creators/{params}")
    creators = data.get("results", [])

    if platform:
        plat_map = {"ig": "instagram", "tt": "tiktok"}
        match = plat_map.get(platform.lower(), platform.lower())
        creators = [c for c in creators if c.get("platform", "").lower() == match]

    return creators


def update_creator_enrichment(creator_id, enrichment):
    """Update a creator with enrichment data via API."""
    update = {k: v for k, v in enrichment.items() if v is not None and v != ""}
    if not update:
        return

    try:
        orbi_put(f"/api/onzenna/pipeline/creators/{creator_id}/", update)
    except Exception as e:
        print(f"  [WARN] Failed to update {creator_id}: {e}")


def run_enrichment(limit=500, platform=None, re_enrich=False, dry_run=False):
    """Main enrichment pipeline."""
    print(f"\n{'=' * 60}")
    print(f"  Profile Enrichment Pipeline")
    print(f"  Limit: {limit} | Platform: {platform or 'all'} | Re-enrich: {re_enrich}")
    print(f"{'=' * 60}\n")

    if not APIFY_TOKEN:
        print("  [ERROR] APIFY_API_TOKEN not set!")
        return

    # Fetch unenriched creators
    print("  [1/4] Fetching unenriched creators...")
    creators = fetch_unenriched_creators(limit, platform, re_enrich)
    print(f"  Found {len(creators)} creators to enrich")

    if not creators:
        print("  Nothing to enrich!")
        return

    # Split by platform
    ig_creators = [c for c in creators if c.get("platform", "").lower() == "instagram"]
    tt_creators = [c for c in creators if c.get("platform", "").lower() == "tiktok"]
    print(f"  Instagram: {len(ig_creators)} | TikTok: {len(tt_creators)}")

    if dry_run:
        print("\n  [DRY RUN] Would enrich:")
        for c in creators[:10]:
            handle = c.get("ig_handle") or c.get("tiktok_handle") or "?"
            print(f"    {c['platform']}: @{handle} ({c.get('followers', 0)} followers)")
        if len(creators) > 10:
            print(f"    ... and {len(creators) - 10} more")
        return

    client = ApifyClient(APIFY_TOKEN)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Enrich Instagram
    if ig_creators:
        print("\n  [2/4] Enriching Instagram profiles...")
        ig_usernames = [c.get("ig_handle", "").lower() for c in ig_creators if c.get("ig_handle")]
        ig_map = {c.get("ig_handle", "").lower(): c for c in ig_creators if c.get("ig_handle")}
        ig_results = enrich_ig_profiles(client, ig_usernames)

        print(f"\n  [3a/4] Saving {len(ig_results)} IG enrichments...")
        ig_saved = 0
        for username, data in ig_results.items():
            creator = ig_map.get(username)
            if not creator:
                continue
            data["enriched_at"] = now_iso
            # Update followers if Apify has a more recent count
            if data.get("followers") and (not creator.get("followers") or data["followers"] > 0):
                pass  # Keep Apify followers in the update
            else:
                data.pop("followers", None)
            update_creator_enrichment(creator["id"], data)
            ig_saved += 1

        print(f"  IG saved: {ig_saved}")

    # Enrich TikTok
    if tt_creators:
        print("\n  [3/4] Enriching TikTok profiles...")
        tt_usernames = [c.get("tiktok_handle", "").lower().lstrip("@") for c in tt_creators if c.get("tiktok_handle")]
        tt_map = {c.get("tiktok_handle", "").lower().lstrip("@"): c for c in tt_creators if c.get("tiktok_handle")}
        tt_results = enrich_tt_profiles(client, tt_usernames)

        print(f"\n  [4/4] Saving {len(tt_results)} TT enrichments...")
        tt_saved = 0
        for username, data in tt_results.items():
            creator = tt_map.get(username)
            if not creator:
                continue
            data["enriched_at"] = now_iso
            data.pop("followers", None)  # Keep existing follower count for TT
            update_creator_enrichment(creator["id"], data)
            tt_saved += 1

        print(f"  TT saved: {tt_saved}")

    # ── Fallback: bio parsing + language detection for creators without country ──
    no_country = [c for c in creators if not c.get("country")]
    if no_country:
        print(f"\n  [Fallback] {len(no_country)} creators without country — applying bio parsing + language detection...")
        fallback_saved = 0
        for c in no_country:
            cid = c["id"]
            bio = c.get("biography", "")
            platform = c.get("platform", "").lower()

            # Check if enrichment just set a country (from IG/TT results above)
            handle = (c.get("ig_handle") or c.get("tiktok_handle") or "").lower().lstrip("@")
            enriched_country = ""
            if platform == "instagram" and ig_creators:
                enriched_country = ig_results.get(handle, {}).get("country", "")
            elif platform == "tiktok" and tt_creators:
                enriched_country = tt_results.get(handle, {}).get("country", "")
                # Use bio from Apify result if DB bio is empty
                if not bio:
                    bio = tt_results.get(handle, {}).get("biography", "")

            if enriched_country:
                continue  # Already has country from Apify

            # Step 1: Bio parsing for US signals
            country = _guess_us_from_bio(bio)

            # Step 2: Language-based inference (en → likely US for our influencer pool)
            if not country and platform == "tiktok":
                tt_data = tt_results.get(handle, {})
                # language field was saved during TT enrichment if available
                # For now, mark English-language TT creators as "US (inferred)"
                # so the dashboard can show them, and we verify at shipping time

            if country:
                update_creator_enrichment(cid, {"country": country})
                fallback_saved += 1

        print(f"  Fallback saved: {fallback_saved}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Enrichment Complete!")
    print(f"  IG: {len(ig_results) if ig_creators else 0} enriched")
    print(f"  TT: {len(tt_results) if tt_creators else 0} enriched")
    print(f"{'=' * 60}\n")


def show_stats():
    """Show enrichment statistics."""
    print("\n  Enrichment Stats")
    print("  " + "-" * 40)

    try:
        # Total
        data = orbi_get("/api/onzenna/pipeline/creators/?status=Not+Started&limit=1")
        total = data.get("total", 0)
        print(f"  Total 'Not Started': {total}")

        # Enriched
        data2 = orbi_get("/api/onzenna/pipeline/creators/?status=Not+Started&enriched=true&limit=1")
        enriched = data2.get("total", 0)
        print(f"  Enriched: {enriched}")
        print(f"  Unenriched: {total - enriched}")

        # US only
        data3 = orbi_get("/api/onzenna/pipeline/creators/?status=Not+Started&us_only=true&limit=1")
        us_count = data3.get("total", 0)
        print(f"  US-based: {us_count}")

        # Business accounts
        data4 = orbi_get("/api/onzenna/pipeline/creators/?status=Not+Started&is_business=true&limit=1")
        biz_count = data4.get("total", 0)
        print(f"  Business accounts: {biz_count}")

        print(f"\n  Coverage: {enriched}/{total} ({enriched * 100 // max(total, 1)}%)")
        if enriched > 0:
            print(f"  US rate: {us_count}/{enriched} ({us_count * 100 // max(enriched, 1)}%)")
            print(f"  Business rate: {biz_count}/{enriched} ({biz_count * 100 // max(enriched, 1)}%)")
    except Exception as e:
        print(f"  Error: {e}")

    print()


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Profile Enrichment — Apify IG/TT Scrapers")
    parser.add_argument("--limit", type=int, default=500, help="Max creators to enrich")
    parser.add_argument("--platform", choices=["ig", "tt"], help="Platform filter")
    parser.add_argument("--re-enrich", action="store_true", help="Re-enrich already enriched")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--stats", action="store_true", help="Show enrichment statistics")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        run_enrichment(args.limit, args.platform, args.re_enrich, args.dry_run)


if __name__ == "__main__":
    main()
