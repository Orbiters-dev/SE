#!/usr/bin/env python3
"""Restore creators whose status regressed from `sent` back to `draft_ready`.

The n8n "Parse & Save Drafts" node overwrites `existing.status = 'draft_ready'`
on every draft regeneration, even when status was already `sent` or later.
This script identifies affected creators and restores them to `sent`.

Identification rule:
  - Current status == draft_ready
  - AND (dm_count > 0 OR has outbound dm_log entry OR has last_dm)

Usage:
  python tools/restore_sent_status.py --dry-run
  python tools/restore_sent_status.py
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


def out_handles_from_logs(dm_logs):
    res = set()
    if isinstance(dm_logs, dict):
        for h, arr in dm_logs.items():
            if isinstance(arr, list) and any(e.get("dir") == "out" for e in arr):
                res.add(h)
    elif isinstance(dm_logs, list):
        for e in dm_logs:
            if e.get("dir") == "out":
                res.add(e.get("username", ""))
    return res


def main():
    parser = argparse.ArgumentParser()
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
    dm_logs = sd.get("global", {}).get("dm_logs", {})
    out_handles = out_handles_from_logs(dm_logs)

    targets = []
    for c in creators:
        if c.get("status") != "draft_ready":
            continue
        h = c.get("username", "")
        has_out = h in out_handles
        has_count = (c.get("dm_count", 0) or 0) > 0
        has_last = bool(c.get("last_dm"))
        if has_out or has_count or has_last:
            targets.append(c)

    print(f"Total creators: {len(creators)}")
    print(f"Regressed (draft_ready + DM-sent evidence): {len(targets)}")
    for c in targets:
        print(f"  {c.get('username','?'):30s} dm_count={c.get('dm_count',0)} "
              f"last_dm={c.get('last_dm','')} in_log={c.get('username','') in out_handles}")

    if args.dry_run:
        print("\n[DRY RUN] No changes made")
        return

    if not targets:
        print("\nNothing to restore.")
        return

    for c in targets:
        c["status"] = "sent"
    sd["global"]["creators"] = creators

    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "staticData": sd,
        "settings": wf.get("settings", {}),
    }
    resp = api("PUT", f"/workflows/{WF_ID}", payload)
    print(f"\nRestored {len(targets)} creator(s) to 'sent' (updated={resp.get('updatedAt','?')})")


if __name__ == "__main__":
    main()
