import json

with open('.tmp/meta_ads_payload_20260301.json', encoding='utf-8') as f:
    raw = json.load(f)
p = raw.get('payload', raw)

print('=== brand_breakdown_30d ===')
for b in p.get('brand_breakdown_30d', []):
    print(f'  {b["brand"]}: ${b["spend"]:.0f}')

print('\n=== Yesterday by_brand ===')
ys = p.get('yesterday_spend', {})
print(f'  Total: ${ys.get("total",0):.0f}')
for b in ys.get('by_brand', []):
    pct = round(b["spend"] / ys["total"] * 100) if ys.get("total") else 0
    print(f'  {b["brand"]}: ${b["spend"]:.0f} ({pct}%)')

print('\n=== Remaining Non-classified top performers ===')
for t in p.get('top_performers', []):
    brand = t.get("brand","?")
    if brand == 'Non-classified':
        camp = t.get("campaign_name","")[:65].encode('ascii','replace').decode()
        ad   = t.get("ad_name","")[:50].encode('ascii','replace').decode()
        print(f'  CAMP: {camp}')
        print(f'  AD:   {ad}')
        print()
