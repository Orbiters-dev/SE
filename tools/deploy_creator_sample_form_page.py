"""Deploy Creator Sample Form page - simplified 2-step form for accepted creators.

Simplified from influencer-gifting2:
  - No personal info / address inputs (already collected at signup)
  - Step 1: Product selection (age-filtered from URL ?age=YYYY-MM-DD)
  - Step 2: Terms & Submit
  - Adds Naeiae Korean Pop Rice Snack as optional product
  - Submits to onzenna-sample-request-submit webhook

Usage:
    python tools/deploy_creator_sample_form_page.py
    python tools/deploy_creator_sample_form_page.py --dry-run
    python tools/deploy_creator_sample_form_page.py --rollback

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
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
N8N_WEBHOOK_URL = "https://n8n.orbiters.co.kr/webhook/onzenna-sample-request-submit"

SECTION_KEY = "sections/creator-sample-form.liquid"
TEMPLATE_KEY = "templates/page.creator-sample-form.json"
PAGE_HANDLE = "creator-sample-form"
PAGE_TITLE = "Creator Sample Request"

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
        "colors": ["Peach", "Skyblue", "White", "Aquagreen", "Pink", "Beige", "Charcoal", "Butter"],
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
        "colors": ["Flower Coral", "Air Balloon Blue", "Cherry Peach", "Olive Pistachio", "Bear Butter"],
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
    "naeiae_rice_snack": {
        "title": "Naeiae Korean Pop Rice Snack",
        "subtitle": "Baby-safe organic rice puff",
        "shopify_product_id": 9431435444546,
        "price": "$3.99",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/essential-feeding-trio-5008956.jpg?v=17696608",
        "colors": [],
        "variant_map": {"Default": 48635607875906},
        "image_map": {},
        "age_min": 6, "age_max": 48, "optional": True,
    },
}

COLLAB_TERMS = (
    '<ul class="csf-terms-list">'
    "<li>Total video length: 30 seconds</li>"
    "<li>Uploaded content must include voiceover + subtitles</li>"
    "<li>Must use royalty-free music</li>"
    "<li>Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG &amp; TikTok)</li>"
    "<li>Must include: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna</li>"
    "<li>Content must be posted within 14 days of receiving the product</li>"
    "<li>You agree that Onzenna may repost your content with credit</li>"
    "</ul>"
)

COLOR_HEX = {
    "Creamy Blue": "#A4C8E1", "Rose Coral": "#E88D8D", "Olive White": "#C5C99A",
    "Bear Pure Gold": "#D4A76A", "Bear White": "#F5F0E8", "Cherry Pure Gold": "#D4A76A",
    "Cherry Rose Gold": "#E8B4B4", "Peach": "#FFB899", "Skyblue": "#87CEEB",
    "White": "#F0F0F0", "Aquagreen": "#7BC8A4", "Pink": "#FFB6C1", "Beige": "#D4C5A9",
    "Charcoal": "#4A4A4A", "Butter": "#F5E6B8", "Flower Coral": "#FF8B7D",
    "Air Balloon Blue": "#7EB5D6", "Cherry Peach": "#FFB4A2", "Olive Pistachio": "#A8BF8A",
    "Bear Butter": "#F5E6B8",
}


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
        shopify_request("PUT", f"/pages/{page_id}.json", page_data)
        print(f"  [OK] Page updated (ID: {page_id})")
        return page_id
    else:
        result = shopify_request("POST", "/pages.json", page_data)
        page_id = result["page"]["id"]
        print(f"  [OK] Page created (ID: {page_id})")
        return page_id


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
        }
    return json.dumps(js_products, indent=2)


def build_color_hex_js():
    return json.dumps(COLOR_HEX, indent=2)


def build_section_liquid(webhook_url):
    products_js = build_products_js()
    color_hex_js = build_color_hex_js()

    return f'''<!-- Creator Sample Form - Simplified 2-step sample request -->
<!-- Generated by tools/deploy_creator_sample_form_page.py -->

<style>
  .csf-container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
    font-family: inherit;
  }}
  .csf-container * {{ box-sizing: border-box; }}

  .csf-progress {{
    display: flex;
    gap: 4px;
    margin-bottom: 32px;
  }}
  .csf-progress-step {{
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: #e0e0e0;
    transition: background 0.3s;
  }}
  .csf-progress-step.active {{ background: #2c6ecb; }}
  .csf-progress-step.done {{ background: #2c6ecb; }}

  .csf-step {{ display: none; }}
  .csf-step.active {{ display: block; }}
  .csf-step h2 {{ font-size: 1.5rem; margin-bottom: 8px; color: #1a1a1a; }}
  .csf-subtitle {{ color: #666; margin-bottom: 24px; font-size: 0.95rem; }}

  .csf-age-badge {{
    display: inline-block;
    padding: 4px 12px;
    background: #e8f4fd;
    color: #2c6ecb;
    border-radius: 12px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 16px;
  }}
  .csf-age-badge.expecting {{ background: #fef3e2; color: #e67e22; }}

  .csf-product-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }}
  @media (min-width: 520px) {{ .csf-product-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  @media (min-width: 768px) {{ .csf-product-grid {{ grid-template-columns: repeat(3, 1fr); }} }}

  .csf-product-card {{
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
    position: relative;
    background: #fff;
  }}
  .csf-product-card:hover {{ border-color: #aaa; transform: translateY(-2px); }}
  .csf-product-card.selected {{
    border-color: #2c6ecb;
    box-shadow: 0 0 0 3px rgba(44,110,203,0.15);
  }}
  .csf-product-card img {{
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
    border-radius: 8px;
    margin-bottom: 12px;
    background: #fafafa;
  }}
  .csf-card-title {{ font-weight: 600; font-size: 0.9rem; margin-bottom: 4px; color: #1a1a1a; }}
  .csf-card-price {{ color: #2c6ecb; font-weight: 700; font-size: 1rem; margin-bottom: 8px; }}
  .csf-card-subtitle {{ color: #888; font-size: 0.8rem; margin-bottom: 8px; }}
  .csf-optional-badge {{
    position: absolute; top: 8px; right: 8px;
    background: #f0f0f0; color: #666;
    font-size: 0.7rem; padding: 2px 8px;
    border-radius: 4px; font-weight: 600;
  }}

  .csf-swatch-row {{
    display: flex; flex-wrap: wrap; gap: 6px;
    justify-content: center; margin-bottom: 10px;
  }}
  .csf-swatch {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border: 1.5px solid #ddd; border-radius: 20px;
    font-size: 0.75rem; cursor: pointer; transition: all 0.15s;
    background: #fff; color: #555; white-space: nowrap;
  }}
  .csf-swatch:hover {{ border-color: #999; }}
  .csf-swatch.active {{ border-color: #2c6ecb; background: #eef4ff; color: #2c6ecb; font-weight: 600; }}
  .csf-swatch-dot {{ width: 12px; height: 12px; border-radius: 50%; border: 1px solid rgba(0,0,0,0.15); flex-shrink: 0; }}

  .csf-select-btn {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 16px; border: 2px solid #2c6ecb;
    border-radius: 8px; background: #fff; color: #2c6ecb;
    font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 0.9rem;
  }}
  .csf-select-btn:hover {{ background: #f0f6ff; }}
  .csf-product-card.selected .csf-select-btn {{ background: #2c6ecb; color: #fff; }}

  .csf-no-products {{
    text-align: center; padding: 40px; color: #666;
    background: #f9f9f9; border-radius: 12px;
  }}

  .csf-field {{ margin-bottom: 20px; }}
  .csf-field label {{ display: block; font-weight: 600; margin-bottom: 6px; font-size: 0.9rem; color: #333; }}

  .csf-terms-box {{
    background: #f9f9f9; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 16px 16px 16px 20px;
    margin-bottom: 20px; font-size: 0.9rem; line-height: 1.8; color: #333;
  }}
  .csf-terms-list {{ list-style: disc; padding-left: 18px; margin: 0; }}
  .csf-terms-list li {{ margin-bottom: 4px; }}

  .csf-toggle-label {{
    display: flex; align-items: center; gap: 10px;
    cursor: pointer; font-weight: 500; padding: 12px;
    background: #f9f9f9; border-radius: 8px;
  }}
  .csf-toggle-label input[type="checkbox"] {{ width: 18px; height: 18px; accent-color: #2c6ecb; }}

  .csf-btn-row {{ display: flex; gap: 12px; margin-top: 24px; }}
  .csf-btn {{
    padding: 12px 24px; border-radius: 8px; font-size: 1rem;
    font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; font-family: inherit;
  }}
  .csf-btn-primary {{ background: #2c6ecb; color: #fff; flex: 1; }}
  .csf-btn-primary:hover {{ background: #245bb0; }}
  .csf-btn-primary:disabled {{ background: #ccc; cursor: not-allowed; }}
  .csf-btn-secondary {{ background: #f0f0f0; color: #333; }}
  .csf-btn-secondary:hover {{ background: #e0e0e0; }}

  .csf-success {{ text-align: center; padding: 60px 20px; }}
  .csf-success h2 {{ color: #27ae60; margin-bottom: 12px; }}
  .csf-success p {{ color: #666; font-size: 1.1rem; }}

  .csf-spinner {{
    display: inline-block; width: 20px; height: 20px;
    border: 2px solid #fff; border-top-color: transparent;
    border-radius: 50%; animation: csf-spin 0.6s linear infinite;
    margin-right: 8px; vertical-align: middle;
  }}
  @keyframes csf-spin {{ to {{ transform: rotate(360deg); }} }}
</style>

<div class="csf-container" id="csf-app">
  <!-- Progress Bar -->
  <div class="csf-progress">
    <div class="csf-progress-step active" data-for="1"></div>
    <div class="csf-progress-step" data-for="2"></div>
  </div>

  <!-- Step 1: Product Selection -->
  <div class="csf-step active" data-step="1">
    <h2>Select Your Samples</h2>
    <p class="csf-subtitle">Products are shown based on your child's age. Select at least one.</p>
    <div id="csf-age-display"></div>
    <div class="csf-product-grid" id="csf-products"></div>
    <div class="csf-btn-row">
      <button type="button" class="csf-btn csf-btn-primary" data-go="2">Next</button>
    </div>
  </div>

  <!-- Step 2: Terms & Submit -->
  <div class="csf-step" data-step="2">
    <h2>Collaboration Terms</h2>
    <p class="csf-subtitle">Please review and agree to the terms below</p>
    <div class="csf-terms-box">{COLLAB_TERMS}</div>
    <div class="csf-field">
      <label class="csf-toggle-label">
        <input type="checkbox" id="csf-agree" required>
        <span>I agree to the collaboration terms *</span>
      </label>
    </div>
    <div class="csf-btn-row">
      <button type="button" class="csf-btn csf-btn-secondary" data-go="1">Back</button>
      <button type="button" class="csf-btn csf-btn-primary" id="csf-submit-btn">Submit Sample Request</button>
    </div>
  </div>

  <!-- Success -->
  <div class="csf-step csf-success" data-step="success">
    <h2>Sample request submitted!</h2>
    <p>We'll prepare your samples and send a shipping confirmation to your email.<br>Thank you for being an Onzenna Creator!</p>
  </div>
</div>

<script>
(function() {{
  "use strict";

  const WEBHOOK_URL = "{webhook_url}";
  const PRODUCTS = {products_js};
  const COLOR_HEX = {color_hex_js};
  let currentStep = 1;
  let selectedProducts = {{}};

  const urlParams = new URLSearchParams(window.location.search);
  const urlEmail = urlParams.get("email") || "";
  const urlCid = urlParams.get("cid") || "";
  const urlAge = urlParams.get("age") || "";  // YYYY-MM-DD format (baby birth date)

  // ── Age Calculation ─────────────────────────────────
  function calcAgeMonths(dateStr) {{
    if (!dateStr) return null;
    const bd = new Date(dateStr);
    if (isNaN(bd.getTime())) return null;
    const now = new Date();
    if (bd > now) return -1;
    return (now.getFullYear() - bd.getFullYear()) * 12 + (now.getMonth() - bd.getMonth());
  }}

  function ageLabel(months) {{
    if (months === null) return "";
    if (months < 0) return '<span class="csf-age-badge expecting">Expecting</span>';
    if (months < 12) return '<span class="csf-age-badge">' + months + ' months old</span>';
    const y = Math.floor(months / 12);
    const m = months % 12;
    return '<span class="csf-age-badge">' + y + (y===1?" year":" years") + (m > 0 ? " " + m + " mo" : "") + '</span>';
  }}

  // ── Product Visibility ───────────────────────────────
  function getAgeMonths() {{
    if (!urlAge) return null;
    return calcAgeMonths(urlAge);
  }}

  function getVisibleProducts() {{
    const ageMonths = getAgeMonths();
    const visible = {{}};
    for (const [key, p] of Object.entries(PRODUCTS)) {{
      if (p.optional) {{ visible[key] = p; continue; }}
      if (ageMonths === null) {{ visible[key] = p; continue; }}
      const eff = ageMonths < 0 ? 0 : ageMonths;
      if (eff >= p.ageMin && eff < p.ageMax) visible[key] = p;
    }}
    return visible;
  }}

  // ── Product Rendering ────────────────────────────────
  function renderProducts() {{
    const grid = document.getElementById("csf-products");
    const visible = getVisibleProducts();
    grid.innerHTML = "";

    const ageMonths = getAgeMonths();
    const ageEl = document.getElementById("csf-age-display");
    if (ageMonths !== null && ageEl) ageEl.innerHTML = ageLabel(ageMonths);

    if (Object.keys(visible).length === 0) {{
      grid.innerHTML = '<div class="csf-no-products">No products available for this age range.</div>';
      return;
    }}

    for (const k of Object.keys(selectedProducts)) {{
      if (!visible[k]) delete selectedProducts[k];
    }}

    for (const [key, p] of Object.entries(visible)) {{
      const card = document.createElement("div");
      card.className = "csf-product-card" + (selectedProducts[key] ? " selected" : "");
      card.dataset.key = key;

      let colorHtml = "";
      if (p.colors && p.colors.length > 0) {{
        const selColor = selectedProducts[key] ? selectedProducts[key].color : "";
        const swatches = p.colors.map(c => {{
          const hex = COLOR_HEX[c] || "#ccc";
          const active = c === selColor ? " active" : "";
          return '<span class="csf-swatch' + active + '" data-key="' + key + '" data-color="' + c + '">' +
            '<span class="csf-swatch-dot" style="background:' + hex + '"></span>' + c + '</span>';
        }}).join("");
        colorHtml = '<div class="csf-swatch-row">' + swatches + '</div>';
      }}

      card.innerHTML =
        (p.optional ? '<div class="csf-optional-badge">Optional</div>' : '') +
        '<img src="' + p.image + '" alt="' + p.title + '" loading="lazy">' +
        '<div class="csf-card-title">' + p.title + '</div>' +
        (p.subtitle ? '<div class="csf-card-subtitle">' + p.subtitle + '</div>' : '') +
        '<div class="csf-card-price">' + p.price + '</div>' +
        colorHtml +
        '<button type="button" class="csf-select-btn" data-key="' + key + '">' +
        (selectedProducts[key] ? '&#10003; Selected' : 'Select') + '</button>';

      grid.appendChild(card);
    }}

    grid.querySelectorAll(".csf-swatch").forEach(sw => {{
      sw.addEventListener("click", function(e) {{
        e.stopPropagation();
        const k = this.dataset.key;
        const c = this.dataset.color;
        const card = this.closest(".csf-product-card");
        card.querySelectorAll(".csf-swatch").forEach(s => s.classList.remove("active"));
        this.classList.add("active");
        const imgMap = PRODUCTS[k].imageMap || {{}};
        if (imgMap[c]) card.querySelector("img").src = imgMap[c];
        if (selectedProducts[k]) {{
          selectedProducts[k].color = c;
          selectedProducts[k].variantId = PRODUCTS[k].variantMap[c] || null;
        }}
      }});
    }});

    grid.querySelectorAll(".csf-select-btn").forEach(btn => {{
      btn.addEventListener("click", function(e) {{
        e.stopPropagation();
        toggleProduct(this.dataset.key);
      }});
    }});

    grid.querySelectorAll(".csf-product-card").forEach(card => {{
      card.addEventListener("click", function(e) {{
        if (e.target.closest(".csf-swatch") || e.target.tagName === "BUTTON") return;
        toggleProduct(this.dataset.key);
      }});
    }});
  }}

  function toggleProduct(key) {{
    if (selectedProducts[key]) {{
      delete selectedProducts[key];
    }} else {{
      const p = PRODUCTS[key];
      const activeSwatch = document.querySelector('.csf-swatch.active[data-key="' + key + '"]');
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

  // ── Step Navigation ───────────────────────────────────
  function goToStep(n) {{
    if (n > currentStep && !validateStep(currentStep)) return;
    if (n === 1) renderProducts();

    document.querySelectorAll(".csf-step").forEach(s => s.classList.remove("active"));
    const target = document.querySelector('.csf-step[data-step="' + n + '"]');
    if (target) target.classList.add("active");

    document.querySelectorAll(".csf-progress-step").forEach(bar => {{
      const barStep = parseInt(bar.dataset.for);
      bar.classList.toggle("done", barStep < n);
      bar.classList.toggle("active", barStep === n);
    }});

    currentStep = n;
    window.scrollTo({{ top: 0, behavior: "smooth" }});
  }}

  // ── Validation ────────────────────────────────────────
  function validateStep(step) {{
    if (step === 1) {{
      const nonOptional = Object.entries(selectedProducts).filter(([k]) => !PRODUCTS[k].optional);
      if (nonOptional.length === 0) {{
        alert("Please select at least one product.");
        return false;
      }}
      for (const [k, sp] of Object.entries(selectedProducts)) {{
        if (PRODUCTS[k].colors.length > 0 && !sp.color) {{
          alert('Please choose a color for "' + sp.title + '".');
          return false;
        }}
      }}
    }}
    if (step === 2) {{
      if (!document.getElementById("csf-agree").checked) {{
        alert("Please agree to the collaboration terms.");
        return false;
      }}
    }}
    return true;
  }}

  // ── Submit ────────────────────────────────────────────
  function submit() {{
    if (!validateStep(2)) return;

    const btn = document.getElementById("csf-submit-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="csf-spinner"></span>Submitting...';

    const payload = {{
      form_type: "creator_sample_request",
      submitted_at: new Date().toISOString(),
      email: urlEmail,
      customer_id: urlCid,
      baby_birth_date: urlAge,
      selected_products: Object.values(selectedProducts).map(sp => ({{
        product_key: sp.productKey,
        product_id: sp.productId,
        variant_id: sp.variantId,
        title: sp.title,
        color: sp.color || "Default",
        price: sp.price,
      }})),
      terms_accepted: true,
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
      btn.innerHTML = "Submit Sample Request";
    }});
  }}

  // ── Init ──────────────────────────────────────────────
  document.querySelectorAll("[data-go]").forEach(btn => {{
    btn.addEventListener("click", () => goToStep(parseInt(btn.dataset.go)));
  }});
  document.getElementById("csf-submit-btn").addEventListener("click", submit);

  renderProducts();
}})();
</script>

{{% schema %}}
{{
  "name": "Creator Sample Form",
  "settings": []
}}
{{% endschema %}}'''


def build_template_json():
    return json.dumps({
        "sections": {
            "creator-sample-form": {
                "type": "creator-sample-form",
                "settings": {}
            }
        },
        "order": ["creator-sample-form"]
    }, indent=2)


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    import argparse
    parser = argparse.ArgumentParser(description="Deploy Creator Sample Form page")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Deploy: {PAGE_TITLE}")
    print(f"  Shop: {SHOP}")
    print(f"  Webhook: {N8N_WEBHOOK_URL}")
    print(f"{'=' * 60}\n")

    liquid = build_section_liquid(N8N_WEBHOOK_URL)
    template = build_template_json()

    if args.dry_run:
        print("[DRY RUN] Liquid section preview (first 500 chars):")
        print(liquid[:500])
        print("...")
        return

    if args.rollback:
        theme_id = get_active_theme_id()
        try:
            shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={SECTION_KEY}")
            print(f"  [OK] Deleted {SECTION_KEY}")
        except Exception as e:
            print(f"  [WARN] {e}")
        try:
            shopify_request("DELETE", f"/themes/{theme_id}/assets.json?asset[key]={TEMPLATE_KEY}")
            print(f"  [OK] Deleted {TEMPLATE_KEY}")
        except Exception as e:
            print(f"  [WARN] {e}")
        return

    theme_id = get_active_theme_id()
    upload_theme_asset(theme_id, SECTION_KEY, liquid)
    upload_theme_asset(theme_id, TEMPLATE_KEY, template)
    create_or_update_page(PAGE_HANDLE, PAGE_TITLE, "creator-sample-form")

    print(f"\n  Page URL: https://onzenna.com/pages/{PAGE_HANDLE}")
    print(f"  Email link format:")
    print(f"    https://onzenna.com/pages/{PAGE_HANDLE}?email=EMAIL&cid=CID&age=YYYY-MM-DD")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
