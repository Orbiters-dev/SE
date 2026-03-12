"""
update_n8n_metafields.py
Update the Gifting workflow's Process Form Data node to save ALL form data as Shopify metafields.

Usage:
    python tools/update_n8n_metafields.py              # dry-run
    python tools/update_n8n_metafields.py --apply       # apply
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
from env_loader import load_env
load_env()

import requests

N8N_BASE_URL = os.environ["N8N_BASE_URL"]
N8N_API_KEY = os.environ["N8N_API_KEY"]

GIFTING_WF_ID = "F0sv8RsCS1v56Gkw"

# Updated Process Form Data — saves ALL form fields as Shopify customer metafields
NEW_PROCESS_CODE = r"""
// Extract form data
const body = $('Webhook').first().json.body || $('Webhook').first().json;
const personal = body.personal_info || {};
const baby = body.baby_info || {};
const addr = body.shipping_address || {};
const fullName = (personal.full_name || '').trim();
const nameParts = fullName.split(/\s+/);
const firstName = nameParts[0] || '';
const lastName = nameParts.slice(1).join(' ') || '';
const email = (personal.email || '').trim().toLowerCase();

if (!email) throw new Error('Missing email in form data');

// Build metafields array — ALL form data
const metafields = [];
const skip = new Set(['none','nope','n/a','na','']);

// Social handles
const ig = (personal.instagram || '').trim();
if (!skip.has(ig.toLowerCase())) {
  metafields.push({namespace:'influencer', key:'instagram', value:ig, type:'single_line_text_field'});
}
const tt = (personal.tiktok || '').trim();
if (!skip.has(tt.toLowerCase())) {
  metafields.push({namespace:'influencer', key:'tiktok', value:tt, type:'single_line_text_field'});
}

// Baby info
if (baby.child_1 && baby.child_1.birthday) {
  metafields.push({namespace:'influencer', key:'child_1_birthday', value:baby.child_1.birthday, type:'date'});
  if (baby.child_1.age_months !== null && baby.child_1.age_months !== undefined) {
    metafields.push({namespace:'influencer', key:'child_1_age_months', value:String(baby.child_1.age_months), type:'number_integer'});
  }
}
if (baby.child_2 && baby.child_2.birthday) {
  metafields.push({namespace:'influencer', key:'child_2_birthday', value:baby.child_2.birthday, type:'date'});
  if (baby.child_2.age_months !== null && baby.child_2.age_months !== undefined) {
    metafields.push({namespace:'influencer', key:'child_2_age_months', value:String(baby.child_2.age_months), type:'number_integer'});
  }
}

// Submission metadata
if (body.submitted_at) {
  metafields.push({namespace:'influencer', key:'submitted_at', value:body.submitted_at, type:'date_time'});
}
metafields.push({namespace:'influencer', key:'form_type', value:body.form_type || 'influencer_gifting', type:'single_line_text_field'});

// Selected products (human-readable summary)
if (body.selected_products && body.selected_products.length > 0) {
  var prodSummary = body.selected_products.map(function(p) { return p.title + ' (' + p.color + ')'; }).join(', ');
  metafields.push({namespace:'influencer', key:'selected_products', value:prodSummary, type:'single_line_text_field'});
}

// Shipping address (single string)
if (addr.street) {
  var addrStr = [addr.street, addr.apt, addr.city, addr.state, addr.zip, addr.country].filter(Boolean).join(', ');
  metafields.push({namespace:'influencer', key:'shipping_address', value:addrStr, type:'single_line_text_field'});
}

// Validate phone (E.164: +1 followed by 10 digits for US/CA)
let phone = (personal.phone || '').trim();
if (phone && !/^\+1\d{10}$/.test(phone)) {
  phone = '';
}

// Output for next nodes
return [{json: {
  email,
  firstName,
  lastName,
  fullName,
  phone,
  metafields,
  shopifyCustomerId: body.shopify_customer_id || null,
  _originalBody: body
}}];
""".strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply

    n8n_headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{GIFTING_WF_ID}", headers=n8n_headers)
    r.raise_for_status()
    wf = r.json()

    print(f"Workflow: {wf['name']}")

    # Find Process Form Data node
    target = None
    for n in wf["nodes"]:
        if n["name"] == "Process Form Data":
            target = n
            break

    if not target:
        print("[ERROR] Process Form Data node not found")
        return

    # Count current vs new metafields
    old_code = target["parameters"].get("jsCode", "")
    old_mf_count = old_code.count("metafields.push")
    new_mf_count = NEW_PROCESS_CODE.count("metafields.push")

    print(f"\nCurrent metafields.push calls: {old_mf_count}")
    print(f"New metafields.push calls: {new_mf_count}")
    print(f"New metafields: form_type, child_1_age_months, child_2_age_months, selected_products, shipping_address")

    if dry_run:
        print("\n[DRY RUN] Would update Process Form Data node.")
        return

    target["parameters"]["jsCode"] = NEW_PROCESS_CODE

    update_payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }

    r2 = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{GIFTING_WF_ID}",
        headers=n8n_headers,
        json=update_payload,
    )

    if r2.status_code == 200:
        print("\n[OK] Process Form Data updated with full metafield set.")
    else:
        print(f"\n[ERROR] {r2.status_code}: {r2.text[:500]}")


if __name__ == "__main__":
    main()
