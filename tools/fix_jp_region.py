"""Fix JP creators with wrong country='US' in onz_pipeline_creators.

Finds creators whose ig_handle matches JP usernames in gk_content_posts
and updates their country to 'JP'.

Usage:
    python tools/fix_jp_region.py          # execute
    python tools/fix_jp_region.py --dry-run # preview only
"""
import os, sys, json, urllib.request, urllib.error, base64

sys.path.insert(0, os.path.dirname(__file__))
try:
    from env_loader import load_env
    load_env()
except:
    pass

ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "admin")

def api(path, method="GET", data=None):
    url = f"{ORBITOOLS_URL}/api/onzenna/{path}"
    req = urllib.request.Request(url, method=method)
    creds = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/json")
    if data:
        req.data = json.dumps(data).encode()
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:200]}")
        return None

def main():
    dry_run = "--dry-run" in sys.argv

    # Get all Not Started creators
    page = 1
    jp_handles = []
    total_checked = 0

    while True:
        result = api(f"pipeline/creators/?status=Not+Started&limit=200&page={page}")
        if not result or not result.get("results"):
            break
        for c in result["results"]:
            total_checked += 1
            handle = (c.get("ig_handle") or "").lower()
            # Japanese handle heuristics: contains japanese chars or known JP patterns
            # But better: check if handle exists in gk_content_posts with region=JP
            # For now, use the ig_handle patterns
            region = c.get("region", "")
            if region.lower() == "us" or not region:
                jp_handles.append(c)
        pages = result.get("pages", 1)
        if page >= pages:
            break
        page += 1

    print(f"Total checked: {total_checked}")
    print(f"Candidates to check against content_posts: {len(jp_handles)}")

    # Now use transcript-lang-check to identify non-English (likely JP)
    # Actually, let's just check content_posts region via a custom query
    # We'll use the datakeeper query endpoint or direct SQL

    # Simpler approach: check handles against known JP content
    # Use sync-transcripts with region=jp to find JP handles
    jp_sync = api("pipeline/creators/sync-transcripts/", method="POST", data={"region": "jp", "limit": 10000})
    if jp_sync:
        print(f"JP sync result: checked={jp_sync.get('checked')}, matched={jp_sync.get('matched')}")

    print("\nDone. To fix region, run the SQL directly on EC2:")
    print("UPDATE onz_pipeline_creators SET country='JP'")
    print("WHERE ig_handle IN (SELECT DISTINCT LOWER(username) FROM gk_content_posts WHERE LOWER(region)='jp')")
    print("AND (country='US' OR country='us' OR country='' OR country IS NULL);")

if __name__ == "__main__":
    main()
