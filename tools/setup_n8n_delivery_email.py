"""Add delivery notification email to Shipped->Delivered workflow.

When a creator's sample is confirmed delivered, sends an email from
affiliates@onzenna.com with:
  - Brand-specific content guidelines (PDF attached)
  - Product-specific hashtags & tags
  - 14-day posting deadline
  - T&C summary

Modifies workflow: [WJ TEST] Shipped -> Delivered (2vsXyHtjo79hnFoD)
Adds nodes after "Update Airtable Delivered":
  -> Prepare Delivery Email (Code)
  -> Download Grosmimi PDF (HTTP) / Download ChaenMom PDF (HTTP)
  -> Send Delivery Email (Gmail)

Usage:
    python tools/setup_n8n_delivery_email.py
    python tools/setup_n8n_delivery_email.py --dry-run
"""
import os
import sys
import json
import uuid
import base64
import urllib.request
import urllib.error
import argparse

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env

load_env()

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
WF_ID = "k61gzrshITfju33V"   # PROD: Shipped -> Delivered (migrated 2026-03-18)

# n8n credential IDs
GMAIL_CRED_ID = "ZSCspnGLmbDXJMBu"
GMAIL_CRED_NAME = "Onzenna Gmail (affiliates@onzenna.com)"

# Content guideline PDFs
GUIDELINE_DIR = "Z:/Orbiters/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/Shared/ONZ Creator Collab/Content guideline"
GROSMIMI_PPSU_PDF = os.path.join(GUIDELINE_DIR, "Grosmimi (PPSU) Content Guidelines v2.pdf")
GROSMIMI_SS_PDF = os.path.join(GUIDELINE_DIR, "Grosmimi (Stainless) Content Guidelines v1.pdf")
CHAENMOM_PDF = os.path.join(
    GUIDELINE_DIR, "CHA&MOM (PS Cream-Phyto Seline) Content Guidelines v2.pdf"
)
NAEIAE_PDF = os.path.join(GUIDELINE_DIR, "Naeiae (Pop rice snck) Content Guidelines v2.pdf")


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


def encode_pdf(filepath):
    """Read PDF and return base64 string."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# ============================================================
# Email HTML template
# ============================================================
EMAIL_HTML = r"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
  <img src="https://cdn.shopify.com/s/files/1/0915/8367/5058/files/onzenna-logo-dark.png"
       alt="Onzenna" style="height: 40px; margin-bottom: 24px; display: block;" />

  <h2 style="font-size: 22px; margin-bottom: 8px;">Your sample has been delivered!</h2>

  <p style="font-size: 15px; line-height: 1.6; color: #555;">
    Hi <strong>${name}</strong>, great news &mdash; your <strong>${productNames}</strong>
    sample has been delivered! We can&rsquo;t wait to see your content.
  </p>

  <div style="background: #f9f9f9; border-radius: 8px; padding: 20px; margin: 20px 0;">
    <h3 style="font-size: 16px; margin-top: 0;">Content Requirements</h3>
    <ul style="padding-left: 20px; font-size: 14px; line-height: 1.8; color: #555;">
      <li>Total video length: <strong>30 seconds</strong></li>
      <li>Must include <strong>voiceover + subtitles</strong></li>
      <li>Use royalty-free music only</li>
      <li>Post within <strong>14 days</strong> of receiving the product</li>
      <li>Onzenna may repost your content with credit</li>
    </ul>
  </div>

  <div style="background: #f0f7ff; border-radius: 8px; padding: 20px; margin: 20px 0;">
    <h3 style="font-size: 16px; margin-top: 0;">Required Tags &amp; Hashtags</h3>
    <p style="font-size: 14px; line-height: 1.6; color: #555;">
      <strong>Tag us:</strong> ${tagsList}
    </p>
    <p style="font-size: 14px; line-height: 1.6; color: #555;">
      <strong>Hashtags:</strong> ${hashtagsList}
    </p>
  </div>

  <p style="font-size: 14px; line-height: 1.6; color: #555;">
    We&rsquo;ve attached the full <strong>Content Guidelines</strong> PDF for your reference.
    Please review it before creating your content.
  </p>

  <p style="font-size: 14px; line-height: 1.6; color: #555;">
    Questions? Just reply to this email &mdash; we&rsquo;re here to help!
  </p>

  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />

  <p style="color: #999; font-size: 12px;">
    Thank you for being an Onzenna Creator!<br/>
    &mdash; The Onzenna Team
  </p>
</div>"""


