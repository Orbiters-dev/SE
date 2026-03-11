"""
Typeform Influencer Gifting Form 생성 도구 v2
- 연령대별 Grosmimi 제품 자동 분기 (Logic Jump)
- 제품 이미지 첨부 (attachment)
- CHA&MOM 번들 옵션 (Optional)
- 실행 시 폼 URL 출력
"""

import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

TYPEFORM_API_KEY = os.getenv("TYPEFORM_API_KEY")
TYPEFORM_API_BASE = "https://api.typeform.com"

# ── 제품 정보 (Shopify 기준) ───────────────────────────────────
PRODUCTS = {
    "ppsu_bottle": {
        "title": "Grosmimi PPSU Baby Bottle 10oz",
        "shopify_product_id": 8288604815682,
        "price": "$19.60",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-ppsu-baby-bottle-10oz-300ml-5542196.jpg",
        "colors": [
            "Creamy Blue", "Rose Coral", "Olive White", "Bear Pure Gold",
            "Bear White", "Cherry Pure Gold", "Cherry Rose Gold",
        ],
        "variant_map": {
            "Creamy Blue": 51854035059058,
            "Rose Coral": 51854035091826,
            "Olive White": 45019086586178,
            "Bear Pure Gold": 45019086618946,
            "Bear White": 45019086651714,
            "Cherry Pure Gold": 45019086684482,
            "Cherry Rose Gold": 45019086717250,
        },
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
            "Peach": 45373972545858,
            "Skyblue": 45018985595202,
            "White": 45018985431362,
            "Aquagreen": 45018985529666,
            "Pink": 45018985562434,
            "Beige": 45018985464130,
            "Charcoal": 45018985496898,
            "Butter": 45373972513090,
        },
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
            "Flower Coral": 51660007342450,
            "Air Balloon Blue": 51660005867890,
            "Cherry Peach": 47142838042946,
            "Olive Pistachio": 47142887981378,
            "Bear Butter": 47142838010178,
        },
    },
    "ss_tumbler": {
        "title": "Grosmimi Stainless Steel Tumbler 10oz",
        "shopify_product_id": 14761459941746,
        "price": "$49.80",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/grosmimi-stainless-steel-tumbler-10oz-300ml-5123735.png",
        "colors": ["Cherry Peach", "Bear Butter", "Olive Pistachio"],
        "variant_map": {
            "Cherry Peach": 52505654854002,
            "Bear Butter": 52505654886770,
            "Olive Pistachio": 52505654919538,
        },
    },
    "chamom_duo": {
        "title": "CHA&MOM Essential Duo Bundle",
        "subtitle": "Lotion + Body Wash",
        "shopify_product_id": 14643954647410,
        "price": "$46.92",
        "image_url": "https://cdn.shopify.com/s/files/1/0738/7876/5890/files/chamom-essential-duo-bundle-2229420.jpg",
        "colors": [],
        "variant_map": {"Default": 51692427510130},
    },
}

# ── Collaboration Terms ────────────────────────────────────────
COLLAB_TERMS = (
    "By submitting this form, you agree to the following:\n\n"
    "- Total video length: 30 seconds\n"
    "- Uploaded content must include voiceover + subtitles\n"
    "- Must use royalty-free music\n"
    "- Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG & TikTok)\n"
    "- Must include: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna"
)


# ── Typeform API Helpers ───────────────────────────────────────
def typeform_request(method, path, data=None):
    """Typeform API 호출"""
    url = f"{TYPEFORM_API_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {TYPEFORM_API_KEY}")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def upload_image_to_typeform(image_url, file_name="product.png"):
    """외부 이미지 URL → Typeform CDN 업로드 → Typeform 이미지 URL 반환"""
    import base64
    print(f"    Uploading: {file_name} ...")

    # Download image
    dl_req = urllib.request.Request(image_url)
    dl_req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(dl_req, timeout=15) as resp:
        image_data = resp.read()

    # Upload as base64 JSON (Typeform's working format)
    b64_data = base64.b64encode(image_data).decode("ascii")
    upload_payload = json.dumps({
        "image": b64_data,
        "file_name": file_name,
    }).encode("utf-8")

    upload_url = f"{TYPEFORM_API_BASE}/images"
    req = urllib.request.Request(upload_url, data=upload_payload, method="POST")
    req.add_header("Authorization", f"Bearer {TYPEFORM_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        typeform_url = result["src"]
        print(f"    [OK] → {typeform_url}")
        return typeform_url
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"    [WARN] Image upload failed: {e.code} {error_body[:200]}")
        return None


