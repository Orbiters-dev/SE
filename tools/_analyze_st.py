import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('.tmp/naeiae_deep_20260308.json', encoding='utf-8') as f:
    d = json.load(f)

st = d['search_terms_top50']
zero = d['search_terms_zero_sales']
harvest = d['search_terms_harvest_candidates']

print(f'Total ST top50: {len(st)}, zero_sales: {len(zero)}, harvest: {len(harvest)}')
print()
print('=== TOP 20 BY SPEND ===')
for s in st[:20]:
    roas = s['roas']
    flag = 'GREEN' if roas>=3 else ('ORANGE' if roas>=2 else 'RED  ')
    print(f'{flag} | {s["searchTerm"][:40]:<40} | spend=${s["spend"]:>6.2f} | sales=${s["sales"]:>7.2f} | roas={roas:>5.2f} | clicks={s["clicks"]:>4} | orders={s["purchases"]:>3}')

print()
print('=== ZERO SALES (WASTED SPEND top15) ===')
for s in zero[:15]:
    print(f'  {s["searchTerm"][:45]:<45} | spend=${s["spend"]:>6.2f} | clicks={s["clicks"]:>3}')

print()
print('=== HARVEST CANDIDATES (ACOS<25%, orders>=1) ===')
for s in harvest[:10]:
    print(f'  {s["searchTerm"][:45]:<45} | spend=${s["spend"]:>6.2f} | acos={s["acos"]*100:.1f}% | orders={s["purchases"]}')

# Summary stats
total_spend = sum(s["spend"] for s in st)
total_sales = sum(s["sales"] for s in st)
wasted = sum(s["spend"] for s in zero)
print(f'\nTop50 summary: spend=${total_spend:.2f}, sales=${total_sales:.2f}, roas={total_sales/max(total_spend,1):.2f}')
print(f'Wasted spend (zero sales >$5): ${wasted:.2f}')
print(f'Harvest candidates: {len(harvest)} terms')
