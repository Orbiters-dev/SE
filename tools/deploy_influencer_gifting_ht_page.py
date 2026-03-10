"""
Shopify Influencer Gifting HT Page 배포 도구
- influencer-gifting 페이지 기반, 확장 버전:
  - Collaboration Terms 제거 (4단계)
  - 제품별 최대 3개 색상 선택 가능
  - 연령 기반 확장 제품 추천 (젖병→빨대컵, 빨대컵→텀블러)
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
N8N_WEBHOOK_URL = os.getenv("N8N_INFLUENCER_HT_WEBHOOK", "") or os.getenv("N8N_INFLUENCER_WEBHOOK", "")

# ── Product Data ─────────────────────────────────────────────────
# bonus_age_min/max: age range where this product appears as optional "Bonus Pick"
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
        "bonus_age_min": 0, "bonus_age_max": 6,
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
        "bonus_age_min": 0, "bonus_age_max": 6,
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
        "bonus_age_min": 6, "bonus_age_max": 18,
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


def is_os2_theme(theme_id):
    try:
        shopify_request("GET", f"/themes/{theme_id}/assets.json?asset[key]=templates/index.json")
        return True
    except urllib.error.HTTPError:
        return False


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

    return f'''<!-- Influencer Gifting HT Form Section -->
<!-- Generated by tools/deploy_influencer_gifting_ht_page.py -->

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

  /* ── Section Divider ────────────────────────────────── */
  .igf-section-label {{
    font-size: 1rem;
    font-weight: 700;
    color: #1a1a1a;
    margin: 28px 0 6px;
    padding-bottom: 6px;
    border-bottom: 2px solid #2c6ecb;
    display: inline-block;
  }}
  .igf-section-hint {{
    color: #888;
    font-size: 0.85rem;
    margin-bottom: 16px;
  }}

  /* ── Product Grid ──────────────────────────────────── */
  .igf-product-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 12px;
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

  /* ── Swatches ───────────────────────────────────────── */
  .igf-swatch-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
    margin-bottom: 6px;
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

  /* ── Color Count Badge ──────────────────────────────── */
  .igf-color-count {{
    text-align: center;
    font-size: 0.75rem;
    color: #888;
    margin-bottom: 8px;
  }}
  .igf-color-count strong {{
    color: #2c6ecb;
  }}

  /* ── Select Button ──────────────────────────────────── */
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

  /* ── Badges ─────────────────────────────────────────── */
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
  .igf-bonus-badge {{
    position: absolute;
    top: 8px;
    right: 8px;
    background: #e8f4fd;
    color: #2c6ecb;
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
  <!-- Progress Bar (4 steps) -->
  <div class="igf-progress">
    <div class="igf-progress-step active" data-for="1"></div>
    <div class="igf-progress-step" data-for="2"></div>
    <div class="igf-progress-step" data-for="3"></div>
    <div class="igf-progress-step" data-for="4"></div>
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

  <!-- ────── Step 3: Product Selection (multi-color, expanded range) ────── -->
  <div class="igf-step" data-step="3">
    <h2>Select Your Products</h2>
    <p class="igf-subtitle">Tap colors to pick up to 3 per product. Bonus products are optional extras for your baby&rsquo;s next stage!</p>

    <div id="igf-core-section"></div>
    <div class="igf-product-grid" id="igf-products-core"></div>

    <div id="igf-bonus-section" style="display:none">
      <div class="igf-section-label">Bonus Picks</div>
      <p class="igf-section-hint">Optional extras your child can grow into &mdash; pick up to 3 colors each</p>
    </div>
    <div class="igf-product-grid" id="igf-products-bonus"></div>

    <div id="igf-optional-section" style="display:none">
      <div class="igf-section-label">Add-ons</div>
      <p class="igf-section-hint">Optional items available for all ages</p>
    </div>
    <div class="igf-product-grid" id="igf-products-optional"></div>

    <div class="igf-btn-row">
      <button type="button" class="igf-btn igf-btn-secondary" data-go="2">Back</button>
      <button type="button" class="igf-btn igf-btn-primary" data-go="4">Next</button>
    </div>
  </div>

  <!-- ────── Step 4: Shipping Address + Submit ────── -->
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

  var WEBHOOK_URL = "{webhook_url}";
  var PRODUCTS = {products_js};
  var TOTAL_STEPS = 4;
  var currentStep = 1;
  // selectedProducts[key] = {{ productKey, productId, title, price, selections: [{{color, variantId}}] }}
  var selectedProducts = {{}};
  var MAX_COLORS = 3;

  // ── Age Calculation ──────────────────────────────────
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
    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-baby2-bday").value;
    document.getElementById("igf-baby1-age").innerHTML = ageLabel(calcAgeMonths(bd1));
    document.getElementById("igf-baby2-age").innerHTML = ageLabel(calcAgeMonths(bd2));
  }}

  // ── Product Visibility (expanded age ranges) ──────────
  function getVisibleProducts() {{
    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;
    var ages = [calcAgeMonths(bd1)];
    if (bd2) ages.push(calcAgeMonths(bd2));

    var result = {{ core: {{}}, bonus: {{}}, optional: {{}} }};

    for (var key in PRODUCTS) {{
      if (!PRODUCTS.hasOwnProperty(key)) continue;
      var p = PRODUCTS[key];

      if (p.optional) {{
        result.optional[key] = p;
        continue;
      }}

      var isCore = false;
      var isBonus = false;

      for (var i = 0; i < ages.length; i++) {{
        var age = ages[i];
        var eff = (age === null || age < 0) ? 0 : age;
        if (eff >= p.ageMin && eff < p.ageMax) {{
          isCore = true;
          break;
        }}
        if (p.bonusAgeMin != null && eff >= p.bonusAgeMin && eff < p.bonusAgeMax) {{
          isBonus = true;
        }}
      }}

      if (isCore) {{
        result.core[key] = p;
      }} else if (isBonus) {{
        result.bonus[key] = p;
      }}
    }}
    return result;
  }}

  // ── Color Hex Map ────────────────────────────────────
  var COLOR_HEX = {{
    "Creamy Blue":"#A4C8E1","Rose Coral":"#E88D8D","Olive White":"#C5C99A",
    "Bear Pure Gold":"#D4A76A","Bear White":"#F5F0E8","Cherry Pure Gold":"#D4A76A",
    "Cherry Rose Gold":"#E8B4B4","Peach":"#FFB899","Skyblue":"#87CEEB",
    "White":"#F0F0F0","Aquagreen":"#7BC8A4","Pink":"#FFB6C1","Beige":"#D4C5A9",
    "Charcoal":"#4A4A4A","Butter":"#F5E6B8","Flower Coral":"#FF8B7D",
    "Air Balloon Blue":"#7EB5D6","Cherry Peach":"#FFB4A2","Olive Pistachio":"#A8BF8A",
    "Bear Butter":"#F5E6B8"
  }};

  // ── Render a single product card ──────────────────────
  function buildCard(key, p, badgeType) {{
    var card = document.createElement("div");
    var sel = selectedProducts[key];
    var selCount = sel ? sel.selections.length : 0;
    card.className = "igf-product-card" + (selCount > 0 ? " selected" : "");
    card.dataset.key = key;

    var badgeHtml = "";
    if (badgeType === "optional") {{
      badgeHtml = '<div class="igf-optional-badge">Optional</div>';
    }} else if (badgeType === "bonus") {{
      badgeHtml = '<div class="igf-bonus-badge">Bonus Pick</div>';
    }}

    var colorHtml = "";
    if (p.colors && p.colors.length > 0) {{
      var selectedColors = sel ? sel.selections.map(function(s) {{ return s.color; }}) : [];
      var swatches = p.colors.map(function(c) {{
        var hex = COLOR_HEX[c] || "#ccc";
        var active = selectedColors.indexOf(c) >= 0 ? " active" : "";
        return '<span class="igf-swatch' + active + '" data-key="' + key + '" data-color="' + c + '">' +
          '<span class="igf-swatch-dot" style="background:' + hex + '"></span>' + c + '</span>';
      }}).join("");
      colorHtml = '<div class="igf-swatch-row">' + swatches + '</div>';
      colorHtml += '<div class="igf-color-count"><strong>' + selCount + '</strong> / ' + MAX_COLORS + ' colors selected</div>';
    }}

    var btnText;
    if (p.colors && p.colors.length > 0) {{
      btnText = selCount > 0 ? "&#10003; " + selCount + " selected" : "Tap colors to select";
    }} else {{
      btnText = selCount > 0 ? "&#10003; Selected" : "Select";
    }}

    card.innerHTML =
      badgeHtml +
      '<img src="' + p.image + '" alt="' + p.title + '" loading="lazy">' +
      '<div class="igf-card-title">' + p.title + '</div>' +
      (p.subtitle ? '<div class="igf-card-subtitle">' + p.subtitle + '</div>' : '') +
      '<div class="igf-card-price">' + p.price + '</div>' +
      colorHtml +
      '<button type="button" class="igf-select-btn" data-key="' + key + '">' + btnText + '</button>';

    return card;
  }}

  // ── Attach card event listeners ────────────────────────
  function attachCardEvents(grid) {{
    // Swatch click: toggle color selection
    grid.querySelectorAll(".igf-swatch").forEach(function(sw) {{
      sw.addEventListener("click", function(e) {{
        e.stopPropagation();
        toggleColorSelection(this.dataset.key, this.dataset.color);
      }});
    }});

    // Select button click
    grid.querySelectorAll(".igf-select-btn").forEach(function(btn) {{
      btn.addEventListener("click", function(e) {{
        e.stopPropagation();
        var k = this.dataset.key;
        var p = PRODUCTS[k];
        if (!p.colors || p.colors.length === 0) {{
          toggleSimpleProduct(k);
        }} else if (selectedProducts[k]) {{
          // Clicking button on color product deselects all
          delete selectedProducts[k];
          renderProducts();
        }}
      }});
    }});

    // Card click for non-color products
    grid.querySelectorAll(".igf-product-card").forEach(function(card) {{
      card.addEventListener("click", function(e) {{
        if (e.target.closest(".igf-swatch") || e.target.tagName === "BUTTON") return;
        var k = this.dataset.key;
        var p = PRODUCTS[k];
        if (!p.colors || p.colors.length === 0) {{
          toggleSimpleProduct(k);
        }}
      }});
    }});
  }}

  // ── Product Rendering ─────────────────────────────────
  function renderProducts() {{
    var visible = getVisibleProducts();

    var coreGrid = document.getElementById("igf-products-core");
    var bonusGrid = document.getElementById("igf-products-bonus");
    var optGrid = document.getElementById("igf-products-optional");
    var coreSection = document.getElementById("igf-core-section");
    var bonusSection = document.getElementById("igf-bonus-section");
    var optSection = document.getElementById("igf-optional-section");

    coreGrid.innerHTML = "";
    bonusGrid.innerHTML = "";
    optGrid.innerHTML = "";

    // Remove selections for products no longer visible
    for (var k in selectedProducts) {{
      if (!visible.core[k] && !visible.bonus[k] && !visible.optional[k]) {{
        delete selectedProducts[k];
      }}
    }}

    var hasCore = Object.keys(visible.core).length > 0;
    var hasBonus = Object.keys(visible.bonus).length > 0;
    var hasOpt = Object.keys(visible.optional).length > 0;

    // Core products
    if (hasCore) {{
      coreSection.innerHTML = '<div class="igf-section-label">Recommended for Your Baby</div><p class="igf-section-hint">Pick up to 3 colors per product</p>';
      for (var ck in visible.core) {{
        coreGrid.appendChild(buildCard(ck, visible.core[ck], "core"));
      }}
      attachCardEvents(coreGrid);
    }} else {{
      coreSection.innerHTML = '<div class="igf-no-products">No core products available for this age range.</div>';
    }}

    // Bonus products
    bonusSection.style.display = hasBonus ? "block" : "none";
    if (hasBonus) {{
      for (var bk in visible.bonus) {{
        bonusGrid.appendChild(buildCard(bk, visible.bonus[bk], "bonus"));
      }}
      attachCardEvents(bonusGrid);
    }}

    // Optional products
    optSection.style.display = hasOpt ? "block" : "none";
    if (hasOpt) {{
      for (var ok in visible.optional) {{
        optGrid.appendChild(buildCard(ok, visible.optional[ok], "optional"));
      }}
      attachCardEvents(optGrid);
    }}
  }}

  // ── Toggle color selection (multi-select up to 3) ──────
  function toggleColorSelection(key, color) {{
    var p = PRODUCTS[key];
    if (!selectedProducts[key]) {{
      // First selection for this product
      selectedProducts[key] = {{
        productKey: key,
        productId: p.productId,
        title: p.title,
        price: p.price,
        selections: [{{ color: color, variantId: p.variantMap[color] || null }}]
      }};
    }} else {{
      var sels = selectedProducts[key].selections;
      var idx = -1;
      for (var i = 0; i < sels.length; i++) {{
        if (sels[i].color === color) {{ idx = i; break; }}
      }}
      if (idx >= 0) {{
        // Deselect this color
        sels.splice(idx, 1);
        if (sels.length === 0) {{
          delete selectedProducts[key];
        }}
      }} else if (sels.length < MAX_COLORS) {{
        // Add this color
        sels.push({{ color: color, variantId: p.variantMap[color] || null }});
      }} else {{
        alert("You can select up to " + MAX_COLORS + " colors per product.");
        return;
      }}
    }}
    renderProducts();
  }}

  // ── Toggle for non-color products (chamom_duo) ─────────
  function toggleSimpleProduct(key) {{
    if (selectedProducts[key]) {{
      delete selectedProducts[key];
    }} else {{
      var p = PRODUCTS[key];
      selectedProducts[key] = {{
        productKey: key,
        productId: p.productId,
        title: p.title,
        price: p.price,
        selections: [{{ color: "Default", variantId: p.variantMap["Default"] || null }}]
      }};
    }}
    renderProducts();
  }}

  // ── Step Navigation ──────────────────────────────────
  function goToStep(n) {{
    if (n > currentStep && !validateStep(currentStep)) return;

    if (n === 3) {{
      updateAgeDisplay();
      renderProducts();
    }}

    document.querySelectorAll(".igf-step").forEach(function(s) {{ s.classList.remove("active"); }});
    var target = document.querySelector('.igf-step[data-step="' + n + '"]');
    if (target) target.classList.add("active");

    document.querySelectorAll(".igf-progress-step").forEach(function(bar) {{
      var barStep = parseInt(bar.dataset.for);
      bar.classList.toggle("done", barStep < n);
      bar.classList.toggle("active", barStep === n);
    }});

    currentStep = n;
    window.scrollTo({{ top: 0, behavior: "smooth" }});
  }}

  // ── Validation ───────────────────────────────────────
  function validateStep(step) {{
    var valid = true;

    function check(id, condition) {{
      var el = document.getElementById(id);
      var errEl = el ? el.closest(".igf-field") : null;
      var err = errEl ? errEl.querySelector(".igf-error") : null;
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
      // Must select at least one product
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
    return valid;
  }}

  // ── Submit ───────────────────────────────────────────
  function submit() {{
    if (!validateStep(4)) return;

    var btn = document.getElementById("igf-submit-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="igf-spinner"></span>Submitting...';

    var bd1 = document.getElementById("igf-baby1-bday").value;
    var bd2 = document.getElementById("igf-has-baby2").checked
      ? document.getElementById("igf-baby2-bday").value : null;

    // Flatten all selections into individual line items
    var products = [];
    for (var key in selectedProducts) {{
      if (!selectedProducts.hasOwnProperty(key)) continue;
      var sp = selectedProducts[key];
      for (var i = 0; i < sp.selections.length; i++) {{
        var s = sp.selections[i];
        products.push({{
          product_key: sp.productKey,
          product_id: sp.productId,
          variant_id: s.variantId,
          title: sp.title,
          color: s.color,
          price: sp.price
        }});
      }}
    }}

    var payload = {{
      form_type: "influencer_gifting_ht",
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
      goToStep("success");
    }})
    .catch(function(err) {{
      console.error("Submit error:", err);
      alert("Something went wrong. Please try again.");
      btn.disabled = false;
      btn.innerHTML = "Submit Application";
    }});
  }}

  // ── Toggle Baby 2 ───────────────────────────────────
  function toggleBaby2() {{
    var show = document.getElementById("igf-has-baby2").checked;
    document.getElementById("igf-baby2-section").style.display = show ? "block" : "none";
    if (!show) document.getElementById("igf-baby2-bday").value = "";
  }}

  // ── Customer Pre-fill (Shopify logged-in) ────────────
  function prefillCustomer() {{
    var el = document.getElementById("igf-customer-data");
    if (!el) return;
    var c = JSON.parse(el.textContent);
    if (!c) return;
    window.__igf_customer = c;
    if (c.name) document.getElementById("igf-name").value = c.name;
    if (c.email) document.getElementById("igf-email").value = c.email;
  }}

  // ── Event Listeners ─────────────────────────────────
  document.getElementById("igf-baby1-bday").addEventListener("change", updateAgeDisplay);
  document.getElementById("igf-baby2-bday").addEventListener("change", updateAgeDisplay);
  document.getElementById("igf-submit-btn").addEventListener("click", submit);
  document.getElementById("igf-has-baby2").addEventListener("change", toggleBaby2);

  document.querySelectorAll("[data-go]").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      goToStep(parseInt(this.dataset.go));
    }});
  }});

  // ── Init ─────────────────────────────────────────────
  prefillCustomer();

  window.IGF = {{ goToStep: goToStep, submit: submit, toggleBaby2: toggleBaby2 }};
}})();
</script>

{{% schema %}}
{{
  "name": "Influencer Gifting HT Form",
  "tag": "section",
  "class": "influencer-gifting-ht-section"
}}
{{% endschema %}}
'''


def build_template_json():
    return json.dumps({
        "sections": {
            "main": {
                "type": "influencer-gifting-ht",
                "settings": {}
            }
        },
        "order": ["main"]
    }, indent=2)


# ── Main Deploy Function ────────────────────────────────────────
HANDLE = "influencer-gifting-ht"
SECTION_NAME = "influencer-gifting-ht"
PAGE_TITLE = "Grosmimi Gifting Application (HT)"


def deploy(dry_run=False):
    print(f"\n{'='*60}")
    print(f"  Shopify Influencer Gifting HT Page Deployment")
    print(f"{'='*60}")
    print(f"  Shop: {SHOP}")
    print(f"  Webhook: {N8N_WEBHOOK_URL or '(not set)'}")

    if not TOKEN:
        print("\n  [ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        return

    if not N8N_WEBHOOK_URL:
        print("\n  [WARN] Webhook URL not set. Form submissions will fail until configured.")

    print(f"\n  [1/4] Getting active theme ...")
    theme_id = get_active_theme_id()

    os2 = is_os2_theme(theme_id)
    print(f"  Theme type: {'Online Store 2.0' if os2 else 'Legacy'}")

    print(f"\n  [2/4] Building template assets ...")
    section_content = build_section_liquid(N8N_WEBHOOK_URL or "")
    print(f"  Section size: {len(section_content):,} bytes")

    if dry_run:
        print(f"\n  [DRY RUN] Would upload:")
        print(f"    - sections/{SECTION_NAME}.liquid ({len(section_content):,} bytes)")
        if os2:
            template_content = build_template_json()
            print(f"    - templates/page.{HANDLE}.json ({len(template_content):,} bytes)")
        else:
            print(f"    - templates/page.{HANDLE}.liquid")
        print(f"    - Create page: {HANDLE}")
        print(f"\n  [DRY RUN] No changes made.")
        return

    print(f"\n  [3/4] Uploading theme assets ...")
    upload_theme_asset(theme_id, f"sections/{SECTION_NAME}.liquid", section_content)

    if os2:
        template_content = build_template_json()
        upload_theme_asset(theme_id, f"templates/page.{HANDLE}.json", template_content)
    else:
        legacy_template = f"{{% section '{SECTION_NAME}' %}}"
        upload_theme_asset(theme_id, f"templates/page.{HANDLE}.liquid", legacy_template)

    print(f"\n  [4/4] Creating Shopify page ...")
    page_id = create_or_update_page(
        handle=HANDLE,
        title=PAGE_TITLE,
        template_suffix=HANDLE,
    )

    page_url = f"https://{SHOP}/pages/{HANDLE}"

    print(f"\n{'='*60}")
    print(f"  [SUCCESS] Page deployed!")
    print(f"  Page ID: {page_id}")
    print(f"  URL: {page_url}")
    print(f"{'='*60}")

    os.makedirs(".tmp/shopify_gifting", exist_ok=True)
    info = {
        "page_id": page_id,
        "page_url": page_url,
        "theme_id": theme_id,
        "webhook_url": N8N_WEBHOOK_URL,
    }
    with open(".tmp/shopify_gifting/deploy_ht_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"\n  Deploy info saved to .tmp/shopify_gifting/deploy_ht_info.json")

    return info


def rollback():
    print(f"\n  Rolling back ...")
    if not TOKEN:
        print("  [ERROR] No token")
        return

    theme_id = get_active_theme_id()

    try:
        shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]=sections/{SECTION_NAME}.liquid")
        print(f"  [OK] Deleted sections/{SECTION_NAME}.liquid")
    except Exception as e:
        print(f"  [SKIP] Section: {e}")

    for key in [f"templates/page.{HANDLE}.json", f"templates/page.{HANDLE}.liquid"]:
        try:
            shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={key}")
            print(f"  [OK] Deleted {key}")
        except Exception:
            pass

    try:
        result = shopify_request("GET", f"/pages.json?handle={HANDLE}")
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