# ============================================================
# Prepare Delivery Email - Code node JS
# ============================================================
PREPARE_EMAIL_CODE = r"""// Determine brand from order products, build email HTML + binary PDF
const updateItems = $input.all();
const prepItems = $('Prepare Order Lookup').all();
const shopifyItems = $('Check Shopify Orders').all();
const results = [];

// PDF base64 data (embedded)
const GROSMIMI_PPSU_PDF = '__GROSMIMI_PPSU_PDF_B64__';
const GROSMIMI_SS_PDF = '__GROSMIMI_SS_PDF_B64__';
const CHAENMOM_PDF = '__CHAENMOM_PDF_B64__';
const NAEIAE_PDF = '__NAEIAE_PDF_B64__';

// Brand detection from Shopify order line items
function detectBrands(orderData) {
  const orders = orderData.orders || [];
  const brands = new Set();
  const productNames = [];

  for (const order of orders) {
    for (const item of (order.line_items || [])) {
      const title = (item.title || '').toLowerCase();
      productNames.push(item.title || '');

      // Stainless products (check before generic grosmimi)
      if (title.includes('stainless')) {
        brands.add('grosmimi_stainless');
      }
      // PPSU products
      else if (title.includes('grosmimi') || title.includes('ppsu') ||
               title.includes('bottle') || title.includes('essten')) {
        brands.add('grosmimi_ppsu');
      }
      // Straw cup / tumbler without stainless = PPSU
      else if (title.includes('straw cup') || title.includes('tumbler')) {
        brands.add('grosmimi_ppsu');
      }
      // CHA&MOM
      if (title.includes('cha') || title.includes('phyto') ||
          title.includes('ps cream') || title.includes('seline') ||
          title.includes('cream') || title.includes('lotion')) {
        brands.add('chaenmom');
      }
      // Naeiae
      if (title.includes('naeiae') || title.includes('rice') ||
          title.includes('snack') || title.includes('pop rice')) {
        brands.add('naeiae');
      }
    }
  }
  if (brands.size === 0) brands.add('grosmimi_ppsu'); // default
  return { brands: Array.from(brands), productNames };
}

// Product-specific hashtags for Grosmimi
function getGrosmimiHashtags(productNames) {
  const tags = ['#Grosmimi', '#Onzenna'];
  const combined = productNames.join(' ').toLowerCase();

  if (combined.includes('bottle') || combined.includes('feeding')) {
    tags.push('#PPSUbabybottle', '#babybottle');
  }
  if (combined.includes('straw cup') && !combined.includes('stainless')) {
    tags.push('#PPSUstrawcup', '#Strawcup', '#PPSU');
  }
  if (combined.includes('tumbler') && !combined.includes('stainless')) {
    tags.push('#PPSUtumbler', '#tumbler', '#PPSU');
  }
  if (combined.includes('stainless') && combined.includes('straw')) {
    tags.push('#Foodgradestrawcup', '#strawcup', '#stainlesssteelcup');
  }
  if (combined.includes('stainless') && combined.includes('tumbler')) {
    tags.push('#Foodgradetumbler', '#tumbler', '#stainlesssteeltumbler');
  }
  // Default if no specific match
  if (tags.length === 2) {
    tags.push('#PPSUstrawcup', '#Strawcup', '#PPSU', '#sippycup');
  }
  return [...new Set(tags)];
}

function getChaenmomHashtags() {
  return ['#PSCream', '#Babycream', '#babyskincare', '#CHA&MOM', '#Onzenna'];
}

function getTagsList(brands) {
  const tags = [];
  if (brands.includes('grosmimi_ppsu') || brands.includes('grosmimi_stainless')) {
    tags.push('@onzenna_official (IG)', '@grosmimi_usa (IG & TikTok)');
  }
  if (brands.includes('chaenmom')) {
    tags.push('@onzenna.official (IG & TikTok)');
  }
  if (brands.includes('naeiae')) {
    tags.push('@onzenna_official (IG)', '@naeiae_usa (IG & TikTok)');
  }
  if (tags.length === 0) tags.push('@onzenna_official (IG & TikTok)');
  return tags.join(', ');
}

for (let i = 0; i < updateItems.length; i++) {
  const prevData = prepItems[i] ? prepItems[i].json : {};
  const shopifyData = shopifyItems[i] ? shopifyItems[i].json : {};
  const updateData = updateItems[i].json;

  const email = updateData.email || prevData.email || '';
  const username = updateData.username || prevData.username || '';
  const name = prevData.name || username || 'Creator';

  if (!email) continue;

  const { brands, productNames } = detectBrands(shopifyData);

  // Build hashtags
  let hashtags = [];
  if (brands.includes('grosmimi_ppsu') || brands.includes('grosmimi_stainless')) {
    hashtags = hashtags.concat(getGrosmimiHashtags(productNames));
  }
  if (brands.includes('chaenmom')) {
    hashtags = hashtags.concat(getChaenmomHashtags());
  }
  if (brands.includes('naeiae')) {
    hashtags = hashtags.concat(['#Naeiae', '#Onzenna', '#popricesnack', '#babysnack', '#organicsnack']);
  }
  hashtags = [...new Set(hashtags)];

  const tagsList = getTagsList(brands);
  const hashtagsList = hashtags.join(' ');
  const productDisplay = productNames.length > 0 ? productNames.join(', ') : 'Onzenna';

  // Build email HTML
  let html = `__EMAIL_HTML__`;
  html = html.replace(/\$\{name\}/g, name);
  html = html.replace(/\$\{productNames\}/g, productDisplay);
  html = html.replace(/\$\{tagsList\}/g, tagsList);
  html = html.replace(/\$\{hashtagsList\}/g, hashtagsList);

  // Subject line
  const hasGrosmimi = brands.includes('grosmimi_ppsu') || brands.includes('grosmimi_stainless');
  const hasChaenmom = brands.includes('chaenmom');
  const hasNaeiae = brands.includes('naeiae');
  const brandCount = (hasGrosmimi ? 1 : 0) + (hasChaenmom ? 1 : 0) + (hasNaeiae ? 1 : 0);
  let brandName = 'Onzenna';
  if (brandCount === 1) {
    if (hasGrosmimi) brandName = 'Grosmimi';
    else if (hasChaenmom) brandName = 'CHA&MOM';
    else if (hasNaeiae) brandName = 'Naeiae';
  }
  const subject = 'Your ' + brandName + ' sample has been delivered! Here are your content guidelines';

  // Determine which PDF(s) to attach
  const binary = {};
  if (brands.includes('grosmimi_ppsu')) {
    binary['grosmimi_ppsu_pdf'] = {
      data: GROSMIMI_PPSU_PDF,
      mimeType: 'application/pdf',
      fileName: 'Grosmimi_PPSU_Content_Guidelines.pdf'
    };
  }
  if (brands.includes('grosmimi_stainless')) {
    binary['grosmimi_ss_pdf'] = {
      data: GROSMIMI_SS_PDF,
      mimeType: 'application/pdf',
      fileName: 'Grosmimi_Stainless_Content_Guidelines.pdf'
    };
  }
  if (brands.includes('chaenmom')) {
    binary['chaenmom_pdf'] = {
      data: CHAENMOM_PDF,
      mimeType: 'application/pdf',
      fileName: 'CHA_MOM_Content_Guidelines.pdf'
    };
  }
  if (brands.includes('naeiae')) {
    binary['naeiae_pdf'] = {
      data: NAEIAE_PDF,
      mimeType: 'application/pdf',
      fileName: 'Naeiae_Content_Guidelines.pdf'
    };
  }

  results.push({
    json: {
      to: email,
      subject: subject,
      html: html,
      brands: brands,
      username: username,
      name: name
    },
    binary: binary
  });
}

if (results.length === 0) {
  return [];
}
return results;
"""


