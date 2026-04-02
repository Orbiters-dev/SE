#!/usr/bin/env python3
"""
ManyChat ↔ Pipeline Cross-Check
================================
ManyChat subscriber DM 이력과 Pipeline CRM을 대조.
불일치(sent인데 ManyChat에 없음, ManyChat에서 trigger됐는데 Pipeline에 없음) 감지.

매일 2회 GitHub Actions cron으로 실행.

Usage:
  python tools/manychat_crosscheck.py                   # Full cross-check
  python tools/manychat_crosscheck.py --dry-run          # Report only, no DB update
  python tools/manychat_crosscheck.py --loop 2           # Run N rounds (default 2)
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env
load_env()

MANYCHAT_API_KEY = os.getenv("MANYCHAT_API_KEY_JP", "")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "orbit1234")


def _mc_headers():
    return {"Authorization": f"Bearer {MANYCHAT_API_KEY}", "Content-Type": "application/json"}


def _dk_auth():
    return "Basic " + base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()


def fetch_manychat_subscribers() -> list[dict]:
    """Fetch all ManyChat subscribers (IG channel)."""
    url = "https://api.manychat.com/fb/subscriber/getSubscribers"
    # ManyChat pagination
    all_subs = []
    page = 1
    while True:
        payload = json.dumps({"page": page, "limit": 100}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        for k, v in _mc_headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            subs = data.get("data", {}).get("subscribers", [])
            if not subs:
                break
            all_subs.extend(subs)
            page += 1
            time.sleep(0.3)  # Rate limit
        except urllib.error.HTTPError as e:
            print(f"  [MC] HTTP {e.code}: {e.read().decode()[:200]}")
            break
        except Exception as e:
            print(f"  [MC] Error: {e}")
            break
    return all_subs


def fetch_pipeline_creators(status_filter: str = "") -> list[dict]:
    """Fetch pipeline creators from EC2."""
    url = f"{ORBITOOLS_URL}/api/onzenna/pipeline/creators/?limit=5000"
    if status_filter:
        url += f"&status={urllib.parse.quote(status_filter)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _dk_auth())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        return data.get("results", [])
    except Exception as e:
        print(f"  [PG] Error: {e}")
        return []


def fetch_dm_logs() -> list[dict]:
    """Fetch DM logs from n8n."""
    url = "https://n8n.orbiters.co.kr/webhook/jp-pipeline-api"
    payload = json.dumps({"action": "dm_log"}).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data if isinstance(data, list) else data.get("logs", [])
    except Exception:
        return []


def crosscheck(dry_run: bool = False) -> dict:
    """Run one round of cross-check."""
    print("\n[1/3] Fetching ManyChat subscribers...")
    mc_subs = fetch_manychat_subscribers()
    print(f"  Got {len(mc_subs)} subscribers")

    # Build handle → subscriber map
    mc_map = {}
    for sub in mc_subs:
        # ManyChat stores IG username in custom fields or name
        ig_username = ""
        for field in sub.get("custom_fields", []):
            if field.get("name", "").lower() in ("instagram_username", "ig_handle", "username"):
                ig_username = (field.get("value") or "").lstrip("@").lower()
                break
        if not ig_username:
            ig_username = (sub.get("name") or "").lower().replace(" ", "")
        if ig_username:
            mc_map[ig_username] = sub

    print(f"  Mapped {len(mc_map)} handles")

    print("\n[2/3] Fetching Pipeline creators...")
    creators = fetch_pipeline_creators()
    print(f"  Got {len(creators)} creators")

    # Build handle → creator map
    pipe_map = {}
    for c in creators:
        handle = (c.get("ig_handle") or c.get("tiktok_handle") or "").lower()
        if handle:
            pipe_map[handle] = c

    print("\n[3/3] Cross-checking...")

    issues = []

    # Check 1: Pipeline "sent" but NOT in ManyChat
    sent_statuses = {"sent", "replied", "accepted", "form_submitted", "contract_sent",
                     "contract_signed", "sample_sent", "sample_shipped", "sample_delivered",
                     "guidelines_sent", "posted"}
    for handle, c in pipe_map.items():
        status = (c.get("pipeline_status") or "").lower().replace(" ", "_")
        if status in sent_statuses and handle not in mc_map:
            issues.append({
                "type": "pipeline_sent_no_manychat",
                "handle": handle,
                "status": c.get("pipeline_status"),
                "detail": f"Pipeline status={c.get('pipeline_status')} but no ManyChat subscriber found",
            })

    # Check 2: ManyChat subscriber NOT in Pipeline → auto-add as inbound
    auto_added = 0
    for handle, sub in mc_map.items():
        if handle not in pipe_map:
            issues.append({
                "type": "manychat_not_in_pipeline",
                "handle": handle,
                "mc_id": sub.get("id"),
                "detail": f"ManyChat subscriber @{handle} not found in Pipeline → adding as inbound",
            })
            if not dry_run:
                _auto_add_to_pipeline(handle, sub)
                auto_added += 1
    if auto_added:
        print(f"  Auto-added {auto_added} ManyChat subscribers to Pipeline")

    # Check 3: Pipeline "draft_ready" with dm_count > 0 (draft generated but already sent?)
    for handle, c in pipe_map.items():
        status = (c.get("pipeline_status") or "").lower().replace(" ", "_")
        if status == "draft_ready" and handle in mc_map:
            issues.append({
                "type": "draft_but_in_manychat",
                "handle": handle,
                "detail": f"Status=Draft Ready but found in ManyChat — may already be contacted",
            })

    # Report
    print(f"\n{'='*50}")
    print(f"Cross-check complete: {len(issues)} issues found")
    by_type = {}
    for issue in issues:
        t = issue["type"]
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in by_type.items():
        print(f"  {t}: {count}")

    if issues:
        print("\nTop issues:")
        for issue in issues[:10]:
            print(f"  [{issue['type']}] @{issue['handle']}: {issue['detail']}")

    # Push results to PG if not dry run
    if not dry_run and issues:
        push_issues(issues)

    return {"total_issues": len(issues), "by_type": by_type, "issues": issues}


def _auto_add_to_pipeline(handle: str, mc_sub: dict):
    """Add ManyChat subscriber to Pipeline as inbound creator."""
    import re
    if not handle or not re.match(r'^[a-zA-Z0-9._]+$', handle):
        return
    email = f"{handle.replace('.', '_')}@inbound.manychat"
    payload = json.dumps({
        "email": email,
        "ig_handle": handle,
        "full_name": mc_sub.get("name", handle),
        "platform": "Instagram",
        "pipeline_status": "Not Started",
        "source": "manychat_inbound",
        "notes": f"Auto-added from ManyChat cross-check. MC ID: {mc_sub.get('id', 'N/A')}",
    }).encode()
    req = urllib.request.Request(
        f"{ORBITOOLS_URL}/api/onzenna/pipeline/creators/",
        data=payload, method="POST"
    )
    req.add_header("Authorization", _dk_auth())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status < 300:
                print(f"    + Added @{handle} to Pipeline (inbound)")
    except Exception as e:
        print(f"    ! Failed to add @{handle}: {e}")


def push_issues(issues: list[dict]):
    """Push cross-check issues to PG for Dashboard Failures tab."""
    payload = json.dumps({
        "action": "crosscheck_results",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issues": issues[:50],  # Cap at 50
    }).encode()
    req = urllib.request.Request(
        f"{ORBITOOLS_URL}/api/onzenna/pipeline/execution/log/",
        data=payload, method="POST"
    )
    req.add_header("Authorization", _dk_auth())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"  [PG] Pushed {len(issues)} issues (status {r.status})")
    except Exception as e:
        print(f"  [PG] Push failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="ManyChat ↔ Pipeline Cross-Check")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no DB update")
    parser.add_argument("--loop", type=int, default=2, help="Number of check rounds (default 2)")
    args = parser.parse_args()

    if not MANYCHAT_API_KEY:
        print("ERROR: MANYCHAT_API_KEY_JP not set")
        sys.exit(1)

    for i in range(args.loop):
        print(f"\n{'#'*50}")
        print(f"  ROUND {i+1}/{args.loop}")
        print(f"{'#'*50}")
        result = crosscheck(dry_run=args.dry_run)
        if i < args.loop - 1:
            print("\n  Waiting 30s before next round...")
            time.sleep(30)

    print(f"\n✓ Done — {args.loop} rounds completed")


if __name__ == "__main__":
    main()
