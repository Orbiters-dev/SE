"""
update_n8n_full_data_save.py
Update Gifting and Gifting2 workflows to save ALL form data to:
- Airtable Applicants (full data)
- Airtable Creators (full data)
- PostgreSQL (full data)
- Shopify Metafields (via customer metafield sync)

Usage:
    python tools/update_n8n_full_data_save.py              # dry-run
    python tools/update_n8n_full_data_save.py --apply       # apply changes
    python tools/update_n8n_full_data_save.py --apply --workflow gifting   # gifting only
    python tools/update_n8n_full_data_save.py --apply --workflow gifting2  # gifting2 only
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
from env_loader import load_env
load_env()

import requests

N8N_BASE_URL = os.environ["N8N_BASE_URL"]
N8N_API_KEY = os.environ["N8N_API_KEY"]
AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]

GIFTING_WF_ID = "F0sv8RsCS1v56Gkw"
GIFTING2_WF_ID = "KqICsN9F1mPwnAQ9"

WJ_BASE = "appT2gLRR0PqMFgII"
WJ_APPLICANTS = "tbloYjIEr5OtEppT0"
WJ_CREATORS = "tbl7zJ1MscP852p9N"

# ============================================================
# GIFTING workflow: Prepare Airtable Payload (Applicants) — FULL DATA
# ============================================================
GIFTING_APPLICANTS_CODE = r"""
var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};
var formData = $('Process Form Data').first().json;
var body = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = body.personal_info || {};
var baby = body.baby_info || {};
var addr = body.shipping_address || {};
var child1 = baby.child_1 || {};
var child2 = baby.child_2 || {};

var fields = {
  "Email": formData.email || personal.email || '',
  "Name": personal.full_name || '',
  "Instagram Handle": (personal.instagram || '').replace(/^@/, ''),
  "TikTok Handle": (personal.tiktok || '').replace(/^@/, ''),
  "Phone": personal.phone || '',
  "Status": "New",
  "Draft Order ID": String(draftOrder.id || ''),
  "Shopify Customer ID": formData.shopifyCustomerId || null,
  "Child 1 Birthday": child1.birthday || '',
  "Child 1 Age Months": child1.age_months || null,
  "Child 2 Birthday": child2 ? (child2.birthday || '') : '',
  "Child 2 Age Months": child2 ? (child2.age_months || null) : null,
  "Address 1": addr.street || '',
  "Address 2": addr.apt || '',
  "City": addr.city || '',
  "State": addr.state || '',
  "ZIP": addr.zip || '',
  "Country": addr.country || 'US',
  "Selected Products": JSON.stringify(body.selected_products || []),
  "Form Type": body.form_type || 'influencer_gifting',
  "Submitted At": body.submitted_at || new Date().toISOString()
};

// Filter empty/null
var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# ============================================================
# GIFTING workflow: Prepare Creators Payload — FULL DATA
# ============================================================
GIFTING_CREATORS_CODE = r"""
var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};
var formData = $('Process Form Data').first().json;
var body = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = body.personal_info || {};
var baby = body.baby_info || {};
var addr = body.shipping_address || {};
var child1 = baby.child_1 || {};
var child2 = baby.child_2 || {};

var instagram = (personal.instagram || '').replace(/^@/, '');
var tiktok = (personal.tiktok || '').replace(/^@/, '');

var platform = 'Instagram';
var username = instagram;
var profileUrl = '';

if (instagram && instagram !== 'None') {
  platform = 'Instagram';
  username = instagram;
  profileUrl = 'https://www.instagram.com/' + instagram;
} else if (tiktok && tiktok !== 'None') {
  platform = 'TikTok';
  username = tiktok;
  profileUrl = 'https://www.tiktok.com/@' + tiktok;
}

var fields = {
  "Email": formData.email || personal.email || '',
  "Name": personal.full_name || '',
  "Username": username || '',
  "Platform": platform,
  "Profile URL": profileUrl,
  "Phone": personal.phone || '',
  "TikTok Handle": tiktok || '',
  "Outreach Status": "Needs Review",
  "Partnership Status": "New",
  "Source": "ManyChat Inbound",
  "Communication Channel": "Email",
  "Initial Discovery Date": new Date().toISOString().split('T')[0],
  "Draft Order ID": String(draftOrder.id || ''),
  "Child 1 Birthday": child1.birthday || '',
  "Child 1 Age Months": child1.age_months || null,
  "Child 2 Birthday": child2 ? (child2.birthday || '') : '',
  "Child 2 Age Months": child2 ? (child2.age_months || null) : null,
  "Street": addr.street || '',
  "Apt": addr.apt || '',
  "City": addr.city || '',
  "State": addr.state || '',
  "ZIP": addr.zip || '',
  "Country": addr.country || 'US',
  "Selected Products": JSON.stringify(body.selected_products || []),
  "Form Type": body.form_type || 'influencer_gifting',
  "Submitted At": body.submitted_at || new Date().toISOString()
};

var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# ============================================================
# GIFTING workflow: Prepare PG Payload — FULL DATA (already mostly complete)
# ============================================================
GIFTING_PG_CODE = r"""
var webhookData = $('Webhook').first().json;
var formData = webhookData.body || webhookData;
var personal = formData.personal_info || {};
var baby = formData.baby_info || {};
var addr = formData.shipping_address || {};
var child1 = baby.child_1 || {};
var child2 = baby.child_2 || {};