def build_email_nodes(grosmimi_ppsu_b64, grosmimi_ss_b64, chaenmom_b64, naeiae_b64):
    """Build the n8n nodes for delivery email."""
    # Prepare the Code with embedded PDF data and HTML
    code = PREPARE_EMAIL_CODE
    code = code.replace("__GROSMIMI_PPSU_PDF_B64__", grosmimi_ppsu_b64)
    code = code.replace("__GROSMIMI_SS_PDF_B64__", grosmimi_ss_b64)
    code = code.replace("__CHAENMOM_PDF_B64__", chaenmom_b64)
    code = code.replace("__NAEIAE_PDF_B64__", naeiae_b64)
    code = code.replace("__EMAIL_HTML__", EMAIL_HTML.replace("`", "\\`").replace("${", "${"))

    nodes = []

    # 1. Prepare Delivery Email (Code)
    nodes.append(
        {
            "id": str(uuid.uuid4()),
            "name": "Prepare Delivery Email",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2000, 300],
            "parameters": {"jsCode": code, "mode": "runOnceForAllItems"},
        }
    )

    # 2. Send Delivery Email (Gmail with attachment)
    nodes.append(
        {
            "id": str(uuid.uuid4()),
            "name": "Send Delivery Email",
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.1,
            "position": [2220, 300],
            "parameters": {
                "sendTo": "={{ $json.to }}",
                "subject": "={{ $json.subject }}",
                "message": "={{ $json.html }}",
                "options": {
                    "appendAttribution": False,
                    "attachmentsUi": {
                        "attachmentsBinary": [
                            {"property": "grosmimi_ppsu_pdf"},
                            {"property": "grosmimi_ss_pdf"},
                            {"property": "chaenmom_pdf"},
                            {"property": "naeiae_pdf"},
                        ],
                    },
                },
            },
            "credentials": {
                "gmailOAuth2": {"id": GMAIL_CRED_ID, "name": GMAIL_CRED_NAME}
            },
        }
    )

    return nodes


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Add delivery email to Shipped->Delivered workflow")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print("  Add Delivery Email to Shipped->Delivered Workflow")
    print(f"  Workflow: {WF_ID}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"{'=' * 60}\n")

    # Check PDFs exist
    pdf_map = [
        (GROSMIMI_PPSU_PDF, "Grosmimi PPSU"),
        (GROSMIMI_SS_PDF, "Grosmimi Stainless"),
        (CHAENMOM_PDF, "CHA&MOM"),
        (NAEIAE_PDF, "Naeiae"),
    ]
    for path, name in pdf_map:
        resolved = os.path.normpath(path)
        if os.path.exists(resolved):
            size = os.path.getsize(resolved)
            print(f"  [OK] {name} PDF: {size:,} bytes")
        else:
            print(f"  [ERROR] {name} PDF not found: {resolved}")
            sys.exit(1)

    # Encode PDFs
    print("\n  Encoding PDFs to base64...")
    grosmimi_ppsu_b64 = encode_pdf(os.path.normpath(GROSMIMI_PPSU_PDF))
    grosmimi_ss_b64 = encode_pdf(os.path.normpath(GROSMIMI_SS_PDF))
    chaenmom_b64 = encode_pdf(os.path.normpath(CHAENMOM_PDF))
    naeiae_b64 = encode_pdf(os.path.normpath(NAEIAE_PDF))
    print(f"    Grosmimi PPSU: {len(grosmimi_ppsu_b64):,} chars")
    print(f"    Grosmimi Stainless: {len(grosmimi_ss_b64):,} chars")
    print(f"    CHA&MOM: {len(chaenmom_b64):,} chars")
    print(f"    Naeiae: {len(naeiae_b64):,} chars")

    if args.dry_run:
        email_nodes = build_email_nodes(grosmimi_ppsu_b64, grosmimi_ss_b64, chaenmom_b64, naeiae_b64)
        print(f"\n  [DRY RUN] Would add {len(email_nodes)} nodes:")
        for n in email_nodes:
            print(f"    - {n['name']} ({n['type']})")
        print("\n  Connections:")
        print("    Update Airtable Delivered -> Prepare Delivery Email")
        print("    Prepare Delivery Email -> Send Delivery Email")
        return

    # Fetch current workflow
    print("\n  Fetching workflow...")
    wf = n8n_request("GET", f"/workflows/{WF_ID}")
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})

    print(f"  Current nodes: {len(nodes)}")

    # Remove existing email nodes if present (for idempotent re-runs)
    remove_names = {"Prepare Delivery Email", "Send Delivery Email"}
    nodes = [n for n in nodes if n.get("name") not in remove_names]
    for name in remove_names:
        connections.pop(name, None)

    # Build and add new nodes
    email_nodes = build_email_nodes(grosmimi_ppsu_b64, grosmimi_ss_b64, chaenmom_b64, naeiae_b64)
    nodes.extend(email_nodes)

    # Wire: Update Airtable Delivered -> Prepare Delivery Email -> Send Delivery Email
    connections["Update Airtable Delivered"] = {
        "main": [[{"node": "Prepare Delivery Email", "type": "main", "index": 0}]]
    }
    connections["Prepare Delivery Email"] = {
        "main": [[{"node": "Send Delivery Email", "type": "main", "index": 0}]]
    }

    # PUT updated workflow
    print("  Updating workflow...")
    payload = {
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
        "name": wf.get("name", ""),
    }
    result = n8n_request("PUT", f"/workflows/{WF_ID}", payload)

    print(f"\n  Updated: {result.get('name', '')}")
    print(f"  Total nodes: {len(result.get('nodes', []))}")

    # Verify
    print("\n  Verification:")
    for n in result.get("nodes", []):
        name = n.get("name", "")
        ntype = n.get("type", "")
        if name in remove_names | {"Update Airtable Delivered"}:
            if ntype == "n8n-nodes-base.code":
                code_len = len(n.get("parameters", {}).get("jsCode", ""))
                print(f"    {name}: Code ({code_len:,} chars)")
            elif ntype == "n8n-nodes-base.gmail":
                print(f"    {name}: Gmail (affiliates@onzenna.com)")
            else:
                print(f"    {name}: {ntype}")

    conns = result.get("connections", {})
    print("\n  Connection chain (last 3):")
    for src in ["Check Delivery Status", "Update Airtable Delivered", "Prepare Delivery Email"]:
        if src in conns:
            for outputs in conns[src].get("main", []):
                for t in outputs:
                    print(f"    {src} -> {t['node']}")

    print(f"\n{'=' * 60}")
    print("  DONE - Delivery email added to workflow")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
