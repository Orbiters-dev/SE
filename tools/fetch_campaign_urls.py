"""
Fetch landing page URLs for specific campaigns (Non-classified diagnosis).
"""
import json, os, sys, urllib.parse, urllib.request
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ACCESS_TOKEN  = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
BASE_URL      = "https://graph.facebook.com/v18.0"

def api_get(path, params):
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())

def fetch_all(path, params):
    results = []
    while True:
        data = api_get(path, params)
        results.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query)
        after = qs.get("after", [None])[0]
        if not after:
            break
        params = {**params, "after": after}
    return results

# 1. Find campaigns by name
TARGET_NAMES = ["ASC Campaign", "NewYear"]
print("Fetching campaigns...")
campaigns = fetch_all(f"/{AD_ACCOUNT_ID}/campaigns", {
    "fields": "id,name",
    "limit": 500,
})
matched = [c for c in campaigns if any(t.lower() in c["name"].lower() for t in TARGET_NAMES)]
print(f"Matched {len(matched)} campaigns:")
for c in matched:
    print(f"  [{c['id']}] {c['name']}")

# 2. For each matched campaign, fetch ads with creative URL
print("\nFetching ads + creative URLs...")
for camp in matched:
    print(f"\n--- Campaign: {camp['name']} ---")
    try:
        ads = fetch_all(f"/{camp['id']}/ads", {
            "fields": "id,name,creative{object_url,object_story_spec{link_data{link,caption},video_data{call_to_action{value{link}}}},effective_object_story_id}",
            "limit": 50,
        })
        for ad in ads[:10]:
            cr = ad.get("creative", {})
            url = cr.get("object_url", "")
            if not url:
                oss = cr.get("object_story_spec", {})
                url = (oss.get("link_data", {}).get("link", "") or
                       oss.get("video_data", {}).get("call_to_action", {})
                           .get("value", {}).get("link", ""))
            eff = cr.get("effective_object_story_id", "")
            print(f"  Ad: {ad['name'][:60]}")
            print(f"  URL: {url or '(empty)'}")
            print(f"  PostID: {eff or '(empty)'}")
            print()
    except Exception as e:
        print(f"  ERROR: {e}")
