"""
Generate deep Naeiae PPC proposal email from search term analysis.
Usage: python tools/generate_naeiae_deep_proposal.py
"""
import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from env_loader import load_env
load_env()

import anthropic
from datetime import date

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR  = os.path.dirname(TOOLS_DIR)
DEEP_PATH = os.path.join(ROOT_DIR, '.tmp', 'naeiae_deep_20260308.json')
OUTPUT    = os.path.join(ROOT_DIR, '.tmp', 'naeiae_deep_proposal.html')

with open(DEEP_PATH, encoding='utf-8') as f:
    d = json.load(f)

st_top = d['search_terms_top50'][:20]
st_zero = d['search_terms_zero_sales']
st_harvest = d['search_terms_harvest_candidates']

# Build compact data for prompt
top_str = "\n".join(
    f"  {'[GREEN]' if s['roas']>=3 else '[ORANGE]' if s['roas']>=2 else '[RED]  '} "
    f"'{s['searchTerm']}' spend=${s['spend']:.2f} sales=${s['sales']:.2f} "
    f"ROAS={s['roas']:.2f} clicks={s['clicks']} orders={s['purchases']}"
    for s in st_top
)
zero_str = "\n".join(
    f"  '{s['searchTerm']}' spend=${s['spend']:.2f} clicks={s['clicks']}"
    for s in st_zero
)
harvest_str = "\n".join(
    f"  '{s['searchTerm']}' spend=${s['spend']:.2f} ACOS={s['acos']*100:.1f}% orders={s['purchases']} ROAS={s['roas']:.2f}"
    for s in st_harvest
)

prompt = f"""You are a senior Amazon PPC specialist. Generate a detailed, actionable execution proposal for Fleeters Inc (brand: Naeiae), based on REAL 14-day search term data.

=== CAMPAIGN CONTEXT (2026-03-06) ===
Brand Summary (Naeiae, 7d):
- 7d: spend=$676.81, sales=$1,648, ROAS=2.44, ACOS=41%
- 30d: spend=$2,554, sales=$6,470, ROAS=2.53
- Target: ROAS 3.0+ / ACOS <25%

Campaign A (ID 444108265805305): ROAS 7d=2.56 (IMPROVING, 30d was 2.26), budget ~$45/day
Campaign B (ID 365330679770972): ROAS 7d=2.32 (DECLINING, 30d was 2.84), yesterday ROAS=1.84, budget ~$51/day

=== SEARCH TERM DATA (14 days, Feb 21 ~ Mar 6) ===
TOP 20 BY SPEND:
{top_str}

ZERO SALES (wasted spend):
{zero_str}

HARVEST CANDIDATES (ACOS<25%, 1+ orders):
{harvest_str}

=== KEY OBSERVATIONS ===
1. ASIN "b0bmjcwyb6" = 55% of total spend ($434/14d), ROAS only 2.15 — likely an auto campaign hitting a competitor ASIN
2. "puffed rice" ROAS 0.78, "toddler snacks" ROAS 0.93 — near zero, need bid cuts
3. "yugwa korean rice puff snack" + "baby snacks" = $52.67 total, 0 sales — pure waste
4. Korean term "떡뻥" ROAS 13.10 with 7 orders — untapped branded term in auto, needs exact match harvest
5. "pop rice snack" and variants performing well (ROAS 5-10) — needs own exact match ad group

=== EXECUTION FRAMEWORK ===
ROAS Rules:
- <1.0: pause/reduce -30%
- 1.0-1.5: reduce_bid -30% (urgent)
- 1.5-2.0: reduce_bid -15% (high)
- 2.0-3.0: monitor
- 3.0-5.0: budget +20% (medium)
- >5.0: bid +10%, budget +30% (high)

Budget cap: $120/day total, $50/campaign max, $3.00 bid max

=== YOUR TASK ===
Generate Outlook-compatible HTML email with SPECIFIC execution proposals:

SECTION 1: Executive Summary (3 bullets)

SECTION 2: Campaign Health Table
- Campaign A vs B: yd/7d/30d ROAS, trend, status, recommended action

SECTION 3: AUTO CAMPAIGN Optimization
- ASIN b0bmjcwyb6: what to do (reduce bid? add as negative? % change?)
- "puffed rice", "toddler snacks": bid reduction % (they're in reduce_bid territory)
- Why auto campaigns need looser targets but still need guardrails
- Recommended auto budget % of total

SECTION 4: MANUAL CAMPAIGN Optimization
- Negative keywords to add NOW (from zero_sales list)
- Why each is a negative candidate
- "yugwa korean rice puff snack" — branded competitor term, should be negative
- "baby snacks", "rice puffs", "teether crackers", "low calorie snacks" — too generic or wrong intent

SECTION 5: Keyword Harvest (Add to Exact Match)
For each harvest candidate, specify:
- Recommended starting bid = (spend/clicks) * 1.1 — calculate this
- Which campaign type to add to (new exact match ad group or existing manual)
- Expected impact on ROAS
Priority: 떡뻥, pop rice snack, pop rice snack baby, baby teething snacks, naeiae pop rice snack

SECTION 6: Budget Reallocation
- Current: Campaign A ~$45/day, Campaign B ~$51/day
- Proposed shift based on ROAS trends
- Total daily budget recommendation

SECTION 7: Expected Impact
- Estimated ROAS improvement range after changes
- Estimated wasted spend recovered per day

CRITICAL HTML RULES (Outlook 2016+):
- ONLY table-based layout (no div with flex/grid/display)
- ALL styles INLINE (no <style> block at all)
- No: box-shadow, linear-gradient, border-radius on tables
- Use bgcolor="#RRGGBB" on <td> for backgrounds
- Max width 620px wrapper table
- Color codes: green=#006100, red=#9C0006, orange=#9C5700, header_bg=#1F3864, row_alt=#F2F2F2
- Tables with border="0" cellpadding="6" cellspacing="0"

Be specific with numbers. Show the math. Korean labels OK."""

print("[1/3] Calling Claude API (deep analysis)...")
client = anthropic.Anthropic()
msg = client.messages.create(
    model='claude-sonnet-4-6',
    max_tokens=5000,
    messages=[{'role': 'user', 'content': prompt}]
)
html_body = msg.content[0].text.strip()
if html_body.startswith('```'):
    html_body = html_body.split('\n', 1)[1] if '\n' in html_body else html_body
    if html_body.endswith('```'):
        html_body = html_body[:-3].strip()

print("[2/3] Saving HTML...")
with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html_body)
print(f"  Saved: {OUTPUT}")

print("[3/3] Sending email...")
recipient = os.getenv('PPC_REPORT_RECIPIENT', 'wj.choi@orbiters.co.kr')
subject = "[Naeiae PPC] Deep Execution Proposal - 2026-03-06 | Search Term Analysis | 13 Harvest + 5 Negatives"
env = os.environ.copy()
env['GMAIL_OAUTH_CREDENTIALS_PATH'] = os.path.join(ROOT_DIR, 'credentials', 'gmail_oauth_credentials.json')
env['ZEZEBAEBAE_GMAIL_TOKEN_PATH']   = os.path.join(ROOT_DIR, 'credentials', 'gmail_token.json')
result = subprocess.run(
    [sys.executable, '-u', os.path.join(TOOLS_DIR, 'send_gmail.py'),
     '--to', recipient, '--subject', subject, '--body-file', OUTPUT],
    cwd=ROOT_DIR, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env
)
if result.returncode == 0:
    print(f"  Sent to {recipient}")
else:
    print(f"  FAIL: {result.stdout} {result.stderr}")
print("[Done]")
