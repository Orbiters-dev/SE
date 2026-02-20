"""
Shopify Influencer Gifting Page 배포 도구
- Shopify Theme Asset API로 커스텀 Liquid 섹션 + 페이지 템플릿 업로드
- Shopify Pages API로 페이지 생성
- 실행 시 페이지 URL 출력
"""

import os
import sys
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"
N8N_WEBHOOK_URL = os.getenv("N8N_INFLUENCER_WEBHOOK", "")

# ── Product Data (from Shopify API) ─────────────────────────────
PRODUCTS = {
    "ppsu_bottle": {
        "title": "Grosmimi PPSU Baby Bottle 10oz",
        "shopify_product_id": 8288604815682,
        "price": "$19.60",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-5231923.png?v=1765928785",
        "colors": [
            "Creamy Blue", "Rose Coral", "Olive White", "Bear Pure Gold",
            "Bear White", "Cherry Pure Gold", "Cherry Rose Gold",
        ],
        "variant_map": {
            "Creamy Blue": 51854035059058, "Rose Coral": 51854035091826,
            "Olive White": 45019086586178, "Bear Pure Gold": 45019086618946,
            "Bear White": 45019086651714, "Cherry Pure Gold": 45019086684482,
            "Cherry Rose Gold": 45019086717250,
        },
        "image_map": {
            "Creamy Blue": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-5231923.png?v=1765928785",
            "Rose Coral": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-4508449.png?v=1765928785",
            "Bear White": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-4625608.jpg?v=1765928785",
        },
        "age_min": 0, "age_max": 6,
    },
    "ppsu_straw": {
        "title": "Grosmimi PPSU Straw Cup 10oz",
        "shopify_product_id": 8288579256642,
        "price": "$24.90",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-straw-cup-10oz-300ml-7356566.png",
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
    },
    "ss_straw": {
        "title": "Grosmimi Stainless Steel Straw Cup 10oz",
        "shopify_product_id": 8864426557762,
        "price": "$46.80",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-straw-cup-with-flip-top-10oz-300ml-6763835.png",
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
    },
    "ss_tumbler": {
        "title": "Grosmimi Stainless Steel Tumbler 10oz",
        "shopify_product_id": 14761459941746,
        "price": "$49.80",
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
    },
    "chamom_duo": {
        "title": "CHA&MOM Essential Duo Bundle",
        "subtitle": "Lotion + Body Wash",
        "shopify_product_id": 14643954647410,
        "price": "$46.92",
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
    """Get the main/active theme ID"""
    result = shopify_request("GET", "/themes.json")
    for theme in result.get("themes", []):
        if theme.get("role") == "main":
            print(f"  Active theme: {theme['name']} (ID: {theme['id']})")
            return theme["id"]
    raise RuntimeError("No active theme found")


def is_os2_theme(theme_id):
    """Check if theme is Online Store 2.0 (has JSON templates)"""
    try:
        shopify_request("GET", f"/themes/{theme_id}/assets.json?asset[key]=templates/index.json")
        return True
    except urllib.error.HTTPError:
        return False


def upload_theme_asset(theme_id, key, value):
    """Upload a file to the theme"""
    print(f"  Uploading: {key} ...")
    shopify_request("PUT", f"/themes/{theme_id}/assets.json", {
        "asset": {"key": key, "value": value}
    })
    print(f"  [OK] {key}")


def create_or_update_page(handle, title, template_suffix):
    """Create or update a Shopify page"""
    # Check if page exists
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
    """Build the JavaScript PRODUCTS object from Python dict"""
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
        }
    return json.dumps(js_products, indent=2)


def build_state_options():
    """Build HTML <option> tags for US states"""
    options = ['<option value="">Select State</option>']
    for code in US_STATES:
        name = US_STATE_NAMES[code]
        options.append(f'<option value="{code}">{name}</option>')
    return "\n".join(options)


def build_section_liquid(webhook_url):
    """Build the complete Liquid section file content"""

    products_js = build_products_js()
    state_options = build_state_options()

    return f'''<!-- Influencer Gifting Form Section -->
<!-- Generated by tools/deploy_influencer_page.py -->

{{% comment %}}
  Customer pre-fill: passes logged-in customer data to JavaScript
{{% endcomment %}}
{{% if customer %}}
<script id="igf-customer-data" type="application/json">
{{"name": {{{{ customer.name | json }}}}, "email": {{{{ customer.email | json }}}}, "phone": {{{{ customer.phone | json }}}}, "id": {{{{ customer.id }}}}}}
</script>
{{% endif %}}

<style>
  /* ── Reset & Container ─────────────────────────────── */
  .igf-container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
    font-family: inherit;
  }}
  .igf-container * {{ box-sizing: border-box; }}

  /* ── Progress Bar ──────────────────────────────────── */
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
  .igf-progress-step.active {{ background: #2c6ecb; }}
  .igf-progress-step.done {{ background: #2c6ecb; }}

  /* ── Steps ─────────────────────────────────────────── */
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

  /* ── Form Fields ───────────────────────────────────── */
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
    border-color: #2c6ecb;
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

  /* ── Phone Group ───────────────────────────────────── */
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

  /* ── Toggle / Checkbox ─────────────────────────────── */
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
    accent-color: #2c6ecb;
  }}

  /* ── Product Grid ──────────────────────────────────── */
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

  /* ── Product Card ──────────────────────────────────── */
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
    border-color: #2c6ecb;
    box-shadow: 0 0 0 3px rgba(44, 110, 203, 0.15);
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
    color: #2c6ecb;
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 8px;
  }}
  .igf-product-card .igf-card-subtitle {{
    color: #888;
    font-size: 0.8rem;
    margin-bottom: 8px;
  }}
  .igf-swatch-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
    margin-bottom: 10px;
  }}
  .igf-swatch {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1.5px solid #ddd;
    border-radius: 20px;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.15s;
    background: #fff;
    color: #555;
    white-space: nowrap;
  }}
  .igf-swatch:hover {{
    border-color: #999;
  }}
  .igf-swatch.active {{
    border-color: #2c6ecb;
    background: #eef4ff;
    color: #2c6ecb;
    font-weight: 600;
  }}
  .igf-swatch-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 1px solid rgba(0,0,0,0.15);
    flex-shrink: 0;
  }}
  .igf-product-card .igf-select-btn {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 2px solid #2c6ecb;
    border-radius: 8px;
    background: #fff;
    color: #2c6ecb;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.9rem;
  }}
  .igf-product-card .igf-select-btn:hover {{
    background: #f0f6ff;
  }}
  .igf-product-card.selected .igf-select-btn {{
    background: #2c6ecb;
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

  /* ── Address Grid ──────────────────────────────────── */
  .igf-address-row {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }}
  @media (min-width: 520px) {{
    .igf-address-row.igf-row-3 {{ grid-template-columns: 2fr 1fr 1fr; }}
    .igf-address-row.igf-row-2 {{ grid-template-columns: 1fr 1fr; }}
  }}

  /* ── Terms ─────────────────────────────────────────── */
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
  .igf-terms-list li {{
    margin-bottom: 4px;
  }}

  /* ── Buttons ───────────────────────────────────────── */
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
    background: #2c6ecb;
    color: #fff;
    flex: 1;
  }}
  .igf-btn-primary:hover {{ background: #245bb0; }}
  .igf-btn-primary:disabled {{
    background: #ccc;
    cursor: not-allowed;
  }}
  .igf-btn-secondary {{
    background: #f0f0f0;
    color: #333;
  }}
  .igf-btn-secondary:hover {{ background: #e0e0e0; }}

  /* ── Success Screen ────────────────────────────────── */
  .igf-success {{
    text-align: center;
    padding: 60px 20px;
  }}
  .igf-success h2 {{
    color: #27ae60;
    margin-bottom: 12px;
  }}
  .igf-success p {{ color: #666; font-size: 1.1rem; }}

  /* ── Loading Spinner ───────────────────────────────── */
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

  /* ── Age Display ───────────────────────────────────── */
  .igf-age-badge {{
    display: inline-block;
    padding: 4px 10px;
    background: #e8f4fd;
    color: #2c6ecb;
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

</style>

<div class="igf-container" id="igf-app">
  <!-- Progress Bar -->
  <div class="igf-progress">
    <div class="igf-progress-step active" data-for="1"></div>
    <div class="igf-progress-step" data-for="2"></div>
    <div class="igf-progress-step" data-for="3"></div>
    <div class="igf-progress-step" data-for="4"></div>
    <div class="igf-progress-step" data-for="5"></div>
  </div>

  <!-- ────── Step 1: Personal Info ────── -->
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

  <!-- ────── Step 2: Baby Info ────── -->
  <div class="igf-step" data-step="2">
    <h2>Baby Information</h2>
    <p class="igf-subtitle">We&rsquo;ll recommend products based on your child&rsquo;s age</p>

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

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="1">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="3">Next</button>
    </div>
  </div>

  <!-- ────── Step 3: Product Selection ────── -->
  <div class="igf-step" data-step="3">
    <h2>Select Your Products</h2>
    <p class="igf-subtitle">Products recommended for your child&rsquo;s age. Click a card to select.</p>
    <div class="igf-product-grid" id="igf-products"></div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="2">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="4">Next</button>
    </div>
  </div>

  <!-- ────── Step 4: Shipping Address ────── -->
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

  <!-- ────── Step 5: Terms & Submit ────── -->
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

  <!-- ────── Success Screen ────── -->
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

  // ── Age Calculation ──────────────────────────────────
  function calcAgeMonths(dateStr) {{
    if (!dateStr) return null;
    const bd = new Date(dateStr);
    const now = new Date();
    if (bd > now) return -1; // Expecting
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

  function updateAgeDisplay() {{
    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-baby2-bday").value;
    document.getElementById("igf-baby1-age").innerHTML = ageLabel(calcAgeMonths(bd1));
    document.getElementById("igf-baby2-age").innerHTML = ageLabel(calcAgeMonths(bd2));
  }}

  // ── Product Visibility ───────────────────────────────
  function getVisibleProducts() {{
    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;
    const ages = [calcAgeMonths(bd1)];
    if (bd2) ages.push(calcAgeMonths(bd2));

    const visible = {{}};
    for (const [key, p] of Object.entries(PRODUCTS)) {{
      if (p.optional) {{ visible[key] = p; continue; }}
      for (const age of ages) {{
        const eff = age < 0 ? 0 : age;
        if (eff >= p.ageMin && eff < p.ageMax) {{
          visible[key] = p;
          break;
        }}
      }}
    }}
    return visible;
  }}

  // ── Color Hex Map ────────────────────────────────────
  const COLOR_HEX = {{
    "Creamy Blue":"#A4C8E1","Rose Coral":"#E88D8D","Olive White":"#C5C99A",
    "Bear Pure Gold":"#D4A76A","Bear White":"#F5F0E8","Cherry Pure Gold":"#D4A76A",
    "Cherry Rose Gold":"#E8B4B4","Peach":"#FFB899","Skyblue":"#87CEEB",
    "White":"#F0F0F0","Aquagreen":"#7BC8A4","Pink":"#FFB6C1","Beige":"#D4C5A9",
    "Charcoal":"#4A4A4A","Butter":"#F5E6B8","Flower Coral":"#FF8B7D",
    "Air Balloon Blue":"#7EB5D6","Cherry Peach":"#FFB4A2","Olive Pistachio":"#A8BF8A",
    "Bear Butter":"#F5E6B8",
  }};

  // ── Product Card Rendering ───────────────────────────
  function renderProducts() {{
    const grid = document.getElementById("igf-products");
    const visible = getVisibleProducts();
    grid.innerHTML = "";

    if (Object.keys(visible).length === 0) {{
      grid.innerHTML = '<div class="igf-no-products">No products available for this age range.</div>';
      return;
    }}

    // Remove selections that are no longer visible
    for (const k of Object.keys(selectedProducts)) {{
      if (!visible[k]) delete selectedProducts[k];
    }}

    for (const [key, p] of Object.entries(visible)) {{
      const card = document.createElement("div");
      card.className = "igf-product-card" + (selectedProducts[key] ? " selected" : "");
      card.dataset.key = key;

      let colorHtml = "";
      if (p.colors && p.colors.length > 0) {{
        const selColor = selectedProducts[key] ? selectedProducts[key].color : "";
        const swatches = p.colors.map(c => {{
          const hex = COLOR_HEX[c] || "#ccc";
          const active = c === selColor ? " active" : "";
          return '<span class="igf-swatch' + active + '" data-key="' + key + '" data-color="' + c + '">' +
            '<span class="igf-swatch-dot" style="background:' + hex + '"></span>' + c + '</span>';
        }}).join("");
        colorHtml = '<div class="igf-swatch-row">' + swatches + '</div>';
      }}

      card.innerHTML =
        (p.optional ? '<div class="igf-optional-badge">Optional</div>' : '') +
        '<img src="' + p.image + '" alt="' + p.title + '" loading="lazy">' +
        '<div class="igf-card-title">' + p.title + '</div>' +
        (p.subtitle ? '<div class="igf-card-subtitle">' + p.subtitle + '</div>' : '') +
        '<div class="igf-card-price">' + p.price + '</div>' +
        colorHtml +
        '<button type="button" class="igf-select-btn" data-key="' + key + '">' +
        (selectedProducts[key] ? '&#10003; Selected' : 'Select') + '</button>';

      grid.appendChild(card);
    }}

    // Event: swatch click
    grid.querySelectorAll(".igf-swatch").forEach(sw => {{
      sw.addEventListener("click", function(e) {{
        e.stopPropagation();
        const k = this.dataset.key;
        const c = this.dataset.color;
        const card = this.closest(".igf-product-card");
        // Highlight active swatch
        card.querySelectorAll(".igf-swatch").forEach(s => s.classList.remove("active"));
        this.classList.add("active");
        // Swap product image if variant image exists
        const imgMap = PRODUCTS[k].imageMap || {{}};
        if (imgMap[c]) {{
          card.querySelector("img").src = imgMap[c];
        }}
        if (selectedProducts[k]) {{
          selectedProducts[k].color = c;
          selectedProducts[k].variantId = PRODUCTS[k].variantMap[c] || null;
        }}
      }});
    }});

    // Event: select button
    grid.querySelectorAll(".igf-select-btn").forEach(btn => {{
      btn.addEventListener("click", function(e) {{
        e.stopPropagation();
        toggleProduct(this.dataset.key);
      }});
    }});

    // Event: card click (toggle selection)
    grid.querySelectorAll(".igf-product-card").forEach(card => {{
      card.addEventListener("click", function(e) {{
        if (e.target.closest(".igf-swatch") || e.target.tagName === "BUTTON") return;
        toggleProduct(this.dataset.key);
      }});
    }});
  }}

  function toggleProduct(key) {{
    if (selectedProducts[key]) {{
      delete selectedProducts[key];
    }} else {{
      const p = PRODUCTS[key];
      const activeSwatch = document.querySelector('.igf-swatch.active[data-key="' + key + '"]');
      const color = activeSwatch ? activeSwatch.dataset.color : "";
      selectedProducts[key] = {{
        productKey: key,
        productId: p.productId,
        title: p.title,
        price: p.price,
        color: color,
        variantId: color ? (p.variantMap[color] || null) : (p.variantMap["Default"] || null),
      }};
    }}
    renderProducts();
  }}

  // ── Step Navigation ──────────────────────────────────
  function goToStep(n) {{
    // Validate current step before advancing
    if (n > currentStep && !validateStep(currentStep)) return;

    // Special: render products when entering step 3
    if (n === 3) {{
      updateAgeDisplay();
      renderProducts();
    }}

    // Hide all steps, show target
    document.querySelectorAll(".igf-step").forEach(s => s.classList.remove("active"));
    const target = document.querySelector('.igf-step[data-step="' + n + '"]');
    if (target) target.classList.add("active");

    // Update progress bar
    document.querySelectorAll(".igf-progress-step").forEach(bar => {{
      const barStep = parseInt(bar.dataset.for);
      bar.classList.toggle("done", barStep < n);
      bar.classList.toggle("active", barStep === n);
    }});

    currentStep = n;
    window.scrollTo({{ top: 0, behavior: "smooth" }});
  }}

  // ── Validation ───────────────────────────────────────
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
      check("igf-phone", /^\d{{10}}$/.test(document.getElementById("igf-phone").value.replace(/\\D/g, "")));
    }}
    if (step === 2) {{
      check("igf-baby1-bday", document.getElementById("igf-baby1-bday").value !== "");
      if (document.getElementById("igf-has-baby2").checked) {{
        check("igf-baby2-bday", document.getElementById("igf-baby2-bday").value !== "");
      }}
    }}
    if (step === 3) {{
      // Must select at least one non-optional product
      const nonOptional = Object.entries(selectedProducts).filter(([k]) => !PRODUCTS[k].optional);
      if (nonOptional.length === 0) {{
        alert("Please select at least one product.");
        valid = false;
      }}
      // Check that selected products with colors have a color chosen
      for (const [k, sp] of Object.entries(selectedProducts)) {{
        if (PRODUCTS[k].colors.length > 0 && !sp.color) {{
          alert('Please choose a color for "' + sp.title + '".');
          valid = false;
          break;
        }}
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

  // ── Submit ───────────────────────────────────────────
  function submit() {{
    if (!validateStep(5)) return;

    const btn = document.getElementById("igf-submit-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="igf-spinner"></span>Submitting...';

    const bd1 = document.getElementById("igf-baby1-bday").value;
    const bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;

    const payload = {{
      form_type: "influencer_gifting",
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

  // ── Toggle Baby 2 ───────────────────────────────────
  function toggleBaby2() {{
    const show = document.getElementById("igf-has-baby2").checked;
    document.getElementById("igf-baby2-section").style.display = show ? "block" : "none";
    if (!show) document.getElementById("igf-baby2-bday").value = "";
  }}

  // ── Customer Pre-fill (Shopify logged-in) ────────────
  function prefillCustomer() {{
    const el = document.getElementById("igf-customer-data");
    if (!el) return;
    const c = JSON.parse(el.textContent);
    if (!c) return;
    window.__igf_customer = c;
    if (c.name) document.getElementById("igf-name").value = c.name;
    if (c.email) document.getElementById("igf-email").value = c.email;
  }}

  // ── Date Input Listeners ─────────────────────────────
  document.getElementById("igf-baby1-bday").addEventListener("change", updateAgeDisplay);
  document.getElementById("igf-baby2-bday").addEventListener("change", updateAgeDisplay);

  // ── Button Event Listeners (CSP-safe) ─────────────────
  document.getElementById("igf-submit-btn").addEventListener("click", submit);
  document.getElementById("igf-has-baby2").addEventListener("change", toggleBaby2);

  document.querySelectorAll("[data-go]").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      goToStep(parseInt(this.dataset.go));
    }});
  }});

  // ── Init ─────────────────────────────────────────────
  prefillCustomer();

  window.IGF = {{ goToStep, submit, toggleBaby2 }};
}})();
</script>

{{% schema %}}
{{
  "name": "Influencer Gifting Form",
  "tag": "section",
  "class": "influencer-gifting-section"
}}
{{% endschema %}}
'''


def build_template_json():
    """Build the JSON page template content"""
    return json.dumps({
        "sections": {
            "main": {
                "type": "influencer-gifting",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# ── Main Deploy Function ────────────────────────────────────────
def deploy(dry_run=False):
    """Deploy the influencer gifting page to Shopify"""
    print(f"\n{'='*60}")
    print(f"  Shopify Influencer Gifting Page Deployment")
    print(f"{'='*60}")
    print(f"  Shop: {SHOP}")
    print(f"  Webhook: {N8N_WEBHOOK_URL or '(not set)'}")

    if not TOKEN:
        print("\n  [ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        print("  Run: python tools/shopify_oauth.py")
        return

    if not N8N_WEBHOOK_URL:
        print("\n  [WARN] N8N_INFLUENCER_WEBHOOK not set in .env")
        print("  Form submissions will fail until webhook URL is configured.")

    # 1. Get active theme
    print(f"\n  [1/4] Getting active theme ...")
    theme_id = get_active_theme_id()

    # 2. Check OS 2.0
    os2 = is_os2_theme(theme_id)
    print(f"  Theme type: {'Online Store 2.0' if os2 else 'Legacy'}")

    # 3. Build assets
    print(f"\n  [2/4] Building template assets ...")
    section_content = build_section_liquid(N8N_WEBHOOK_URL or "")
    print(f"  Section size: {len(section_content):,} bytes")

    if dry_run:
        print(f"\n  [DRY RUN] Would upload:")
        print(f"    - sections/influencer-gifting.liquid ({len(section_content):,} bytes)")
        if os2:
            template_content = build_template_json()
            print(f"    - templates/page.influencer-gifting.json ({len(template_content):,} bytes)")
        else:
            print(f"    - templates/page.influencer-gifting.liquid")
        print(f"    - Create page: influencer-gifting")
        print(f"\n  [DRY RUN] No changes made.")
        return

    # 4. Upload assets
    print(f"\n  [3/4] Uploading theme assets ...")
    upload_theme_asset(theme_id, "sections/influencer-gifting.liquid", section_content)

    if os2:
        template_content = build_template_json()
        upload_theme_asset(theme_id, "templates/page.influencer-gifting.json", template_content)
    else:
        legacy_template = "{% section 'influencer-gifting' %}"
        upload_theme_asset(theme_id, "templates/page.influencer-gifting.liquid", legacy_template)

    # 5. Create page
    print(f"\n  [4/4] Creating Shopify page ...")
    page_id = create_or_update_page(
        handle="influencer-gifting",
        title="Grosmimi Gifting Application",
        template_suffix="influencer-gifting",
    )

    # Get store domain for URL
    custom_domain = SHOP.replace(".myshopify.com", "")
    page_url = f"https://{SHOP}/pages/influencer-gifting"

    print(f"\n{'='*60}")
    print(f"  [SUCCESS] Page deployed!")
    print(f"  Page ID: {page_id}")
    print(f"  URL: {page_url}")
    print(f"{'='*60}")

    # Save deployment info
    os.makedirs(".tmp/shopify_gifting", exist_ok=True)
    info = {
        "page_id": page_id,
        "page_url": page_url,
        "theme_id": theme_id,
        "webhook_url": N8N_WEBHOOK_URL,
    }
    with open(".tmp/shopify_gifting/deploy_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"\n  Deploy info saved to .tmp/shopify_gifting/deploy_info.json")

    return info


def rollback():
    """Remove deployed assets and page"""
    print(f"\n  Rolling back ...")

    if not TOKEN:
        print("  [ERROR] No token")
        return

    theme_id = get_active_theme_id()

    # Delete section
    try:
        shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]=sections/influencer-gifting.liquid")
        print("  [OK] Deleted sections/influencer-gifting.liquid")
    except Exception as e:
        print(f"  [SKIP] Section: {e}")

    # Delete template (try both OS2 and legacy)
    for key in ["templates/page.influencer-gifting.json", "templates/page.influencer-gifting.liquid"]:
        try:
            shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={key}")
            print(f"  [OK] Deleted {key}")
        except Exception:
            pass

    # Delete page
    try:
        result = shopify_request("GET", "/pages.json?handle=influencer-gifting")
        for page in result.get("pages", []):
            shopify_request("DELETE", f"/pages/{page['id']}.json")
            print(f"  [OK] Deleted page {page['id']}")
    except Exception as e:
        print(f"  [SKIP] Page: {e}")

    print("  [DONE] Rollback complete")


# ── CLI ──────────────────────────────────────────────────────────
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
