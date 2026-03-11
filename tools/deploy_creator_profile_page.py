"""Deploy the Onzenna Creator Profile page (Part 2) to Shopify.

Creates a Liquid section + page template + Shopify page at /pages/creator-profile.
Collects 7 creator questions: platform, handle, other channels, following size,
hashtags, content type, brand partnerships.
This is a standalone test page -- in production, this goes into the Thank-You page extension.

Usage:
    python tools/deploy_creator_profile_page.py
    python tools/deploy_creator_profile_page.py --dry-run
    python tools/deploy_creator_profile_page.py --unpublish     # deploy hidden
    python tools/deploy_creator_profile_page.py --rollback      # remove assets

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
N8N_WEBHOOK_URL = os.getenv("N8N_CREATOR_PROFILE_WEBHOOK", "https://n8n.orbiters.co.kr/webhook/onzenna-creator-profile")
N8N_METAFIELD_WEBHOOK = "https://n8n.orbiters.co.kr/webhook/onzenna-save-metafields"
N8N_AIRTABLE_WEBHOOK = os.getenv("N8N_CREATOR_AIRTABLE_WEBHOOK", "https://n8n.orbiters.co.kr/webhook/onzenna-creator-to-airtable")

SECTION_KEY = "sections/creator-signup.liquid"
TEMPLATE_KEY = "templates/page.creator-signup.json"
PAGE_HANDLE = "creator-signup"
PAGE_TITLE = "Join as a Creator"


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
  Onzenna Creator Signup - Checkout-style page
  Collects: primary platform, handle, other channels, following size,
  hashtags, content type, brand partnerships.
  Deployed by tools/deploy_creator_profile_page.py
{{% endcomment %}}

<!-- Hide site chrome -->
<style>
  header,.header,.site-header,.shopify-section-header,
  footer,.footer,.site-footer,.shopify-section-footer,
  .announcement-bar,.shopify-section-announcement-bar,
  #shopify-section-header,#shopify-section-footer,
  #shopify-section-announcement-bar,
  [class*="header-section"],[class*="footer-section"],
  .shopify-section--header,.shopify-section--footer,
  .shopify-section--announcement-bar {{ display:none!important; }}
  body {{ background:#fff!important; margin:0!important; padding:0!important; }}
  .main-content,main,#MainContent,#main {{ padding:0!important; margin:0!important; max-width:100%!important; }}
</style>

<div class="ck" id="onz-creator-signup">
  <div class="ck-layout">
    <!-- ========== LEFT COLUMN ========== -->
    <div class="ck-left">
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
          <p class="ck-p">We already have your creator profile on file. Our team will reach out about collaboration opportunities.</p>
          <a href="/collections/all" class="ck-pay-btn" style="display:inline-block;margin-top:16px;text-align:center;">Return to store</a>
        </div>

        <!-- ===== FORM ===== -->
        <div id="onz-creator-form" style="display:none;">
          <h2 class="ck-h2">Join as a Creator</h2>
          <p class="ck-p-sm">Tell us about your social media presence. We love collaborating with creators who share our values.</p>

          <form id="onz-form" onsubmit="return false;">
            <!-- Contact & Shipping (shown only when no address on file) -->
            <div id="onz-contact-section" style="display:none;">
              <h3 class="ck-h2" style="margin-bottom:12px;">Contact & Shipping</h3>
              <p class="ck-p-xs" style="margin-bottom:14px;">We need your shipping info to send free samples.</p>

              <div class="ck-float-field">
                <input type="email" id="onz-email" class="ck-finput" placeholder=" "
                  value="{{% if customer %}}{{{{ customer.email }}}}{{% endif %}}" />
                <label class="ck-flabel">Email</label>
              </div>
              <div style="display:flex;gap:10px;">
                <div class="ck-float-field" style="flex:1;">
                  <input type="text" id="onz-firstname" class="ck-finput" placeholder=" "
                    value="{{% if customer %}}{{{{ customer.first_name }}}}{{% endif %}}" />
                  <label class="ck-flabel">First name</label>
                </div>
                <div class="ck-float-field" style="flex:1;">
                  <input type="text" id="onz-lastname" class="ck-finput" placeholder=" "
                    value="{{% if customer %}}{{{{ customer.last_name }}}}{{% endif %}}" />
                  <label class="ck-flabel">Last name</label>
                </div>
              </div>
              <div class="ck-float-field">
                <input type="tel" id="onz-phone" class="ck-finput" placeholder=" "
                  value="{{% if customer.default_address.phone %}}{{{{ customer.default_address.phone }}}}{{% elsif customer.phone %}}{{{{ customer.phone }}}}{{% endif %}}" />
                <label class="ck-flabel">Phone</label>
              </div>
              <div class="ck-float-field">
                <select id="onz-country" class="ck-finput ck-fselect">
                  <option value="US" selected>United States</option>
                  <option value="CA">Canada</option>
                </select>
                <label class="ck-flabel">Country</label>
              </div>
              <div class="ck-float-field">
                <input type="text" id="onz-address1" class="ck-finput" placeholder=" "
                  value="{{% if customer.default_address %}}{{{{ customer.default_address.address1 }}}}{{% endif %}}" />
                <label class="ck-flabel">Address</label>
              </div>
              <div class="ck-float-field">
                <input type="text" id="onz-address2" class="ck-finput" placeholder=" "
                  value="{{% if customer.default_address %}}{{{{ customer.default_address.address2 }}}}{{% endif %}}" />
                <label class="ck-flabel">Apartment, suite, etc. (optional)</label>
              </div>
              <div style="display:flex;gap:10px;">
                <div class="ck-float-field" style="flex:1;">
                  <input type="text" id="onz-city" class="ck-finput" placeholder=" "
                    value="{{% if customer.default_address %}}{{{{ customer.default_address.city }}}}{{% endif %}}" />
                  <label class="ck-flabel">City</label>
                </div>
                <div class="ck-float-field" style="flex:1;">
                  <input type="text" id="onz-state" class="ck-finput" placeholder=" "
                    value="{{% if customer.default_address %}}{{{{ customer.default_address.province }}}}{{% endif %}}" />
                  <label class="ck-flabel">State</label>
                </div>
                <div class="ck-float-field" style="flex:1;">
                  <input type="text" id="onz-zip" class="ck-finput" placeholder=" "
                    value="{{% if customer.default_address %}}{{{{ customer.default_address.zip }}}}{{% endif %}}" />
                  <label class="ck-flabel">ZIP code</label>
                </div>
              </div>
              <div class="ck-divider-light" style="height:1px;background:#e5e5e5;margin:20px 0;"></div>
            </div>

            <!-- Primary Platform -->
            <div class="ck-field">
              <label class="ck-field-label">What is your primary social media platform?</label>
              <div class="ck-opts">
                <label class="ck-opt"><input type="radio" name="primary_platform" value="instagram"><span class="ck-oradio"></span>Instagram</label>
                <label class="ck-opt"><input type="radio" name="primary_platform" value="tiktok"><span class="ck-oradio"></span>TikTok</label>
                <label class="ck-opt"><input type="radio" name="primary_platform" value="youtube"><span class="ck-oradio"></span>YouTube</label>
                <label class="ck-opt"><input type="radio" name="primary_platform" value="blog"><span class="ck-oradio"></span>Blog</label>
                <label class="ck-opt"><input type="radio" name="primary_platform" value="pinterest"><span class="ck-oradio"></span>Pinterest</label>
                <label class="ck-opt"><input type="radio" name="primary_platform" value="other"><span class="ck-oradio"></span>Other</label>
              </div>
            </div>

            <!-- Primary Handle with verify -->
            <div class="ck-field" id="onz-handle-field" style="display:none;">
              <label class="ck-field-label" id="onz-handle-label">Your handle or profile URL</label>
              <div style="display:flex;gap:8px;">
                <div class="ck-float-field" style="flex:1;margin-bottom:0;">
                  <input type="text" id="onz-primary-handle" class="ck-finput" placeholder=" " />
                  <label class="ck-flabel" id="onz-handle-placeholder">@yourhandle</label>
                </div>
                <button type="button" id="onz-verify-btn" class="ck-verify-btn" onclick="verifyHandle()">Verify</button>
              </div>
              <div id="onz-verify-result" style="display:none;margin-top:6px;font-size:12px;"></div>
            </div>

            <!-- Other Platforms -->
            <div class="ck-field">
              <label class="ck-field-label">Are you active on other platforms?</label>
              <p class="ck-p-xs" style="margin-bottom:8px;">Select all that apply</p>
              <div class="ck-chips" data-field="other_platforms">
                <label class="ck-chip"><input type="checkbox" value="instagram"><span>Instagram</span></label>
                <label class="ck-chip"><input type="checkbox" value="tiktok"><span>TikTok</span></label>
                <label class="ck-chip"><input type="checkbox" value="youtube"><span>YouTube</span></label>
                <label class="ck-chip"><input type="checkbox" value="blog"><span>Blog</span></label>
                <label class="ck-chip"><input type="checkbox" value="pinterest"><span>Pinterest</span></label>
                <label class="ck-chip"><input type="checkbox" value="facebook"><span>Facebook</span></label>
                <label class="ck-chip"><input type="checkbox" value="twitter"><span>X (Twitter)</span></label>
              </div>
              <div id="onz-other-handles" style="margin-top:10px;"></div>
            </div>

            <!-- Following Size -->
            <div class="ck-field">
              <label class="ck-field-label">Total following size (across all platforms)</label>
              <div class="ck-opts">
                <label class="ck-opt"><input type="radio" name="following_size" value="under_1k"><span class="ck-oradio"></span>Under 1K</label>
                <label class="ck-opt"><input type="radio" name="following_size" value="1k_10k"><span class="ck-oradio"></span>1K - 10K</label>
                <label class="ck-opt"><input type="radio" name="following_size" value="10k_50k"><span class="ck-oradio"></span>10K - 50K</label>
                <label class="ck-opt"><input type="radio" name="following_size" value="50k_100k"><span class="ck-oradio"></span>50K - 100K</label>
                <label class="ck-opt"><input type="radio" name="following_size" value="100k_plus"><span class="ck-oradio"></span>100K+</label>
              </div>
            </div>

            <!-- Hashtags -->
            <div class="ck-field">
              <label class="ck-field-label">Hashtags you commonly use</label>
              <div class="ck-float-field">
                <input type="text" id="onz-hashtags" class="ck-finput" placeholder=" " />
                <label class="ck-flabel">#momlife, #newmom, #babyproducts...</label>
              </div>
            </div>

            <!-- Content Type -->
            <div class="ck-field">
              <label class="ck-field-label">What type of content do you create?</label>
              <p class="ck-p-xs" style="margin-bottom:8px;">Select all that apply</p>
              <div class="ck-chips" data-field="content_type">
                <label class="ck-chip"><input type="checkbox" value="product_reviews"><span>Product reviews</span></label>
                <label class="ck-chip"><input type="checkbox" value="tutorials"><span>Tutorials / How-to</span></label>
                <label class="ck-chip"><input type="checkbox" value="lifestyle"><span>Lifestyle / Day-in-life</span></label>
                <label class="ck-chip"><input type="checkbox" value="educational"><span>Educational</span></label>
                <label class="ck-chip"><input type="checkbox" value="unboxing"><span>Unboxing</span></label>
                <label class="ck-chip"><input type="checkbox" value="recipes"><span>Recipes / Feeding tips</span></label>
                <label class="ck-chip"><input type="checkbox" value="other"><span>Other</span></label>
              </div>
              <div id="onz-content-other" style="display:none;margin-top:8px;">
                <div class="ck-float-field">
                  <input type="text" id="onz-content-other-text" class="ck-finput" placeholder=" " />
                  <label class="ck-flabel">Describe your content type</label>
                </div>
              </div>
            </div>

            <!-- Brand Partnerships -->
            <div class="ck-field">
              <label class="ck-field-label">Have you worked with brands before?</label>
              <div class="ck-opts">
                <label class="ck-opt"><input type="radio" name="has_brand_partnerships" value="yes"><span class="ck-oradio"></span>Yes</label>
                <label class="ck-opt"><input type="radio" name="has_brand_partnerships" value="no_but_interested"><span class="ck-oradio"></span>No, but interested</label>
                <label class="ck-opt"><input type="radio" name="has_brand_partnerships" value="not_interested"><span class="ck-oradio"></span>Not interested</label>
              </div>
              <div id="onz-brand-detail" style="display:none;margin-top:10px;">
                <div class="ck-float-field">
                  <input type="text" id="onz-brand-names" class="ck-finput" placeholder=" " />
                  <label class="ck-flabel">Which brands? (e.g., Nike, Honest Co.)</label>
                </div>
              </div>
            </div>

            <div id="onz-error" class="ck-error" style="display:none;"></div>

            <button type="button" id="onz-submit-btn" class="ck-pay-btn" onclick="submitCreatorProfile()">
              Submit
            </button>
          </form>

          <div class="ck-footer">
            <a href="/policies/privacy-policy">Privacy policy</a>
            <a href="/policies/terms-of-service">Terms of service</a>
            <a href="/pages/contact">Contact</a>
          </div>
        </div>

        <!-- ===== SUCCESS ===== -->
        <div id="onz-success" style="display:none;text-align:center;padding:60px 0;">
          <svg width="50" height="50" viewBox="0 0 50 50"><circle cx="25" cy="25" r="25" fill="#3A5A40"/><path d="M15 26l7 7 13-13" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <h2 class="ck-h2" style="margin-top:16px;">Thank you, creator!</h2>
          <p class="ck-p">We've saved your profile. Our team will review it and reach out about collaboration opportunities.</p>
          <div style="margin-top:28px;display:flex;flex-direction:column;gap:12px;align-items:center;max-width:360px;margin-left:auto;margin-right:auto;">
            <a href="/collections/all" class="ck-pay-btn" style="display:block;width:100%;padding:16px 32px;">Continue shopping</a>
            {{% unless customer.metafields.onzenna_loyalty.loyalty_completed_at %}}
            <a href="/pages/loyalty-survey" style="display:block;width:100%;padding:16px 32px;border:1px solid #333;border-radius:5px;color:#333;text-decoration:none;font-size:14px;font-weight:500;text-align:center;">
              Unlock 10% off
              <span style="display:block;font-size:12px;font-weight:400;color:#717171;margin-top:2px;">Answer a few more questions to get your discount</span>
            </a>
            {{% endunless %}}
          </div>
        </div>
      </div>
    </div>

    <!-- ========== RIGHT COLUMN (dark green) ========== -->
    <div class="ck-right">
      <div class="ck-right-inner">
        <div class="ck-promo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
          <div class="ck-promo-content">
            <p class="ck-promo-title">Become an Onzenna Creator</p>
            <p class="ck-promo-desc">Get early access to products, exclusive collabs, and creator perks.</p>
          </div>
        </div>

        <div class="ck-divider"></div>
        <div class="ck-sum-row"><span>Creator perks</span></div>
        <ul style="list-style:none;padding:0;margin:12px 0 0;">
          <li style="color:rgba(255,255,255,0.7);font-size:13px;margin-bottom:10px;display:flex;gap:8px;align-items:flex-start;">
            <span style="color:#8BC34A;">&#10003;</span> Free product samples
          </li>
          <li style="color:rgba(255,255,255,0.7);font-size:13px;margin-bottom:10px;display:flex;gap:8px;align-items:flex-start;">
            <span style="color:#8BC34A;">&#10003;</span> Exclusive discount codes for your followers
          </li>
          <li style="color:rgba(255,255,255,0.7);font-size:13px;margin-bottom:10px;display:flex;gap:8px;align-items:flex-start;">
            <span style="color:#8BC34A;">&#10003;</span> Early access to new launches
          </li>
          <li style="color:rgba(255,255,255,0.7);font-size:13px;margin-bottom:10px;display:flex;gap:8px;align-items:flex-start;">
            <span style="color:#8BC34A;">&#10003;</span> Featured on our social channels
          </li>
        </ul>
      </div>
    </div>
  </div>
</div>

<style>
  .ck,.ck *{{box-sizing:border-box;margin:0;padding:0;}}
  .ck{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;color:#333;line-height:1.5;-webkit-font-smoothing:antialiased;}}
  .ck-layout{{display:flex;min-height:100vh;}}
  .ck-left{{flex:1;background:#fff;display:flex;flex-direction:column;align-items:flex-end;}}
  .ck-right{{width:42%;max-width:480px;background:#323E32;border-left:1px solid #2a352a;}}
  .ck-topbar{{display:flex;justify-content:space-between;align-items:center;width:100%;max-width:460px;padding:20px 40px 16px;}}
  .ck-logo img{{height:28px;width:auto;}}
  .ck-logo{{text-decoration:none;}}
  .ck-cart-icon{{color:#333;text-decoration:none;}}
  .ck-form-area{{width:100%;max-width:460px;padding:0 40px 40px;flex:1;}}
  .ck-h2{{font-size:17px;font-weight:600;color:#333;letter-spacing:-0.2px;}}
  .ck-p{{font-size:14px;color:#545454;margin-top:4px;}}
  .ck-p-sm{{font-size:13px;color:#717171;margin:2px 0 14px;}}
  .ck-p-xs{{font-size:11px;color:#999;line-height:1.4;}}
  .ck-float-field{{position:relative;margin-bottom:12px;}}
  .ck-finput{{width:100%;padding:20px 12px 8px;border:1px solid #d9d9d9;border-radius:5px;font-size:14px;background:#fff;color:#333;outline:none;transition:border-color .15s;appearance:none;-webkit-appearance:none;}}
  .ck-finput:focus{{border-color:#333;box-shadow:0 0 0 1px #333;}}
  .ck-fselect{{appearance:auto;-webkit-appearance:auto;padding:20px 12px 8px;}}
  .ck-flabel{{position:absolute;top:14px;left:13px;font-size:14px;color:#999;pointer-events:none;transition:all .15s;}}
  .ck-finput:focus~.ck-flabel,.ck-finput:not(:placeholder-shown)~.ck-flabel,.ck-fselect~.ck-flabel{{top:6px;font-size:11px;color:#737373;}}
  .ck-field{{margin-bottom:18px;}}
  .ck-field-label{{display:block;font-size:14px;font-weight:600;color:#333;margin-bottom:8px;}}
  .ck-opts{{border:1px solid #d9d9d9;border-radius:5px;overflow:hidden;background:#fff;}}
  .ck-opt{{display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid #d9d9d9;cursor:pointer;transition:background .1s;font-size:14px;color:#333;}}
  .ck-opt:last-child{{border-bottom:none;}}
  .ck-opt:hover{{background:#f9fafb;}}
  .ck-opt input{{display:none;}}
  .ck-oradio{{width:18px;height:18px;border:2px solid #d9d9d9;border-radius:50%;margin-right:12px;flex-shrink:0;position:relative;transition:border-color .15s;}}
  .ck-opt input:checked~.ck-oradio{{border-color:#333;}}
  .ck-opt input:checked~.ck-oradio::after{{content:"";position:absolute;top:3px;left:3px;width:8px;height:8px;border-radius:50%;background:#333;}}
  .ck-opt:has(input:checked){{background:#fafafa;}}
  /* Chip-style multi-select */
  .ck-chips{{display:flex;flex-wrap:wrap;gap:8px;}}
  .ck-chip{{display:inline-flex;align-items:center;padding:8px 14px;border:1px solid #d9d9d9;border-radius:20px;font-size:13px;cursor:pointer;transition:all .15s;user-select:none;}}
  .ck-chip input{{display:none;}}
  .ck-chip:hover{{border-color:#999;}}
  .ck-chip:has(input:checked){{background:#f0f4f0;border-color:#3A5A40;color:#3A5A40;font-weight:500;}}
  /* Verify button */
  .ck-verify-btn{{padding:20px 16px 8px;background:#3A5A40;color:#fff;border:none;border-radius:5px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;transition:background .15s;}}
  .ck-verify-btn:hover{{background:#2d4a33;}}
  .ck-verify-btn:disabled{{background:#aaa;cursor:not-allowed;}}
  .ck-verify-ok{{color:#3A5A40;}}
  .ck-verify-fail{{color:#e32c2b;}}
  /* Other handle fields */
  .ck-other-handle{{margin-bottom:8px;}}
  .ck-other-handle-label{{font-size:12px;font-weight:600;color:#717171;margin-bottom:4px;display:block;}}
  .ck-pay-btn{{display:block;width:100%;padding:18px;background:#333;color:#fff;border:none;border-radius:5px;font-size:15px;font-weight:600;cursor:pointer;text-decoration:none;text-align:center;margin-top:24px;transition:background .15s;}}
  .ck-pay-btn:hover{{background:#222;}}
  .ck-pay-btn:disabled{{background:#aaa;cursor:not-allowed;}}
  .ck-error{{color:#e32c2b;font-size:13px;padding:10px 14px;background:#fef1f1;border:1px solid #f5c6c6;border-radius:5px;margin-top:8px;}}
  .ck-footer{{display:flex;flex-wrap:wrap;gap:16px;padding-top:20px;margin-top:28px;border-top:1px solid #e5e5e5;}}
  .ck-footer a{{font-size:12px;color:#197bbd;text-decoration:none;}}
  .ck-footer a:hover{{text-decoration:underline;}}
  .ck-right-inner{{padding:32px 40px;position:sticky;top:0;}}
  .ck-promo{{display:flex;gap:12px;align-items:flex-start;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:16px;margin-bottom:20px;}}
  .ck-promo svg{{flex-shrink:0;margin-top:2px;}}
  .ck-promo-title{{color:rgba(255,255,255,0.9);font-size:13px;font-weight:600;margin-bottom:2px;}}
  .ck-promo-desc{{color:rgba(255,255,255,0.6);font-size:12px;}}
  .ck-divider{{height:1px;background:rgba(255,255,255,0.12);margin:16px 0;}}
  .ck-sum-row{{display:flex;justify-content:space-between;font-size:14px;color:rgba(255,255,255,0.7);margin-bottom:10px;}}
  @media(max-width:768px){{
    .ck-layout{{flex-direction:column;}}
    .ck-left{{align-items:stretch;}}
    .ck-right{{width:100%;max-width:100%;order:-1;}}
    .ck-right-inner{{position:static;padding:20px 24px;}}
    .ck-topbar,.ck-form-area{{max-width:100%;padding-left:24px;padding-right:24px;}}
  }}
</style>

<script>
(function() {{
  var WEBHOOK_URL = "{N8N_WEBHOOK_URL}";
  var METAFIELD_WEBHOOK = "{N8N_METAFIELD_WEBHOOK}";
  var AIRTABLE_WEBHOOK = "{N8N_AIRTABLE_WEBHOOK}";
  var customerId = {{% if customer %}}{{{{ customer.id }}}}{{% else %}}null{{% endif %}};
  var customerEmail = {{% if customer %}}{{{{ customer.email | json }}}}{{% else %}}null{{% endif %}};
  var customerName = {{% if customer %}}{{{{ customer.name | json }}}}{{% else %}}null{{% endif %}};
  // Check if user already provided address: Liquid metafield OR Shopify address OR URL param OR sessionStorage
  var hasAddressLiquid = {{% if customer.default_address.address1 %}}true{{% elsif customer.metafields.onzenna_survey.signup_completed_at %}}true{{% else %}}false{{% endif %}};
  var urlParams = new URLSearchParams(window.location.search);
  var fromCheckout = urlParams.get("from") === "checkout";
  var sessionDone = false;
  try {{ sessionDone = sessionStorage.getItem("onz_checkout_done") === "1"; }} catch(e) {{}}
  var hasAddress = hasAddressLiquid || fromCheckout || sessionDone;

  // Shopify-stored address (pre-populated for logged-in users)
  var shopifyAddress = {{
    phone: {{% if customer.phone %}}"{{{{ customer.phone }}}}"{{% elsif customer.default_address.phone %}}"{{{{ customer.default_address.phone }}}}"{{% else %}}null{{% endif %}},
    address1: {{% if customer.default_address.address1 %}}"{{{{ customer.default_address.address1 }}}}"{{% else %}}null{{% endif %}},
    address2: {{% if customer.default_address.address2 %}}"{{{{ customer.default_address.address2 }}}}"{{% else %}}null{{% endif %}},
    city: {{% if customer.default_address.city %}}"{{{{ customer.default_address.city }}}}"{{% else %}}null{{% endif %}},
    province: {{% if customer.default_address.province %}}"{{{{ customer.default_address.province }}}}"{{% else %}}null{{% endif %}},
    zip: {{% if customer.default_address.zip %}}"{{{{ customer.default_address.zip }}}}"{{% else %}}null{{% endif %}},
    country: {{% if customer.default_address.country %}}"{{{{ customer.default_address.country }}}}"{{% else %}}null{{% endif %}},
  }};

  // Existing creator metafield data
  var existingCreator = {{
    primary_platform: {{% if customer.metafields.onzenna_creator.primary_platform %}}"{{{{ customer.metafields.onzenna_creator.primary_platform.value }}}}"{{% else %}}null{{% endif %}},
    primary_handle: {{% if customer.metafields.onzenna_creator.primary_handle %}}"{{{{ customer.metafields.onzenna_creator.primary_handle.value }}}}"{{% else %}}null{{% endif %}},
    other_platforms: {{% if customer.metafields.onzenna_creator.other_platforms %}}{{{{ customer.metafields.onzenna_creator.other_platforms.value }}}}{{% else %}}null{{% endif %}},
    following_size: {{% if customer.metafields.onzenna_creator.following_size %}}"{{{{ customer.metafields.onzenna_creator.following_size.value }}}}"{{% else %}}null{{% endif %}},
    hashtags: {{% if customer.metafields.onzenna_creator.hashtags %}}"{{{{ customer.metafields.onzenna_creator.hashtags.value }}}}"{{% else %}}null{{% endif %}},
    content_type: {{% if customer.metafields.onzenna_creator.content_type %}}{{{{ customer.metafields.onzenna_creator.content_type.value }}}}{{% else %}}null{{% endif %}},
    has_brand_partnerships: {{% if customer.metafields.onzenna_creator.has_brand_partnerships %}}"{{{{ customer.metafields.onzenna_creator.has_brand_partnerships.value }}}}"{{% else %}}null{{% endif %}},
    brand_names: {{% if customer.metafields.onzenna_creator.brand_names %}}"{{{{ customer.metafields.onzenna_creator.brand_names.value }}}}"{{% else %}}null{{% endif %}},
    creator_completed_at: {{% if customer.metafields.onzenna_creator.creator_completed_at %}}"{{{{ customer.metafields.onzenna_creator.creator_completed_at.value }}}}"{{% else %}}null{{% endif %}},
  }};

  // Core signup metafield data (from Part 1 checkout)
  var existingCoreData = {{
    journey_stage: {{% if customer.metafields.onzenna_survey.journey_stage %}}"{{{{ customer.metafields.onzenna_survey.journey_stage.value }}}}"{{% else %}}null{{% endif %}},
    baby_birth_month: {{% if customer.metafields.onzenna_survey.baby_birth_month %}}"{{{{ customer.metafields.onzenna_survey.baby_birth_month.value }}}}"{{% else %}}null{{% endif %}},
    has_other_children: {{% if customer.metafields.onzenna_survey.has_other_children %}}"{{{{ customer.metafields.onzenna_survey.has_other_children.value }}}}"{{% else %}}null{{% endif %}},
    other_child_birth: {{% if customer.metafields.onzenna_survey.other_child_birth %}}"{{{{ customer.metafields.onzenna_survey.other_child_birth.value }}}}"{{% else %}}null{{% endif %}},
    signup_completed_at: {{% if customer.metafields.onzenna_survey.signup_completed_at %}}"{{{{ customer.metafields.onzenna_survey.signup_completed_at.value }}}}"{{% else %}}null{{% endif %}},
  }};

  var formEl = document.getElementById("onz-creator-form");
  var successEl = document.getElementById("onz-success");

  function showSection(el) {{
    formEl.style.display = "none";
    successEl.style.display = "none";
    el.style.display = "block";
  }}

  // Platform config
  var platformInfo = {{
    instagram: {{ label: "Instagram", placeholder: "@username", urlPattern: "instagram.com/" }},
    tiktok: {{ label: "TikTok", placeholder: "@username", urlPattern: "tiktok.com/@" }},
    youtube: {{ label: "YouTube", placeholder: "Channel URL or @handle", urlPattern: "youtube.com/" }},
    blog: {{ label: "Blog", placeholder: "https://yourblog.com", urlPattern: "" }},
    pinterest: {{ label: "Pinterest", placeholder: "@username or URL", urlPattern: "pinterest.com/" }},
    facebook: {{ label: "Facebook", placeholder: "Page name or URL", urlPattern: "facebook.com/" }},
    twitter: {{ label: "X (Twitter)", placeholder: "@username", urlPattern: "x.com/" }},
    other: {{ label: "Other", placeholder: "Profile URL", urlPattern: "" }},
  }};

  // Show handle field when platform selected, update label
  document.querySelectorAll('input[name="primary_platform"]').forEach(function(r) {{
    r.addEventListener("change", function() {{
      var info = platformInfo[this.value] || platformInfo.other;
      document.getElementById("onz-handle-field").style.display = "block";
      document.getElementById("onz-handle-label").textContent = info.label + " handle";
      document.getElementById("onz-handle-placeholder").textContent = info.placeholder;
      document.getElementById("onz-verify-result").style.display = "none";
      document.getElementById("onz-primary-handle").value = "";
    }});
  }});

  // Verify handle
  window.verifyHandle = function() {{
    var handle = document.getElementById("onz-primary-handle").value.trim();
    var resultEl = document.getElementById("onz-verify-result");
    var btn = document.getElementById("onz-verify-btn");
    if (!handle) {{
      resultEl.innerHTML = '<span class="ck-verify-fail">Please enter a handle first.</span>';
      resultEl.style.display = "block";
      return;
    }}
    btn.disabled = true;
    btn.textContent = "Checking...";
    resultEl.style.display = "none";

    var platform = document.querySelector('input[name="primary_platform"]:checked');
    var pVal = platform ? platform.value : "";
    var info = platformInfo[pVal] || platformInfo.other;

    // Build profile URL to check
    var profileUrl = handle;
    if (handle.startsWith("@")) handle = handle.substring(1);
    if (!handle.startsWith("http")) {{
      if (pVal === "instagram") profileUrl = "https://www.instagram.com/" + handle + "/";
      else if (pVal === "tiktok") profileUrl = "https://www.tiktok.com/@" + handle;
      else if (pVal === "youtube") profileUrl = "https://www.youtube.com/@" + handle;
      else if (pVal === "pinterest") profileUrl = "https://www.pinterest.com/" + handle + "/";
      else if (pVal === "twitter") profileUrl = "https://x.com/" + handle;
      else if (pVal === "facebook") profileUrl = "https://www.facebook.com/" + handle;
    }}

    // Simple check: try to fetch via a head-like approach
    // Since we can't do cross-origin, we show the link for manual verify
    setTimeout(function() {{
      resultEl.innerHTML = '<span class="ck-verify-ok">&#10003; Profile link: </span><a href="' + profileUrl + '" target="_blank" rel="noopener" style="color:#197bbd;font-size:12px;">' + profileUrl + '</a><br><span style="color:#717171;font-size:11px;">Please confirm this is your profile.</span>';
      resultEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Verify";
    }}, 500);
  }};

  // Other platforms: show/hide handle inputs dynamically
  var otherHandlesEl = document.getElementById("onz-other-handles");
  document.querySelectorAll('[data-field="other_platforms"] input').forEach(function(cb) {{
    cb.addEventListener("change", function() {{
      var val = this.value;
      var existing = document.getElementById("onz-oh-" + val);
      if (this.checked && !existing) {{
        var info = platformInfo[val] || platformInfo.other;
        var div = document.createElement("div");
        div.className = "ck-other-handle";
        div.id = "onz-oh-" + val;
        div.innerHTML = '<span class="ck-other-handle-label">' + info.label + '</span><div class="ck-float-field" style="margin-bottom:0;"><input type="text" class="ck-finput onz-oh-input" data-platform="' + val + '" placeholder=" " /><label class="ck-flabel">' + info.placeholder + '</label></div>';
        otherHandlesEl.appendChild(div);
      }} else if (!this.checked && existing) {{
        existing.remove();
      }}
    }});
  }});

  // Content type "Other" toggle
  document.querySelector('[data-field="content_type"] input[value="other"]').addEventListener("change", function() {{
    document.getElementById("onz-content-other").style.display = this.checked ? "block" : "none";
  }});

  // Brand partnerships "Yes" toggle
  document.querySelectorAll('input[name="has_brand_partnerships"]').forEach(function(r) {{
    r.addEventListener("change", function() {{
      document.getElementById("onz-brand-detail").style.display = this.value === "yes" ? "block" : "none";
    }});
  }});

  var doneEl = document.getElementById("onz-already-done");

  // Show contact/shipping section if no address on file OR not logged in
  var contactSection = document.getElementById("onz-contact-section");
  if (!hasAddress) {{
    contactSection.style.display = "block";
  }}

  // Read email/name/survey from sessionStorage (saved by core-signup)
  var sessionEmail = null;
  var sessionName = null;
  var sessionCid = null;
  var sessionCoreSurvey = null;
  var sessionContact = null;
  var sessionShipping = null;
  try {{
    sessionEmail = sessionStorage.getItem("onz_email") || null;
    sessionName = sessionStorage.getItem("onz_name") || null;
    sessionCid = sessionStorage.getItem("onz_customer_id") || null;
    var raw = sessionStorage.getItem("onz_core_survey");
    if (raw) sessionCoreSurvey = JSON.parse(raw);
    var rawContact = sessionStorage.getItem("onz_contact");
    if (rawContact) sessionContact = JSON.parse(rawContact);
    var rawShipping = sessionStorage.getItem("onz_shipping");
    if (rawShipping) sessionShipping = JSON.parse(rawShipping);
  }} catch(e) {{}}
  if (!customerEmail && sessionEmail) customerEmail = sessionEmail;
  if (!customerName && sessionName) customerName = sessionName;
  if (!customerId && sessionCid) customerId = sessionCid;

  // Check if creator profile already completed
  if (existingCreator.creator_completed_at) {{
    doneEl.style.display = "block";
    formEl.style.display = "none";
  }} else {{
    formEl.style.display = "block";
    doneEl.style.display = "none";

    // Pre-fill and hide already-answered sections
    if (existingCreator.primary_platform) {{
      var radio = document.querySelector('input[name="primary_platform"][value="' + existingCreator.primary_platform + '"]');
      if (radio) {{
        radio.checked = true;
        radio.closest(".ck-field").style.display = "none";
        // Also show and pre-fill handle
        var info = platformInfo[existingCreator.primary_platform] || platformInfo.other;
        document.getElementById("onz-handle-field").style.display = "block";
        document.getElementById("onz-handle-label").textContent = info.label + " handle";
        if (existingCreator.primary_handle) {{
          document.getElementById("onz-primary-handle").value = existingCreator.primary_handle;
          document.getElementById("onz-handle-field").style.display = "none";
        }}
      }}
    }}

    if (existingCreator.following_size) {{
      var radio = document.querySelector('input[name="following_size"][value="' + existingCreator.following_size + '"]');
      if (radio) {{ radio.checked = true; radio.closest(".ck-field").style.display = "none"; }}
    }}

    if (existingCreator.hashtags) {{
      document.getElementById("onz-hashtags").value = existingCreator.hashtags;
      document.getElementById("onz-hashtags").closest(".ck-field").style.display = "none";
    }}

    if (existingCreator.has_brand_partnerships) {{
      var radio = document.querySelector('input[name="has_brand_partnerships"][value="' + existingCreator.has_brand_partnerships + '"]');
      if (radio) {{
        radio.checked = true;
        radio.closest(".ck-field").style.display = "none";
      }}
    }}

    if (existingCreator.content_type && existingCreator.content_type.length > 0) {{
      existingCreator.content_type.forEach(function(ct) {{
        var cb = document.querySelector('[data-field="content_type"] input[value="' + ct + '"]');
        if (cb) cb.checked = true;
      }});
      document.querySelector('[data-field="content_type"]').closest(".ck-field").style.display = "none";
    }}

    if (existingCreator.other_platforms && existingCreator.other_platforms.length > 0) {{
      // Pre-check other platform chips
      existingCreator.other_platforms.forEach(function(p) {{
        var cb = document.querySelector('[data-field="other_platforms"] input[value="' + p + '"]');
        if (cb) cb.checked = true;
      }});
      document.querySelector('[data-field="other_platforms"]').closest(".ck-field").style.display = "none";
    }}
  }}

  // Submit
  window.submitCreatorProfile = function() {{
    var btn = document.getElementById("onz-submit-btn");
    var errorEl = document.getElementById("onz-error");
    errorEl.style.display = "none";
    btn.disabled = true;
    btn.textContent = "Submitting...";

    function getRadio(name) {{
      var el = document.querySelector('input[name="' + name + '"]:checked');
      return el ? el.value : "";
    }}
    function getChecked(field) {{
      var els = document.querySelectorAll('[data-field="' + field + '"] input:checked');
      return Array.from(els).map(function(el) {{ return el.value; }});
    }}

    // Always capture phone (field is pre-filled from Shopify even when hasAddress=true)
    var cPhone = document.getElementById("onz-phone").value.trim();

    // Validate contact/shipping if section is visible
    if (!hasAddress) {{
      var cEmail = document.getElementById("onz-email").value.trim();
      var cFirst = document.getElementById("onz-firstname").value.trim();
      var cLast = document.getElementById("onz-lastname").value.trim();
      var cAddr1 = document.getElementById("onz-address1").value.trim();
      var cCity = document.getElementById("onz-city").value.trim();
      var cState = document.getElementById("onz-state").value.trim();
      var cZip = document.getElementById("onz-zip").value.trim();

      if (!cEmail) {{
        errorEl.textContent = "Please enter your email address.";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      if (!cFirst || !cLast) {{
        errorEl.textContent = "Please enter your first and last name.";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      if (!cPhone) {{
        errorEl.textContent = "Please enter your phone number.";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      // US phone validation
      var cleanPhone = cPhone.replace(/[\s\-\(\)\.]/g, "");
      if (cleanPhone.startsWith("+1")) cleanPhone = cleanPhone.slice(2);
      else if (cleanPhone.startsWith("1") && cleanPhone.length === 11) cleanPhone = cleanPhone.slice(1);
      if (!/^\d{{10}}$/.test(cleanPhone)) {{
        errorEl.textContent = "Please enter a valid US phone number (10 digits).";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      if (!cAddr1 || !cCity || !cState || !cZip) {{
        errorEl.textContent = "Please fill in your shipping address.";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      // US ZIP validation
      if (!/^\d{{5}}(-\d{{4}})?$/.test(cZip)) {{
        errorEl.textContent = "Please enter a valid US ZIP code (e.g. 90210).";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
      // US country validation
      var cCountry = document.getElementById("onz-country").value;
      if (cCountry && cCountry !== "US" && cCountry !== "United States") {{
        errorEl.textContent = "We currently ship to US addresses only.";
        errorEl.style.display = "block";
        btn.disabled = false; btn.textContent = "Submit"; return;
      }}
    }}

    // Only require platform/handle if not already saved
    if (!getRadio("primary_platform") && !existingCreator.primary_platform) {{
      errorEl.textContent = "Please select your primary platform.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Submit"; return;
    }}
    var handle = document.getElementById("onz-primary-handle").value.trim() || existingCreator.primary_handle || "";
    if (!handle && !existingCreator.primary_handle) {{
      errorEl.textContent = "Please enter your handle or profile URL.";
      errorEl.style.display = "block";
      btn.disabled = false; btn.textContent = "Submit"; return;
    }}

    // Collect other platform handles
    var otherHandles = {{}};
    document.querySelectorAll(".onz-oh-input").forEach(function(inp) {{
      var p = inp.getAttribute("data-platform");
      var v = inp.value.trim();
      if (v) otherHandles[p] = v;
    }});

    var contentTypes = getChecked("content_type");
    if (contentTypes.length === 0 && existingCreator.content_type) contentTypes = existingCreator.content_type;
    var contentOther = "";
    if (contentTypes.indexOf("other") !== -1) {{
      contentOther = document.getElementById("onz-content-other-text").value.trim();
    }}

    var otherPlatforms = getChecked("other_platforms");
    if (otherPlatforms.length === 0 && existingCreator.other_platforms) otherPlatforms = existingCreator.other_platforms;

    // Build contact/shipping data if provided
    var contactData = null;
    var shippingData = null;
    if (!hasAddress) {{
      var emailVal = document.getElementById("onz-email").value.trim();
      contactData = {{
        first_name: document.getElementById("onz-firstname").value.trim(),
        last_name: document.getElementById("onz-lastname").value.trim(),
        phone: document.getElementById("onz-phone").value.trim(),
        email: emailVal,
      }};
      shippingData = {{
        address1: document.getElementById("onz-address1").value.trim(),
        address2: document.getElementById("onz-address2").value.trim(),
        city: document.getElementById("onz-city").value.trim(),
        province: document.getElementById("onz-state").value.trim(),
        zip: document.getElementById("onz-zip").value.trim(),
        country: document.getElementById("onz-country").value,
      }};
      // Use form email/name if customer not logged in
      if (!customerEmail && emailVal) customerEmail = emailVal;
      if (!customerName && contactData.first_name) customerName = contactData.first_name + " " + contactData.last_name;
    }}

    var payload = {{
      form_type: "onzenna_creator_signup",
      customer_id: customerId,
      customer_email: customerEmail,
      submitted_at: new Date().toISOString(),
      contact: contactData,
      shipping_address: shippingData,
      survey_data: {{
        primary_platform: getRadio("primary_platform") || existingCreator.primary_platform || "",
        primary_handle: handle,
        other_platforms: otherPlatforms,
        other_handles: otherHandles,
        following_size: getRadio("following_size") || existingCreator.following_size || "",
        hashtags: document.getElementById("onz-hashtags").value.trim() || existingCreator.hashtags || "",
        content_type: contentTypes,
        content_type_other: contentOther,
        has_brand_partnerships: getRadio("has_brand_partnerships") || existingCreator.has_brand_partnerships || "",
        brand_names: document.getElementById("onz-brand-names").value.trim() || existingCreator.brand_names || "",
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

    // Send to Airtable inbound pipeline (include core-signup data from metafields)
    fetch(AIRTABLE_WEBHOOK, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        customer_name: customerName || (payload.customer_email ? payload.customer_email.split("@")[0] : "Unknown"),
        customer_email: payload.customer_email || "",
        customer_id: customerId,
        submitted_at: payload.submitted_at,
        survey_data: payload.survey_data,
        contact: {{
          phone: cPhone || (contactData && contactData.phone) || (sessionContact && sessionContact.phone) || shopifyAddress.phone || null,
          first_name: (contactData && contactData.first_name) || (sessionContact && sessionContact.first_name) || null,
          last_name: (contactData && contactData.last_name) || (sessionContact && sessionContact.last_name) || null,
        }},
        shipping_address: {{
          address1: (shippingData && shippingData.address1) || (sessionShipping && sessionShipping.address1) || shopifyAddress.address1 || null,
          address2: (shippingData && shippingData.address2) || (sessionShipping && sessionShipping.address2) || shopifyAddress.address2 || null,
          city: (shippingData && shippingData.city) || (sessionShipping && sessionShipping.city) || shopifyAddress.city || null,
          province: (shippingData && shippingData.province) || (sessionShipping && sessionShipping.province) || shopifyAddress.province || null,
          zip: (shippingData && shippingData.zip) || (sessionShipping && sessionShipping.zip) || shopifyAddress.zip || null,
          country: (shippingData && shippingData.country) || (sessionShipping && sessionShipping.country) || shopifyAddress.country || null,
        }},
        core_signup_data: {{
          journey_stage: (sessionCoreSurvey && sessionCoreSurvey.journey_stage) || existingCoreData.journey_stage || null,
          baby_birth_month: (sessionCoreSurvey && sessionCoreSurvey.baby_birth_month) || existingCoreData.baby_birth_month || null,
          has_other_children: (sessionCoreSurvey && sessionCoreSurvey.has_other_children) || existingCoreData.has_other_children || null,
          other_child_birth: (sessionCoreSurvey && sessionCoreSurvey.other_child_birth) || existingCoreData.other_child_birth || null,
          third_child_birth: (sessionCoreSurvey && sessionCoreSurvey.third_child_birth) || existingCoreData.third_child_birth || null,
        }},
      }}),
    }}).catch(function() {{}});

    showSection(successEl);
  }};
}})();
</script>

{{% schema %}}
{{
  "name": "Creator Signup",
  "tag": "section",
  "class": "creator-signup-section"
}}
{{% endschema %}}
'''


def build_page_template():
    return json.dumps({
        "sections": {
            "main": {
                "type": "creator-signup",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# -- Deploy / Rollback --
def deploy(dry_run=False, published=True):
    print(f"\n{'=' * 60}")
    print(f"  Deploy Creator Signup Page")
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
    create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "creator-signup", published=published)

    page_url = f"https://{SHOP.replace('.myshopify.com', '')}.com/pages/{PAGE_HANDLE}"
    print(f"\n  Page URL: {page_url}")
    if not published:
        print(f"  (Page is hidden -- only accessible by direct URL)")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


def rollback():
    print(f"\n{'=' * 60}")
    print(f"  Rollback Creator Signup Page")
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

    parser = argparse.ArgumentParser(description="Deploy Onzenna Creator Profile page (Part 2)")
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
