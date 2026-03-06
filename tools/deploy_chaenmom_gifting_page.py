"""CHA&MOM + Naeiae Influencer Gifting Page 배포

CHA&MOM 제품 필수 (연령제한 없음) + Naeiae 옵셔널 (아기 6-24개월만 표시)
기존 deploy_influencer_page.py 와 동일한 5-step 폼 + Shopify Theme API 배포 구조.

Usage:
    python tools/deploy_chaenmom_gifting_page.py
    python tools/deploy_chaenmom_gifting_page.py --dry-run
    python tools/deploy_chaenmom_gifting_page.py --rollback
"""

import os
import sys
import json
import urllib.request
import urllib.error
from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"
N8N_WEBHOOK_URL = os.getenv("N8N_CHAMOM_GIFTING_WEBHOOK", "")

SECTION_KEY = "sections/influencer-gifting-chamom.liquid"
TEMPLATE_KEY = "templates/page.influencer-gifting-chamom.json"
PAGE_HANDLE = "influencer-gifting-chamom"
PAGE_TITLE = "CHA&MOM Gifting Application"

# ── Product Data ─────────────────────────────────────────────
# CHA&MOM: optional, no age restriction (age_min=0, age_max=999)
# Naeiae: optional, baby 6-24 months only
PRODUCTS = {
    "chamom_lotion": {
        "title": "CHA&MOM Phyto Seline Moisture Lotion",
        "subtitle": "8.46oz",
        "shopify_product_id": 9431441965378,
        "price": "$28.70",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/chamom-phyto-seline-moisture-lotion-846oz-1508457.jpg?v=1765928671",
        "colors": [],
        "variant_map": {"Default": 48635619148098},
        "image_map": {},
        "age_min": 0, "age_max": 999,
        "optional": True,
        "brand": "CHA&MOM",
    },
    "chamom_wash": {
        "title": "CHA&MOM Phyto Seline Hair & Body Wash",
        "subtitle": "10.58oz",
        "shopify_product_id": 9431446061378,
        "price": "$26.50",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/chamom-phyto-seline-hydro-hair-body-wash-1058oz-5587747.jpg?v=1765928671",
        "colors": [],
        "variant_map": {"Default": 48635632484674},
        "image_map": {},
        "age_min": 0, "age_max": 999,
        "optional": True,
        "brand": "CHA&MOM",
    },
    "chamom_cream": {
        "title": "CHA&MOM Phyto Seline Intense Cream",
        "subtitle": "5.29oz",
        "shopify_product_id": 9431443210562,
        "price": "$29.70",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/chamom-phyto-seline-intense-cream-529oz-6253768.jpg?v=1765928671",
        "colors": [],
        "variant_map": {"Default": 48635621441858},
        "image_map": {},
        "age_min": 0, "age_max": 999,
        "optional": True,
        "brand": "CHA&MOM",
    },
    # Naeiae: optional, only shown if baby 6-24 months
    "naeiae_rice_snack": {
        "title": "Naeiae Pop Rice Snack Bundle",
        "subtitle": "5 Packs - Korean Organic Rice",
        "shopify_product_id": 9699496853826,
        "price": "$24.60",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/naeiae-korean-pop-rice-snack-bundle-5-packs-70-off-clearance-1741934.jpg?v=1772589433",
        "colors": [],
        "variant_map": {"Default": 49691166212418},
        "image_map": {},
        "age_min": 6, "age_max": 24,
        "optional": True,
        "brand": "Naeiae",
    },
}

COLLAB_TERMS = (
    '<ul class="igf-terms-list">'
    "<li>Total video length: 30 seconds</li>"
    "<li>Uploaded content must include voiceover + subtitles</li>"
    "<li>Must use royalty-free music</li>"
    "<li>Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @chamom_official (IG)</li>"
    "<li>Must include: #CHAMOM #ChaAndMom #BabySkincare #KBeautyBaby #Onzenna</li>"
    "<li>Content must be posted within 14 days of receiving the product</li>"
    "<li>You agree that Onzenna may repost your content with credit</li>"
    "</ul>"
)

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY",
]

US_STATE_NAMES = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","DC":"District of Columbia",
    "FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois",
    "IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana",
    "ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota",
    "MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada",
    "NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York",
    "NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma",
    "OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina",
    "SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont",
    "VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming",
}


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