var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};

var payload = {
  form_type: formData.form_type || 'influencer_gifting',
  email: (personal.email || formData.email || '').trim().toLowerCase(),
  full_name: personal.full_name || '',
  phone: personal.phone || '',
  instagram: personal.instagram || '',
  tiktok: personal.tiktok || '',
  shopify_customer_id: formData.shopify_customer_id || null,
  shopify_draft_order_id: draftOrder.id || null,
  child_1_birthday: child1.birthday || null,
  child_1_age_months: child1.age_months || null,
  child_2_birthday: child2 ? (child2.birthday || null) : null,
  child_2_age_months: child2 ? (child2.age_months || null) : null,
  street: addr.street || '',
  apt: addr.apt || '',
  city: addr.city || '',
  state: addr.state || '',
  zip: addr.zip || '',
  country: addr.country || 'US',
  selected_products: JSON.stringify(formData.selected_products || []),
  submitted_at: formData.submitted_at || new Date().toISOString()
};

return [{json: payload}];
""".strip()

# ============================================================
# GIFTING2 workflow: Prepare Applicants Upsert — FULL DATA
# ============================================================
GIFTING2_APPLICANTS_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};
const baby = buildData.baby_info || {};
const addr = buildData.shipping_address || {};
const child1 = (baby.child_1) || {};
const child2 = (baby.child_2) || {};

var fields = {
  "Email": mergeData.airtable_email || personal.email || '',
  "Name": personal.full_name || '',
  "Draft Order ID": String(draftOrder.id || ''),
  "Shopify Customer ID": mergeData.customer_id ? Number(mergeData.customer_id) : null,
  "Status": "Accepted",
  "Instagram Handle": (personal.instagram || '').replace(/^@/, ''),
  "TikTok Handle": (personal.tiktok || '').replace(/^@/, ''),
  "Phone": personal.phone || '',
  "Child 1 Birthday": child1.birthday || '',
  "Child 1 Age Months": child1.age_months || null,
  "Child 2 Birthday": child2 ? (child2.birthday || '') : '',
  "Child 2 Age Months": child2 ? (child2.age_months || null) : null,
  "Address 1": addr.street || '',
  "Address 2": addr.apt || '',
  "City": addr.city || '',
  "State": addr.state || '',
  "ZIP": addr.zip || '',
  "Country": addr.country || 'US',
  "Selected Products": JSON.stringify(buildData.selected_products || []),
  "Form Type": "gifting2_sample_request",
  "Submitted At": new Date().toISOString()
};

var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# ============================================================
# GIFTING2 workflow: Prepare Creators Upsert — FULL DATA
# ============================================================
GIFTING2_CREATORS_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};
const baby = buildData.baby_info || {};
const addr = buildData.shipping_address || {};
const child1 = (baby.child_1) || {};
const child2 = (baby.child_2) || {};

var instagram = (personal.instagram || '').replace(/^@/, '');
var tiktok = (personal.tiktok || '').replace(/^@/, '');

var platform = 'Instagram';
var username = instagram;
var profileUrl = '';

if (instagram && instagram !== 'None') {
  platform = 'Instagram';
  username = instagram;
  profileUrl = 'https://www.instagram.com/' + instagram;
} else if (tiktok && tiktok !== 'None') {
  platform = 'TikTok';
  username = tiktok;
  profileUrl = 'https://www.tiktok.com/@' + tiktok;
}

var fields = {
  "Email": mergeData.airtable_email || personal.email || '',
  "Name": personal.full_name || '',
  "Username": username || '',
  "Platform": platform,
  "Profile URL": profileUrl,
  "Phone": personal.phone || '',
  "TikTok Handle": tiktok || '',
  "Outreach Status": "Sample Sent",
  "Partnership Status": "New",
  "Source": "ManyChat Inbound",
  "Communication Channel": "Email",
  "Draft Order ID": String(draftOrder.id || ''),
  "Child 1 Birthday": child1.birthday || '',
  "Child 1 Age Months": child1.age_months || null,
  "Child 2 Birthday": child2 ? (child2.birthday || '') : '',
  "Child 2 Age Months": child2 ? (child2.age_months || null) : null,
  "Street": addr.street || '',
  "Apt": addr.apt || '',
  "City": addr.city || '',
  "State": addr.state || '',
  "ZIP": addr.zip || '',
  "Country": addr.country || 'US',
  "Selected Products": JSON.stringify(buildData.selected_products || []),
  "Form Type": "gifting2_sample_request",
  "Submitted At": new Date().toISOString()
};

var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# ============================================================
# GIFTING2 workflow: Prepare PG Payload — FULL DATA
# ============================================================
GIFTING2_PG_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};
const addr = buildData.shipping_address || {};
const baby = buildData.baby_info || {};
const child1 = (baby.child_1) || {};
const child2 = (baby.child_2) || {};

return [{json: {
  form_type: "gifting2_sample_request",
  email: personal.email || mergeData.airtable_email || '',
  full_name: personal.full_name || '',
  phone: personal.phone || '',
  instagram: personal.instagram || '',
  tiktok: personal.tiktok || '',
  shopify_customer_id: mergeData.customer_id || null,
  shopify_draft_order_id: draftOrder.id || null,
  child_1_birthday: child1.birthday || null,
  child_1_age_months: child1.age_months || null,
  child_2_birthday: child2 ? (child2.birthday || null) : null,
  child_2_age_months: child2 ? (child2.age_months || null) : null,
  street: addr.street || '',
  apt: addr.apt || '',
  city: addr.city || '',
  state: addr.state || '',
  zip: addr.zip || '',
  country: addr.country || 'US',
  selected_products: JSON.stringify(buildData.selected_products || []),
  submitted_at: new Date().toISOString()
}}];
""".strip()


