"""
Autopilot Mode: Visual Draft Gen Pipeline Test
===============================================
Playwright 기반 시각적 워크플로우 시뮬레이터.
실제 브라우저 창을 열어 Draft Gen 파이프라인 실행 과정을 눈으로 본다.

Usage:
  python tools/autopilot.py                    # 전체 자동 실행
  python tools/autopilot.py --step             # 단계별 (Enter로 진행)
  python tools/autopilot.py --no-cleanup       # 테스트 데이터 유지
  python tools/autopilot.py --headless         # 스크린샷만 (CI용)
  python tools/autopilot.py --skip-seed        # seed 건너뛰기 (기존 데이터 사용)
"""

import argparse
import json
import os
import random
import string
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── Encoding fix (Windows cp949) ────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── Paths ───────────────────────────────────────────────────────────────────
DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
TMP = ROOT / ".tmp"
AUTOPILOT_DIR = TMP / "autopilot"
AUTOPILOT_DIR.mkdir(parents=True, exist_ok=True)

BROWSER_PROFILE = Path.home() / ".autopilot_state" / "chrome_profile"
BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

# ─── Env loading ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(DIR))
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# ─── Django API (orbitools) Config ──────────────────────────────────────────
ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/onzenna/pipeline"
DATAKEEPER_SAVE_URL = "https://orbitools.orbiters.co.kr/api/datakeeper/save/"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

# n8n Draft Gen workflow
DRAFT_GEN_WF = "fwwOeLiDLSnR77E1"

# URLs for browser tabs
DASHBOARD_URL = "https://orbitools.orbiters.co.kr/pipeline/jp/"
N8N_EXEC_URL = f"{N8N_BASE_URL}/workflow/{DRAFT_GEN_WF}/executions"
GMAIL_AUTO_OUTREACH_URL = "https://mail.google.com/mail/u/1/#label/Auto+Outreach"

# Test email domain
TEST_EMAIL_DOMAIN = "orbiters.co.kr"

# ─── Console helpers ─────────────────────────────────────────────────────────
def log(msg):   print(f"[AUTOPILOT] {msg}")
def ok(msg):    print(f"  [PASS] {msg}")
def fail(msg):  print(f"  [FAIL] {msg}")
def info(msg):  print(f"  [INFO] {msg}")
def sep():      print("=" * 70)


# ─── HTTP utility ────────────────────────────────────────────────────────────
def api_request(method, url, payload=None, headers=None, timeout=30):
    """Simple urllib HTTP request -> (status, body_dict)"""
    _headers = {"Content-Type": "application/json"}
    if headers:
        _headers.update(headers)
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=_headers, method=method)

    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body


def pg_headers():
    """Basic Auth headers for Django orbitools API."""
    import base64
    cred = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return {"Authorization": f"Basic {cred}"}


def pg_url(resource, record_id=""):
    """Build Django API URL. resource: creators, conversations, content-posts."""
    base = f"{ORBITOOLS_BASE}/{resource}"
    return f"{base}/{record_id}/" if record_id else f"{base}/"


def rand_suffix():
    return "".join(random.choices(string.ascii_lowercase, k=3))