def create_or_update_page(handle, title, template_suffix):
    result = shopify_request("GET", f"/pages.json?handle={handle}")
    pages = result.get("pages", [])

    page_data = {
        "page": {
            "title": title,
            "handle": handle,
            "template_suffix": template_suffix,
            "body_html": "",
            "published": True,
        }
    }

    if pages:
        page_id = pages[0]["id"]
        print(f"  Updating existing page (ID: {page_id}) ...")
        shopify_request("PUT", f"/pages/{page_id}.json", page_data)
        print(f"  [OK] Page updated")
        return page_id
    else:
        print(f"  Creating new page ...")
        result = shopify_request("POST", "/pages.json", page_data)
        page_id = result["page"]["id"]
        print(f"  [OK] Page created (ID: {page_id})")
        return page_id


# ── Liquid Section Builder ─────────────────────────────────────
def build_products_js():
    js_products = {}
    for key, p in PRODUCTS.items():
        js_products[key] = {
            "title": p["title"],
            "price": p["price"],
            "productId": p["shopify_product_id"],
            "image": p["image_url"],
            "colors": p["colors"],
            "variantMap": p["variant_map"],
            "imageMap": p.get("image_map", {}),
            "ageMin": p["age_min"],
            "ageMax": p["age_max"],
            "optional": p.get("optional", False),
            "subtitle": p.get("subtitle", ""),
            "brand": p.get("brand", ""),
        }
    return json.dumps(js_products, indent=2)


def build_state_options():
    options = ['<option value="">Select State</option>']
    for code in US_STATES:
        name = US_STATE_NAMES[code]
        options.append(f'<option value="{code}">{name}</option>')
    return "\n".join(options)


