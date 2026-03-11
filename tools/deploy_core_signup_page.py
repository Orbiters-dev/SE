"""Deploy the Onzenna Core Signup page (Part 1) to Shopify.

Creates a Liquid section + page template + Shopify page at /pages/core-signup.
Collects Q4-Q7: journey stage, baby birth month, other children, creator interest.
This is a standalone test page -- in production, these questions go into Checkout UI Extension.

Usage:
    python tools/deploy_core_signup_page.py
    python tools/deploy_core_signup_page.py --dry-run
    python tools/deploy_core_signup_page.py --unpublish     # deploy hidden
    python tools/deploy_core_signup_page.py --rollback      # remove assets

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (write_themes, write_content)
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
N8N_WEBHOOK_URL = os.getenv("N8N_CORE_SIGNUP_WEBHOOK", "https://n8n.orbiters.co.kr/webhook/onzenna-core-signup")
N8N_METAFIELD_WEBHOOK = "https://n8n.orbiters.co.kr/webhook/onzenna-save-metafields"

SECTION_KEY = "sections/core-signup.liquid"
TEMPLATE_KEY = "templates/page.core-signup.json"
PAGE_HANDLE = "core-signup"
PAGE_TITLE = "Tell Us About You"


# -- Shopify API Helpers --
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


# -- Liquid Section Builder --
def build_section_liquid():
    logo_url = "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/logo_500w_x320.png?v=1769045135"
    return f'''
{{% comment %}}
  Onzenna Core Signup - Part 1
  Pixel-perfect replica of Onzenna's Shopify checkout.
  Deployed by tools/deploy_core_signup_page.py
{{% endcomment %}}

<!-- Hide site chrome -->
<style>
  header,.header,.site-header,.shopify-section-header,
  footer,.footer,.site-footer,.shopify-section-footer,
  .announcement-bar,.shopify-section-announcement-bar {{ display:none!important; }}
  body {{ background:#fff!important; margin:0!important; padding:0!important; }}
  .main-content,main,#MainContent,#main {{ padding:0!important; margin:0!important; max-width:100%!important; }}
</style>

<div class="ck" id="onz-core-signup">
  <div class="ck-layout">
    <!-- ========== LEFT COLUMN ========== -->
    <div class="ck-left">
      <!-- Logo + cart icon header -->
      <div class="ck-topbar">
        <a href="/" class="ck-logo"><img src="{logo_url}" alt="Onzenna" /></a>
        <a href="/cart" class="ck-cart-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>
        </a>
      </div>

      <div class="ck-form-area">
        <!-- Already completed -->
        <div id="onz-already-done" style="display:none;">
          <h2 class="ck-h2">Already completed</h2>
          <p class="ck-p">We already have your information on file.</p>
          <a href="/" class="ck-pay-btn" style="display:inline-block;margin-top:16px;text-align:center;">Return to store</a>
        </div>

        <!-- ===== FORM ===== -->
        <div id="onz-signup-form" style="display:none;">

          <!-- Express checkout -->
          <p class="ck-express-label">Express checkout</p>
          <div class="ck-express-btns">
            <button type="button" class="ck-express ck-express-shop" disabled>
              <svg viewBox="0 0 341 81" fill="#fff" xmlns="http://www.w3.org/2000/svg" height="20"><path d="M227.297 0C220.96 0 216.308 4.652 216.308 10.67v1.603l-5.07 6.236c-.756.94-.756 2.07 0 2.822l5.07 6.236v1.603c0 6.019 4.652 10.67 10.989 10.67h113.484c6.337 0 10.989-4.651 10.989-10.67V10.67C351.77 4.652 347.118 0 340.781 0H227.297z" fill="#5A31F4"/><text x="255" y="28" font-family="Arial" font-weight="bold" font-size="22" fill="#fff">shop</text></svg>
            </button>
            <button type="button" class="ck-express ck-express-paypal" disabled>
              <svg height="18" viewBox="0 0 101 24" xmlns="http://www.w3.org/2000/svg"><text x="5" y="19" font-family="Arial" font-weight="bold" font-size="20" fill="#003087">Pay</text><text x="42" y="19" font-family="Arial" font-weight="bold" font-size="20" fill="#009CDE">Pal</text></svg>
            </button>
            <button type="button" class="ck-express ck-express-gpay" disabled>
              <svg height="18" viewBox="0 0 80 24" xmlns="http://www.w3.org/2000/svg"><text x="5" y="19" font-family="Arial" font-weight="600" font-size="18" fill="#5f6368">G Pay</text></svg>
            </button>
          </div>
          <div class="ck-or"><span>OR</span></div>

          <!-- Contact -->
          <div class="ck-section-hdr">
            <h2 class="ck-h2">Contact</h2>
            <a href="/account/login?return_url=/pages/{PAGE_HANDLE}" class="ck-link-sm">Sign in</a>
          </div>
          <div class="ck-float-field">
            <input type="email" id="ck-email" class="ck-finput" placeholder=" "
              value="{{% if customer %}}{{{{ customer.email }}}}{{% endif %}}" />
            <label for="ck-email" class="ck-flabel">Email</label>
          </div>
          <label class="ck-checkbox">
            <input type="checkbox" checked />
            <span class="ck-checkmark"></span>
            Email me with news and offers
          </label>

          <!-- Delivery -->
          <h2 class="ck-h2" style="margin-top:28px;">Delivery</h2>
          <div class="ck-float-field" style="margin-top:12px;">
            <select id="ck-country" class="ck-finput ck-fselect">
              <option value="US" selected>United States</option>
              <option value="CA">Canada</option>
              <option value="KR">South Korea</option>
            </select>
            <label class="ck-flabel">Country/Region</label>
          </div>
          <div style="display:flex;gap:10px;">
            <div class="ck-float-field" style="flex:1;">
              <input type="text" id="ck-firstname" class="ck-finput" placeholder=" "
                value="{{% if customer %}}{{{{ customer.first_name }}}}{{% endif %}}" />
              <label class="ck-flabel">First name</label>
            </div>
            <div class="ck-float-field" style="flex:1;">
              <input type="text" id="ck-lastname" class="ck-finput" placeholder=" "
                value="{{% if customer %}}{{{{ customer.last_name }}}}{{% endif %}}" />
              <label class="ck-flabel">Last name</label>
            </div>
          </div>
          <div class="ck-float-field">
            <input type="text" id="ck-address1" class="ck-finput" placeholder=" "
              value="{{% if customer.default_address %}}{{{{ customer.default_address.address1 }}}}{{% endif %}}" />
            <label class="ck-flabel">Address</label>
          </div>
          <div class="ck-float-field">
            <input type="text" id="ck-address2" class="ck-finput" placeholder=" "
              value="{{% if customer.default_address %}}{{{{ customer.default_address.address2 }}}}{{% endif %}}" />
            <label class="ck-flabel">Apartment, suite, etc. (optional)</label>
          </div>
          <div style="display:flex;gap:10px;">
            <div class="ck-float-field" style="flex:1;">
              <input type="text" id="ck-city" class="ck-finput" placeholder=" "
                value="{{% if customer.default_address %}}{{{{ customer.default_address.city }}}}{{% endif %}}" />
              <label class="ck-flabel">City</label>
            </div>
            <div class="ck-float-field" style="flex:1;">
              <input type="text" id="ck-state" class="ck-finput" placeholder=" "
                value="{{% if customer.default_address %}}{{{{ customer.default_address.province }}}}{{% endif %}}" />
              <label class="ck-flabel">State</label>
            </div>
            <div class="ck-float-field" style="flex:1;">
              <input type="text" id="ck-zip" class="ck-finput" placeholder=" "
                value="{{% if customer.default_address %}}{{{{ customer.default_address.zip }}}}{{% endif %}}" />
              <label class="ck-flabel">ZIP code</label>
            </div>
          </div>
          <div class="ck-float-field">
            <input type="tel" id="ck-phone" class="ck-finput" placeholder=" "
              value="{{% if customer.default_address %}}{{{{ customer.default_address.phone }}}}{{% elsif customer.phone %}}{{{{ customer.phone }}}}{{% endif %}}" />
            <label class="ck-flabel">Phone</label>
          </div>

          <!-- Baby's Date of Birth (matches real checkout) -->
          <h2 class="ck-h2" style="margin-top:28px;">Baby's Date of Birth</h2>
          <p class="ck-p-sm">Tell us your baby's birthdate (optional)</p>
          <div class="ck-row3">
            <div class="ck-float-field">
              <select id="onz-birth-year" class="ck-finput ck-fselect"><option value="">Year</option></select>
              <label class="ck-flabel">Year</label>
            </div>
            <div class="ck-float-field">
              <select id="onz-birth-month" class="ck-finput ck-fselect">
                <option value="">Month</option>
                <option value="01">January</option><option value="02">February</option>
                <option value="03">March</option><option value="04">April</option>
                <option value="05">May</option><option value="06">June</option>
                <option value="07">July</option><option value="08">August</option>
                <option value="09">September</option><option value="10">October</option>
                <option value="11">November</option><option value="12">December</option>
              </select>
              <label class="ck-flabel">Month</label>
            </div>
            <div class="ck-float-field">
              <select id="onz-birth-day" class="ck-finput ck-fselect"><option value="">Day</option></select>
              <label class="ck-flabel">Day</label>
            </div>
          </div>
          <p class="ck-p-xs">By providing this information, you consent to its use for marketing and personalization purposes, such as birthday-related offers or product recommendations.</p>

          <!-- Personalize (our custom section) -->
          <h2 class="ck-h2" style="margin-top:28px;">Personalize</h2>
          <p class="ck-p-sm">Help us recommend the right products for you.</p>

          <form id="onz-form" onsubmit="return false;">
            <!-- Journey Stage -->
            <div class="ck-field">
              <label class="ck-field-label">Where are you in your parenting journey?</label>
              <div class="ck-opts">
                <label class="ck-opt"><input type="radio" name="journey_stage" value="trying_to_conceive"><span class="ck-oradio"></span>Trying to conceive</label>
                <label class="ck-opt"><input type="radio" name="journey_stage" value="pregnant"><span class="ck-oradio"></span>Pregnant</label>
                <label class="ck-opt"><input type="radio" name="journey_stage" value="new_mom_0_12m"><span class="ck-oradio"></span>New parent (baby 0-12 months)</label>
                <label class="ck-opt"><input type="radio" name="journey_stage" value="mom_toddler_1_3y"><span class="ck-oradio"></span>Toddler parent (1-3 years)</label>
                <label class="ck-opt"><input type="radio" name="journey_stage" value="gift_shopping"><span class="ck-oradio"></span>Shopping for a gift</label>
                <label class="ck-opt"><input type="radio" name="journey_stage" value="just_browsing"><span class="ck-oradio"></span>Just browsing</label>
              </div>
            </div>

            <!-- Other Children -->
            <div class="ck-field">
              <label class="ck-field-label">Do you have other children?</label>
              <div class="ck-opts">
                <label class="ck-opt"><input type="radio" name="has_other_children" value="yes"><span class="ck-oradio"></span>Yes</label>
                <label class="ck-opt"><input type="radio" name="has_other_children" value="no"><span class="ck-oradio"></span>No</label>
              </div>
              <div id="onz-other-children-detail" style="display:none;margin-top:10px;">
                <p class="ck-p-sm">Second child's date of birth</p>
                <div class="ck-row3">
                  <div class="ck-float-field">
                    <select id="onz-other-birth-year" class="ck-finput ck-fselect"><option value="">Year</option></select>
                    <label class="ck-flabel">Year</label>
                  </div>
                  <div class="ck-float-field">
                    <select id="onz-other-birth-month" class="ck-finput ck-fselect">
                      <option value="">Month</option>
                      <option value="01">January</option><option value="02">February</option>
                      <option value="03">March</option><option value="04">April</option>
                      <option value="05">May</option><option value="06">June</option>
                      <option value="07">July</option><option value="08">August</option>
                      <option value="09">September</option><option value="10">October</option>
                      <option value="11">November</option><option value="12">December</option>
                    </select>
                    <label class="ck-flabel">Month</label>
                  </div>
                  <div class="ck-float-field">
                    <select id="onz-other-birth-day" class="ck-finput ck-fselect"><option value="">Day</option></select>
                    <label class="ck-flabel">Day</label>
                  </div>
                </div>
                <p class="ck-p-sm" style="margin-top:14px;">Third child's date of birth (optional)</p>
                <div class="ck-row3">
                  <div class="ck-float-field">
                    <select id="onz-third-birth-year" class="ck-finput ck-fselect"><option value="">Year</option></select>
                    <label class="ck-flabel">Year</label>
                  </div>
                  <div class="ck-float-field">
                    <select id="onz-third-birth-month" class="ck-finput ck-fselect">
                      <option value="">Month</option>
                      <option value="01">January</option><option value="02">February</option>
                      <option value="03">March</option><option value="04">April</option>
                      <option value="05">May</option><option value="06">June</option>
                      <option value="07">July</option><option value="08">August</option>
                      <option value="09">September</option><option value="10">October</option>
                      <option value="11">November</option><option value="12">December</option>
                    </select>
                    <label class="ck-flabel">Month</label>
                  </div>
                  <div class="ck-float-field">
                    <select id="onz-third-birth-day" class="ck-finput ck-fselect"><option value="">Day</option></select>
                    <label class="ck-flabel">Day</label>
                  </div>
                </div>
              </div>
            </div>

            <div id="onz-error" class="ck-error" style="display:none;"></div>

            <!-- Pay now button (full width, matches checkout) -->
            <button type="button" id="onz-submit-btn" class="ck-pay-btn" onclick="submitCoreSignup()">
              Pay now
            </button>
          </form>

          <!-- Footer links -->
          <div class="ck-footer">
            <a href="/policies/refund-policy">Refund policy</a>
            <a href="/policies/shipping-policy">Shipping</a>
            <a href="/policies/privacy-policy">Privacy policy</a>
            <a href="/policies/terms-of-service">Terms of service</a>
            <a href="/pages/contact">Contact</a>
          </div>
        </div>

        <!-- ===== SUCCESS ===== -->
        <div id="onz-success" style="display:none;text-align:center;padding:60px 0;">
          <svg width="50" height="50" viewBox="0 0 50 50"><circle cx="25" cy="25" r="25" fill="#3A5A40"/><path d="M15 26l7 7 13-13" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <h2 class="ck-h2" style="margin-top:16px;">Thank you!</h2>
          <p class="ck-p">Your preferences have been saved.</p>
          <div style="margin-top:28px;display:flex;flex-direction:column;gap:12px;align-items:center;max-width:360px;margin-left:auto;margin-right:auto;">
            <a href="/collections/all" class="ck-pay-btn" style="display:block;width:100%;padding:16px 32px;">Continue shopping</a>
            {{% unless customer.metafields.onzenna_loyalty.loyalty_completed_at %}}
            <a href="/pages/loyalty-survey" class="ck-outline-btn" style="display:block;width:100%;padding:16px 32px;border:1px solid #333;border-radius:5px;color:#333;text-decoration:none;font-size:14px;font-weight:500;text-align:center;">
              Unlock 10% off
              <span style="display:block;font-size:12px;font-weight:400;color:#717171;margin-top:2px;">Answer a few more questions to get your discount</span>
            </a>
            {{% endunless %}}
            {{% unless customer.metafields.onzenna_creator.creator_completed_at %}}
            <a href="/pages/creator-signup?from=checkout" class="ck-outline-btn" style="display:block;width:100%;padding:16px 32px;border:1px solid #333;border-radius:5px;color:#333;text-decoration:none;font-size:14px;font-weight:500;text-align:center;">
              Join as a Creator
              <span style="display:block;font-size:12px;font-weight:400;color:#717171;margin-top:2px;">Interested in creating content with us?</span>
            </a>
            {{% endunless %}}
          </div>
        </div>
      </div>
    </div>

    <!-- ========== RIGHT COLUMN (dark green) ========== -->
    <div class="ck-right">
      <div class="ck-right-inner">
        <!-- Promo -->
        <div class="ck-promo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="1.5"><path d="M20 12V8H6a2 2 0 010-4h12v4"/><path d="M4 6v12a2 2 0 002 2h14v-4"/><path d="M18 12a2 2 0 000 4h4v-4h-4z"/></svg>
          <div class="ck-promo-content">
            <p class="ck-promo-title">Complete this survey to personalize your experience</p>
            <p class="ck-promo-desc">Help us recommend the right products for you.</p>
          </div>
        </div>

        <!-- Discount code -->
        <div class="ck-discount-row">
          <div class="ck-float-field" style="flex:1;">
            <input type="text" class="ck-finput ck-finput-dark" placeholder=" " disabled />
            <label class="ck-flabel ck-flabel-dark">Discount code or gift card</label>
          </div>
          <button type="button" class="ck-apply-btn" disabled>Apply</button>
        </div>

        <div class="ck-divider"></div>
        <div class="ck-sum-row"><span>Subtotal</span><span>--</span></div>
        <div class="ck-sum-row"><span>Shipping</span><span class="ck-sum-muted">Enter shipping address</span></div>
        <div class="ck-divider"></div>
        <div class="ck-sum-row ck-sum-total"><span>Total</span><span><small class="ck-sum-curr">USD</small> --</span></div>
      </div>
    </div>
  </div>
</div>

<style>
  .ck,.ck *{{box-sizing:border-box;margin:0;padding:0;}}
  .ck{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;color:#333;line-height:1.5;-webkit-font-smoothing:antialiased;}}

  /* Layout */
  .ck-layout{{display:flex;min-height:100vh;}}
  .ck-left{{flex:1;background:#fff;display:flex;flex-direction:column;align-items:flex-end;}}
  .ck-right{{width:42%;max-width:480px;background:#323E32;border-left:1px solid #2a352a;}}

  /* Topbar */
  .ck-topbar{{display:flex;justify-content:space-between;align-items:center;width:100%;max-width:460px;padding:20px 40px 16px;}}
  .ck-logo img{{height:28px;width:auto;}}
  .ck-logo{{text-decoration:none;}}
  .ck-cart-icon{{color:#333;text-decoration:none;}}

  /* Form area */
  .ck-form-area{{width:100%;max-width:460px;padding:0 40px 40px;flex:1;}}

  /* Express checkout */
  .ck-express-label{{text-align:center;font-size:12px;color:#717171;margin-bottom:12px;}}
  .ck-express-btns{{display:flex;gap:8px;margin-bottom:16px;}}
  .ck-express{{flex:1;height:44px;border:none;border-radius:5px;cursor:default;display:flex;align-items:center;justify-content:center;}}
  .ck-express-shop{{background:#5A31F4;}}
  .ck-express-paypal{{background:#FFC439;}}
  .ck-express-gpay{{background:#fff;border:1px solid #d9d9d9;}}

  /* OR divider */
  .ck-or{{display:flex;align-items:center;gap:16px;margin:20px 0;}}
  .ck-or::before,.ck-or::after{{content:"";flex:1;height:1px;background:#d9d9d9;}}
  .ck-or span{{font-size:12px;color:#717171;}}

  /* Section header */
  .ck-section-hdr{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;}}
  .ck-h2{{font-size:17px;font-weight:600;color:#333;letter-spacing:-0.2px;}}
  .ck-link-sm{{font-size:13px;color:#197bbd;text-decoration:none;}}
  .ck-p{{font-size:14px;color:#545454;margin-top:4px;}}
  .ck-p-sm{{font-size:13px;color:#717171;margin:2px 0 14px;}}
  .ck-p-xs{{font-size:11px;color:#999;margin-top:8px;line-height:1.4;}}

  /* Floating label field */
  .ck-float-field{{position:relative;margin-bottom:12px;}}
  .ck-finput{{width:100%;padding:20px 12px 8px;border:1px solid #d9d9d9;border-radius:5px;font-size:14px;background:#fff;color:#333;outline:none;transition:border-color .15s;appearance:none;-webkit-appearance:none;}}
  .ck-fselect{{appearance:auto;-webkit-appearance:auto;padding:20px 12px 8px;}}
  .ck-finput:focus{{border-color:#333;box-shadow:0 0 0 1px #333;}}
  .ck-flabel{{position:absolute;top:14px;left:13px;font-size:14px;color:#999;pointer-events:none;transition:all .15s;}}
  .ck-finput:focus~.ck-flabel,.ck-finput:not(:placeholder-shown)~.ck-flabel,.ck-fselect~.ck-flabel{{top:6px;font-size:11px;color:#737373;}}

  /* Dark variant for right panel */
  .ck-finput-dark{{background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.2);color:#fff;}}
  .ck-finput-dark:focus{{border-color:rgba(255,255,255,0.5);box-shadow:none;}}
  .ck-flabel-dark{{color:rgba(255,255,255,0.5);}}

  /* Checkbox */
  .ck-checkbox{{display:flex;align-items:center;gap:8px;font-size:14px;color:#545454;cursor:pointer;margin:12px 0 0;}}
  .ck-checkbox input{{display:none;}}
  .ck-checkmark{{width:18px;height:18px;border:1px solid #d9d9d9;border-radius:3px;position:relative;flex-shrink:0;background:#fff;}}
  .ck-checkbox input:checked~.ck-checkmark{{background:#323E32;border-color:#323E32;}}
  .ck-checkbox input:checked~.ck-checkmark::after{{content:"";position:absolute;top:2px;left:5px;width:6px;height:10px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg);}}

  /* 3-column row */
  .ck-row3{{display:flex;gap:10px;}}
  .ck-row3 .ck-float-field{{flex:1;}}

  /* Fields */
  .ck-field{{margin-bottom:18px;}}
  .ck-field-label{{display:block;font-size:14px;font-weight:600;color:#333;margin-bottom:8px;}}

  /* Radio options (checkout style) */
  .ck-opts{{border:1px solid #d9d9d9;border-radius:5px;overflow:hidden;background:#fff;}}
  .ck-opt{{display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid #d9d9d9;cursor:pointer;transition:background .1s;font-size:14px;color:#333;}}
  .ck-opt:last-child{{border-bottom:none;}}
  .ck-opt:hover{{background:#f9fafb;}}
  .ck-opt input{{display:none;}}
  .ck-oradio{{width:18px;height:18px;border:2px solid #d9d9d9;border-radius:50%;margin-right:12px;flex-shrink:0;position:relative;transition:border-color .15s;}}
  .ck-opt input:checked~.ck-oradio{{border-color:#333;}}
  .ck-opt input:checked~.ck-oradio::after{{content:"";position:absolute;top:3px;left:3px;width:8px;height:8px;border-radius:50%;background:#333;}}
  .ck-opt:has(input:checked){{background:#fafafa;}}

  /* Pay now button */
  .ck-pay-btn{{display:block;width:100%;padding:18px;background:#333;color:#fff;border:none;border-radius:5px;font-size:15px;font-weight:600;cursor:pointer;text-decoration:none;text-align:center;margin-top:24px;transition:background .15s;}}
  .ck-pay-btn:hover{{background:#222;}}
  .ck-pay-btn:disabled{{background:#aaa;cursor:not-allowed;}}

  /* Error */
  .ck-error{{color:#e32c2b;font-size:13px;padding:10px 14px;background:#fef1f1;border:1px solid #f5c6c6;border-radius:5px;margin-top:8px;}}

  /* Footer */
  .ck-footer{{display:flex;flex-wrap:wrap;gap:16px;padding-top:20px;margin-top:28px;border-top:1px solid #e5e5e5;}}
  .ck-footer a{{font-size:12px;color:#197bbd;text-decoration:none;}}
  .ck-footer a:hover{{text-decoration:underline;}}

  /* Right panel */
  .ck-right-inner{{padding:32px 40px;position:sticky;top:0;}}
  .ck-promo{{display:flex;gap:12px;align-items:flex-start;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:16px;margin-bottom:20px;}}
  .ck-promo svg{{flex-shrink:0;margin-top:2px;}}
  .ck-promo-title{{color:rgba(255,255,255,0.9);font-size:13px;font-weight:600;margin-bottom:2px;}}
  .ck-promo-desc{{color:rgba(255,255,255,0.6);font-size:12px;}}
  .ck-discount-row{{display:flex;gap:8px;margin-bottom:16px;}}
  .ck-apply-btn{{padding:12px 20px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:5px;color:rgba(255,255,255,0.6);font-size:14px;cursor:default;white-space:nowrap;}}
  .ck-divider{{height:1px;background:rgba(255,255,255,0.12);margin:16px 0;}}
  .ck-sum-row{{display:flex;justify-content:space-between;font-size:14px;color:rgba(255,255,255,0.7);margin-bottom:10px;}}
  .ck-sum-total{{font-size:16px;font-weight:600;color:#fff;margin-bottom:0;}}
  .ck-sum-muted{{font-size:12px;color:rgba(255,255,255,0.45);}}
  .ck-sum-curr{{font-size:12px;font-weight:400;color:rgba(255,255,255,0.45);margin-right:4px;}}

  /* Mobile */
  @media(max-width:768px){{
    .ck-layout{{flex-direction:column;}}
    .ck-left{{align-items:stretch;}}
    .ck-right{{width:100%;max-width:100%;order:-1;}}
    .ck-right-inner{{position:static;padding:20px 24px;}}
    .ck-topbar,.ck-form-area{{max-width:100%;padding-left:24px;padding-right:24px;}}
    .ck-row3{{flex-direction:column;}}
  }}
</style>

<script>
(function() {{
  var WEBHOOK_URL = "{N8N_WEBHOOK_URL}";
  var METAFIELD_WEBHOOK = "{N8N_METAFIELD_WEBHOOK}";
  var customerId = {{% if customer %}}{{{{ customer.id }}}}{{% else %}}null{{% endif %}};
  var customerEmail = {{% if customer %}}{{{{ customer.email | json }}}}{{% else %}}null{{% endif %}};

  // Existing metafield data (populated via Liquid for logged-in customers)
  var existingData = {{
    journey_stage: {{% if customer.metafields.onzenna_survey.journey_stage %}}"{{{{ customer.metafields.onzenna_survey.journey_stage.value }}}}"{{% else %}}null{{% endif %}},
    baby_birth_month: {{% if customer.metafields.onzenna_survey.baby_birth_month %}}"{{{{ customer.metafields.onzenna_survey.baby_birth_month.value }}}}"{{% else %}}null{{% endif %}},
    has_other_children: {{% if customer.metafields.onzenna_survey.has_other_children %}}{{{{ customer.metafields.onzenna_survey.has_other_children.value }}}}{{% else %}}null{{% endif %}},
    other_child_birth: {{% if customer.metafields.onzenna_survey.other_child_birth %}}"{{{{ customer.metafields.onzenna_survey.other_child_birth.value }}}}"{{% else %}}null{{% endif %}},
    third_child_birth: {{% if customer.metafields.onzenna_survey.third_child_birth %}}"{{{{ customer.metafields.onzenna_survey.third_child_birth.value }}}}"{{% else %}}null{{% endif %}},
    signup_completed_at: {{% if customer.metafields.onzenna_survey.signup_completed_at %}}"{{{{ customer.metafields.onzenna_survey.signup_completed_at.value }}}}"{{% else %}}null{{% endif %}},
  }};

  var doneEl = document.getElementById("onz-already-done");
  var formEl = document.getElementById("onz-signup-form");
  var successEl = document.getElementById("onz-success");

  function showSection(el) {{
    doneEl.style.display = "none";
    formEl.style.display = "none";
    successEl.style.display = "none";
    el.style.display = "block";
  }}

  // Populate year dropdown
  var yearSelect = document.getElementById("onz-birth-year");
  var now = new Date();
  var cy = now.getFullYear();
  for (var y = cy + 1; y >= cy - 5; y--) {{
    var o = document.createElement("option"); o.value = y; o.textContent = y;
    yearSelect.appendChild(o);
  }}

  // Populate day dropdown
  var daySelect = document.getElementById("onz-birth-day");
  for (var d = 1; d <= 31; d++) {{
    var o = document.createElement("option"); o.value = d; o.textContent = d;
    daySelect.appendChild(o);
  }}

  // Populate other child year dropdown
  var otherYearSelect = document.getElementById("onz-other-birth-year");
  for (var y2 = cy + 1; y2 >= cy - 15; y2--) {{
    var o2 = document.createElement("option"); o2.value = y2; o2.textContent = y2;
    otherYearSelect.appendChild(o2);
  }}

  // Populate other child day dropdown
  var otherDaySelect = document.getElementById("onz-other-birth-day");
  for (var d2 = 1; d2 <= 31; d2++) {{
    var o3 = document.createElement("option"); o3.value = d2; o3.textContent = d2;
    otherDaySelect.appendChild(o3);
  }}

  // Populate third child year dropdown
  var thirdYearSelect = document.getElementById("onz-third-birth-year");
  for (var y3 = cy + 1; y3 >= cy - 15; y3--) {{
    var o4 = document.createElement("option"); o4.value = y3; o4.textContent = y3;
    thirdYearSelect.appendChild(o4);
  }}

  // Populate third child day dropdown
  var thirdDaySelect = document.getElementById("onz-third-birth-day");
  for (var d3 = 1; d3 <= 31; d3++) {{
    var o5 = document.createElement("option"); o5.value = d3; o5.textContent = d3;
    thirdDaySelect.appendChild(o5);
  }}

  // Show/hide other children detail
  document.querySelectorAll('input[name="has_other_children"]').forEach(function(r) {{
    r.addEventListener("change", function() {{
      document.getElementById("onz-other-children-detail").style.display = this.value === "yes" ? "block" : "none";
    }});
  }});

  // Check if survey already completed
  if (existingData.signup_completed_at) {{
    showSection(doneEl);
  }} else {{
    showSection(formEl);

    // Pre-fill existing data (hide sections that already have answers)
    if (existingData.journey_stage) {{
      var radio = document.querySelector('input[name="journey_stage"][value="' + existingData.journey_stage + '"]');
      if (radio) {{ radio.checked = true; radio.closest(".ck-field").style.display = "none"; }}
    }}

    if (existingData.has_other_children !== null) {{
      var val = existingData.has_other_children ? "yes" : "no";
      var radio = document.querySelector('input[name="has_other_children"][value="' + val + '"]');
      if (radio) {{
        radio.checked = true;
        if (val === "yes") document.getElementById("onz-other-children-detail").style.display = "block";
        // If we also have child birth data, hide the whole section
        if (existingData.other_child_birth) {{
          radio.closest(".ck-field").style.display = "none";
        }}
      }}
    }}

    // Pre-fill baby birth month if available
    if (existingData.baby_birth_month) {{
      var parts = existingData.baby_birth_month.split("-");
      if (parts.length >= 2) {{
        // Will be populated after dropdown init below
        setTimeout(function() {{
          document.getElementById("onz-birth-year").value = parts[0];
          document.getElementById("onz-birth-month").value = parts[1];
          // Hide baby DOB section if already filled
          var babySection = document.getElementById("onz-birth-year").closest(".ck-row3");
          if (babySection) babySection.parentElement.querySelector("h2").style.display = "none";
          babySection.parentElement.querySelector("p.ck-p-sm").style.display = "none";
          babySection.style.display = "none";
          babySection.parentElement.querySelector("p.ck-p-xs").style.display = "none";
        }}, 50);
      }}
    }}
  }}

  window.submitCoreSignup = function() {{
    var btn = document.getElementById("onz-submit-btn");
    var errorEl = document.getElementById("onz-error");
    errorEl.style.display = "none";
    btn.disabled = true;
    btn.textContent = "Processing...";

    function getRadio(n) {{
      var el = document.querySelector('input[name="'+n+'"]:checked');
      return el ? el.value : "";
    }}

    var by = document.getElementById("onz-birth-year").value;
    var bm = document.getElementById("onz-birth-month").value;
    var babyBirthMonth = (by && bm) ? by + "-" + bm : "";

    var oby = document.getElementById("onz-other-birth-year").value;
    var obm = document.getElementById("onz-other-birth-month").value;
    var obd = document.getElementById("onz-other-birth-day").value;
    var otherChildBirth = (oby && obm && obd) ? oby + "-" + obm + "-" + obd : (oby && obm) ? oby + "-" + obm : "";

    var tby = document.getElementById("onz-third-birth-year").value;
    var tbm = document.getElementById("onz-third-birth-month").value;
    var tbd = document.getElementById("onz-third-birth-day").value;
    var thirdChildBirth = (tby && tbm && tbd) ? tby + "-" + tbm + "-" + tbd : (tby && tbm) ? tby + "-" + tbm : "";

    var email = customerEmail || document.getElementById("ck-email").value;
    var firstName = document.getElementById("ck-firstname").value.trim();
    var lastName = document.getElementById("ck-lastname").value.trim();
    var address1 = document.getElementById("ck-address1").value.trim();
    var city = document.getElementById("ck-city").value.trim();
    var state = document.getElementById("ck-state").value.trim();
    var zip = document.getElementById("ck-zip").value.trim();
    var country = document.getElementById("ck-country").value;
    var phone = document.getElementById("ck-phone").value.trim();

    // Validate required fields
    if (!email) {{
      errorEl.textContent = "Please enter your email address.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    if (!firstName || !lastName) {{
      errorEl.textContent = "Please enter your first and last name.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    if (!address1 || !city || !state || !zip) {{
      errorEl.textContent = "Please fill in your shipping address.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    if (!phone) {{
      errorEl.textContent = "Please enter your phone number.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    // US phone validation: must be 10 digits (optionally +1 prefix)
    var cleanPhone = phone.replace(/[\s\-\(\)\.]/g, "");
    if (cleanPhone.startsWith("+1")) cleanPhone = cleanPhone.slice(2);
    else if (cleanPhone.startsWith("1") && cleanPhone.length === 11) cleanPhone = cleanPhone.slice(1);
    if (!/^\d{{10}}$/.test(cleanPhone)) {{
      errorEl.textContent = "Please enter a valid US phone number (10 digits).";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    // US address validation: country must be US/United States
    if (country && country !== "US" && country !== "United States") {{
      errorEl.textContent = "We currently ship to US addresses only.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    // US ZIP validation: must be 5 digits (optionally 5+4)
    if (!/^\d{{5}}(-\d{{4}})?$/.test(zip)) {{
      errorEl.textContent = "Please enter a valid US ZIP code (e.g. 90210).";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}
    // Only require journey_stage if not already saved
    if (!getRadio("journey_stage") && !existingData.journey_stage) {{
      errorEl.textContent = "Please select where you are in your journey.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Pay now"; return;
    }}

    var payload = {{
      form_type: "onzenna_core_signup",
      customer_id: customerId,
      customer_email: email,
      submitted_at: new Date().toISOString(),
      contact: {{
        first_name: firstName,
        last_name: lastName,
        phone: phone,
      }},
      shipping_address: {{
        address1: address1,
        address2: document.getElementById("ck-address2").value.trim(),
        city: city,
        province: state,
        zip: zip,
        country: country,
      }},
      survey_data: {{
        journey_stage: getRadio("journey_stage") || existingData.journey_stage || "",
        baby_birth_month: babyBirthMonth || existingData.baby_birth_month || "",
        has_other_children: getRadio("has_other_children") ? getRadio("has_other_children") === "yes" : (existingData.has_other_children || false),
        other_child_birth: otherChildBirth || existingData.other_child_birth || "",
        third_child_birth: thirdChildBirth || existingData.third_child_birth || "",
      }},
    }};

    var bodyStr = JSON.stringify(payload);

    // Send to main webhook
    fetch(WEBHOOK_URL, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: bodyStr,
    }}).catch(function() {{}});

    // Save to customer metafields (if logged in)
    if (customerId) {{
      fetch(METAFIELD_WEBHOOK, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: bodyStr,
      }}).catch(function() {{}});
    }}

    // Remember checkout data (for creator-signup page -> Airtable)
    try {{
      sessionStorage.setItem("onz_checkout_done", "1");
      sessionStorage.setItem("onz_email", email);
      sessionStorage.setItem("onz_name", firstName + " " + lastName);
      if (customerId) sessionStorage.setItem("onz_customer_id", String(customerId));
      sessionStorage.setItem("onz_core_survey", JSON.stringify(payload.survey_data));
      sessionStorage.setItem("onz_contact", JSON.stringify(payload.contact));
      sessionStorage.setItem("onz_shipping", JSON.stringify(payload.shipping_address));
    }} catch(e) {{}}

    showSection(successEl);
  }};
}})();
</script>

{{% schema %}}
{{
  "name": "Core Signup",
  "tag": "section",
  "class": "core-signup-section"
}}
{{% endschema %}}
'''


def build_page_template():
    return json.dumps({
        "sections": {
            "main": {
                "type": "core-signup",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# -- Deploy / Rollback --
def deploy(dry_run=False, published=True):
    print(f"\n{'=' * 60}")
    print(f"  Deploy Core Signup Page (Part 1)")
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

    upload_theme_asset(theme_id, SECTION_KEY, section_liquid)
    upload_theme_asset(theme_id, TEMPLATE_KEY, page_template)
    create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "core-signup", published=published)

    page_url = f"https://{SHOP.replace('.myshopify.com', '')}.com/pages/{PAGE_HANDLE}"
    print(f"\n  Page URL: {page_url}")
    if not published:
        print(f"  (Page is hidden -- only accessible by direct URL)")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


def rollback():
    print(f"\n{'=' * 60}")
    print(f"  Rollback Core Signup Page")
    print(f"{'=' * 60}\n")

    theme_id = get_active_theme_id()
    delete_theme_asset(theme_id, SECTION_KEY)
    delete_theme_asset(theme_id, TEMPLATE_KEY)

    result = shopify_request("GET", f"/pages.json?handle={PAGE_HANDLE}")
    pages = result.get("pages", [])
    if pages:
        print(f"\n  [NOTE] Page still exists (ID: {pages[0]['id']})")
        print(f"  Delete manually: Shopify Admin > Online Store > Pages > {PAGE_TITLE}")

    print(f"\n{'=' * 60}")
    print(f"  ROLLBACK DONE")
    print(f"{'=' * 60}\n")


# -- CLI --
def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Deploy Onzenna Core Signup page (Part 1)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    parser.add_argument("--unpublish", action="store_true", help="Deploy as hidden (test mode)")
    parser.add_argument("--rollback", action="store_true", help="Remove theme assets")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    if args.rollback:
        rollback()
    else:
        deploy(dry_run=args.dry_run, published=not args.unpublish)


if __name__ == "__main__":
    main()
