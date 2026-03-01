"""Deploy the Onzenna Loyalty Survey page to Shopify.

Creates a Liquid section + page template + Shopify page at /pages/loyalty-survey.
The page collects Part 3 survey data and rewards completion with a discount code.

Usage:
    python tools/deploy_loyalty_survey_page.py
    python tools/deploy_loyalty_survey_page.py --dry-run
    python tools/deploy_loyalty_survey_page.py --unpublish     # hide page
    python tools/deploy_loyalty_survey_page.py --rollback      # remove assets

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (write_themes, write_content)
    .env: N8N_LOYALTY_SURVEY_WEBHOOK (webhook URL for survey submission)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"
N8N_WEBHOOK_URL = os.getenv("N8N_LOYALTY_SURVEY_WEBHOOK", "https://n8n.orbiters.co.kr/webhook/onzenna-loyalty-survey")

SECTION_KEY = "sections/loyalty-survey.liquid"
TEMPLATE_KEY = "templates/page.loyalty-survey.json"
PAGE_HANDLE = "loyalty-survey"
PAGE_TITLE = "Complete Your Profile"


# ── Shopify API Helpers ──────────────────────────────────────────
def shopify_request(method, path, data=None):
    url = f"https://{SHOP}/admin/api/{API_VERSION}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def get_active_theme_id():
    result = shopify_request("GET", "/themes.json")
    for theme in result.get("themes", []):
        if theme.get("role") == "main":
            print(f"  Active theme: {theme['name']} (ID: {theme['id']})")
            return theme["id"]
    raise RuntimeError("No active theme found")


def upload_theme_asset(theme_id, key, value):
    print(f"  Uploading: {key} ...")
    shopify_request("PUT", f"/themes/{theme_id}/assets.json", {
        "asset": {"key": key, "value": value}
    })
    print(f"  [OK] {key}")


def delete_theme_asset(theme_id, key):
    print(f"  Deleting: {key} ...")
    try:
        shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={key}")
        print(f"  [OK] Deleted {key}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  [SKIP] {key} not found")
        else:
            raise


def create_or_update_page(handle, title, template_suffix, published=True):
    result = shopify_request("GET", f"/pages.json?handle={handle}")
    pages = result.get("pages", [])

    page_data = {
        "page": {
            "title": title,
            "handle": handle,
            "template_suffix": template_suffix,
            "body_html": "",
            "published": published,
        }
    }

    if pages:
        page_id = pages[0]["id"]
        print(f"  Updating existing page (ID: {page_id}) ...")
        shopify_request("PUT", f"/pages/{page_id}.json", page_data)
        print(f"  [OK] Page updated (published={published})")
        return page_id
    else:
        print(f"  Creating new page ...")
        result = shopify_request("POST", "/pages.json", page_data)
        page_id = result["page"]["id"]
        print(f"  [OK] Page created (ID: {page_id}, published={published})")
        return page_id


# ── Liquid Section Builder ──────────────────────────────────────
def build_section_liquid():
    """Build the complete Liquid section with HTML + CSS + JS."""
    return f'''
{{% comment %}}
  Onzenna Loyalty Survey - Part 3
  Collects customer preference data, rewards with a discount code.
  Deployed by tools/deploy_loyalty_survey_page.py
{{% endcomment %}}

<div class="onz-loyalty-survey" id="onz-loyalty-survey">
  <!-- Loading state -->
  <div id="onz-loading" style="text-align:center; padding:40px;">
    <div class="onz-spinner"></div>
    <p>Loading...</p>
  </div>

  <!-- Login required -->
  <div id="onz-login-required" style="display:none; text-align:center; padding:40px;">
    <h2>Please sign in first</h2>
    <p>You need to be logged in to complete the loyalty survey.</p>
    <a href="/account/login?return_url=/pages/{PAGE_HANDLE}" class="onz-btn onz-btn-primary">Sign In</a>
  </div>

  <!-- Already completed -->
  <div id="onz-already-done" style="display:none; text-align:center; padding:40px;">
    <h2>You already completed the survey!</h2>
    <p>Your $10 gift card code:</p>
    <div class="onz-discount-reveal" id="onz-existing-code"></div>
    <p>Use this code at checkout — it works like store credit.</p>
  </div>

  <!-- Survey form -->
  <div id="onz-survey-form" style="display:none;">
    <div class="onz-header">
      <h2>Unlock Your $10 Gift Card</h2>
      <p>Answer 6 quick questions about your preferences and we will send you a $10 gift card for your next order.</p>
    </div>

    <form id="onz-form" onsubmit="return false;">
      <!-- Q1: Biggest challenges -->
      <div class="onz-question">
        <label class="onz-label">1. What are your biggest challenges right now?</label>
        <p class="onz-hint">Select all that apply</p>
        <div class="onz-checkbox-group" data-field="challenges">
          <label class="onz-check"><input type="checkbox" value="sleep"> Sleep</label>
          <label class="onz-check"><input type="checkbox" value="feeding"> Feeding</label>
          <label class="onz-check"><input type="checkbox" value="development"> Development</label>
          <label class="onz-check"><input type="checkbox" value="postpartum"> Postpartum recovery</label>
          <label class="onz-check"><input type="checkbox" value="products"> Finding the right products</label>
          <label class="onz-check"><input type="checkbox" value="routine"> Building a routine</label>
        </div>
      </div>

      <!-- Q2: Advice preference -->
      <div class="onz-question">
        <label class="onz-label">2. How do you prefer to get advice?</label>
        <p class="onz-hint">Select all that apply</p>
        <div class="onz-checkbox-group" data-field="advice_format">
          <label class="onz-check"><input type="checkbox" value="short_videos"> Short videos</label>
          <label class="onz-check"><input type="checkbox" value="articles"> Long-form articles</label>
          <label class="onz-check"><input type="checkbox" value="recommendations"> Product recommendations</label>
          <label class="onz-check"><input type="checkbox" value="community"> Community</label>
          <label class="onz-check"><input type="checkbox" value="expert_qa"> Expert Q&A</label>
        </div>
      </div>

      <!-- Q3: Product categories -->
      <div class="onz-question">
        <label class="onz-label">3. What types of products do you shop for most?</label>
        <p class="onz-hint">Select all that apply</p>
        <div class="onz-checkbox-group" data-field="product_categories">
          <label class="onz-check"><input type="checkbox" value="feeding_gear"> Feeding gear</label>
          <label class="onz-check"><input type="checkbox" value="skincare"> Skincare</label>
          <label class="onz-check"><input type="checkbox" value="clothing"> Clothing</label>
          <label class="onz-check"><input type="checkbox" value="nursery"> Nursery</label>
          <label class="onz-check"><input type="checkbox" value="toys"> Developmental toys</label>
          <label class="onz-check"><input type="checkbox" value="postpartum"> Postpartum recovery</label>
        </div>
      </div>

      <!-- Q4: Purchase frequency -->
      <div class="onz-question">
        <label class="onz-label">4. How often do you buy new baby products?</label>
        <div class="onz-radio-group" data-field="purchase_frequency">
          <label class="onz-radio"><input type="radio" name="purchase_frequency" value="weekly"> Weekly</label>
          <label class="onz-radio"><input type="radio" name="purchase_frequency" value="monthly"> Monthly</label>
          <label class="onz-radio"><input type="radio" name="purchase_frequency" value="every_few_months"> Every few months</label>
          <label class="onz-radio"><input type="radio" name="purchase_frequency" value="only_when_needed"> Only when needed</label>
        </div>
      </div>

      <!-- Q5: Product discovery -->
      <div class="onz-question">
        <label class="onz-label">5. Where do you discover new products?</label>
        <p class="onz-hint">Select all that apply</p>
        <div class="onz-checkbox-group" data-field="product_discovery">
          <label class="onz-check"><input type="checkbox" value="instagram"> Instagram</label>
          <label class="onz-check"><input type="checkbox" value="tiktok"> TikTok</label>
          <label class="onz-check"><input type="checkbox" value="google"> Google</label>
          <label class="onz-check"><input type="checkbox" value="word_of_mouth"> Word of mouth</label>
          <label class="onz-check"><input type="checkbox" value="blogs"> Blogs</label>
          <label class="onz-check"><input type="checkbox" value="pinterest"> Pinterest</label>
        </div>
      </div>

      <!-- Q6: Purchase criteria -->
      <div class="onz-question">
        <label class="onz-label">6. What matters most when buying baby products?</label>
        <p class="onz-hint">Select all that apply</p>
        <div class="onz-checkbox-group" data-field="purchase_criteria">
          <label class="onz-check"><input type="checkbox" value="safety"> Safety</label>
          <label class="onz-check"><input type="checkbox" value="brand_trust"> Brand trust</label>
          <label class="onz-check"><input type="checkbox" value="price"> Price</label>
          <label class="onz-check"><input type="checkbox" value="ingredients"> Korean / natural ingredients</label>
          <label class="onz-check"><input type="checkbox" value="aesthetic"> Aesthetic</label>
          <label class="onz-check"><input type="checkbox" value="reviews"> Reviews</label>
        </div>
      </div>

      <!-- SMS opt-in (required) -->
      <div style="margin:20px 0 8px;padding:14px;background:#f9f9f9;border:1px solid #eee;border-radius:8px;">
        <label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer;font-size:13px;color:#545454;line-height:1.5;">
          <input type="checkbox" id="onz-sms-consent" style="width:16px;height:16px;margin-top:2px;flex-shrink:0;accent-color:#4a6cf7;cursor:pointer;" />
          <span>I agree to receive SMS marketing messages from Onzenna at the number provided. Msg &amp; data rates may apply. Reply STOP to unsubscribe. <a href="/policies/privacy-policy" style="color:#4a6cf7;">Privacy policy</a>.</span>
        </label>
      </div>

      <button type="button" id="onz-submit-btn" class="onz-btn onz-btn-primary" onclick="submitLoyaltySurvey()">
        Unlock My Discount
      </button>
      <div id="onz-error" class="onz-error" style="display:none;"></div>
    </form>
  </div>

  <!-- Success state -->
  <div id="onz-success" style="display:none; text-align:center; padding:40px;">
    <h2>Your $10 gift card is ready!</h2>
    <div class="onz-discount-reveal" id="onz-new-code"></div>
    <p>Use this code at checkout — it works like <strong>$10 store credit</strong> on any order.</p>
    <a href="/collections/all" class="onz-btn onz-btn-primary" style="margin-top:20px;">Start Shopping</a>
  </div>
</div>

<style>
  .onz-loyalty-survey {{
    max-width: 640px;
    margin: 0 auto;
    padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .onz-header {{
    text-align: center;
    margin-bottom: 30px;
  }}
  .onz-header h2 {{
    font-size: 24px;
    margin-bottom: 8px;
  }}
  .onz-header p {{
    color: #666;
    font-size: 14px;
  }}
  .onz-question {{
    margin-bottom: 24px;
    padding-bottom: 24px;
    border-bottom: 1px solid #eee;
  }}
  .onz-label {{
    display: block;
    font-weight: 600;
    font-size: 15px;
    margin-bottom: 4px;
  }}
  .onz-hint {{
    font-size: 13px;
    color: #888;
    margin-bottom: 10px;
  }}
  .onz-checkbox-group,
  .onz-radio-group {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .onz-check,
  .onz-radio {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: 1px solid #ddd;
    border-radius: 20px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }}
  .onz-check:has(input:checked),
  .onz-radio:has(input:checked) {{
    background: #f0f4ff;
    border-color: #4a6cf7;
    color: #4a6cf7;
  }}
  .onz-check input,
  .onz-radio input {{
    display: none;
  }}
  .onz-btn {{
    display: inline-block;
    padding: 14px 32px;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s;
  }}
  .onz-btn-primary {{
    background: #4a6cf7;
    color: #fff;
  }}
  .onz-btn-primary:hover {{
    background: #3a5ce5;
  }}
  .onz-btn-primary:disabled {{
    background: #ccc;
    cursor: not-allowed;
  }}
  .onz-discount-reveal {{
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 16px 24px;
    background: #f0f4ff;
    border: 2px dashed #4a6cf7;
    border-radius: 12px;
    display: inline-block;
    margin: 16px 0;
    color: #4a6cf7;
  }}
  .onz-error {{
    color: #e53e3e;
    margin-top: 12px;
    font-size: 14px;
  }}
  .onz-spinner {{
    width: 32px;
    height: 32px;
    border: 3px solid #eee;
    border-top-color: #4a6cf7;
    border-radius: 50%;
    animation: onz-spin 0.6s linear infinite;
    margin: 0 auto 12px;
  }}
  @keyframes onz-spin {{
    to {{ transform: rotate(360deg); }}
  }}
  #onz-submit-btn {{
    width: 100%;
    margin-top: 16px;
  }}
</style>

<script>
(function() {{
  var WEBHOOK_URL = "{N8N_WEBHOOK_URL}";
  var STATUS_URL = "{N8N_WEBHOOK_URL.replace('/onzenna-loyalty-survey', '/onzenna-check-survey-status')}";

  // Check login status using Shopify Liquid
  var customerId = {{% if customer %}}{{{{ customer.id }}}}{{% else %}}null{{% endif %}};
  var customerEmail = {{% if customer %}}"{{{{ customer.email }}}}"{{% else %}}null{{% endif %}};

  var loadingEl = document.getElementById("onz-loading");
  var loginEl = document.getElementById("onz-login-required");
  var doneEl = document.getElementById("onz-already-done");
  var formEl = document.getElementById("onz-survey-form");
  var successEl = document.getElementById("onz-success");

  function showSection(el) {{
    loadingEl.style.display = "none";
    loginEl.style.display = "none";
    doneEl.style.display = "none";
    formEl.style.display = "none";
    successEl.style.display = "none";
    el.style.display = "block";
  }}

  // Init: show form (login not required, but if logged in we can check status)
  if (customerId) {{
    // Logged-in customer: check if already completed
    fetch(STATUS_URL + "?customer_id=" + customerId, {{
      method: "GET",
      headers: {{ "Content-Type": "application/json" }},
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.completed && data.gift_card_code) {{
        document.getElementById("onz-existing-code").textContent = data.gift_card_code;
        showSection(doneEl);
      }} else {{
        showSection(formEl);
      }}
    }})
    .catch(function() {{
      showSection(formEl);
    }});
  }} else {{
    // Guest: show form directly (no status check)
    showSection(formEl);
  }}

  // Make submit function global
  window.submitLoyaltySurvey = function() {{
    var btn = document.getElementById("onz-submit-btn");
    var errorEl = document.getElementById("onz-error");
    errorEl.style.display = "none";
    btn.disabled = true;
    btn.textContent = "Submitting...";

    // Collect checkbox group values
    function getChecked(field) {{
      var els = document.querySelectorAll('[data-field="' + field + '"] input:checked');
      return Array.from(els).map(function(el) {{ return el.value; }});
    }}

    // Collect radio value
    function getRadio(name) {{
      var el = document.querySelector('input[name="' + name + '"]:checked');
      return el ? el.value : "";
    }}

    var payload = {{
      form_type: "onzenna_loyalty_survey",
      customer_id: customerId,
      customer_email: customerEmail,
      submitted_at: new Date().toISOString(),
      survey_data: {{
        challenges: getChecked("challenges"),
        advice_format: getChecked("advice_format"),
        product_categories: getChecked("product_categories"),
        purchase_frequency: getRadio("purchase_frequency"),
        product_discovery: getChecked("product_discovery"),
        purchase_criteria: getChecked("purchase_criteria"),
      }},
    }};

    // Validate: at least one answer
    var hasAnswer = false;
    var sd = payload.survey_data;
    if (sd.challenges.length || sd.advice_format.length || sd.product_categories.length ||
        sd.purchase_frequency || sd.product_discovery.length || sd.purchase_criteria.length) {{
      hasAnswer = true;
    }}

    if (!hasAnswer) {{
      errorEl.textContent = "Please answer at least one question.";
      errorEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Unlock My Discount";
      return;
    }}

    // Validate SMS consent (required)
    if (!document.getElementById("onz-sms-consent").checked) {{
      errorEl.textContent = "Please agree to receive SMS messages to continue.";
      errorEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Unlock My Discount";
      return;
    }}

    // Try webhook first, fallback to showing code directly
    var DISCOUNT_CODE = "";  // fallback — gift card code comes from webhook

    function revealError() {{
      // Gift card couldn't be generated — show a helpful message
      document.getElementById("onz-new-code").textContent = "";
      document.getElementById("onz-new-code").insertAdjacentHTML(
        "afterend",
        "<p style='color:#c00;margin-top:8px;'>Something went wrong generating your gift card. Please contact us and we will send it manually.</p>"
      );
      showSection(successEl);
    }}

    // Send survey to webhook — webhook returns gift card code
    fetch(WEBHOOK_URL, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.gift_card_code) {{
        document.getElementById("onz-new-code").textContent = data.gift_card_code;
        showSection(successEl);
      }} else {{
        revealError();
      }}
    }})
    .catch(function(err) {{
      revealError();
    }});
  }};
}})();
</script>

{{% schema %}}
{{
  "name": "Loyalty Survey",
  "tag": "section",
  "class": "loyalty-survey-section"
}}
{{% endschema %}}
'''


def build_page_template():
    """Build the JSON template that uses the loyalty-survey section."""
    return json.dumps({
        "sections": {
            "main": {
                "type": "loyalty-survey",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# ── Deploy / Rollback ──────────────────────────────────────────
def deploy(dry_run=False, published=True):
    print(f"\n{'=' * 60}")
    print(f"  Deploy Loyalty Survey Page")
    print(f"  Shop: {SHOP}")
    print(f"  Published: {published}")
    if dry_run:
        print(f"  Mode: DRY RUN")
    print(f"{'=' * 60}\n")

    section_liquid = build_section_liquid()
    page_template = build_page_template()

    if dry_run:
        print(f"  [DRY RUN] Section size: {len(section_liquid)} chars")
        print(f"  [DRY RUN] Template: {page_template[:100]}...")
        print(f"  [DRY RUN] Would upload: {SECTION_KEY}")
        print(f"  [DRY RUN] Would upload: {TEMPLATE_KEY}")
        print(f"  [DRY RUN] Would create page: /pages/{PAGE_HANDLE}")
        return

    theme_id = get_active_theme_id()

    # Upload section
    upload_theme_asset(theme_id, SECTION_KEY, section_liquid)

    # Upload template
    upload_theme_asset(theme_id, TEMPLATE_KEY, page_template)

    # Create/update page
    create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "loyalty-survey", published=published)

    page_url = f"https://{SHOP.replace('.myshopify.com', '')}.com/pages/{PAGE_HANDLE}"
    print(f"\n  Page URL: {page_url}")
    if not published:
        print(f"  (Page is hidden -- only accessible by direct URL)")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


def rollback():
    print(f"\n{'=' * 60}")
    print(f"  Rollback Loyalty Survey Page")
    print(f"{'=' * 60}\n")

    theme_id = get_active_theme_id()
    delete_theme_asset(theme_id, SECTION_KEY)
    delete_theme_asset(theme_id, TEMPLATE_KEY)

    # Check if page exists and note it (don't auto-delete)
    result = shopify_request("GET", f"/pages.json?handle={PAGE_HANDLE}")
    pages = result.get("pages", [])
    if pages:
        print(f"\n  [NOTE] Page still exists (ID: {pages[0]['id']})")
        print(f"  Delete manually: Shopify Admin > Online Store > Pages > {PAGE_TITLE}")

    print(f"\n{'=' * 60}")
    print(f"  ROLLBACK DONE")
    print(f"{'=' * 60}\n")


# ── CLI ──────────────────────────────────────────────────────
def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Deploy Onzenna Loyalty Survey page to Shopify")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    parser.add_argument("--unpublish", action="store_true", help="Deploy as hidden (test mode)")
    parser.add_argument("--rollback", action="store_true", help="Remove theme assets")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    if args.rollback:
        rollback()
    else:
        deploy(dry_run=args.dry_run, published=not args.unpublish)


if __name__ == "__main__":
    main()