def update_node_code(wf, node_name, new_code):
    """Update jsCode of a named node."""
    for n in wf["nodes"]:
        if n["name"] == node_name:
            n["parameters"]["jsCode"] = new_code
            return True
    return False


def update_workflow(wf_id, wf_name, updates, dry_run=True):
    """Update a workflow with new node code."""
    n8n_headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=n8n_headers)
    r.raise_for_status()
    wf = r.json()

    print(f"\n{'='*50}")
    print(f"Workflow: {wf['name']} ({wf_id})")
    print(f"Nodes: {len(wf['nodes'])}")

    if dry_run:
        print(f"\n[DRY RUN] Would update:")
        for node_name, _ in updates:
            found = any(n["name"] == node_name for n in wf["nodes"])
            status = "FOUND" if found else "NOT FOUND"
            print(f"  {node_name} [{status}]")
        return

    changed = 0
    for node_name, new_code in updates:
        if update_node_code(wf, node_name, new_code):
            print(f"  [OK] Updated: {node_name}")
            changed += 1
        else:
            print(f"  [SKIP] Not found: {node_name}")

    if changed == 0:
        print("  No changes needed.")
        return

    update_payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }

    r2 = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}",
        headers=n8n_headers,
        json=update_payload,
    )

    if r2.status_code == 200:
        print(f"\n  [OK] Workflow saved. {changed} nodes updated.")
    else:
        print(f"\n  [ERROR] {r2.status_code}: {r2.text[:500]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workflow", choices=["gifting", "gifting2", "both"], default="both")
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        print("[DRY RUN MODE] Use --apply to save changes.\n")

    if args.workflow in ("gifting", "both"):
        update_workflow(GIFTING_WF_ID, "Gifting", [
            ("Prepare Airtable Payload", GIFTING_APPLICANTS_CODE),
            ("Prepare Creators Payload", GIFTING_CREATORS_CODE),
            ("Prepare PG Payload", GIFTING_PG_CODE),
        ], dry_run)

    if args.workflow in ("gifting2", "both"):
        update_workflow(GIFTING2_WF_ID, "Gifting2", [
            ("Prepare Applicants Upsert", GIFTING2_APPLICANTS_CODE),
            ("Prepare Creators Upsert", GIFTING2_CREATORS_CODE),
            ("Prepare PG Payload", GIFTING2_PG_CODE),
        ], dry_run)


if __name__ == "__main__":
    main()