def build_section_liquid(webhook_url):
    products_js = build_products_js()
    state_options = build_state_options()

    return f'''<!-- CHA&MOM + Naeiae Influencer Gifting Form -->
<!-- Generated by tools/deploy_chaenmom_gifting_page.py -->

{{% comment %}}
  CHA&MOM products: required, no age restriction
  Naeiae products: optional, shown only if baby 6-24 months
{{% endcomment %}}
{{% if customer %}}
<script id="igf-customer-data" type="application/json">
{{"name": {{{{ customer.name | json }}}}, "email": {{{{ customer.email | json }}}}, "phone": {{{{ customer.phone | json }}}}, "id": {{{{ customer.id }}}}}}
</script>
{{% endif %}}

<style>
  .igf-container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
    font-family: inherit;
  }}
  .igf-container * {{ box-sizing: border-box; }}

  .igf-progress {{
    display: flex;
    gap: 4px;
    margin-bottom: 32px;
  }}
  .igf-progress-step {{
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: #e0e0e0;
    transition: background 0.3s;
  }}
  .igf-progress-step.active {{ background: #3A5A40; }}
  .igf-progress-step.done {{ background: #3A5A40; }}

  .igf-step {{ display: none; }}
  .igf-step.active {{ display: block; }}
  .igf-step h2 {{
    font-size: 1.5rem;
    margin-bottom: 8px;
    color: #1a1a1a;
  }}
  .igf-subtitle {{
    color: #666;
    margin-bottom: 24px;
    font-size: 0.95rem;
  }}

  .igf-field {{
    margin-bottom: 20px;
  }}
  .igf-field label {{
    display: block;
    font-weight: 600;
    margin-bottom: 6px;
    font-size: 0.9rem;
    color: #333;
  }}
  .igf-field input,
  .igf-field select,
  .igf-field textarea {{
    width: 100%;
    padding: 10px 12px;
    border: 1.5px solid #ccc;
    border-radius: 8px;
    font-size: 1rem;
    transition: border-color 0.2s;
    font-family: inherit;
  }}
  .igf-field input:focus,
  .igf-field select:focus {{
    outline: none;
    border-color: #3A5A40;
  }}
  .igf-field input.invalid {{
    border-color: #e74c3c;
  }}
  .igf-field small {{
    display: block;
    margin-top: 4px;
    color: #888;
    font-size: 0.8rem;
  }}
  .igf-field .igf-error {{
    color: #e74c3c;
    font-size: 0.8rem;
    margin-top: 4px;
    display: none;
  }}

  .igf-phone-group {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .igf-phone-prefix {{
    padding: 10px 12px;
    background: #f5f5f5;
    border: 1.5px solid #ccc;
    border-radius: 8px;
    font-size: 1rem;
    white-space: nowrap;
  }}
  .igf-phone-group input {{ flex: 1; }}

  .igf-toggle-label {{
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    font-weight: 500;
    padding: 12px;
    background: #f9f9f9;
    border-radius: 8px;
  }}
  .igf-toggle-label input[type="checkbox"] {{
    width: 18px;
    height: 18px;
    accent-color: #3A5A40;
  }}

  .igf-brand-section {{
    margin-bottom: 24px;
    padding: 16px;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
  }}
  .igf-brand-section h3 {{
    font-size: 1.1rem;
    margin-bottom: 4px;
  }}
  .igf-brand-required {{
    display: inline-block;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
    margin-left: 8px;
    vertical-align: middle;
  }}
  .igf-brand-required.required {{
    background: #fde8e8;
    color: #c0392b;
  }}
  .igf-brand-required.optional-label {{
    background: #f0f0f0;
    color: #666;
  }}
  .igf-brand-desc {{
    color: #666;
    font-size: 0.85rem;
    margin-bottom: 12px;
  }}

  .igf-product-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }}
  @media (min-width: 520px) {{
    .igf-product-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (min-width: 768px) {{
    .igf-product-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}

  .igf-product-card {{
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
    position: relative;
    background: #fff;
  }}
  .igf-product-card:hover {{
    border-color: #aaa;
    transform: translateY(-2px);
  }}
  .igf-product-card.selected {{
    border-color: #3A5A40;
    box-shadow: 0 0 0 3px rgba(58, 90, 64, 0.15);
  }}
  .igf-product-card img {{
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
    border-radius: 8px;
    margin-bottom: 12px;
    background: #fafafa;
  }}
  .igf-product-card .igf-card-title {{
    font-weight: 600;
    font-size: 0.9rem;
    margin-bottom: 4px;
    color: #1a1a1a;
  }}
  .igf-product-card .igf-card-price {{
    color: #3A5A40;
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 8px;
  }}
  .igf-product-card .igf-card-subtitle {{
    color: #888;
    font-size: 0.8rem;
    margin-bottom: 8px;
  }}
  .igf-product-card .igf-select-btn {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 2px solid #3A5A40;
    border-radius: 8px;
    background: #fff;
    color: #3A5A40;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.9rem;
  }}
  .igf-product-card .igf-select-btn:hover {{ background: #f0f4f0; }}
  .igf-product-card.selected .igf-select-btn {{
    background: #3A5A40;
    color: #fff;
  }}
  .igf-optional-badge {{
    position: absolute;
    top: 8px;
    right: 8px;
    background: #f0f0f0;
    color: #666;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
  }}

  .igf-address-row {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }}
  @media (min-width: 520px) {{
    .igf-address-row.igf-row-3 {{ grid-template-columns: 2fr 1fr 1fr; }}
  }}

  .igf-terms-box {{
    background: #f9f9f9;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px 16px 16px 20px;
    margin-bottom: 20px;
    font-size: 0.9rem;
    line-height: 1.8;
    color: #333;
  }}
  .igf-terms-list {{
    list-style: disc;
    padding-left: 18px;
    margin: 0;
  }}
  .igf-terms-list li {{ margin-bottom: 4px; }}

  .igf-btn-row {{
    display: flex;
    gap: 12px;
    margin-top: 24px;
  }}
  .igf-btn {{
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
    font-family: inherit;
  }}
  .igf-btn-primary {{
    background: #3A5A40;
    color: #fff;
    flex: 1;
  }}
  .igf-btn-primary:hover {{ background: #2d4832; }}
  .igf-btn-primary:disabled {{
    background: #ccc;
    cursor: not-allowed;
  }}
  .igf-btn-secondary {{
    background: #f0f0f0;
    color: #333;
  }}
  .igf-btn-secondary:hover {{ background: #e0e0e0; }}

  .igf-success {{
    text-align: center;
    padding: 60px 20px;
  }}
  .igf-success h2 {{
    color: #27ae60;
    margin-bottom: 12px;
  }}
  .igf-success p {{ color: #666; font-size: 1.1rem; }}

  .igf-spinner {{
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 2px solid #fff;
    border-top-color: transparent;
    border-radius: 50%;
    animation: igf-spin 0.6s linear infinite;
    margin-right: 8px;
    vertical-align: middle;
  }}
  @keyframes igf-spin {{
    to {{ transform: rotate(360deg); }}
  }}

  .igf-age-badge {{
    display: inline-block;
    padding: 4px 10px;
    background: #e8f4fd;
    color: #3A5A40;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 6px;
  }}
  .igf-age-badge.expecting {{
    background: #fef3e2;
    color: #e67e22;
  }}
  .igf-no-products {{
    text-align: center;
    padding: 40px;
    color: #666;
    background: #f9f9f9;
    border-radius: 12px;
  }}
  .igf-naeiae-note {{
    background: #fff8e1;
    border: 1px solid #ffe082;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 0.85rem;
    color: #666;
    margin-top: 8px;
  }}
</style>

<div class="igf-container" id="igf-app">
  <div class="igf-progress">
    <div class="igf-progress-step active" data-for="1"></div>
    <div class="igf-progress-step" data-for="2"></div>
    <div class="igf-progress-step" data-for="3"></div>
    <div class="igf-progress-step" data-for="4"></div>
    <div class="igf-progress-step" data-for="5"></div>
  </div>

  <!-- Step 1: Personal Info -->
  <div class="igf-step active" data-step="1">
    <h2>Personal Information</h2>
    <p class="igf-subtitle">Tell us about yourself</p>

    <div class="igf-field">
      <label for="igf-name">Full Name *</label>
      <input type="text" id="igf-name" required placeholder="Jane Smith">
      <div class="igf-error">Please enter your full name</div>
    </div>
    <div class="igf-field">
      <label for="igf-email">Email *</label>
      <input type="email" id="igf-email" required placeholder="jane@example.com">
      <div class="igf-error">Please enter a valid email</div>
    </div>
    <div class="igf-field">
      <label for="igf-phone">Phone Number *</label>
      <div class="igf-phone-group">
        <span class="igf-phone-prefix">+1</span>
        <input type="tel" id="igf-phone" required placeholder="(555) 123-4567">
      </div>
      <div class="igf-error">US phone number only (10 digits)</div>
    </div>
    <div class="igf-field">
      <label for="igf-instagram">Instagram Handle</label>
      <input type="text" id="igf-instagram" placeholder="@yourusername">
      <small>Leave blank or type &lsquo;None&rsquo; if not applicable</small>
    </div>
    <div class="igf-field">
      <label for="igf-tiktok">TikTok Handle</label>
      <input type="text" id="igf-tiktok" placeholder="@yourusername">
      <small>Leave blank or type &lsquo;None&rsquo; if not applicable</small>
    </div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-primary" data-go="2">Next</button>
    </div>
  </div>

  <!-- Step 2: Baby Info -->
  <div class="igf-step" data-step="2">
    <h2>Baby Information</h2>
    <p class="igf-subtitle">We&rsquo;ll check if additional products are available for your child</p>

    <div class="igf-field">
      <label for="igf-baby1-bday">First Child Birthday / Expected Due Date *</label>
      <input type="date" id="igf-baby1-bday" required>
      <div id="igf-baby1-age"></div>
      <div class="igf-error">Please enter a date</div>
    </div>

    <div class="igf-field">
      <label class="igf-toggle-label">
        <input type="checkbox" id="igf-has-baby2">
        <span>I have another child</span>
      </label>
    </div>

    <div class="igf-field" id="igf-baby2-section" style="display:none">
      <label for="igf-baby2-bday">Second Child Birthday / Expected Due Date *</label>
      <input type="date" id="igf-baby2-bday">
      <div id="igf-baby2-age"></div>
    </div>

    <div class="igf-naeiae-note" id="igf-naeiae-hint" style="display:none">
      Your child qualifies for Naeiae baby snacks! You can optionally add them in the next step.
    </div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="1">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="3">Next</button>
    </div>
  </div>

  <!-- Step 3: Product Selection -->
  <div class="igf-step" data-step="3">
    <h2>Select Your Products</h2>
    <p class="igf-subtitle">Choose the products you'd like to try. Click a card to select.</p>

    <div class="igf-brand-section" id="igf-chamom-section">
      <h3>CHA&amp;MOM <span class="igf-brand-required optional-label">Optional</span></h3>
      <p class="igf-brand-desc">Gentle baby skincare from 60 years of trusted care</p>
      <div class="igf-product-grid" id="igf-products-chamom"></div>
    </div>

    <div class="igf-brand-section" id="igf-naeiae-section" style="display:none">
      <h3>Naeiae <span class="igf-brand-required optional-label">Optional</span></h3>
      <p class="igf-brand-desc">Organic rice snacks for babies 6-24 months</p>
      <div class="igf-product-grid" id="igf-products-naeiae"></div>
    </div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="2">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="4">Next</button>
    </div>
  </div>

  <!-- Step 4: Shipping Address -->
  <div class="igf-step" data-step="4">
    <h2>Shipping Address</h2>
    <p class="igf-subtitle">Where should we send your products?</p>

    <div class="igf-field">
      <label for="igf-street">Street Address *</label>
      <input type="text" id="igf-street" required placeholder="123 Main St">
      <div class="igf-error">Please enter your street address</div>
    </div>
    <div class="igf-field">
      <label for="igf-apt">Apt / Suite / Unit</label>
      <input type="text" id="igf-apt" placeholder="Apt 4B">
    </div>
    <div class="igf-address-row igf-row-3">
      <div class="igf-field">
        <label for="igf-city">City *</label>
        <input type="text" id="igf-city" required placeholder="New York">
        <div class="igf-error">Required</div>
      </div>
      <div class="igf-field">
        <label for="igf-state">State *</label>
        <select id="igf-state" required>
          {state_options}
        </select>
        <div class="igf-error">Required</div>
      </div>
      <div class="igf-field">
        <label for="igf-zip">ZIP Code *</label>
        <input type="text" id="igf-zip" required placeholder="10001" maxlength="10">
        <div class="igf-error">Required</div>
      </div>
    </div>
    <div class="igf-field">
      <label for="igf-country">Country *</label>
      <select id="igf-country" required>
        <option value="US" selected>United States</option>
        <option value="CA">Canada</option>
      </select>
    </div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="3">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="5">Next</button>
    </div>
  </div>

  <!-- Step 5: Terms & Submit -->
  <div class="igf-step" data-step="5">
    <h2>Collaboration Terms</h2>
    <p class="igf-subtitle">Please review and agree to the terms below</p>

    <div class="igf-terms-box">{COLLAB_TERMS}</div>

    <div class="igf-field">
      <label class="igf-toggle-label">
        <input type="checkbox" id="igf-agree" required>
        <span>I agree to the collaboration terms *</span>
      </label>
      <div class="igf-error">You must agree to the terms</div>
    </div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="4">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" id="igf-submit-btn">
        Submit Application
      </button>
    </div>
  </div>

  <!-- Success -->
  <div class="igf-step igf-success" data-step="success">
    <h2>Thank you for your application!</h2>
    <p>We will review your request and get back to you shortly.<br>Keep an eye on your email!</p>
  </div>
</div>

<script>
(function() {{
  "use strict";

  const WEBHOOK_URL = "{webhook_url}";
  const PRODUCTS = {products_js};
  const TOTAL_STEPS = 5;
  let currentStep = 1;
  let selectedProducts = {{}};

  function calcAgeMonths(dateStr) {{
    if (!dateStr) return null;
    const bd = new Date(dateStr);
    const now = new Date();
    if (bd > now) return -1;
    return (now.getFullYear() - bd.getFullYear()) * 12 + (now.getMonth() - bd.getMonth());
  }}

  function ageLabel(months) {{
    if (months === null) return "";
    if (months < 0) return '<span class="igf-age-badge expecting">Expecting</span>';
    if (months < 12) return '<span class="igf-age-badge">' + months + ' months old</span>';
    const y = Math.floor(months / 12);
    const m = months % 12;
    const txt = y + (y === 1 ? " year" : " years") + (m > 0 ? " " + m + " mo" : "");
    return '<span class="igf-age-badge">' + txt + '</span>';
  }}

  function getAges() {{
    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;
    const ages = [calcAgeMonths(bd1)];
    if (bd2) ages.push(calcAgeMonths(bd2));
    return ages;
  }}

  function isNaeiaeEligible() {{
    const ages = getAges();
    for (const age of ages) {{
      const eff = age < 0 ? 0 : (age || 0);
      if (eff >= 6 && eff < 24) return true;
    }}
    return false;
  }}

  function updateAgeDisplay() {{
    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-baby2-bday").value;
    document.getElementById("igf-baby1-age").innerHTML = ageLabel(calcAgeMonths(bd1));
    document.getElementById("igf-baby2-age").innerHTML = ageLabel(calcAgeMonths(bd2));

    // Show/hide Naeiae hint
    const hint = document.getElementById("igf-naeiae-hint");
    if (hint) hint.style.display = isNaeiaeEligible() ? "block" : "none";
  }}

  // ── Product Rendering (split by brand) ─────────────────────
  function renderProducts() {{
    const chamomGrid = document.getElementById("igf-products-chamom");
    const naeiaeGrid = document.getElementById("igf-products-naeiae");
    const naeiaeSection = document.getElementById("igf-naeiae-section");
    const eligible = isNaeiaeEligible();

    chamomGrid.innerHTML = "";
    naeiaeGrid.innerHTML = "";
    naeiaeSection.style.display = eligible ? "block" : "none";

    // Remove Naeiae selections if no longer eligible
    if (!eligible) {{
      for (const k of Object.keys(selectedProducts)) {{
        if (PRODUCTS[k] && PRODUCTS[k].brand === "Naeiae") delete selectedProducts[k];
      }}
    }}

    for (const [key, p] of Object.entries(PRODUCTS)) {{
      if (p.brand === "Naeiae" && !eligible) continue;
      const grid = p.brand === "Naeiae" ? naeiaeGrid : chamomGrid;
      const card = document.createElement("div");
      card.className = "igf-product-card" + (selectedProducts[key] ? " selected" : "");
      card.dataset.key = key;

      card.innerHTML =
        '<div class="igf-optional-badge">Optional</div>' +
        '<img src="' + p.image + '" alt="' + p.title + '" loading="lazy">' +
        '<div class="igf-card-title">' + p.title + '</div>' +
        (p.subtitle ? '<div class="igf-card-subtitle">' + p.subtitle + '</div>' : '') +
        '<div class="igf-card-price">' + p.price + '</div>' +
        '<button type="button" class="igf-select-btn" data-key="' + key + '">' +
        (selectedProducts[key] ? '&#10003; Selected' : 'Select') + '</button>';

      grid.appendChild(card);
    }}

    // Event listeners
    document.querySelectorAll("#igf-products-chamom .igf-select-btn, #igf-products-naeiae .igf-select-btn").forEach(btn => {{
      btn.addEventListener("click", function(e) {{
        e.stopPropagation();
        toggleProduct(this.dataset.key);
      }});
    }});
    document.querySelectorAll("#igf-products-chamom .igf-product-card, #igf-products-naeiae .igf-product-card").forEach(card => {{
      card.addEventListener("click", function(e) {{
        if (e.target.tagName === "BUTTON") return;
        toggleProduct(this.dataset.key);
      }});
    }});
  }}

  function toggleProduct(key) {{
    if (selectedProducts[key]) {{
      delete selectedProducts[key];
    }} else {{
      const p = PRODUCTS[key];
      selectedProducts[key] = {{
        productKey: key,
        productId: p.productId,
        title: p.title,
        price: p.price,
        color: "",
        variantId: p.variantMap["Default"] || null,
      }};
    }}
    renderProducts();
  }}

  // ── Step Navigation ────────────────────────────────────────
  function goToStep(n) {{
    if (n > currentStep && !validateStep(currentStep)) return;
    if (n === 3) {{ updateAgeDisplay(); renderProducts(); }}

    document.querySelectorAll(".igf-step").forEach(s => s.classList.remove("active"));
    const target = document.querySelector('.igf-step[data-step="' + n + '"]');
    if (target) target.classList.add("active");

    document.querySelectorAll(".igf-progress-step").forEach(bar => {{
      const barStep = parseInt(bar.dataset.for);
      bar.classList.toggle("done", barStep < n);
      bar.classList.toggle("active", barStep === n);
    }});

    currentStep = n;
    window.scrollTo({{ top: 0, behavior: "smooth" }});
  }}

  // ── Validation ─────────────────────────────────────────────
  function validateStep(step) {{
    let valid = true;
    function check(id, condition) {{
      const el = document.getElementById(id);
      const errEl = el ? el.closest(".igf-field") : null;
      const err = errEl ? errEl.querySelector(".igf-error") : null;
      if (!condition) {{
        if (el) el.classList.add("invalid");
        if (err) err.style.display = "block";
        valid = false;
      }} else {{
        if (el) el.classList.remove("invalid");
        if (err) err.style.display = "none";
      }}
    }}

    if (step === 1) {{
      check("igf-name", document.getElementById("igf-name").value.trim().length > 0);
      check("igf-email", /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(document.getElementById("igf-email").value));
      check("igf-phone", /^\\d{{10}}$/.test(document.getElementById("igf-phone").value.replace(/\\D/g, "")));
    }}
    if (step === 2) {{
      check("igf-baby1-bday", document.getElementById("igf-baby1-bday").value !== "");
      if (document.getElementById("igf-has-baby2").checked) {{
        check("igf-baby2-bday", document.getElementById("igf-baby2-bday").value !== "");
      }}
    }}
    if (step === 3) {{
      if (Object.keys(selectedProducts).length === 0) {{
        alert("Please select at least one product.");
        valid = false;
      }}
    }}
    if (step === 4) {{
      check("igf-street", document.getElementById("igf-street").value.trim().length > 0);
      check("igf-city", document.getElementById("igf-city").value.trim().length > 0);
      check("igf-state", document.getElementById("igf-state").value !== "");
      check("igf-zip", document.getElementById("igf-zip").value.trim().length >= 5);
    }}
    if (step === 5) {{
      check("igf-agree", document.getElementById("igf-agree").checked);
    }}
    return valid;
  }}

  // ── Submit ─────────────────────────────────────────────────
  function submit() {{
    if (!validateStep(5)) return;

    const btn = document.getElementById("igf-submit-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="igf-spinner"></span>Submitting...';

    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;

    const payload = {{
      form_type: "influencer_gifting_chamom",
      submitted_at: new Date().toISOString(),
      personal_info: {{
        full_name: document.getElementById("igf-name").value.trim(),
        email: document.getElementById("igf-email").value.trim(),
        phone: "+1" + document.getElementById("igf-phone").value.replace(/\\D/g, ""),
        instagram: document.getElementById("igf-instagram").value.trim() || "None",
        tiktok: document.getElementById("igf-tiktok").value.trim() || "None",
      }},
      baby_info: {{
        child_1: {{ birthday: bd1, age_months: calcAgeMonths(bd1) }},
        child_2: bd2 ? {{ birthday: bd2, age_months: calcAgeMonths(bd2) }} : null,
      }},
      selected_products: Object.values(selectedProducts).map(sp => ({{
        product_key: sp.productKey,
        product_id: sp.productId,
        variant_id: sp.variantId,
        title: sp.title,
        color: sp.color || "Default",
        price: sp.price,
        brand: PRODUCTS[sp.productKey] ? PRODUCTS[sp.productKey].brand : "",
      }})),
      shipping_address: {{
        street: document.getElementById("igf-street").value.trim(),
        apt: document.getElementById("igf-apt").value.trim(),
        city: document.getElementById("igf-city").value.trim(),
        state: document.getElementById("igf-state").value,
        zip: document.getElementById("igf-zip").value.trim(),
        country: document.getElementById("igf-country").value,
      }},
      terms_accepted: true,
      shopify_customer_id: window.__igf_customer ? window.__igf_customer.id : null,
    }};

    fetch(WEBHOOK_URL, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }})
    .then(r => {{
      if (!r.ok) throw new Error("HTTP " + r.status);
      goToStep("success");
    }})
    .catch(err => {{
      console.error("Submit error:", err);
      alert("Something went wrong. Please try again.");
      btn.disabled = false;
      btn.innerHTML = "Submit Application";
    }});
  }}

  function toggleBaby2() {{
    const show = document.getElementById("igf-has-baby2").checked;
    document.getElementById("igf-baby2-section").style.display = show ? "block" : "none";
    if (!show) document.getElementById("igf-baby2-bday").value = "";
    updateAgeDisplay();
  }}

  function prefillCustomer() {{
    const el = document.getElementById("igf-customer-data");
    if (!el) return;
    const c = JSON.parse(el.textContent);
    if (!c) return;
    window.__igf_customer = c;
    if (c.name) document.getElementById("igf-name").value = c.name;
    if (c.email) document.getElementById("igf-email").value = c.email;
  }}

  // ── Event Listeners ────────────────────────────────────────
  document.getElementById("igf-baby1-bday").addEventListener("change", updateAgeDisplay);
  document.getElementById("igf-baby2-bday").addEventListener("change", updateAgeDisplay);
  document.getElementById("igf-submit-btn").addEventListener("click", submit);
  document.getElementById("igf-has-baby2").addEventListener("change", toggleBaby2);

  document.querySelectorAll("[data-go]").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      goToStep(parseInt(this.dataset.go));
    }});
  }});

  prefillCustomer();
  window.IGF = {{ goToStep, submit, toggleBaby2 }};
}})();
</script>

{{% schema %}}
{{
  "name": "CHA&MOM Gifting Form",
  "tag": "section",
  "class": "influencer-gifting-chamom-section"
}}
{{% endschema %}}
'''