# ─── Test Data Definitions ───────────────────────────────────────────────────
def make_test_data():
    """Generate 3 test creators + 3 content records for 3-brand detection."""
    ts = datetime.now().strftime("%m%d%H%M")
    suffix = rand_suffix()

    creators = [
        {
            "brand": "grosmimi",
            "fields": {
                "creator_handle": f"auto_grosmimi_{ts}",
                "channel": "Instagram",
                "email": f"auto_gros_{ts}_{suffix}@{TEST_EMAIL_DOMAIN}",
                "name": "Sarah Kim (Auto)",
                "followers": 12500,
                "avg_views": 4800,
                "recent_30d_views": 8200,
                "partnership_status": "New",
                "status": "not_started",
                "outreach_type": "Low Touch",
                "source": "Autopilot Test",
                "brand": "grosmimi",
                "profile_url": f"https://instagram.com/auto_grosmimi_{ts}",
            },
            "content": {
                "channel": "Instagram",
                "post_date": datetime.now().strftime("%Y-%m-%d"),
                "views": 4800, "likes": 384, "comments": 48,
                "caption": "#grosmimi #ppsu #strawcup #babycup #momlife",
                "summary": "Grosmimi PPSU product review",
                "post_url": f"https://www.instagram.com/reel/auto_grosmimi_{ts}_test/",
                "transcript": "Let me show you this cup my daughter loves. It's the Grosmimi PPSU straw cup and the suction is perfect. The PPSU material is BPA-free which was huge for me. I also got their baby bottle and the anti-colic system actually works!",
                "content_status": "Pending",
            },
        },
        {
            "brand": "chamom",
            "fields": {
                "creator_handle": f"auto_chamom_{ts}",
                "channel": "TikTok",
                "email": f"auto_cham_{ts}_{suffix}@{TEST_EMAIL_DOMAIN}",
                "name": "Emily Torres (Auto)",
                "followers": 8900,
                "avg_views": 3200,
                "recent_30d_views": 5100,
                "partnership_status": "New",
                "status": "not_started",
                "outreach_type": "Low Touch",
                "source": "Autopilot Test",
                "brand": "chamom",
                "profile_url": f"https://tiktok.com/auto_chamom_{ts}",
            },
            "content": {
                "channel": "TikTok",
                "post_date": datetime.now().strftime("%Y-%m-%d"),
                "views": 3200, "likes": 256, "comments": 32,
                "caption": "#chamom #babyskincare #eczema #pscream #babylotion",
                "summary": "CHA&MOM skincare product review",
                "post_url": f"https://www.tiktok.com/@auto_chamom_{ts}_test",
                "transcript": "This baby cream changed everything. The PS Cream by CHA&MOM with Phyto Seline fixed my son's eczema. The moisturizer absorbs quickly and the ingredients are super clean - no parabens, no fragrance. Best baby skincare lotion I've tried.",
                "content_status": "Pending",
            },
        },
        {
            "brand": "naeiae",
            "fields": {
                "creator_handle": f"auto_naeiae_{ts}",
                "channel": "Instagram",
                "email": f"auto_naei_{ts}_{suffix}@{TEST_EMAIL_DOMAIN}",
                "name": "Jessica Park (Auto)",
                "followers": 6700,
                "avg_views": 2100,
                "recent_30d_views": 3400,
                "partnership_status": "New",
                "status": "not_started",
                "outreach_type": "Low Touch",
                "source": "Autopilot Test",
                "brand": "naeiae",
                "profile_url": f"https://instagram.com/auto_naeiae_{ts}",
            },
            "content": {
                "channel": "Instagram",
                "post_date": datetime.now().strftime("%Y-%m-%d"),
                "views": 2100, "likes": 168, "comments": 21,
                "caption": "#naeiae #babysnacks #ricepuff #blw #organicbaby",
                "summary": "Naeiae rice snack product review",
                "post_url": f"https://www.instagram.com/reel/auto_naeiae_{ts}_test/",
                "transcript": "These organic pop rice puffs from Naeiae are perfect for baby led weaning. They dissolve easily and have no added sugar. The rice puff texture is great for little fingers. Naeiae uses organic Korean rice which I love.",
                "content_status": "Pending",
            },
        },
    ]
    return creators


# ─── Phase 1: Seed Test Data ─────────────────────────────────────────────────
def seed_test_data(test_data):
    """Create 3 test creators + 3 content records via Django API (orbitools)."""
    log("Phase 1: Seeding test data into Django API...")
    sep()

    created_ids = []

    for item in test_data:
        brand = item["brand"]

        # Create Creator via Django API
        status, resp = api_request(
            "POST", pg_url("creators"),
            payload=item["fields"],
            headers=pg_headers(),
        )
        if status in (200, 201):
            creator_id = resp.get("id", "")
            ok(f"Creator [{brand}]: {creator_id} -- {item['fields']['creator_handle']}")
        else:
            fail(f"Creator [{brand}]: HTTP {status} -- {resp}")
            created_ids.append({"brand": brand, "creator_id": None, "content_id": None})
            continue

        # Create Content via DataKeeper API (content_posts table)
        content_fields = dict(item["content"])
        content_fields["creator_id"] = creator_id
        content_fields["creator_handle"] = item["fields"]["creator_handle"]
        status2, resp2 = api_request(
            "POST", DATAKEEPER_SAVE_URL,
            payload={"table": "content_posts", "rows": [content_fields]},
            headers=pg_headers(),
        )
        content_id = ""
        if status2 in (200, 201):
            # DataKeeper may return saved count or row IDs
            content_id = str(resp2.get("id", resp2.get("saved", "")))
            ok(f"Content [{brand}]: {content_id} -- transcript loaded")
        else:
            fail(f"Content [{brand}]: HTTP {status2} -- {resp2}")

        created_ids.append({
            "brand": brand,
            "creator_id": creator_id,
            "content_id": content_id,
            "username": item["fields"]["creator_handle"],
            "email": item["fields"]["email"],
        })

    sep()
    log(f"Seed complete: {len([x for x in created_ids if x.get('creator_id')])} creators + content records")
    return created_ids


