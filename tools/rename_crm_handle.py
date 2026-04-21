#!/usr/bin/env python3
"""Rename a CRM creator's username (handle) in n8n JP pipeline.

Usage:
  python tools/rename_crm_handle.py --old ao.channn --new __ao.channn --dry-run
  python tools/rename_crm_handle.py --old ao.channn --new __ao.channn
"""
import argparse
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

N8N_BASE = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_KEY = os.getenv("N8N_API_KEY", "")
WF_ID = "ynMO08sqdUEDk4Rc"

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def api(method, path, body=None):
    url = f"{N8N_BASE}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", N8N_KEY)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
        return json.loads(r.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, help="Current username")
    parser.add_argument("--new", required=True, help="New username")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not N8N_KEY:
        print("[FATAL] N8N_API_KEY missing")
        sys.exit(1)

    wf = api("GET", f"/workflows/{WF_ID}")
    sd = wf.get("staticData", {})
    if isinstance(sd, str):
        sd = json.loads(sd)
    creators = sd.get("global", {}).get("creators", []) or []

    # Check duplicate
    new_exists = any(c.get("username") == args.new for c in creators)
    if new_exists:
        print(f"ERROR: New handle '{args.new}' already exists in CRM")
        sys.exit(1)

    target = None
    for c in creators:
        if c.get("username") == args.old:
            target = c
            break
    if not target:
        print(f"ERROR: Handle '{args.old}' not found in CRM")
        sys.exit(1)

    print(f"  {args.old} -> {args.new}")
    print(f"    status={target.get('status')} dm_count={target.get('dm_count',0)}")

    # Also rename in dm_logs keys if present
    dm_logs = sd.get("global", {}).get("dm_logs", {})
    log_renamed = False
    if isinstance(dm_logs, dict) and args.old in dm_logs:
        print(f"    dm_logs entry exists ({len(dm_logs[args.old])} records), will rename key")
        log_renamed = True

    if args.dry_run:
        print("[DRY RUN] No changes made")
        return

    target["username"] = args.new
    # Update dm_link if points to old handle
    if target.get("dm_link", "").endswith(f"/{args.old}"):
        target["dm_link"] = f"https://instagram.com/{args.new}"
    if log_renamed:
        dm_logs[args.new] = dm_logs.pop(args.old)
        sd["global"]["dm_logs"] = dm_logs
    sd["global"]["creators"] = creators

    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "staticData": sd,
        "settings": wf.get("settings", {}),
    }
    resp = api("PUT", f"/workflows/{WF_ID}", payload)
    print(f"OK (updated={resp.get('updatedAt','?')})")


if __name__ == "__main__":
    main()