def build_template_json():
    return json.dumps({
        "sections": {
            "main": {
                "type": "influencer-gifting-chamom",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# ── Deploy ───────────────────────────────────────────────────────
def deploy(dry_run=False):
    print(f"\n{'='*60}")
    print(f"  Deploy CHA&MOM Gifting Page")
    print(f"{'='*60}")
    print(f"  Shop: {SHOP}")
    print(f"  Webhook: {N8N_WEBHOOK_URL or '(not set)'}")

    if not TOKEN:
        print("\n  [ERROR] SHOPIFY_ACCESS_TOKEN not set")
        return

    if not N8N_WEBHOOK_URL:
        print("\n  [WARN] N8N_CHAMOM_GIFTING_WEBHOOK not set")
        print("  Form submissions will fail until webhook URL is configured.")

    print(f"\n  [1/4] Getting active theme ...")
    theme_id = get_active_theme_id()

    print(f"\n  [2/4] Building template assets ...")
    section_content = build_section_liquid(N8N_WEBHOOK_URL or "")
    print(f"  Section size: {len(section_content):,} bytes")

    if dry_run:
        print(f"\n  [DRY RUN] Would upload:")
        print(f"    - {SECTION_KEY} ({len(section_content):,} bytes)")
        print(f"    - {TEMPLATE_KEY}")
        print(f"    - Create page: {PAGE_HANDLE}")
        return

    print(f"\n  [3/4] Uploading theme assets ...")
    upload_theme_asset(theme_id, SECTION_KEY, section_content)
    template_content = build_template_json()
    upload_theme_asset(theme_id, TEMPLATE_KEY, template_content)

    print(f"\n  [4/4] Creating Shopify page ...")
    page_id = create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "influencer-gifting-chamom")

    page_url = f"https://{SHOP}/pages/{PAGE_HANDLE}"
    print(f"\n{'='*60}")
    print(f"  [SUCCESS] Page deployed!")
    print(f"  Page ID: {page_id}")
    print(f"  URL: {page_url}")
    print(f"{'='*60}")

    os.makedirs(".tmp/shopify_gifting", exist_ok=True)
    info = {"page_id": page_id, "page_url": page_url, "theme_id": theme_id, "webhook_url": N8N_WEBHOOK_URL}
    with open(".tmp/shopify_gifting/chamom_deploy_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)

    return info


def rollback():
    print(f"\n  Rolling back ...")
    if not TOKEN:
        print("  [ERROR] No token")
        return

    theme_id = get_active_theme_id()

    try:
        shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={SECTION_KEY}")
        print(f"  [OK] Deleted {SECTION_KEY}")
    except Exception as e:
        print(f"  [SKIP] Section: {e}")

    for key in [TEMPLATE_KEY, "templates/page.influencer-gifting-chamom.liquid"]:
        try:
            shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={key}")
            print(f"  [OK] Deleted {key}")
        except Exception:
            pass

    try:
        result = shopify_request("GET", f"/pages.json?handle={PAGE_HANDLE}")
        for page in result.get("pages", []):
            shopify_request("DELETE", f"/pages/{page['id']}.json")
            print(f"  [OK] Deleted page {page['id']}")
    except Exception as e:
        print(f"  [SKIP] Page: {e}")

    print("  [DONE] Rollback complete")


def main():
    args = sys.argv[1:]
    if "--rollback" in args:
        rollback()
    elif "--dry-run" in args:
        deploy(dry_run=True)
    else:
        deploy()


if __name__ == "__main__":
    main()