# ─── Phase 2: Open Browser ──────────────────────────────────────────────────
def open_browser(headless=False, slow_mo=500):
    """Open Playwright browser with 3 tabs."""
    from playwright.sync_api import sync_playwright

    log("Phase 2: Opening browser...")
    sep()

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE),
        headless=headless,
        channel="chromium",
        viewport={"width": 1400, "height": 900},
        slow_mo=slow_mo if not headless else 0,
    )

    # Tab 1: JP Pipeline CRM Dashboard
    tab_at = context.pages[0] if context.pages else context.new_page()
    info("Tab 1: JP Pipeline CRM Dashboard")
    tab_at.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)

    # Tab 2: n8n Executions
    tab_n8n = context.new_page()
    info("Tab 2: n8n Draft Gen executions")
    tab_n8n.goto(N8N_EXEC_URL, wait_until="domcontentloaded", timeout=30000)

    # Tab 3: Gmail Auto Outreach
    tab_gmail = context.new_page()
    info("Tab 3: Gmail Auto Outreach label")
    tab_gmail.goto(GMAIL_AUTO_OUTREACH_URL, wait_until="domcontentloaded", timeout=30000)

    sep()
    log("Browser ready -- 3 tabs open")

    return pw, context, tab_at, tab_n8n, tab_gmail


# ─── Phase 3: Trigger Draft Gen ──────────────────────────────────────────────
def trigger_draft_gen():
    """Trigger the Draft Gen workflow via n8n API."""
    log("Phase 3: Triggering Draft Gen workflow...")
    sep()

    # Method: Use n8n API to get test execution or trigger manually
    # The Draft Gen uses scheduleTrigger (10-min poll), so we can:
    # 1. Wait for next poll cycle (~10 min max)
    # 2. Or use the n8n API to trigger test execution

    # Try triggering via n8n webhook (may 404 on PROD since it uses schedule)
    url = f"{N8N_BASE_URL}/api/v1/workflows/{DRAFT_GEN_WF}"
    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    status, resp = api_request("GET", url, headers=headers)

    if status == 200:
        info(f"Draft Gen workflow found: {resp.get('name', 'unknown')}")
        info(f"Active: {resp.get('active', False)}")
    else:
        fail(f"Could not fetch workflow info: HTTP {status}")

    # Try POST to trigger a test execution
    exec_url = f"{N8N_BASE_URL}/api/v1/executions"
    status2, resp2 = api_request(
        "POST", exec_url,
        payload={"workflowId": DRAFT_GEN_WF},
        headers=headers,
    )

    if status2 in (200, 201):
        exec_id = resp2.get("id", "unknown")
        ok(f"Execution triggered: {exec_id}")
        return exec_id
    else:
        info(f"Direct trigger returned HTTP {status2} -- workflow uses schedule trigger")
        info("Waiting for next 10-min poll cycle to pick up test creators...")
        return None


# ─── Phase 4: Watch & Verify ─────────────────────────────────────────────────
def watch_and_verify(created_ids, tab_at, tab_n8n, tab_gmail, step_mode=False):
    """Poll Django API for status changes, refresh browser tabs, take screenshots."""
    log("Phase 4: Watching for Draft Ready status change...")
    sep()

    max_wait = 720  # 12 minutes max (slightly over 10-min poll)
    poll_interval = 15
    elapsed = 0
    all_ready = False

    while elapsed < max_wait and not all_ready:
        # Check each creator's status
        ready_count = 0
        for item in created_ids:
            if not item.get("creator_id"):
                continue
            status, resp = api_request(
                "GET", pg_url("creators", item["creator_id"]),
                headers=pg_headers(),
            )
            if status == 200:
                # Django returns flat JSON (no {fields: {...}} wrapper)
                outreach_status = resp.get("status", "")
                if outreach_status == "draft_ready":
                    ready_count += 1
                    if not item.get("_notified"):
                        ok(f"[{item['brand']}] {item['username']} -> Draft Ready!")
                        item["_notified"] = True

        info(f"Status: {ready_count}/3 Draft Ready (elapsed: {elapsed}s / {max_wait}s)")

        if ready_count == len([x for x in created_ids if x.get("creator_id")]):
            all_ready = True
            break

        # Refresh browser tabs
        try:
            tab_at.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        try:
            tab_n8n.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

        if step_mode:
            input(f"\n  [STEP] Press Enter to continue (or Ctrl+C to stop)...")
        else:
            time.sleep(poll_interval)

        elapsed += poll_interval

    sep()
    if all_ready:
        ok("All 3 creators reached Draft Ready!")
    else:
        fail(f"Timeout after {max_wait}s -- only {ready_count}/3 ready")

    return all_ready


