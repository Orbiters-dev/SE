"""Clean up Airtable references in n8n workflows.

All HTTP calls already migrated to Django API (orbitools).
This script cleans residual comments, variable names, and sticky notes.
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_loader import load_env
import requests

load_env()
BASE = os.getenv("N8N_BASE_URL")
KEY = os.getenv("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
PUT_KEYS = ("name", "nodes", "connections", "settings")


def fetch_wf(wf_id):
    r = requests.get(f"{BASE}/api/v1/workflows/{wf_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def save_wf(wf_id, wf):
    payload = {k: wf[k] for k in PUT_KEYS}
    r = requests.put(f"{BASE}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    return r.status_code


def clean_code(js, replacements):
    """Apply a list of (old, new) string replacements."""
    for old, new in replacements:
        js = js.replace(old, new)
    return js


def cleanup_reply_handler():
    wf_id = "K99grtW9iWq8V79f"
    wf = fetch_wf(wf_id)
    changes = []

    node_fixes = {
        "Merge Config (C)": [
            ("// MERGE CONFIG (v2 - Airtable Dashboard)", "// MERGE CONFIG (v2 - Django Dashboard)"),
            ("// --- Brand Config from Airtable Dashboard ---", "// --- Brand Config from Django Dashboard ---"),
        ],
        "Extract Thread Records": [
            ("// Splits Airtable response { records: [...] }", "// Splits Django API response"),
            ("// Airtable HTTP response has records array", "// Django API HTTP response has records array"),
        ],
        "Config: Environment (C)": [
            ("// Reads Human-in-Loop + config from Airtable Dashboard",
             "// Reads Human-in-Loop + config from Django Dashboard"),
        ],
        "Config: Tables": [
            ("// Centralized Airtable IDs \u2014 update these when transitioning to client base",
             "// DEPRECATED: Airtable IDs no longer used \u2014 all calls go to Django API (orbitools)"),
        ],
    }

    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.code" and n["name"] in node_fixes:
            js = n["parameters"].get("jsCode", "")
            new_js = clean_code(js, node_fixes[n["name"]])
            if new_js != js:
                n["parameters"]["jsCode"] = new_js
                changes.append(n["name"])

        # Clean sticky notes
        if n["type"] == "n8n-nodes-base.stickyNote":
            content = n["parameters"].get("content", "")
            if "airtable" in content.lower():
                new_content = content.replace("Airtable", "Django API (PG)")
                if new_content != content:
                    n["parameters"]["content"] = new_content
                    changes.append(f"Note:{n['name']}")

    status = save_wf(wf_id, wf)
    print(f"Reply Handler: {status} {'OK' if status == 200 else 'FAIL'} | Cleaned: {changes}")
    return status == 200


def cleanup_fulfillment():
    wf_id = "ufMPgU6cjwuzLM0y"
    wf = fetch_wf(wf_id)
    changes = []

    for n in wf["nodes"]:
        if n["type"] != "n8n-nodes-base.code":
            if n["type"] == "n8n-nodes-base.stickyNote":
                content = n["parameters"].get("content", "")
                if "airtable" in content.lower():
                    n["parameters"]["content"] = content.replace("Airtable", "Django API (PG)")
                    changes.append(f"Note:{n['name']}")
            continue

        js = n["parameters"].get("jsCode", "")
        name = n["name"]
        original = js

        if name == "Extract Order Info":
            js = js.replace("// Airtable record info from earlier in the flow",
                            "// Record info from earlier in the flow (migrated to Django API)")
            js = js.replace("const airtableData =", "const upstreamData =")
            # Fix all airtableData. references
            js = js.replace("airtableData.", "upstreamData.")

        elif name == "Load Config":
            js = js.replace("// Load workflow config from Google Sheet + Airtable Dashboard/Config",
                            "// Load workflow config from Google Sheet + Django Dashboard/Config")
            js = js.replace("// Read Airtable Dashboard + Config",
                            "// Read Django Dashboard + Config")

        elif name == "Extract Shipped Records":
            js = js.replace("airtableRecordId: r.id,", "recordId: r.id,")

        elif name == "Check Draft Status":
            js = js.replace("const airtableData =", "const upstreamData =")
            js = js.replace("airtableData.", "upstreamData.")

        elif name == "Config: Tables":
            js = js.replace(
                "// Centralized Airtable IDs \u2014 update these when transitioning to client base",
                "// DEPRECATED: Airtable IDs no longer used \u2014 all calls go to Django API (orbitools)")

        if js != original:
            n["parameters"]["jsCode"] = js
            changes.append(name)

    status = save_wf(wf_id, wf)
    print(f"Fulfillment: {status} {'OK' if status == 200 else 'FAIL'} | Cleaned: {changes}")
    return status == 200


def cleanup_syncly():
    wf_id = "l86XnrL1JPFOMSA4GOoYy"
    wf = fetch_wf(wf_id)
    changes = []

    comment_fixes = [
        ("// Map sheet -> Airtable Content fields", "// Map sheet -> Django API Content fields"),
        ("// auto-creates missing creators in Airtable", "// auto-creates missing creators via Django API"),
        ("//          creators for auto-creation in Airtable.",
         "//          creators for auto-creation via Django API."),
    ]

    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            content = n["parameters"].get("content", "")
            if "airtable" in content.lower():
                new_c = content.replace("Airtable", "Django API (PG)")
                new_c = new_c.replace("airtable", "Django API")
                if new_c != content:
                    n["parameters"]["content"] = new_c
                    changes.append(f"Note:{n['name']}")

        elif n["type"] == "n8n-nodes-base.code":
            js = n["parameters"].get("jsCode", "")
            new_js = clean_code(js, comment_fixes)
            if new_js != js:
                n["parameters"]["jsCode"] = new_js
                changes.append(n["name"])

    status = save_wf(wf_id, wf)
    print(f"Syncly: {status} {'OK' if status == 200 else 'FAIL'} | Cleaned: {changes}")
    return status == 200


if __name__ == "__main__":
    print("=== Cleaning Airtable references from n8n workflows ===\n")
    ok1 = cleanup_reply_handler()
    ok2 = cleanup_fulfillment()
    ok3 = cleanup_syncly()
    print(f"\nDone. All OK: {ok1 and ok2 and ok3}")
