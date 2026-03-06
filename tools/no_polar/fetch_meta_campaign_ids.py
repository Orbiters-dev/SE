"""
fetch_meta_campaign_ids.py - Meta campaign name->ID mapping (Q9)

Output: .tmp/polar_data/q9_meta_campaign_ids.json
Format: {"campaign_map": {"Campaign Name": "campaign_id"}, "account_id": "act_..."}

Usage:
    python tools/no_polar/fetch_meta_campaign_ids.py
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q9_meta_campaign_ids.json"

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


def api_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_all_campaigns():
    """Fetch all campaigns (including archived) with name and ID."""
    campaign_map = {}
    params = urllib.parse.urlencode({
        "fields": "id,name",
        "limit": "500",
        "access_token": ACCESS_TOKEN,
    })
    url = f"{BASE_URL}/{AD_ACCOUNT_ID}/campaigns?{params}"

    while url:
        data = api_get(url)
        for c in data.get("data", []):
            campaign_map[c["name"]] = c["id"]
        url = data.get("paging", {}).get("next")

    return campaign_map


def main():
    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        print("[ERROR] META_ACCESS_TOKEN and META_AD_ACCOUNT_ID must be set")
        sys.exit(1)

    print("[Meta Q9] Fetching campaign IDs...")
    campaign_map = fetch_all_campaigns()
    print(f"[Meta Q9] Found {len(campaign_map)} campaigns")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"campaign_map": campaign_map, "account_id": AD_ACCOUNT_ID}, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Q9 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
