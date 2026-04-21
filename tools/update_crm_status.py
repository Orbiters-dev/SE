#!/usr/bin/env python3
"""Update JP CRM pipeline creator status via n8n API.

Usage:
  python tools/update_crm_status.py --handle meu_kiroku --status guidelines_sent
  python tools/update_crm_status.py --handle meu_kiroku --status guidelines_sent --dry-run
  python tools/update_crm_status.py --list-statuses
"""

import argparse
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

N8N_BASE = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_KEY = os.getenv("N8N_API_KEY", "")
WF_ID = "ynMO08sqdUEDk4Rc"

# Pipeline order (confirmed by dashboard)
# Not Started → Draft → Sent → Replied → Accepted → Contract → Delivered → Guide → Posted
PIPELINE_ORDER = [
    "not_started",
    "draft_ready",
    "sent",
    "contacted_manual",
    "replied",
    "accepted",
    "declined",        # branch (exit)
    "contract_sent",
    "contract_signed",
    "form_submitted",
    "sample_sent",
    "sample_shipped",
    "sample_delivered",
    "guidelines_sent",
    "posted",
]

# DM workflow STEP → CRM status mapping
STEP_TO_STATUS = {
    "1":    "sent",              # リチアウト DM 발송
    "2":    "replied",           # 답변 받음 (관심)
    "3":    "replied",           # 가이드라인 공유 (초기)
    "4":    "replied",           # 보수 확인 (네고)
    "5":    "replied",           # 월령확인/제품추천
    "6":    "contract_sent",     # 계약조건 확인 + DocuSign
    "6.5":  "contract_sent",     # DocuSign 발송
    "7":    "contract_signed",   # 배송지 수집 (서명 완료 후)
    "8":    "sample_shipped",    # 발송 요청
    "9":    "sample_shipped",    # 발송 완료
    "10":   "sample_shipped",    # 송장번호
    "10.5": "sample_delivered",  # 도착 확인
    "10.7": "guidelines_sent",   # 하서 수령 (가이드라인 발송 후)
    "11":   "guidelines_sent",   # 하서 확인
    "12":   "posted",            # 투고 완료
}

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _api(method, path, body=None):
    url = f"{N8N_BASE}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", N8N_KEY)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def get_status_index(status):
    try:
        return PIPELINE_ORDER.index(status)
    except ValueError:
        return -1


def update_creator_status(handle, new_status, dry_run=False, posted_date=None, content_url=None):
    if new_status not in PIPELINE_ORDER:
        print(f"ERROR: Invalid status '{new_status}'")
        print(f"Valid: {', '.join(PIPELINE_ORDER)}")
        return False

    wf = _api("GET", f"/workflows/{WF_ID}")
    sd = wf.get("staticData", {})
    if isinstance(sd, str):
        sd = json.loads(sd)
    creators = sd.get("global", {}).get("creators", [])

    creator = None
    for c in creators:
        if c.get("username") == handle:
            creator = c
            break

    if not creator:
        print(f"ERROR: Handle '{handle}' not found in CRM ({len(creators)} creators)")
        return False

    old_status = creator.get("status", "?")
    old_idx = get_status_index(old_status)
    new_idx = get_status_index(new_status)

    # Warn if going backwards (except declined)
    if new_status != "declined" and old_idx > new_idx and old_idx >= 0 and new_idx >= 0:
        print(f"WARNING: Going backwards! {old_status}({old_idx}) -> {new_status}({new_idx})")

    status_changed = (old_status != new_status)
    meta_changed = False
    if posted_date and creator.get("posted_date") != posted_date:
        meta_changed = True
    if content_url and creator.get("content_url") != content_url:
        meta_changed = True

    if not status_changed and not meta_changed:
        print(f"NO CHANGE: {handle} is already '{new_status}' (and metadata unchanged)")
        return True

    if status_changed:
        print(f"  {handle}: {old_status} -> {new_status}")
    if posted_date:
        print(f"    posted_date: {posted_date}")
    if content_url:
        print(f"    content_url: {content_url}")

    if dry_run:
        print("  [DRY RUN] No changes made")
        return True

    creator["status"] = new_status
    if posted_date:
        creator["posted_date"] = posted_date
    if content_url:
        creator["content_url"] = content_url
    sd["global"]["creators"] = creators

    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "staticData": sd,
        "settings": wf.get("settings", {}),
    }
    resp = _api("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  OK (updated={resp.get('updatedAt', '?')})")
    return True


