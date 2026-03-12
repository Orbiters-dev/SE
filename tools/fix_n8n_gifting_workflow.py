"""Fix corrupted Build Draft Order code + Airtable target in Gifting workflow.

Issues fixed:
1. Build Draft Order: corrupted $() references, optional chaining, nullish coalescing
2. Save to Airtable: target changed from Production CRM (403) to Inbound table

Usage:
    python tools/fix_n8n_gifting_workflow.py --dry-run
    python tools/fix_n8n_gifting_workflow.py
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env

load_env()

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")

DEFAULT_WORKFLOW_ID = "F0sv8RsCS1v56Gkw"

# Inbound Applicants table (our API key has access)
AIRTABLE_INBOUND_BASE_ID = "appT2gLRR0PqMFgII"
AIRTABLE_INBOUND_TABLE_ID = "tbloYjIEr5OtEppT0"
AIRTABLE_INBOUND_URL = f"https://api.airtable.com/v0/{AIRTABLE_INBOUND_BASE_ID}/{AIRTABLE_INBOUND_TABLE_ID}"

# Fixed Build Draft Order code - NO optional chaining, NO nullish coalescing
BUILD_DRAFT_ORDER_CODE = r"""
// Get customer ID from create/update response
var customerResponse = $('Create or Update Customer').first().json;
var customer = customerResponse.customer || {};
var customerId = customer.id;
if (!customerId) throw new Error('No customer ID returned');

// Get original form body
var decisionData = $('Decide Create or Update').first().json;
var body = decisionData._originalBody;
var personal = body.personal_info || {};
var addr = body.shipping_address || {};

var fullName = (personal.full_name || '').trim();
var nameParts = fullName.split(/\s+/);
var firstName = nameParts[0] || '';
var lastName = nameParts.slice(1).join(' ') || '';

// Build line items
var lineItems = (body.selected_products || []).map(function(p) {
  return {
    variant_id: p.variant_id,
    quantity: 1,
    title: p.title,
    properties: [{ name: 'Color', value: p.color || 'Default' }]
  };
});

if (lineItems.length === 0) throw new Error('No products selected');

// Build note
var baby = body.baby_info || {};
var noteLines = [
  'Influencer Gifting Application',
  '---',
  'Instagram: ' + (personal.instagram || 'N/A'),
  'TikTok: ' + (personal.tiktok || 'N/A'),
];
var child1 = baby.child_1 || null;
var child2 = baby.child_2 || null;
if (child1) noteLines.push('Child 1: ' + (child1.birthday || 'N/A') + ' (' + (child1.age_months || '?') + ' months)');
if (child2) noteLines.push('Child 2: ' + (child2.birthday || 'N/A') + ' (' + (child2.age_months || '?') + ' months)');
noteLines.push('Submitted: ' + (body.submitted_at || new Date().toISOString()));

return [{json: {
  draft_order: {
    line_items: lineItems,
    customer: { id: customerId },
    applied_discount: {
      description: 'Influencer Gifting - 100% PR Discount',
      value_type: 'percentage',
      value: '100.0',
      title: 'PR Gifting'
    },
    shipping_address: {
      first_name: firstName,
      last_name: lastName,
      address1: addr.street || '',
      address2: addr.apt || '',
      city: addr.city || '',
      province: addr.state || '',
      zip: addr.zip || '',
      country: addr.country || 'US',
      phone: personal.phone || ''
    },
    billing_address: {
      first_name: firstName,
      last_name: lastName,
      address1: addr.street || '',
      address2: addr.apt || '',
      city: addr.city || '',
      province: addr.state || '',
      zip: addr.zip || '',
      country: addr.country || 'US',
      phone: personal.phone || ''
    },
    note: noteLines.join('\n'),
    tags: 'pr, influencer-gifting',
    use_customer_default_address: false,
    shipping_line: { title: 'Influencer Gifting - Free Shipping', price: '0.00' }
  }
}}];
""".strip()


def n8n_request(method, path, data=None):
    url = f"{N8N_BASE_URL}/api/v1{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [n8n ERROR] {e.code}: {error_body[:500]}")
        raise


def fix_workflow(wf):
    nodes = wf.get("nodes", [])
    changes = []

    for node in nodes:
        # Fix 1: Build Draft Order code
        if node.get("name") == "Build Draft Order":
            node["parameters"]["jsCode"] = BUILD_DRAFT_ORDER_CODE
            changes.append("Fixed Build Draft Order code (removed ?., ??, corrupted $ refs)")

        # Fix 2: Prepare Airtable Payload - use correct Inbound table field names
        if node.get("name") == "Prepare Airtable Payload":
            fixed_at_code = r"""
var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};
var formData = $('Process Form Data').first().json;
var body = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = body.personal_info || {};

// Use only fields that exist in Inbound Applicants table
var fields = {
  "Email": formData.email || '',
  "Name": formData.firstName ? (formData.firstName + ' ' + (formData.lastName || '')).trim() : (personal.full_name || ''),
  "Instagram Handle": (personal.instagram || body.instagramHandle || '').replace(/^@/, ''),
  "Status": "New"
};

// Add TikTok if available
var tiktok = personal.tiktok || '';
if (tiktok && tiktok !== 'None') {
  fields["TikTok Handle"] = tiktok.replace(/^@/, '');
}

