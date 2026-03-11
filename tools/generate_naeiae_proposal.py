"""
Generate Fleeters Inc (Naeiae) PPC execution proposal email.
Usage: python tools/generate_naeiae_proposal.py
"""
import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from env_loader import load_env
load_env()

import anthropic

PAYLOAD_PATH = os.path.join(os.path.dirname(__file__), '..', '.tmp', 'ppc_payload_20260306.json')
OUTPUT_PATH  = os.path.join(os.path.dirname(__file__), '..', '.tmp', 'naeiae_proposal_email.html')

with open(PAYLOAD_PATH, encoding='utf-8') as f:
    payload = json.load(f)

prompt = """You are a senior Amazon PPC specialist. Generate a detailed execution proposal email for Fleeters Inc (brand: Naeiae).

PERFORMANCE DATA (2026-03-06):

Brand Summary (Naeiae):
- 7d total: spend=$676.81, sales=$1,648.20, ROAS=2.44, ACOS=41%
- 30d total: spend=$2,553.95, sales=$6,469.80, ROAS=2.53, ACOS=39%
- Target ROAS: 3.0+ | Target ACOS: <25%

Campaign A (ID: 444108265805305):
- Yesterday: spend=$45.25, ROAS=2.17, ACOS=46%
- 7d: spend=$316/wk (~$45/day), ROAS=2.56, ACOS=39%, CVR=11.87%, CPC=$1.14, clicks=278
- 30d: spend=$1,361/mo, ROAS=2.26, ACOS=44%, CVR=11.03%, CPC=$1.22
- Trend: IMPROVING (ROAS 2.26->2.56, CVR 11.03->11.87%, CPC dropping)

Campaign B (ID: 365330679770972):
- Yesterday: spend=$40.13, ROAS=1.84, ACOS=54%
- 7d: spend=$360/wk (~$51/day), ROAS=2.32, ACOS=43%, CVR=7.44%, CPC=$0.79, clicks=457
- 30d: spend=$1,193/mo, ROAS=2.84, ACOS=35%, CVR=8.73%, CPC=$0.78
- Trend: DECLINING (ROAS 2.84->2.32->1.84yd, CVR 8.73->7.44%)

ROAS Decision Framework:
- 1.5-2.0: reduce_bid -15% (high priority)
- 2.0-3.0: monitor
- Drop rule: if yesterday ROAS drops 30%+ vs 7d -> additional -20% bid
- Campaign B yesterday (1.84) is in reduce_bid -15% territory

Budget constraints: $120/day total, $50/campaign max, $3.00 bid max

USER NOTE: Believes there is significant room for improvement in daily budget allocation and manual campaign optimization.

Generate HTML email with:
1. Executive Summary (2-3 lines)
2. Campaign Diagnosis table (yd/7d/30d ROAS, trend arrow, status)
3. Specific Execution Proposals - exact actions with numbers:
   - Bid adjustments (% and estimated new bid range)
   - Budget reallocation ($amount)
   - Priority: urgent / high / medium
4. Expected Impact (ROAS/spend improvement estimate)
5. Missing Data needed to go deeper (keyword-level, search terms)

CRITICAL HTML REQUIREMENTS (Outlook compatibility):
- Use ONLY table-based layout (no div with flex/grid)
- All styles must be INLINE (no <style> block, no external CSS)
- No CSS properties: flex, grid, box-shadow, linear-gradient, border-radius on tables
- Use bgcolor attribute on <td> for background colors
- Use <font> or inline style="color:..." for text colors
- Use <table width="100%" cellpadding="0" cellspacing="0" border="0"> structure
- Color coding inline: style="color:#006100" for green, style="color:#9C0006" for red, style="color:#9C5700" for orange
- Max width 600px wrapper table
- Simple, clean, readable in Outlook 2016+

Be direct and specific. No fluff. Korean OK for labels if helpful."""

print("[1/3] Calling Claude API...")
client = anthropic.Anthropic()
msg = client.messages.create(
    model='claude-sonnet-4-6',
    max_tokens=3000,
    messages=[{'role': 'user', 'content': prompt}]
)
html_body = msg.content[0].text.strip()
# Strip markdown code fences if present
if html_body.startswith('```'):
    html_body = html_body.split('\n', 1)[1] if '\n' in html_body else html_body
    if html_body.endswith('```'):
        html_body = html_body[:-3].strip()
print("[2/3] Saving HTML...")
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html_body)
print(f"  Saved: {OUTPUT_PATH}")

print("[3/3] Sending email...")
recipient = os.getenv('PPC_REPORT_RECIPIENT', 'wj.choi@orbiters.co.kr')
subject = "[Naeiae PPC] Execution Proposal - 2026-03-06 | ROAS 2.44x | Action Required"
tools_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(tools_dir)
env = os.environ.copy()
env['GMAIL_OAUTH_CREDENTIALS_PATH'] = os.path.join(root_dir, 'credentials', 'gmail_oauth_credentials.json')
env['GMAIL_TOKEN_PATH'] = os.path.join(root_dir, 'credentials', 'gmail_token.json')
result = subprocess.run(
    [sys.executable, '-u', os.path.join(tools_dir, 'send_gmail.py'),
     '--to', recipient, '--subject', subject, '--body-file', OUTPUT_PATH],
    cwd=root_dir, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env
)
if result.returncode == 0:
    print(f"  Sent to {recipient}")
else:
    print(f"  Send result: {result.stdout} {result.stderr}")
print("[Done]")