# ─── Phase 5: Verify Drafts & Gmail ──────────────────────────────────────────
def verify_results(created_ids, tab_at, tab_n8n, tab_gmail):
    """Check conversation records and Gmail Auto Outreach emails."""
    log("Phase 5: Verifying drafts and Gmail Auto Outreach...")
    sep()

    results = {"creators": 0, "conversations": 0, "gmail": 0, "brand_match": 0}
    brand_form_map = {
        "grosmimi": "influencer-gifting",
        "chamom": "influencer-gifting-chamom",
        "naeiae": "influencer-gifting-naeiae",
    }

    for item in created_ids:
        if not item.get("creator_id"):
            continue

        # Check creator status via Django API
        status, resp = api_request(
            "GET", pg_url("creators", item["creator_id"]),
            headers=pg_headers(),
        )
        if status == 200:
            # Django returns flat JSON
            if resp.get("status") == "draft_ready":
                results["creators"] += 1

            # Get conversations for this creator
            convo_url = f"{ORBITOOLS_BASE}/conversations/?creator_id={item['creator_id']}"
            cs, cr = api_request("GET", convo_url, headers=pg_headers())
            if cs == 200:
                convos = cr if isinstance(cr, list) else cr.get("results", [])
                if convos:
                    latest = convos[-1]
                    msg = latest.get("message_content", "")
                    results["conversations"] += 1
                    ok(f"[{item['brand']}] Conversation: {latest.get('id', '?')}")

                    # Check brand-specific form link
                    expected_form = brand_form_map.get(item["brand"], "")
                    if expected_form and expected_form in msg:
                        results["brand_match"] += 1
                        ok(f"  Form link matched: {expected_form}")
                    else:
                        fail(f"  Expected form link '{expected_form}' not found in draft")

    # Refresh Gmail tab
    try:
        tab_gmail.reload(wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
    except Exception:
        pass

    sep()
    log("Verification Results:")
    log(f"  Creators Draft Ready: {results['creators']}/3")
    log(f"  Conversations Created: {results['conversations']}/3")
    log(f"  Brand Form Links Matched: {results['brand_match']}/3")

    return results


# ─── Phase 6: Screenshots ────────────────────────────────────────────────────
def take_screenshots(tab_at, tab_n8n, tab_gmail):
    """Take full-page screenshots of all tabs."""
    log("Phase 6: Taking screenshots...")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    screenshots = {}
    for name, tab in [("dashboard", tab_at), ("n8n", tab_n8n), ("gmail", tab_gmail)]:
        path = AUTOPILOT_DIR / f"{name}_{ts}.png"
        try:
            tab.screenshot(path=str(path), full_page=True)
            ok(f"Screenshot: {path.name}")
            screenshots[name] = str(path)
        except Exception as e:
            fail(f"Screenshot {name}: {e}")

    return screenshots


# ─── Phase 7: Cleanup ────────────────────────────────────────────────────────
def cleanup(created_ids):
    """Delete test data from Django API."""
    log("Phase 7: Cleaning up test data...")
    sep()

    for item in created_ids:
        # Delete content via DataKeeper
        if item.get("content_id") and item.get("creator_id"):
            # Delete content_posts rows linked to this creator
            status, _ = api_request(
                "POST", DATAKEEPER_SAVE_URL,
                payload={"table": "content_posts", "delete_by": {"creator_id": item["creator_id"]}},
                headers=pg_headers(),
            )
            if status in (200, 204):
                ok(f"Deleted content for creator: {item['creator_id']}")

        # Delete creator (Django may cascade conversations)
        if item.get("creator_id"):
            status, _ = api_request(
                "DELETE", pg_url("creators", item["creator_id"]),
                headers=pg_headers(),
            )
            if status in (200, 204):
                ok(f"Deleted creator: {item['creator_id']}")

    sep()


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Autopilot: Visual Draft Gen Pipeline Test")
    parser.add_argument("--step", action="store_true", help="Step-by-step mode (Enter to advance)")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep test data after run")
    parser.add_argument("--headless", action="store_true", help="Run headless (screenshots only)")
    parser.add_argument("--skip-seed", action="store_true", help="Skip seeding (use existing test data)")
    parser.add_argument("--slow-mo", type=int, default=500, help="Playwright slow_mo ms (default 500)")
    args = parser.parse_args()

    sep()
    log("AUTOPILOT MODE: Visual Draft Gen Pipeline Test")
    log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Mode: {'Step-by-step' if args.step else 'Auto'} | "
        f"{'Headless' if args.headless else 'Visual'} | "
        f"{'No cleanup' if args.no_cleanup else 'Auto cleanup'}")
    sep()

    # Pre-check
    if not ORBITOOLS_USER or not ORBITOOLS_PASS:
        fail("ORBITOOLS_USER / ORBITOOLS_PASS not set"); return
    if not N8N_API_KEY:
        fail("N8N_API_KEY not set"); return

    created_ids = []
    pw = None
    context = None

    try:
        # Phase 1: Seed
        if not args.skip_seed:
            test_data = make_test_data()
            if args.step:
                log("Seed data prepared:")
                for td in test_data:
                    info(f"  {td['brand']}: {td['fields']['Username']}")
                input("\n  [STEP] Press Enter to seed into Django API...")
            created_ids = seed_test_data(test_data)
        else:
            log("Skipping seed (--skip-seed)")

        if args.step:
            input("\n  [STEP] Press Enter to open browser...")

        # Phase 2: Browser
        pw, context, tab_at, tab_n8n, tab_gmail = open_browser(
            headless=args.headless,
            slow_mo=args.slow_mo,
        )

        if args.step:
            input("\n  [STEP] Browser open. Press Enter to trigger Draft Gen...")

        # Phase 3: Trigger
        exec_id = trigger_draft_gen()

        if args.step:
            input("\n  [STEP] Trigger sent. Press Enter to start watching...")

        # Phase 4: Watch
        if created_ids:
            all_ready = watch_and_verify(created_ids, tab_at, tab_n8n, tab_gmail, step_mode=args.step)
        else:
            log("No seeded data to watch. Open browser for manual inspection.")
            all_ready = False

        if args.step:
            input("\n  [STEP] Press Enter to verify results...")

        # Phase 5: Verify
        if created_ids and all_ready:
            results = verify_results(created_ids, tab_at, tab_n8n, tab_gmail)
        elif created_ids:
            log("Skipping verification (not all creators reached Draft Ready)")
            results = {}
        else:
            results = {}

        # Phase 6: Screenshots
        screenshots = take_screenshots(tab_at, tab_n8n, tab_gmail)

        # Save run summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "mode": "step" if args.step else "auto",
            "headless": args.headless,
            "created_ids": created_ids,
            "all_ready": all_ready if created_ids else None,
            "results": results,
            "screenshots": screenshots,
            "exec_id": exec_id,
        }
        summary_path = AUTOPILOT_DIR / "last_run.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        info(f"Summary saved: {summary_path}")

        # Final report
        sep()
        log("AUTOPILOT COMPLETE")
        if results:
            total = results.get("creators", 0) + results.get("conversations", 0) + results.get("brand_match", 0)
            log(f"Score: {total}/9 checks passed")
            if total == 9:
                ok("ALL PASS -- Draft Gen pipeline working correctly!")
            else:
                fail(f"Some checks failed ({total}/9)")
        log(f"Screenshots: {AUTOPILOT_DIR}")
        sep()

        if args.step:
            input("\n  [STEP] Press Enter to close browser and finish...")

    except KeyboardInterrupt:
        log("\nInterrupted by user")

    finally:
        # Cleanup
        if created_ids and not args.no_cleanup and not args.skip_seed:
            cleanup(created_ids)
        elif created_ids and args.no_cleanup:
            log("Test data preserved (--no-cleanup)")

        # Close browser
        if context:
            try:
                context.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