def upload_all_product_images():
    """모든 제품 이미지를 Typeform CDN에 업로드하고 URL 매핑 반환"""
    print("\n  제품 이미지 Typeform CDN 업로드 중...")
    image_map = {}
    for key, product in PRODUCTS.items():
        url = product.get("image_url")
        if not url:
            continue
        ext = "png" if ".png" in url else "jpg"
        tf_url = upload_image_to_typeform(url, f"{key}.{ext}")
        if tf_url:
            image_map[key] = tf_url
    print(f"  [OK] {len(image_map)}/{len(PRODUCTS)}개 이미지 업로드 완료\n")
    return image_map


def build_form_payload(title="Grosmimi Gifting Application", image_map=None):
    """연령대별 Logic Jump이 포함된 Typeform 폼 페이로드 생성"""
    image_map = image_map or {}
    fields = []
    logic = []

    # ── 1. Personal Info ──────────────────────────────────────
    fields.append({
        "ref": "full_name",
        "type": "short_text",
        "title": "What is your full name?",
        "validations": {"required": True},
    })
    fields.append({
        "ref": "email",
        "type": "email",
        "title": "What is your email address?",
        "validations": {"required": True},
    })
    fields.append({
        "ref": "phone",
        "type": "phone_number",
        "title": "What is your phone number?",
        "validations": {"required": True},
        "properties": {"default_country_code": "US"},
    })
    fields.append({
        "ref": "instagram",
        "type": "short_text",
        "title": "What is your Instagram handle?",
        "validations": {"required": False},
        "properties": {
            "description": "e.g. @yourusername \u2014 Type 'None' if not applicable",
        },
    })
    fields.append({
        "ref": "tiktok",
        "type": "short_text",
        "title": "What is your TikTok handle?",
        "validations": {"required": False},
        "properties": {
            "description": "e.g. @yourusername \u2014 Type 'None' if not applicable",
        },
    })

    # ── 2. Baby Info ──────────────────────────────────────────
    fields.append({
        "ref": "baby_birthday",
        "type": "date",
        "title": "What is your baby's birthday or expected due date?",
        "validations": {"required": True},
        "properties": {
            "description": "If expecting, please enter the expected due date.",
        },
    })
    fields.append({
        "ref": "age_range",
        "type": "multiple_choice",
        "title": "What is your baby's current age range?",
        "validations": {"required": True},
        "properties": {
            "allow_multiple_selection": False,
            "choices": [
                {"ref": "expecting_under_6mo", "label": "Expecting / Under 6 months"},
                {"ref": "age_6_18mo", "label": "6 - 18 months"},
                {"ref": "age_18_36mo", "label": "18 - 36 months"},
                {"ref": "age_36_48mo", "label": "36 - 48 months"},
            ],
        },
    })

    # ── 3. Product Selection (age-based) ──────────────────────

    # 3a. Baby Bottle (Expecting / Under 6 months)
    bottle = PRODUCTS["ppsu_bottle"]
    bottle_field = {
        "ref": "bottle_color",
        "type": "dropdown",
        "title": f"Choose your {bottle['title']} color ({bottle['price']}):",
        "validations": {"required": False},
        "properties": {
            "alphabetical_order": False,
            "choices": [{"label": c} for c in bottle["colors"]],
        },
    }
    if "ppsu_bottle" in image_map:
        bottle_field["attachment"] = {"type": "image", "href": image_map["ppsu_bottle"]}
    fields.append(bottle_field)

    # 3b. Straw Cup type selection (6-18 months)
    fields.append({
        "ref": "straw_type",
        "type": "multiple_choice",
        "title": "Which straw cup would you like?",
        "validations": {"required": True},
        "properties": {
            "allow_multiple_selection": False,
            "choices": [
                {"ref": "ppsu_only", "label": "PPSU Straw Cup ($24.90)"},
                {"ref": "ss_only", "label": "Stainless Steel Straw Cup ($46.80)"},
                {"ref": "both_cups", "label": "Both"},
            ],
        },
    })

    # 3c. PPSU Straw Cup color
    ppsu = PRODUCTS["ppsu_straw"]
    ppsu_field = {
        "ref": "ppsu_straw_color",
        "type": "dropdown",
        "title": f"Choose your {ppsu['title']} color ({ppsu['price']}):",
        "validations": {"required": False},
        "properties": {
            "alphabetical_order": False,
            "choices": [{"label": c} for c in ppsu["colors"]],
        },
    }
    if "ppsu_straw" in image_map:
        ppsu_field["attachment"] = {"type": "image", "href": image_map["ppsu_straw"]}
    fields.append(ppsu_field)

    # 3d. SS Straw Cup color
    ss_straw = PRODUCTS["ss_straw"]
    ss_field = {
        "ref": "ss_straw_color",
        "type": "dropdown",
        "title": f"Choose your {ss_straw['title']} color ({ss_straw['price']}):",
        "validations": {"required": False},
        "properties": {
            "alphabetical_order": False,
            "choices": [{"label": c} for c in ss_straw["colors"]],
        },
    }
    if "ss_straw" in image_map:
        ss_field["attachment"] = {"type": "image", "href": image_map["ss_straw"]}
    fields.append(ss_field)

    # 3e. SS Tumbler color (18-36 months)
    tumbler = PRODUCTS["ss_tumbler"]
    tumbler_field = {
        "ref": "tumbler_color",
        "type": "dropdown",
        "title": f"Choose your {tumbler['title']} color ({tumbler['price']}):",
        "validations": {"required": False},
        "properties": {
            "alphabetical_order": False,
            "choices": [{"label": c} for c in tumbler["colors"]],
        },
    }
    if "ss_tumbler" in image_map:
        tumbler_field["attachment"] = {"type": "image", "href": image_map["ss_tumbler"]}
    fields.append(tumbler_field)

    # ── 4. CHA&MOM (Optional, all ages 0-48 months) ──────────
    chamom = PRODUCTS["chamom_duo"]
    chamom_field = {
        "ref": "chamom_yesno",
        "type": "yes_no",
        "title": f"Would you also like a {chamom['title']}? ({chamom['price']})",
        "validations": {"required": True},
        "properties": {
            "description": "Optional \u2014 Lotion + Body Wash bundle for babies 0-48 months.",
        },
    }
    if "chamom_duo" in image_map:
        chamom_field["attachment"] = {"type": "image", "href": image_map["chamom_duo"]}
    fields.append(chamom_field)

    # ── 5. Shipping Address ───────────────────────────────────
    fields.append({
        "ref": "address",
        "type": "long_text",
        "title": "What is your shipping address?",
        "validations": {"required": True},
        "properties": {
            "description": "Please include: Street, City, State, ZIP, Country",
        },
    })

    # ── 6. Collaboration Terms ────────────────────────────────
    fields.append({
        "ref": "terms",
        "type": "statement",
        "title": "Collaboration Terms",
        "properties": {
            "description": COLLAB_TERMS,
            "button_text": "I agree",
        },
    })

    # ── Logic Jumps ───────────────────────────────────────────

    # Age range → appropriate product
    logic.append({
        "type": "field",
        "ref": "age_range",
        "actions": [
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "bottle_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "age_range"},
                        {"type": "choice", "value": "expecting_under_6mo"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "straw_type"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "age_range"},
                        {"type": "choice", "value": "age_6_18mo"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "tumbler_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "age_range"},
                        {"type": "choice", "value": "age_18_36mo"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "chamom_yesno"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "age_range"},
                        {"type": "choice", "value": "age_36_48mo"},
                    ],
                },
            },
        ],
    })

    # Bottle color → skip to CHA&MOM
    logic.append({
        "type": "field",
        "ref": "bottle_color",
        "actions": [{
            "action": "jump",
            "details": {"to": {"type": "field", "value": "chamom_yesno"}},
            "condition": {"op": "always", "vars": []},
        }],
    })

    # Straw type → PPSU color or SS color
    logic.append({
        "type": "field",
        "ref": "straw_type",
        "actions": [
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "ppsu_straw_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "straw_type"},
                        {"type": "choice", "value": "ppsu_only"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "ss_straw_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "straw_type"},
                        {"type": "choice", "value": "ss_only"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "ppsu_straw_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "straw_type"},
                        {"type": "choice", "value": "both_cups"},
                    ],
                },
            },
        ],
    })

    # PPSU straw color → SS straw (if Both) or CHA&MOM
    logic.append({
        "type": "field",
        "ref": "ppsu_straw_color",
        "actions": [
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "ss_straw_color"}},
                "condition": {
                    "op": "is",
                    "vars": [
                        {"type": "field", "value": "straw_type"},
                        {"type": "choice", "value": "both_cups"},
                    ],
                },
            },
            {
                "action": "jump",
                "details": {"to": {"type": "field", "value": "chamom_yesno"}},
                "condition": {"op": "always", "vars": []},
            },
        ],
    })

    # SS straw color → CHA&MOM
    logic.append({
        "type": "field",
        "ref": "ss_straw_color",
        "actions": [{
            "action": "jump",
            "details": {"to": {"type": "field", "value": "chamom_yesno"}},
            "condition": {"op": "always", "vars": []},
        }],
    })

    # SS Tumbler color → CHA&MOM
    logic.append({
        "type": "field",
        "ref": "tumbler_color",
        "actions": [{
            "action": "jump",
            "details": {"to": {"type": "field", "value": "chamom_yesno"}},
            "condition": {"op": "always", "vars": []},
        }],
    })

    # ── Build Full Payload ────────────────────────────────────
    payload = {
        "title": title,
        "settings": {
            "language": "en",
            "is_public": True,
            "progress_bar": "percentage",
            "show_progress_bar": True,
        },
        "welcome_screens": [
            {
                "ref": "welcome",
                "title": title,
                "properties": {
                    "description": (
                        "Thank you for your interest in collaborating with us! "
                        "Please fill out this form to request your gifting samples."
                    ),
                    "button_text": "Start",
                },
            },
        ],
        "thankyou_screens": [
            {
                "ref": "thankyou",
                "title": "Thank you for your request!",
                "properties": {
                    "description": (
                        "We will review your request and get back to you shortly. "
                        "Keep an eye on your email!"
                    ),
                    "show_button": False,
                },
            },
        ],
        "fields": fields,
        "logic": logic,
    }

    return payload


