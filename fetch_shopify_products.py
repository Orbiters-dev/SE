import os
import json
import urllib.request

# Shopify API credentials
shop = "mytoddie.myshopify.com"
token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
api_version = "2024-01"

# Fetch products
url = f"https://{shop}/admin/api/{api_version}/products.json?limit=250"
headers = {"X-Shopify-Access-Token": token}

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode('utf-8'))

products = data.get('products', [])

# Find target products
targets = {}

for product in products:
    title = product.get('title', '')
    title_lower = title.lower()
    
    # PPSU Straw Cup with Flip Top & Weight - 10oz (300ml)
    if 'ppsu straw cup with flip top' in title_lower and 'weight' in title_lower and '300ml' in title:
        targets['ppsu_300ml'] = product
    
    # PPSU Straw Cup with Flip Top & Weight - 6oz (200ml)
    elif 'ppsu straw cup with flip top' in title_lower and 'weight' in title_lower and '200ml' in title:
        targets['ppsu_200ml'] = product
    
    # Stainless Steel Tumbler or PPSU Tumbler
    elif ('stainless steel tumbler' in title_lower) or ('ppsu' in title_lower and 'tumbler' in title_lower and '10oz' in title):
        targets['tumbler'] = product

# Output results
for key in sorted(targets.keys()):
    product = targets[key]
    print(f"\n{'='*120}")
    print(f"PRODUCT KEY: {key.upper()}")
    print(f"Title: {product['title']}")
    print(f"Product ID: {product['id']}")
    print(f"Handle: {product['handle']}")
    print(f"\nVariants ({len(product['variants'])} total):")
    
    for v in product['variants']:
        opts = [o for o in [v.get('option1'), v.get('option2'), v.get('option3')] if o]
        opts_str = ', '.join(opts) if opts else 'No options'
        print(f"  ID: {v['id']} | {v['title']} | Options: {opts_str} | Price: ${v['price']} | SKU: {v.get('sku')}")
    
    print(f"\nImages ({len(product['images'])} total):")
    for i, img in enumerate(product['images'][:3]):
        print(f"  [{i+1}] {img['src']}")

print(f"\n{'='*120}")