// Filter out empty values
var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{
    fields: cleanFields
  }],
  performUpsert: {
    fieldsToMergeOn: ["Email"]
  },
  typecast: true
}}];
""".strip()
            node["parameters"]["jsCode"] = fixed_at_code
            changes.append("Fixed Prepare Airtable Payload: use Inbound table field names")

        # Fix 3: Success Response - corrupted $json references
        if node.get("name") == "Success Response":
            rb = node.get("parameters", {}).get("responseBody", "")
            if ".draft_order" in rb and "$json.draft_order" not in rb:
                node["parameters"]["responseBody"] = '={{ JSON.stringify({ success: true, draft_order_id: $json.draft_order ? $json.draft_order.id : null, draft_order_name: $json.draft_order ? $json.draft_order.name : "", invoice_url: $json.draft_order ? $json.draft_order.invoice_url : "" }) }}'
                changes.append("Fixed Success Response: restored $json references")

        # Fix 4: Save to Airtable URL + continueOnFail
        if node.get("name") == "Save to Airtable":
            old_url = node["parameters"].get("url", "")
            node["parameters"]["url"] = AIRTABLE_INBOUND_URL
            # Also update the API key in headers
            header_params = node["parameters"].get("headerParameters", {}).get("parameters", [])
            for hp in header_params:
                if hp.get("name") == "Authorization":
                    hp["value"] = f"Bearer {AIRTABLE_API_KEY}"
            # Don't let Airtable errors kill PG branch
            node["onError"] = "continueRegularOutput"
            changes.append(f"Changed Airtable target + added continueOnFail")

        # Fix 5: Save to PostgreSQL - fix URL (https) + continueOnFail
        if node.get("name") == "Save to PostgreSQL":
            node["parameters"]["url"] = "https://orbitools.orbiters.co.kr/api/onzenna/gifting/save/"
            node["onError"] = "continueRegularOutput"
            changes.append("Fixed Save to PostgreSQL URL (https) + continueOnFail")

        # Fix 6: Prepare PG Payload - fix email extraction + continueOnFail
        if node.get("name") == "Prepare PG Payload":
            fixed_pg_code = r"""
var webhookData = $('Webhook').first().json;
var formData = webhookData.body || webhookData;

var personal = formData.personal_info || {};
var baby = formData.baby_info || {};
var addr = formData.shipping_address || {};
var child1 = (baby.child_1) || {};
var child2 = (baby.child_2) || {};

var payload = {
  email: (personal.email || formData.email || '').trim().toLowerCase(),
  full_name: personal.full_name || ((formData.firstName || '') + ' ' + (formData.lastName || '')).trim(),
  phone: personal.phone || formData.phone || '',
  instagram: personal.instagram || formData.instagramHandle || '',
  tiktok: personal.tiktok || '',
  child_1_birthday: child1.birthday || '',
  child_1_age_months: child1.age_months || null,
  child_2_birthday: child2.birthday || '',
  child_2_age_months: child2.age_months || null,
  selected_products: formData.selected_products || formData.selectedProducts || [],
  shipping_address: {
    street: addr.street || addr.address1 || '',
    apt: addr.apt || '',
    city: addr.city || '',
    state: addr.state || addr.province || '',
    zip: addr.zip || '',
    country: addr.country || 'US'
  }
};

// Add Shopify data if available from previous nodes
try {
  var shopifyResult = $('Create or Update Customer').first().json;
  if (shopifyResult && shopifyResult.customer) {
    payload.shopify_customer_id = String(shopifyResult.customer.id);
  }
} catch(e) {}

try {
  var draftResult = $('Create Draft Order').first().json;
  if (draftResult && draftResult.draft_order) {
    payload.shopify_draft_order_id = String(draftResult.draft_order.id);
    payload.shopify_draft_order_name = draftResult.draft_order.name || '';
  }
} catch(e) {}

return [{json: payload}];
""".strip()
            node["parameters"]["jsCode"] = fixed_pg_code
            node["onError"] = "continueRegularOutput"
            changes.append("Fixed Prepare PG Payload: email from personal_info + continueOnFail")

    if not changes:
        print("  No changes needed!")
        return None

    return {
        "name": wf.get("name", "Influencer Gifting"),
        "nodes": nodes,
        "connections": wf.get("connections", {}),
        "settings": wf.get("settings", {}),
    }, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workflow-id", default=DEFAULT_WORKFLOW_ID)
    args = parser.parse_args()

    wf_id = args.workflow_id
    print(f"Fetching workflow {wf_id}...")
    wf = n8n_request("GET", f"/workflows/{wf_id}")
    print(f"  Name: {wf.get('name')}")
    print(f"  Nodes: {len(wf.get('nodes', []))}")

    print("\nApplying fixes...")
    result = fix_workflow(wf)
    if result is None:
        return

    updated, changes = result
    for c in changes:
        print(f"  [FIX] {c}")

    if args.dry_run:
        print("\n[DRY RUN] Would apply above fixes. Use without --dry-run to deploy.")
        return

    if wf.get("active"):
        print("\nDeactivating workflow...")
        n8n_request("POST", f"/workflows/{wf_id}/deactivate")

    print("Updating workflow...")
    result = n8n_request("PUT", f"/workflows/{wf_id}", updated)
    print(f"  Updated: {len(result.get('nodes', []))} nodes")

    print("Reactivating workflow...")
    n8n_request("POST", f"/workflows/{wf_id}/activate")

    print("\nDone! Fixes applied.")


if __name__ == "__main__":
    main()
