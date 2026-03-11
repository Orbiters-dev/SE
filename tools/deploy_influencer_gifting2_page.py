"""Deploy Influencer Gifting 2 page - for accepted creators from the inbound pipeline.

Cloned from deploy_influencer_page.py with these additions:
  - Pre-fills personal info from customer metafields / URL params
  - Shows creator profile data (IG, TikTok, following size) as read-only
  - Same age-based product selection logic
  - Same terms & conditions
  - Submits to a separate n8n webhook that creates Shopify draft order + updates Airtable

Usage:
    python tools/deploy_influencer_gifting2_page.py
    python tools/deploy_influencer_gifting2_page.py --dry-run
    python tools/deploy_influencer_gifting2_page.py --rollback

Prerequisites:
    .wat_secrets: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN, N8N_GIFTING2_WEBHOOK
"""

import os
import sys
import json
import urllib.request
import urllib.error
from env_loader import load_env

load_env()

SHOP = "mytoddie.myshopify.com"  # onzenna.com = mytoddie (NOT toddie-4080)
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"
N8N_WEBHOOK_URL = os.getenv("N8N_GIFTING2_WEBHOOK", "https://n8n.orbiters.co.kr/webhook/onzenna-gifting2-submit")

SECTION_KEY = "sections/influencer-gifting2.liquid"
TEMPLATE_KEY = "templates/page.influencer-gifting2.json"
PAGE_HANDLE = "influencer-gifting2"
PAGE_TITLE = "Creator Sample Request"

# ── Product Data ─────────────────────────────────────────────────
# bonus_age_min/max: age range where this product appears as optional "Bonus Pick"
PRODUCTS = {
    "ppsu_bottle": {
        "title": "Grosmimi PPSU Baby Bottle 10oz",
        "shopify_product_id": 8288604815682,
        "price": "$19.60",
        "product_url": "/products/ppsu-baby-bottle-10oz-300ml",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-5231923.png?v=1765928785",
        "colors": [
            "Creamy Blue", "Rose Coral", "Olive White", "Bear Pure Gold",
            "Bear White", "Cherry Pure Gold", "Cherry Rose Gold",
            "Cherry Peach", "Bear Butter", "Olive Pistachio",
        ],
        "variant_map": {
            "Creamy Blue": 51854035059058, "Rose Coral": 51854035091826,
            "Olive White": 45019086586178, "Bear Pure Gold": 45019086618946,
            "Bear White": 45019086651714, "Cherry Pure Gold": 45019086684482,
            "Cherry Rose Gold": 45019086717250,
            "Cherry Peach": 61621722349938, "Bear Butter": 61621722382706,
            "Olive Pistachio": 61621722415474,
        },
        "image_map": {
            "Creamy Blue": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-5231923.png?v=1765928785",
            "Rose Coral": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-4508449.png?v=1765928785",
            "Cherry Peach": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-7825518.png?v=1773004689",
            "Bear Butter": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-1000369.png?v=1773004689",
            "Olive Pistachio": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-1787705.png?v=1773004689",
        },
        "age_min": 0, "age_max": 6,
    },
    "ppsu_straw": {
        "title": "Grosmimi PPSU Straw Cup 10oz",
        "shopify_product_id": 8288579256642,
        "price": "$24.90",
        "product_url": "/products/ppsu-straw-cup-10oz-300ml",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-6846270.jpg?v=1769647041",
        "colors": [
            "Peach", "Skyblue", "White", "Aquagreen",
            "Pink", "Beige", "Charcoal", "Butter",
        ],
        "variant_map": {
            "Peach": 45373972545858, "Skyblue": 45018985595202,
            "White": 45018985431362, "Aquagreen": 45018985529666,
            "Pink": 45018985562434, "Beige": 45018985464130,
            "Charcoal": 45018985496898, "Butter": 45373972513090,
        },
        "image_map": {
            "Peach": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-6846270.jpg?v=1769647041",
            "Skyblue": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-5894511.jpg?v=1769647041",
            "White": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-5455905.jpg?v=1769647041",
            "Aquagreen": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-7099813.jpg?v=1769647041",
            "Pink": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-6870757.jpg?v=1769647041",
            "Beige": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-8885168.jpg?v=1769647041",
            "Charcoal": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-6527979.jpg?v=1769647041",
            "Butter": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-stage-2-straw-replacement-kit-bundle-1988015.jpg?v=1769647041",
        },
        "age_min": 6, "age_max": 18,
        "bonus_age_min": 0, "bonus_age_max": 6,
    },
    "ss_straw": {
        "title": "Grosmimi Stainless Steel Straw Cup 10oz",
        "shopify_product_id": 8864426557762,
        "price": "$46.80",
        "product_url": "/products/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-300ml",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-2204065.webp?v=1770248040",
        "colors": [
            "Flower Coral", "Air Balloon Blue", "Cherry Peach",
            "Olive Pistachio", "Bear Butter",
        ],
        "variant_map": {
            "Flower Coral": 51660007342450, "Air Balloon Blue": 51660005867890,
            "Cherry Peach": 47142838042946, "Olive Pistachio": 47142887981378,
            "Bear Butter": 47142838010178,
        },
        "image_map": {
            "Flower Coral": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-2204065.webp?v=1770248040",
            "Air Balloon Blue": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-8173628.webp?v=1766435768",
            "Cherry Peach": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-9797780.webp?v=1770248040",
            "Olive Pistachio": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-8797130.webp?v=1766435769",
            "Bear Butter": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-12-months-6976331.webp?v=1766435769",
        },
        "age_min": 6, "age_max": 18,
        "bonus_age_min": 0, "bonus_age_max": 6,
    },
    "ss_tumbler": {
        "title": "Grosmimi Stainless Steel Tumbler 10oz",
        "shopify_product_id": 14761459941746,
        "price": "$49.80",
        "product_url": "/products/grosmimi-stainless-steel-tumbler-10oz-300ml",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-tumbler-10oz-300ml-2105333.png?v=1765928662",
        "colors": ["Cherry Peach", "Bear Butter", "Olive Pistachio"],
        "variant_map": {
            "Cherry Peach": 52505654854002, "Bear Butter": 52505654886770,
            "Olive Pistachio": 52505654919538,
        },
        "image_map": {
            "Cherry Peach": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-tumbler-10oz-300ml-2105333.png?v=1765928662",
            "Bear Butter": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-tumbler-10oz-300ml-4079603.png?v=1766377611",
            "Olive Pistachio": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-tumbler-10oz-300ml-8675516.png?v=1766377611",
        },
        "age_min": 18, "age_max": 36,
        "bonus_age_min": 6, "bonus_age_max": 18,
    },
    "chamom_duo": {
        "title": "CHA&MOM Essential Duo Bundle",
        "subtitle": "Lotion + Body Wash",
        "shopify_product_id": 14643954647410,
        "price": "$46.92",
        "product_url": "/products/cha-mom-wash-lotion-bundle",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/chamom-essential-duo-bundle-2229420.jpg",
        "colors": [],
        "variant_map": {"Default": 51692427510130},
        "image_map": {},
        "age_min": 0, "age_max": 48, "optional": True,
    },
}

