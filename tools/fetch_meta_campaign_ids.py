"""Fetch Meta (Facebook) campaign name→ID mapping for direct links.

Saves to .tmp/polar_data/q9_meta_campaign_ids.json
"""
import os, json, urllib.request, urllib.parse
from dotenv import load_dotenv

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_dotenv(os.path.join(ROOT, ".env"))

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
OUT = os.path.join(ROOT, ".tmp", "polar_data", "q9_meta_campaign_ids.json")


def api_get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        raise Exception(f"Meta API error: {body.get('error', {}).get('message', str(e))}")


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
        # Pagination
        url = data.get("paging", {}).get("next")

    return campaign_map


def main():
    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        print("ERROR: META_ACCESS_TOKEN and META_AD_ACCOUNT_ID must be set in .env")
        return

    print("Fetching Meta campaign IDs...")
    campaign_map = fetch_all_campaigns()
    print(f"  Found {len(campaign_map)} campaigns")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"campaign_map": campaign_map, "account_id": AD_ACCOUNT_ID}, f, indent=2)
    print(f"  Saved to {OUT}")


if __name__ == "__main__":
    main()