def create_form(title="Grosmimi Gifting Application", webhook_url=None):
    """Typeform 폼 생성 → URL 반환"""
    print(f"\n=== Typeform Influencer Form v2 ===\n")
    print(f"  Title: {title}")

    # Upload product images to Typeform CDN
    image_map = upload_all_product_images()

    payload = build_form_payload(title, image_map=image_map)
    print(f"  Fields: {len(payload['fields'])}개")
    print(f"  Logic rules: {len(payload['logic'])}개")

    # Create form
    print(f"\n  Typeform API 호출 중...")
    result = typeform_request("POST", "/forms", payload)

    form_id = result["id"]
    form_url = result["_links"]["display"]
    print(f"\n  [OK] Form created!")
    print(f"  Form ID: {form_id}")
    print(f"  Form URL: {form_url}")

    # Register webhook if provided
    if webhook_url:
        print(f"\n  Webhook 등록 중: {webhook_url}")
        webhook_payload = {"url": webhook_url, "enabled": True}
        typeform_request("PUT", f"/forms/{form_id}/webhooks/n8n", webhook_payload)
        print(f"  [OK] Webhook registered!")

    print(f"\n{'='*60}")
    print(f"  Form URL: {form_url}")
    print(f"{'='*60}")

    return {"form_id": form_id, "form_url": form_url}


# ── Main ─────────────────────────────────────────────────────
def main():
    if not TYPEFORM_API_KEY:
        print("[ERROR] TYPEFORM_API_KEY not set in .env")
        return

    result = create_form(title="Grosmimi Gifting Application")

    # Save form info
    os.makedirs(".tmp/typeform", exist_ok=True)
    with open(".tmp/typeform/last_form.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Form info saved to .tmp/typeform/last_form.json")


if __name__ == "__main__":
    main()