COLLAB_TERMS = (
    '<ul class="igf-terms-list">'
    "<li>Total video length: 30 seconds</li>"
    "<li>Uploaded content must include voiceover + subtitles</li>"
    "<li>Must use royalty-free music</li>"
    "<li>Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG &amp; TikTok)</li>"
    "<li>Must include: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna</li>"
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


# ── Liquid Section Template Builder ─────────────────────────────
def build_products_js():
    js_products = {}
    for key, p in PRODUCTS.items():
        js_products[key] = {
            "title": p["title"],
            "price": p["price"],
            "productId": p["shopify_product_id"],
            "productUrl": p.get("product_url", ""),
            "image": p["image_url"],
            "colors": p["colors"],
            "variantMap": p["variant_map"],
            "imageMap": p.get("image_map", {}),
            "ageMin": p["age_min"],
            "ageMax": p["age_max"],
            "optional": p.get("optional", False),
            "subtitle": p.get("subtitle", ""),
            "bonusAgeMin": p.get("bonus_age_min"),
            "bonusAgeMax": p.get("bonus_age_max"),
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

    return f'''<!-- Influencer Gifting 2 Form — Conversational UI (Claude-inspired) -->
<!-- Generated by tools/deploy_influencer_gifting2_page.py -->

{{% comment %}}
  Customer pre-fill: passes logged-in customer data to JavaScript
{{% endcomment %}}
{{% if customer %}}
<script id="igf-customer-data" type="application/json">
{{"name": {{{{ customer.name | json }}}}, "email": {{{{ customer.email | json }}}}, "phone": {{{{ customer.phone | json }}}}, "id": {{{{ customer.id }}}}}}
</script>
{{% endif %}}

<!-- Uses Fustat font from parent Onzenna theme -->

<style>
  /* ── Base — Claude Desktop aesthetic ─────────────────── */
  :root {{
    --igf-accent: #D97757;
    --igf-accent-hover: #C16842;
    --igf-accent-soft: #FFF0E9;
    --igf-bg: #F5EEE6;
    --igf-warm: #EDE7DD;
    --igf-card: #FFFFFF;
    --igf-text: #3D3929;
    --igf-text-muted: #9A917F;
    --igf-border: #E3DDD1;
    --igf-error: #D93025;
    --igf-radius: 20px;
    --igf-shadow: 0 2px 16px rgba(45,43,40,0.05);
  }}
  .igf-wrap {{
    min-height: 80vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 32px 16px 80px;
    background: var(--igf-bg);
    font-family: var(--font-body-family, Fustat), sans-serif;
    letter-spacing: 0.01em;
    color: var(--igf-text);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }}
  .igf-wrap * {{ box-sizing: border-box; }}

  /* ── Progress ──────────────────────────────────────── */
  .igf-progress-bar {{
    position: fixed;
    top: 0;
    left: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--igf-accent), #E8A88D);
    transition: width 0.6s cubic-bezier(.16,1,.3,1);
    z-index: 9999;
  }}

  /* ── Card Container ────────────────────────────────── */
  .igf-card {{
    width: 100%;
    max-width: 540px;
    background: var(--igf-card);
    border-radius: var(--igf-radius);
    box-shadow: var(--igf-shadow);
    padding: 48px 40px 40px;
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(227,221,209,0.6);
  }}
  @media (max-width: 560px) {{
    .igf-card {{ padding: 36px 24px 28px; border-radius: 16px; }}
  }}

  /* ── Slides ────────────────────────────────────────── */
  .igf-slide {{
    display: none;
    animation: igf-fadeIn 0.5s cubic-bezier(.16,1,.3,1);
  }}
  .igf-slide.active {{ display: block; }}
  @keyframes igf-fadeIn {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  /* ── Typing reveal for questions ────────────────────── */
  .igf-slide.active .igf-question {{
    animation: igf-typeReveal 0.6s cubic-bezier(.16,1,.3,1) forwards;
  }}
  .igf-slide.active .igf-input,
  .igf-slide.active .igf-social-group,
  .igf-slide.active .igf-phone-row,
  .igf-slide.active .igf-toggle {{
    animation: igf-fadeIn 0.5s cubic-bezier(.16,1,.3,1) 0.15s both;
  }}
  .igf-slide.active .igf-actions {{
    animation: igf-fadeIn 0.4s cubic-bezier(.16,1,.3,1) 0.25s both;
  }}
  @keyframes igf-typeReveal {{
    from {{ opacity: 0; transform: translateY(8px); filter: blur(2px); }}
    to {{ opacity: 1; transform: translateY(0); filter: blur(0); }}
  }}

  /* ── Step Counter ──────────────────────────────────── */
  .igf-step-counter {{
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--igf-text-muted);
    margin-bottom: 12px;
  }}

  /* ── Question Title ────────────────────────────────── */
  .igf-question {{
    font-family: var(--font-heading-family, Fustat), sans-serif;
    font-size: 1.4rem;
    font-weight: 600;
    line-height: 1.4;
    letter-spacing: 0.02em;
    color: var(--igf-text);
    margin-bottom: 28px;
  }}
  @media (min-width: 520px) {{
    .igf-question {{ font-size: 1.55rem; }}
  }}

  /* ── Input Fields ──────────────────────────────────── */
  .igf-input {{
    width: 100%;
    padding: 14px 0;
    border: none;
    border-bottom: 1.5px solid var(--igf-border);
    font-size: 1.05rem;
    font-family: inherit;
    background: transparent;
    color: var(--igf-text);
    transition: border-color 0.3s cubic-bezier(.16,1,.3,1);
    outline: none;
  }}
  .igf-input:focus {{
    border-bottom-color: var(--igf-accent);
  }}
  .igf-input::placeholder {{
    color: #C5BFB6;
  }}
  .igf-input.invalid {{
    border-bottom-color: var(--igf-error);
  }}
  select.igf-input {{
    cursor: pointer;
    -webkit-appearance: none;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L6 6L11 1' stroke='%238B8680' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 4px center;
    padding-right: 24px;
  }}
  .igf-input-hint {{
    font-size: 0.82rem;
    color: var(--igf-text-muted);
    margin-top: 8px;
  }}
  .igf-error-msg {{
    color: var(--igf-error);
    font-size: 0.8rem;
    margin-top: 6px;
    display: none;
  }}

  /* ── Social Media Row ───────────────────────────────── */
  .igf-social-group {{
    margin-bottom: 20px;
  }}
  .igf-social-label {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--igf-text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .igf-social-label svg {{
    width: 16px;
    height: 16px;
    opacity: 0.6;
  }}

  /* ── Phone Prefix ──────────────────────────────────── */
  .igf-phone-row {{
    display: flex;
    align-items: flex-end;
    gap: 12px;
  }}
  .igf-phone-prefix {{
    padding: 14px 0;
    border-bottom: 2px solid var(--igf-border);
    font-size: 1.1rem;
    color: var(--igf-text-muted);
    white-space: nowrap;
  }}
  .igf-phone-row .igf-input {{ flex: 1; }}

  /* ── Buttons ───────────────────────────────────────── */
  .igf-actions {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 36px;
  }}
  .igf-btn {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 26px;
    border-radius: 50px;
    font-size: 0.92rem;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    border: none;
    transition: all 0.2s ease;
  }}
  .igf-btn-next {{
    background: var(--igf-accent);
    color: #fff;
    flex-shrink: 0;
  }}
  .igf-btn-next:hover {{ background: var(--igf-accent-hover); transform: translateY(-1px); }}
  .igf-btn-next:disabled {{ background: #C5BFB6; cursor: not-allowed; transform: none; }}
  .igf-btn-next svg {{ width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; }}
  .igf-btn-back {{
    background: none;
    color: var(--igf-text-muted);
    padding: 12px 14px;
    font-weight: 500;
  }}
  .igf-btn-back:hover {{ color: var(--igf-text); }}
  .igf-btn-skip {{
    background: none;
    color: var(--igf-text-muted);
    padding: 12px 14px;
    font-weight: 500;
    font-size: 0.85rem;
    margin-left: auto;
  }}
  .igf-btn-skip:hover {{ color: var(--igf-text); }}
  .igf-enter-hint {{
    font-size: 0.72rem;
    color: #C5BFB6;
    margin-left: auto;
  }}
  .igf-enter-hint kbd {{
    display: inline-block;
    padding: 2px 6px;
    background: var(--igf-warm);
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.68rem;
    margin-right: 4px;
  }}

  /* ── Toggle / Checkbox ─────────────────────────────── */
  .igf-toggle {{
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 14px 16px;
    background: var(--igf-warm);
    border-radius: 12px;
    margin-top: 18px;
    font-weight: 500;
    font-size: 0.92rem;
    transition: background 0.2s;
  }}
  .igf-toggle:hover {{ background: #EAE3D8; }}
  .igf-toggle input[type="checkbox"] {{
    width: 20px;
    height: 20px;
    accent-color: var(--igf-accent);
    cursor: pointer;
  }}

  /* ── Age Badge ─────────────────────────────────────── */
  .igf-age-badge {{
    display: inline-block;
    padding: 5px 14px;
    background: var(--igf-accent-soft);
    color: var(--igf-accent);
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 10px;
  }}
  .igf-age-badge.expecting {{
    background: #FEF3E2;
    color: #D4760A;
  }}

  /* ── Product Grid ──────────────────────────────────── */
  .igf-products-wrap {{
    max-width: 740px;
    width: 100%;
  }}
  .igf-product-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }}
  @media (min-width: 480px) {{
    .igf-product-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (min-width: 720px) {{
    .igf-product-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}

  /* ── Product Card ──────────────────────────────────── */
  .igf-pcard {{
    background: var(--igf-card);
    border: 2px solid var(--igf-border);
    border-radius: 14px;
    padding: 16px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .igf-pcard:hover {{ border-color: #C5BFB6; transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
  .igf-pcard.selected {{
    border-color: var(--igf-accent);
    box-shadow: 0 0 0 3px var(--igf-accent-soft);
  }}
  .igf-pcard-img {{
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
    border-radius: 10px;
    background: #F8F6F2;
    margin-bottom: 12px;
  }}
  .igf-pcard-title {{
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--igf-text);
    margin-bottom: 2px;
    line-height: 1.3;
  }}
  .igf-pcard-subtitle {{
    font-size: 0.75rem;
    color: var(--igf-text-muted);
    margin-bottom: 4px;
  }}
  .igf-pcard-price {{
    font-weight: 700;
    font-size: 0.95rem;
    color: var(--igf-accent);
    margin-bottom: 6px;
  }}

  /* ── Product Detail Link ────────────────────────────── */
  .igf-pcard-link {{
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--igf-text-muted);
    text-decoration: none;
    margin-bottom: 10px;
    transition: color 0.2s;
  }}
  .igf-pcard-link:hover {{ color: var(--igf-accent); text-decoration: underline; }}

  /* ── Swatches ──────────────────────────────────────── */
  .igf-swatches {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    justify-content: center;
    margin-bottom: 8px;
  }}
  .igf-sw {{
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid #E8E4DE;
    cursor: pointer;
    transition: all 0.15s;
    position: relative;
  }}
  .igf-sw:hover {{ border-color: #aaa; transform: scale(1.15); }}
  .igf-sw.active {{
    border-color: var(--igf-accent);
    box-shadow: 0 0 0 2px var(--igf-accent-soft);
    transform: scale(1.15);
  }}
  .igf-sw.active::after {{
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 8px;
    height: 8px;
    background: var(--igf-accent);
    border-radius: 50%;
    transform: translate(-50%, -50%);
  }}
  .igf-sw-tooltip {{
    display: none;
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--igf-text);
    color: #fff;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.68rem;
    white-space: nowrap;
    z-index: 10;
    pointer-events: none;
  }}
  .igf-sw:hover .igf-sw-tooltip {{ display: block; }}
  .igf-sw-count {{
    text-align: center;
    font-size: 0.72rem;
    color: var(--igf-text-muted);
    margin-bottom: 6px;
  }}
  .igf-sw-count strong {{ color: var(--igf-accent); }}

  /* ── Out-of-Stock Swatch ────────────────────────────── */
  .igf-sw.oos {{
    opacity: 0.45;
    cursor: not-allowed;
    pointer-events: none;
  }}
  .igf-sw.oos::before {{
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 120%;
    height: 1.5px;
    background: rgba(255,255,255,0.9);
    box-shadow: 0 0 2px rgba(0,0,0,0.2);
    transform: translate(-50%, -50%) rotate(-45deg);
    border-radius: 2px;
    z-index: 2;
  }}
  .igf-sw.oos::after {{
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 120%;
    height: 1.5px;
    background: rgba(255,255,255,0.9);
    box-shadow: 0 0 2px rgba(0,0,0,0.2);
    transform: translate(-50%, -50%) rotate(45deg);
    border-radius: 2px;
    z-index: 2;
  }}
  .igf-sw.oos .igf-sw-tooltip::after {{ content: " (sold out)"; }}

  /* ── Card Pill Button ──────────────────────────────── */
  .igf-pcard-btn {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 7px 16px;
    border-radius: 50px;
    border: 1.5px solid var(--igf-border);
    background: var(--igf-card);
    color: var(--igf-text-muted);
    font-size: 0.76rem;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.2s;
    margin-top: auto;
  }}
  .igf-pcard-btn:hover {{ border-color: var(--igf-accent); color: var(--igf-accent); }}
  .igf-pcard.selected .igf-pcard-btn {{
    background: var(--igf-accent);
    border-color: var(--igf-accent);
    color: #fff;
  }}

  /* ── Badges ────────────────────────────────────────── */
  .igf-badge {{
    position: absolute;
    top: 8px;
    right: 8px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }}
  .igf-badge-bonus {{
    background: var(--igf-accent-soft);
    color: var(--igf-accent);
  }}
  .igf-badge-optional {{
    background: var(--igf-warm);
    color: #9A8E7E;
  }}

  /* ── Section Labels ────────────────────────────────── */
  .igf-section-title {{
    font-family: var(--font-heading-family, Fustat), sans-serif;
    font-size: 0.88rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--igf-accent);
    margin: 28px 0 6px;
    padding-bottom: 6px;
  }}
  .igf-section-desc {{
    color: var(--igf-text-muted);
    font-size: 0.82rem;
    margin-bottom: 14px;
  }}

  /* ── Address Grid ──────────────────────────────────── */
  .igf-addr-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
  }}
  @media (min-width: 480px) {{
    .igf-addr-grid.cols-3 {{ grid-template-columns: 2fr 1fr 1fr; }}
    .igf-addr-grid.cols-2 {{ grid-template-columns: 1fr 1fr; }}
  }}
  .igf-addr-field {{ margin-bottom: 4px; }}
  .igf-addr-field label {{
    display: block;
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--igf-text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  /* ── Success ───────────────────────────────────────── */
  .igf-success-wrap {{
    text-align: center;
    padding: 48px 24px;
  }}
  .igf-success-icon {{
    width: 68px;
    height: 68px;
    border-radius: 50%;
    background: var(--igf-accent-soft);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 24px;
  }}
  .igf-success-icon svg {{ width: 28px; height: 28px; color: var(--igf-accent); }}
  .igf-success-wrap h2 {{
    font-family: var(--font-heading-family, Fustat), sans-serif;
    color: var(--igf-accent);
    font-size: 1.5rem;
    margin-bottom: 12px;
    font-weight: 700;
  }}
  .igf-success-wrap p {{
    color: var(--igf-text-muted);
    font-size: 1rem;
    line-height: 1.6;
  }}

  /* ── Spinner ───────────────────────────────────────── */
  .igf-spinner {{
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid #fff;
    border-top-color: transparent;
    border-radius: 50%;
    animation: igf-spin 0.6s linear infinite;
    margin-right: 6px;
    vertical-align: middle;
  }}
  @keyframes igf-spin {{ to {{ transform: rotate(360deg); }} }}

  .igf-no-products {{
    text-align: center;
    padding: 32px;
    color: var(--igf-text-muted);
    background: var(--igf-warm);
    border-radius: 12px;
    font-size: 0.9rem;
  }}

  /* ── Date Dropdown Row ────────────────────────────── */
  .igf-date-row {{
    display: grid;
    grid-template-columns: 2fr 1fr 1.2fr;
    gap: 10px;
  }}
  @media (max-width: 400px) {{
    .igf-date-row {{ grid-template-columns: 1fr; }}
  }}
</style>

<form id="igf-form" autocomplete="on" onsubmit="return false;">
<div class="igf-wrap" id="igf-app">
  <!-- Thin progress bar at top of viewport -->
  <div class="igf-progress-bar" id="igf-progress" style="width:0%"></div>

  <!-- ── Slides 1-5: Personal + Baby (card layout) ── -->
  <div class="igf-card" id="igf-card-main">

    <!-- Slide 1: Name -->
    <div class="igf-slide active" data-slide="1">
      <div class="igf-step-counter">Step 1 of 7</div>
      <div class="igf-question">What&rsquo;s your name?</div>
      <input class="igf-input" type="text" id="igf-name" placeholder="Jane Smith" autocomplete="name">
      <div class="igf-error-msg" id="igf-err-name">Please enter your full name</div>
      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-next" data-next="2">Continue <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
        <span class="igf-enter-hint"><kbd>Enter</kbd></span>
      </div>
    </div>

    <!-- Slide 2: Email -->
    <div class="igf-slide" data-slide="2">
      <div class="igf-step-counter">Step 2 of 7</div>
      <div class="igf-question">What&rsquo;s your email?</div>
      <input class="igf-input" type="email" id="igf-email" placeholder="jane@example.com" autocomplete="email">
      <div class="igf-error-msg" id="igf-err-email">Please enter a valid email</div>
      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-back" data-prev="1">&larr; Back</button>
        <button type="button" class="igf-btn igf-btn-next" data-next="3">Continue <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
        <span class="igf-enter-hint"><kbd>Enter</kbd></span>
      </div>
    </div>

    <!-- Slide 3: Phone -->
    <div class="igf-slide" data-slide="3">
      <div class="igf-step-counter">Step 3 of 7</div>
      <div class="igf-question">What&rsquo;s your phone number?</div>
      <div class="igf-phone-row">
        <span class="igf-phone-prefix">+1</span>
        <input class="igf-input" type="tel" id="igf-phone" placeholder="(555) 123-4567" autocomplete="tel-national">
      </div>
      <div class="igf-error-msg" id="igf-err-phone">US phone number only (10 digits)</div>
      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-back" data-prev="2">&larr; Back</button>
        <button type="button" class="igf-btn igf-btn-next" data-next="4">Continue <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
        <span class="igf-enter-hint"><kbd>Enter</kbd></span>
      </div>
    </div>

    <!-- Slide 4: Social Media (Instagram + TikTok combined) -->
    <div class="igf-slide" data-slide="4">
      <div class="igf-step-counter">Step 4 of 7</div>
      <div class="igf-question">Share your social media</div>
      <div class="igf-input-hint" style="margin-bottom:20px;margin-top:-16px">At least one is recommended</div>
      <div class="igf-social-group">
        <div class="igf-social-label">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
          Instagram
        </div>
        <input class="igf-input" type="text" id="igf-instagram" placeholder="@yourusername" autocomplete="off">
      </div>
      <div class="igf-social-group">
        <div class="igf-social-label">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.51a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 0010.86 4.43 6.3 6.3 0 001.88-4.48V8.73a8.3 8.3 0 004.89 1.58V6.84a4.84 4.84 0 01-1.19-.15z"/></svg>
          TikTok
        </div>
        <input class="igf-input" type="text" id="igf-tiktok" placeholder="@yourusername" autocomplete="off">
      </div>
      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-back" data-prev="3">&larr; Back</button>
        <button type="button" class="igf-btn igf-btn-next" data-next="5">Continue <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
        <button type="button" class="igf-btn igf-btn-skip" data-next="5">Skip</button>
      </div>
    </div>

    <!-- Slide 5: Baby Birthday -->
    <div class="igf-slide" data-slide="5">
      <div class="igf-step-counter">Step 5 of 7</div>
      <div class="igf-question">When was your baby born?</div>
      <div class="igf-date-row">
        <div class="igf-addr-field">
          <label>Month</label>
          <select class="igf-input" id="igf-baby1-month">
            <option value="">Month</option>
            <option value="1">January</option><option value="2">February</option>
            <option value="3">March</option><option value="4">April</option>
            <option value="5">May</option><option value="6">June</option>
            <option value="7">July</option><option value="8">August</option>
            <option value="9">September</option><option value="10">October</option>
            <option value="11">November</option><option value="12">December</option>
          </select>
        </div>
        <div class="igf-addr-field">
          <label>Day</label>
          <select class="igf-input" id="igf-baby1-day"><option value="">Day</option></select>
        </div>
        <div class="igf-addr-field">
          <label>Year</label>
          <select class="igf-input" id="igf-baby1-year"><option value="">Year</option></select>
        </div>
      </div>
      <input type="hidden" id="igf-baby1-bday">
      <div id="igf-baby1-age"></div>
      <div class="igf-error-msg" id="igf-err-baby">Please select month, day, and year</div>

      <label class="igf-toggle">
        <input type="checkbox" id="igf-has-baby2">
        <span>I have another child</span>
      </label>

      <div id="igf-baby2-section" style="display:none;margin-top:16px">
        <div class="igf-question" style="font-size:1.1rem;margin-bottom:14px">Second child&rsquo;s birthday?</div>
        <div class="igf-date-row">
          <div class="igf-addr-field">
            <label>Month</label>
            <select class="igf-input" id="igf-baby2-month">
              <option value="">Month</option>
              <option value="1">January</option><option value="2">February</option>
              <option value="3">March</option><option value="4">April</option>
              <option value="5">May</option><option value="6">June</option>
              <option value="7">July</option><option value="8">August</option>
              <option value="9">September</option><option value="10">October</option>
              <option value="11">November</option><option value="12">December</option>
            </select>
          </div>
          <div class="igf-addr-field">
            <label>Day</label>
            <select class="igf-input" id="igf-baby2-day"><option value="">Day</option></select>
          </div>
          <div class="igf-addr-field">
            <label>Year</label>
            <select class="igf-input" id="igf-baby2-year"><option value="">Year</option></select>
          </div>
        </div>
        <input type="hidden" id="igf-baby2-bday">
        <div id="igf-baby2-age"></div>
      </div>

      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-back" data-prev="4">&larr; Back</button>
        <button type="button" class="igf-btn igf-btn-next" data-next="6">Continue <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
      </div>
    </div>
  </div><!-- /igf-card-main -->

  <!-- ── Slide 6: Products (wider layout) ── -->
  <div class="igf-slide igf-products-wrap" data-slide="6" style="display:none">
    <div class="igf-step-counter" style="text-align:center;margin-bottom:6px">Step 6 of 7</div>
    <div class="igf-question" style="text-align:center;margin-bottom:4px">Pick your products</div>
    <p class="igf-section-desc" style="text-align:center;margin-bottom:24px">Tap a color to select your product</p>

    <div id="igf-core-section"></div>
    <div class="igf-product-grid" id="igf-products-core"></div>

    <div id="igf-optional-section" style="display:none">
      <div class="igf-section-title">Optional Add-on</div>
      <p class="igf-section-desc">Available for all ages</p>
    </div>
    <div class="igf-product-grid" id="igf-products-optional"></div>

    <div class="igf-actions" style="justify-content:center;margin-top:32px">
      <button type="button" class="igf-btn igf-btn-back" data-prev="5">&larr; Back</button>
      <button type="button" class="igf-btn igf-btn-next" data-next="7">Continue to shipping <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
    </div>
  </div>

  <!-- ── Slide 7: Shipping Address (card layout) ── -->
  <div class="igf-card" id="igf-card-address" style="display:none">
    <div class="igf-slide active" data-slide="7">
      <div class="igf-step-counter">Step 7 of 7</div>
      <div class="igf-question">Where should we send your samples?</div>

      <div class="igf-addr-field">
        <label for="igf-street">Street Address *</label>
        <input class="igf-input" type="text" id="igf-street" placeholder="123 Main St" autocomplete="address-line1">
        <div class="igf-error-msg" id="igf-err-street">Please enter your address</div>
      </div>
      <div class="igf-addr-field">
        <label for="igf-apt">Apt / Suite / Unit</label>
        <input class="igf-input" type="text" id="igf-apt" placeholder="Apt 4B" autocomplete="address-line2">
      </div>
      <div class="igf-addr-grid cols-3" style="margin-top:8px">
        <div class="igf-addr-field">
          <label for="igf-city">City *</label>
          <input class="igf-input" type="text" id="igf-city" placeholder="New York" autocomplete="address-level2">
          <div class="igf-error-msg" id="igf-err-city">Required</div>
        </div>
        <div class="igf-addr-field">
          <label for="igf-state">State *</label>
          <select class="igf-input" id="igf-state" autocomplete="address-level1">
            {state_options}
          </select>
          <div class="igf-error-msg" id="igf-err-state">Required</div>
        </div>
        <div class="igf-addr-field">
          <label for="igf-zip">ZIP *</label>
          <input class="igf-input" type="text" id="igf-zip" placeholder="10001" maxlength="10" autocomplete="postal-code">
          <div class="igf-error-msg" id="igf-err-zip">Required</div>
        </div>
      </div>
      <div class="igf-addr-field" style="margin-top:8px">
        <label for="igf-country">Country *</label>
        <select class="igf-input" id="igf-country" autocomplete="country">
          <option value="US" selected>United States</option>
          <option value="CA">Canada</option>
        </select>
      </div>

      <div class="igf-actions">
        <button type="button" class="igf-btn igf-btn-back" data-prev="6">&larr; Back</button>
        <button type="button" class="igf-btn igf-btn-next" id="igf-submit-btn">Submit Application <svg viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></button>
      </div>
    </div>
  </div>

  <!-- ── Success ── -->
  <div class="igf-card" id="igf-card-success" style="display:none">
    <div class="igf-success-wrap">
      <div class="igf-success-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg></div>
      <h2>Thank you!</h2>
      <p>We&rsquo;ll review your application and get back to you soon.<br>Keep an eye on your email!</p>
    </div>
  </div>
</div>
</form>

<script>
(function() {{
  "use strict";

  var WEBHOOK_URL = "{webhook_url}";
  var PRODUCTS = {products_js};
  var TOTAL_SLIDES = 7;
  var currentSlide = 1;
  var selectedProducts = {{}};
  var lastTappedColor = {{}};
  var MAX_COLORS = 1;

  // ── Containers ────────────────────────────────────────
  var cardMain = document.getElementById("igf-card-main");
  var cardAddr = document.getElementById("igf-card-address");
  var cardSuccess = document.getElementById("igf-card-success");
  var prodWrap = document.querySelector('.igf-products-wrap[data-slide="6"]');
  var progressBar = document.getElementById("igf-progress");

  // ── Age helpers ───────────────────────────────────────
  function calcAgeMonths(dateStr) {{
    if (!dateStr) return null;
    var bd = new Date(dateStr);
    var now = new Date();
    if (bd > now) return -1;
    return (now.getFullYear() - bd.getFullYear()) * 12 + (now.getMonth() - bd.getMonth());
  }}

  function ageLabel(months) {{
    if (months === null) return "";
    if (months < 0) return '<span class="igf-age-badge expecting">Expecting</span>';
    if (months < 12) return '<span class="igf-age-badge">' + months + ' months old</span>';
    var y = Math.floor(months / 12);
    var m = months % 12;
    var txt = y + (y === 1 ? " year" : " years") + (m > 0 ? " " + m + " mo" : "");
    return '<span class="igf-age-badge">' + txt + '</span>';
  }}

  function updateAgeDisplay() {{
    syncDateDropdown("igf-baby1");
    syncDateDropdown("igf-baby2");
    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-baby2-bday").value;
    document.getElementById("igf-baby1-age").innerHTML = ageLabel(calcAgeMonths(bd1));
    document.getElementById("igf-baby2-age").innerHTML = ageLabel(calcAgeMonths(bd2));
  }}

  // ── Date Dropdown Helpers ───────────────────────────────
  function initDateDropdowns(prefix) {{
    var daySel = document.getElementById(prefix + "-day");
    var yearSel = document.getElementById(prefix + "-year");
    // Populate days 1-31
    for (var d = 1; d <= 31; d++) {{
      var opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      daySel.appendChild(opt);
    }}
    // Populate years (current year down to 6 years ago + expecting)
    var currentYear = new Date().getFullYear();
    for (var y = currentYear; y >= currentYear - 6; y--) {{
      var opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      yearSel.appendChild(opt);
    }}
    // Attach change listeners
    [prefix + "-month", prefix + "-day", prefix + "-year"].forEach(function(id) {{
      document.getElementById(id).addEventListener("change", updateAgeDisplay);
    }});
  }}

  function syncDateDropdown(prefix) {{
    var m = document.getElementById(prefix + "-month").value;
    var d = document.getElementById(prefix + "-day").value;
    var y = document.getElementById(prefix + "-year").value;
    var hidden = document.getElementById(prefix + "-bday");
    if (m && d && y) {{
      hidden.value = y + "-" + (m.length === 1 ? "0" + m : m) + "-" + (d.length === 1 ? "0" + d : d);
    }} else {{
      hidden.value = "";
    }}
  }}

  initDateDropdowns("igf-baby1");
  initDateDropdowns("igf-baby2");

  // ── Product Visibility ────────────────────────────────
  function getVisibleProducts() {{
    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;
    var ages = [calcAgeMonths(bd1)];
    if (bd2) ages.push(calcAgeMonths(bd2));

    var result = {{ core: {{}}, optional: {{}} }};
    for (var key in PRODUCTS) {{
      if (!PRODUCTS.hasOwnProperty(key)) continue;
      var p = PRODUCTS[key];
      if (p.optional) {{ result.optional[key] = p; continue; }}
      for (var i = 0; i < ages.length; i++) {{
        var eff = (ages[i] === null || ages[i] < 0) ? 0 : ages[i];
        if (eff >= p.ageMin && eff < p.ageMax) {{ result.core[key] = p; break; }}
      }}
    }}
    return result;
  }}

  // ── Color Hex Map ─────────────────────────────────────
  var COLOR_HEX = {{
    "Creamy Blue":"#A4C8E1","Rose Coral":"#E88D8D","Olive White":"#C5C99A",
    "Bear Pure Gold":"#D4A76A","Bear White":"#F5F0E8","Cherry Pure Gold":"#D4A76A",
    "Cherry Rose Gold":"#E8B4B4","Peach":"#FFB899","Skyblue":"#87CEEB",
    "White":"#F0F0F0","Aquagreen":"#7BC8A4","Pink":"#FFB6C1","Beige":"#D4C5A9",
    "Charcoal":"#4A4A4A","Butter":"#F5E6B8","Flower Coral":"#FF8B7D",
    "Air Balloon Blue":"#7EB5D6","Cherry Peach":"#FFB4A2","Olive Pistachio":"#A8BF8A",
    "Bear Butter":"#F5E6B8"
  }};

  // ── Inventory / Out-of-Stock ────────────────────────────
  var inventoryData = {{}};  // variantId -> boolean (true=available)
  var inventoryLoaded = false;

  function fetchInventory() {{
    if (inventoryLoaded) return Promise.resolve();
    var handles = [];
    for (var key in PRODUCTS) {{
      if (!PRODUCTS.hasOwnProperty(key)) continue;
      var p = PRODUCTS[key];
      if (p.productUrl) {{
        var h = p.productUrl.replace(/^\\/products\\//, "");
        handles.push({{ key: key, handle: h }});
      }}
    }}
    console.log("[IGF] Fetching inventory for", handles.length, "products");
    var promises = handles.map(function(item) {{
      return fetch("/products/" + item.handle + ".js")
        .then(function(r) {{
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        }})
        .then(function(data) {{
          if (data && data.variants) {{
            var availCount = 0;
            data.variants.forEach(function(v) {{
              inventoryData[v.id] = v.available;
              if (v.available) availCount++;
            }});
            console.log("[IGF] " + item.handle + ": " + availCount + "/" + data.variants.length + " available");
          }}
        }})
        .catch(function(err) {{
          console.warn("[IGF] Inventory fetch failed for " + item.handle, err);
        }});
    }});
    return Promise.all(promises).then(function() {{
      inventoryLoaded = true;
      console.log("[IGF] Inventory loaded:", Object.keys(inventoryData).length, "variants tracked");
    }});
  }}

  function isColorAvailable(key, color) {{
    var p = PRODUCTS[key];
    if (!p.variantMap || !p.variantMap[color]) return true;
    var vid = p.variantMap[color];
    if (inventoryData[vid] === undefined) return true; // unknown = assume available
    return inventoryData[vid];
  }}

  // ── Build Card ────────────────────────────────────────
  function buildCard(key, p, badgeType) {{
    var card = document.createElement("div");
    var sel = selectedProducts[key];
    var selCount = sel ? sel.selections.length : 0;
    card.className = "igf-pcard" + (selCount > 0 ? " selected" : "");
    card.dataset.key = key;

    var badge = "";
    if (badgeType === "optional") badge = '<div class="igf-badge igf-badge-optional">Optional</div>';

    // Color swatches
    var colorHtml = "";
    if (p.colors && p.colors.length > 0) {{
      var selected = sel ? sel.selections.map(function(s){{ return s.color; }}) : [];
      var dots = p.colors.map(function(c) {{
        var hex = COLOR_HEX[c] || "#ccc";
        var act = selected.indexOf(c) >= 0 ? " active" : "";
        var oosClass = !isColorAvailable(key, c) ? " oos" : "";
        return '<span class="igf-sw' + act + oosClass + '" style="background:' + hex + '" data-key="' + key + '" data-color="' + c + '"><span class="igf-sw-tooltip">' + c + '</span></span>';
      }}).join("");
      colorHtml = '<div class="igf-swatches">' + dots + '</div>';
    }}

    var btnText = (p.colors && p.colors.length > 0)
      ? (selCount > 0 ? "&#10003; " + selCount + " selected" : "Tap colors")
      : (selCount > 0 ? "&#10003; Selected" : "Select");

    // Use imageMap for the most recently TAPPED color, else default image
    var imgSrc = p.image;
    if (lastTappedColor[key] && p.imageMap && p.imageMap[lastTappedColor[key]]) {{
      imgSrc = p.imageMap[lastTappedColor[key]];
    }} else if (sel && sel.selections.length > 0 && p.imageMap) {{
      // Fallback: show last selected color's image if no tap tracked yet
      var lastColor = sel.selections[sel.selections.length - 1].color;
      if (p.imageMap[lastColor]) imgSrc = p.imageMap[lastColor];
    }}

    // Product detail link
    var detailLink = "";
    if (p.productUrl) {{
      detailLink = '<a href="' + p.productUrl + '" target="_blank" class="igf-pcard-link" onclick="event.stopPropagation()">See details &rarr;</a>';
    }}

    card.innerHTML = badge
      + '<img class="igf-pcard-img" src="' + imgSrc + '" alt="' + p.title + '" loading="lazy">'
      + '<div class="igf-pcard-title">' + p.title + '</div>'
      + (p.subtitle ? '<div class="igf-pcard-subtitle">' + p.subtitle + '</div>' : '')
      + '<div class="igf-pcard-price">' + p.price + '</div>'
      + detailLink
      + colorHtml
      + '<button type="button" class="igf-pcard-btn" data-key="' + key + '">' + btnText + '</button>';
    return card;
  }}

  // ── Attach card events ────────────────────────────────
  function attachCardEvents(grid) {{
    grid.querySelectorAll(".igf-sw").forEach(function(sw) {{
      sw.addEventListener("click", function(e) {{
        e.stopPropagation();
        toggleColorSelection(this.dataset.key, this.dataset.color);
      }});
    }});
    grid.querySelectorAll(".igf-pcard-btn").forEach(function(btn) {{
      btn.addEventListener("click", function(e) {{
        e.stopPropagation();
        var k = this.dataset.key, p = PRODUCTS[k];
        if (!p.colors || p.colors.length === 0) toggleSimpleProduct(k);
        else if (selectedProducts[k]) {{ delete selectedProducts[k]; renderProducts(); }}
      }});
    }});
    grid.querySelectorAll(".igf-pcard").forEach(function(card) {{
      card.addEventListener("click", function(e) {{
        if (e.target.closest(".igf-sw") || e.target.tagName === "BUTTON" || e.target.tagName === "A") return;
        var k = this.dataset.key, p = PRODUCTS[k];
        if (!p.colors || p.colors.length === 0) toggleSimpleProduct(k);
      }});
    }});
  }}

  // ── Render Products ───────────────────────────────────
  function renderProducts() {{
    var visible = getVisibleProducts();
    var coreGrid = document.getElementById("igf-products-core");
    var optGrid = document.getElementById("igf-products-optional");
    var coreSection = document.getElementById("igf-core-section");
    var optSection = document.getElementById("igf-optional-section");

    coreGrid.innerHTML = "";
    optGrid.innerHTML = "";

    for (var k in selectedProducts) {{
      if (!visible.core[k] && !visible.optional[k]) delete selectedProducts[k];
    }}

    var hasCore = Object.keys(visible.core).length > 0;
    var hasOpt = Object.keys(visible.optional).length > 0;

    if (hasCore) {{
      coreSection.innerHTML = '<div class="igf-section-title">Recommended for Your Baby</div><p class="igf-section-desc">Pick 1 color per product</p>';
      for (var ck in visible.core) coreGrid.appendChild(buildCard(ck, visible.core[ck], "core"));
      attachCardEvents(coreGrid);
    }} else {{
      coreSection.innerHTML = '<div class="igf-no-products">No core products for this age range.</div>';
    }}

    optSection.style.display = hasOpt ? "block" : "none";
    if (hasOpt) {{
      for (var ok in visible.optional) optGrid.appendChild(buildCard(ok, visible.optional[ok], "optional"));
      attachCardEvents(optGrid);
    }}
  }}

  // ── Toggle Color Selection ────────────────────────────
  function toggleColorSelection(key, color) {{
    if (!isColorAvailable(key, color)) return; // OOS: can't select
    lastTappedColor[key] = color;
    var p = PRODUCTS[key];
    if (!selectedProducts[key]) {{
      selectedProducts[key] = {{
        productKey: key, productId: p.productId, title: p.title, price: p.price,
        selections: [{{ color: color, variantId: p.variantMap[color] || null }}]
      }};
    }} else {{
      var sels = selectedProducts[key].selections;
      var idx = -1;
      for (var i = 0; i < sels.length; i++) if (sels[i].color === color) {{ idx = i; break; }}
      if (idx >= 0) {{
        sels.splice(idx, 1);
        if (sels.length === 0) delete selectedProducts[key];
      }} else if (sels.length < MAX_COLORS) {{
        sels.push({{ color: color, variantId: p.variantMap[color] || null }});
      }} else {{
        sels[0] = {{ color: color, variantId: p.variantMap[color] || null }};
      }}
    }}
    renderProducts();
  }}

  function toggleSimpleProduct(key) {{
    if (selectedProducts[key]) {{ delete selectedProducts[key]; }}
    else {{
      var p = PRODUCTS[key];
      selectedProducts[key] = {{
        productKey: key, productId: p.productId, title: p.title, price: p.price,
        selections: [{{ color: "Default", variantId: p.variantMap["Default"] || null }}]
      }};
    }}
    renderProducts();
  }}

  // ── Navigation ────────────────────────────────────────
  function goToSlide(n) {{
    if (typeof n === "string" && n === "success") {{
      cardMain.style.display = "none";
      prodWrap.style.display = "none";
      cardAddr.style.display = "none";
      cardSuccess.style.display = "block";
      progressBar.style.width = "100%";
      window.scrollTo({{ top: 0, behavior: "smooth" }});
      return;
    }}
    n = parseInt(n);
    if (n > currentSlide && !validateSlide(currentSlide)) return;

    // Before entering product slide, fetch inventory + render products
    if (n === 6) {{
      updateAgeDisplay();
      fetchInventory().then(function() {{ renderProducts(); }});
      renderProducts(); // render immediately, update when inventory loads
    }}

    // Hide all containers, show the right one
    cardMain.style.display = "none";
    prodWrap.style.display = "none";
    cardAddr.style.display = "none";
    cardSuccess.style.display = "none";

    if (n >= 1 && n <= 5) {{
      cardMain.style.display = "block";
      cardMain.querySelectorAll(".igf-slide").forEach(function(s) {{ s.classList.remove("active"); }});
      var target = cardMain.querySelector('.igf-slide[data-slide="' + n + '"]');
      if (target) target.classList.add("active");
    }} else if (n === 6) {{
      prodWrap.style.display = "block";
    }} else if (n === 7) {{
      cardAddr.style.display = "block";
    }}

    progressBar.style.width = Math.round((n / TOTAL_SLIDES) * 100) + "%";
    currentSlide = n;
    window.scrollTo({{ top: 0, behavior: "smooth" }});

    // Auto-focus the input on the slide
    setTimeout(function() {{
      var activeSlide = document.querySelector('.igf-slide[data-slide="' + n + '"]')
        || document.querySelector('[data-slide="' + n + '"]');
      if (activeSlide) {{
        var inp = activeSlide.querySelector("input:not([type=checkbox]):not([type=date]),select");
        if (inp) inp.focus();
      }}
    }}, 100);
  }}

  // ── Validation ────────────────────────────────────────
  function validateSlide(slide) {{
    var valid = true;
    function err(id, show) {{
      var el = document.getElementById(id);
      var msg = document.getElementById("igf-err-" + id.replace("igf-",""));
      if (el) el.classList.toggle("invalid", !show);
      if (msg) msg.style.display = show ? "none" : "block";
      if (!show) valid = false;
    }}
    if (slide === 1) err("igf-name", document.getElementById("igf-name").value.trim().length > 0);
    if (slide === 2) err("igf-email", /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(document.getElementById("igf-email").value));
    if (slide === 3) err("igf-phone", /^\\d{{10}}$/.test(document.getElementById("igf-phone").value.replace(/\\D/g, "")));
    if (slide === 5) {{
      syncDateDropdown("igf-baby1");
      var bd1Val = document.getElementById("igf-baby1-bday").value;
      err("igf-baby1-bday", bd1Val !== "");
      if (!bd1Val) {{
        // Highlight the empty dropdown(s)
        ["igf-baby1-month","igf-baby1-day","igf-baby1-year"].forEach(function(id) {{
          var el = document.getElementById(id);
          if (!el.value) el.classList.add("invalid");
          else el.classList.remove("invalid");
        }});
      }}
      if (document.getElementById("igf-has-baby2").checked) {{
        syncDateDropdown("igf-baby2");
        var bd2Val = document.getElementById("igf-baby2-bday").value;
        if (!bd2Val) {{ valid = false; }}
      }}
    }}
    if (slide === 6) {{
      if (Object.keys(selectedProducts).length === 0) {{
        alert("Please select at least one product.");
        valid = false;
      }}
    }}
    if (slide === 7) {{
      err("igf-street", document.getElementById("igf-street").value.trim().length > 0);
      err("igf-city", document.getElementById("igf-city").value.trim().length > 0);
      err("igf-state", document.getElementById("igf-state").value !== "");
      err("igf-zip", document.getElementById("igf-zip").value.trim().length >= 5);
    }}
    return valid;
  }}

  // ── Submit ────────────────────────────────────────────
  function submit() {{
    if (!validateSlide(7)) return;
    var btn = document.getElementById("igf-submit-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="igf-spinner"></span>Submitting...';

    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;

    var products = [];
    for (var key in selectedProducts) {{
      if (!selectedProducts.hasOwnProperty(key)) continue;
      var sp = selectedProducts[key];
      for (var i = 0; i < sp.selections.length; i++) {{
        var s = sp.selections[i];
        products.push({{
          product_key: sp.productKey, product_id: sp.productId,
          variant_id: s.variantId, title: sp.title, color: s.color, price: sp.price
        }});
      }}
    }}

    var payload = {{
      form_type: "influencer_gifting2",
      submitted_at: new Date().toISOString(),
      personal_info: {{
        full_name: document.getElementById("igf-name").value.trim(),
        email: document.getElementById("igf-email").value.trim(),
        phone: "+1" + document.getElementById("igf-phone").value.replace(/\\D/g, ""),
        instagram: document.getElementById("igf-instagram").value.trim() || "None",
        tiktok: document.getElementById("igf-tiktok").value.trim() || "None"
      }},
      baby_info: {{
        child_1: {{ birthday: bd1, age_months: calcAgeMonths(bd1) }},
        child_2: bd2 ? {{ birthday: bd2, age_months: calcAgeMonths(bd2) }} : null
      }},
      selected_products: products,
      shipping_address: {{
        street: document.getElementById("igf-street").value.trim(),
        apt: document.getElementById("igf-apt").value.trim(),
        city: document.getElementById("igf-city").value.trim(),
        state: document.getElementById("igf-state").value,
        zip: document.getElementById("igf-zip").value.trim(),
        country: document.getElementById("igf-country").value
      }},
      shopify_customer_id: window.__igf_customer ? window.__igf_customer.id : null
    }};

    fetch(WEBHOOK_URL, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload)
    }})
    .then(function(r) {{
      if (!r.ok) throw new Error("HTTP " + r.status);
      goToSlide("success");
    }})
    .catch(function(err) {{
      console.error("Submit error:", err);
      alert("Something went wrong. Please try again.");
      btn.disabled = false;
      btn.innerHTML = "Submit Application";
    }});
  }}

  // ── Toggle Baby 2 ────────────────────────────────────
  function toggleBaby2() {{
    var show = document.getElementById("igf-has-baby2").checked;
    document.getElementById("igf-baby2-section").style.display = show ? "block" : "none";
    if (!show) document.getElementById("igf-baby2-bday").value = "";
  }}

  // ── Customer Pre-fill ─────────────────────────────────
  function prefillCustomer() {{
    var el = document.getElementById("igf-customer-data");
    if (!el) return;
    var c = JSON.parse(el.textContent);
    if (!c) return;
    window.__igf_customer = c;
    if (c.name) document.getElementById("igf-name").value = c.name;
    if (c.email) document.getElementById("igf-email").value = c.email;
  }}

  // ── Event Listeners ───────────────────────────────────
  document.getElementById("igf-submit-btn").addEventListener("click", submit);
  document.getElementById("igf-has-baby2").addEventListener("change", toggleBaby2);

  // Next / Back / Skip buttons
  document.querySelectorAll("[data-next]").forEach(function(btn) {{
    btn.addEventListener("click", function() {{ goToSlide(parseInt(this.dataset.next)); }});
  }});
  document.querySelectorAll("[data-prev]").forEach(function(btn) {{
    btn.addEventListener("click", function() {{ goToSlide(parseInt(this.dataset.prev)); }});
  }});

  // Enter key advances to next slide
  document.addEventListener("keydown", function(e) {{
    if (e.key !== "Enter") return;
    if (e.target.tagName === "TEXTAREA") return;
    var nextBtn = null;
    if (currentSlide >= 1 && currentSlide <= 5) {{
      var activeSlide = cardMain.querySelector('.igf-slide[data-slide="' + currentSlide + '"]');
      if (activeSlide) nextBtn = activeSlide.querySelector("[data-next]");
    }}
    if (nextBtn) {{ e.preventDefault(); nextBtn.click(); }}
  }});

  // ── Init ──────────────────────────────────────────────
  prefillCustomer();
  progressBar.style.width = Math.round((1 / TOTAL_SLIDES) * 100) + "%";

  window.IGF = {{ goToSlide: goToSlide, submit: submit }};
}})();
</script>

{{% schema %}}
{{
  "name": "Influencer Gifting 2",
  "tag": "section",
  "class": "influencer-gifting2-section"
}}
{{% endschema %}}
'''


def build_template_json():
    return json.dumps({
        "sections": {
            "main": {
                "type": "influencer-gifting2",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# ── Deploy ───────────────────────────────────────────────────────
def deploy(dry_run=False):
    print(f"\n{'='*60}")
    print(f"  Deploy Influencer Gifting 2 Page")
    print(f"{'='*60}")
    print(f"  Shop: {SHOP}")
    print(f"  Webhook: {N8N_WEBHOOK_URL or '(not set)'}")

    if not TOKEN:
        print("\n  [ERROR] SHOPIFY_ACCESS_TOKEN not set")
        return

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
    page_id = create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "influencer-gifting2")

    page_url = f"https://{SHOP}/pages/{PAGE_HANDLE}"
    print(f"\n{'='*60}")
    print(f"  [SUCCESS] Page deployed!")
    print(f"  Page ID: {page_id}")
    print(f"  URL: {page_url}")
    print(f"{'='*60}")

    os.makedirs(".tmp/shopify_gifting", exist_ok=True)
    info = {"page_id": page_id, "page_url": page_url, "theme_id": theme_id, "webhook_url": N8N_WEBHOOK_URL}
    with open(".tmp/shopify_gifting/gifting2_deploy_info.json", "w", encoding="utf-8") as f:
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

    for key in [TEMPLATE_KEY, "templates/page.influencer-gifting2.liquid"]:
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