def add_creator(handle, name="", status="not_started", followers=0, platform="instagram", dry_run=False):
    if status not in PIPELINE_ORDER:
        print(f"ERROR: Invalid status '{status}'")
        return False

    wf = _api("GET", f"/workflows/{WF_ID}")
    sd = wf.get("staticData", {})
    if isinstance(sd, str):
        sd = json.loads(sd)
    creators = sd.get("global", {}).get("creators", [])

    existing = any(c.get("username") == handle for c in creators)
    if existing:
        print(f"EXISTS: {handle} already in CRM, use --status to update")
        return False

    new_creator = {
        "username": handle,
        "name": name,
        "followers": followers,
        "platform": platform,
        "program": "collab",
        "status": status,
        "content_script": "",
        "dm_draft": "",
        "dm_link": f"https://instagram.com/{handle}",
        "dm_count": 0,
    }

    print(f"  ADD {handle}: {status} (followers={followers})")

    if dry_run:
        print("  [DRY RUN] No changes made")
        return True

    creators.append(new_creator)
    sd["global"]["creators"] = creators

    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "staticData": sd,
        "settings": wf.get("settings", {}),
    }
    resp = _api("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  OK (updated={resp.get('updatedAt', '?')})")
    return True


def main():
    parser = argparse.ArgumentParser(description="Update JP CRM pipeline status")
    parser.add_argument("--handle", help="IG handle (without @)")
    parser.add_argument("--status", help="New pipeline status")
    parser.add_argument("--step", help="DM workflow STEP number (auto-maps to status)")
    parser.add_argument("--add", action="store_true", help="Add new creator")
    parser.add_argument("--name", default="", help="Creator display name (for --add)")
    parser.add_argument("--followers", type=int, default=0, help="Follower count (for --add)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--list-statuses", action="store_true", help="Show pipeline order")
    parser.add_argument("--list-steps", action="store_true", help="Show STEP → status mapping")
    parser.add_argument("--posted-date", help="Posted date (YYYY-MM-DD), stored with posted status")
    parser.add_argument("--content-url", help="Content permalink URL, stored with posted status")
    args = parser.parse_args()

    if args.list_statuses:
        print("Pipeline order:")
        for i, s in enumerate(PIPELINE_ORDER):
            print(f"  {i:2d}. {s}")
        return

    if args.list_steps:
        print("STEP → CRM status mapping:")
        for step, status in sorted(STEP_TO_STATUS.items(), key=lambda x: float(x[0])):
            print(f"  STEP {step:5s} → {status}")
        return

    if not args.handle:
        parser.error("--handle is required")

    # Resolve status from --step if provided
    status = args.status
    if args.step:
        status = STEP_TO_STATUS.get(args.step)
        if not status:
            print(f"ERROR: Unknown STEP '{args.step}'")
            print(f"Valid STEPs: {', '.join(sorted(STEP_TO_STATUS.keys(), key=float))}")
            return

    if not status:
        parser.error("--status or --step is required")

    if args.add:
        add_creator(args.handle, args.name, status, args.followers, dry_run=args.dry_run)
    else:
        update_creator_status(
            args.handle,
            status,
            dry_run=args.dry_run,
            posted_date=args.posted_date,
            content_url=args.content_url,
        )


if __name__ == "__main__":
    main()
