"""
3-Brand Parallel Outreach Pipeline Test
========================================
Tests the full outreach flow for Grosmimi, CHA&MOM, and Naeiae in parallel.
All Low Touch. HiL=on (drafts saved, not sent).

For each brand:
  1. Seed Creator + Content with brand-specific keywords
  2. Trigger Draft Generation via webhook
  3. Poll for AI-generated draft in Conversations table
  4. Log config, detected brand, email subject/body, form link
  5. Compare all 3 side by side
  6. Cleanup test data

Usage:
    python tools/test_outreach_brands.py               # Full test (3 brands)
    python tools/test_outreach_brands.py --no-cleanup   # Keep test data
    python tools/test_outreach_brands.py --dry-run      # Preview only
    python tools/test_outreach_brands.py --brand grosmimi  # Single brand

Output: .tmp/outreach_brand_test/report_YYYYMMDD_HHMMSS.html
"""

import os
import sys
import json
import time
import random
import string
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)
from env_loader import load_env
load_env()

# ─── Constants ────────────────────────────────────────────────────────────────
# Pathlight PROD base — the live Airtable connected to Pathlight
AT_BASE = "app3Vnmh7hLAVsevE"  # PROD (Orbiters Creator CRM)
AT_CREATORS = "tblv2Jw3ZAtAMhiYY"
AT_CONTENT = "tble4cuyVnXP4OvZR"
AT_CONVERSATIONS = "tblNeTyVwMomsfSk7"
AT_DAILY_CONFIG = "tbl6gGyLMvp57q1v7"

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")

DRAFT_GEN_WEBHOOK = f"{N8N_BASE_URL}/webhook/draft-gen"
DRAFT_GEN_WF_ID = "fwwOeLiDLSnR77E1"  # PROD Draft Generation

TEST_EMAIL_DOMAIN = "orbiters.co.kr"
TMP_DIR = os.path.join(ROOT, ".tmp", "outreach_brand_test")
os.makedirs(TMP_DIR, exist_ok=True)

# ─── Brand Test Configs ───────────────────────────────────────────────────────
BRAND_CONFIGS = {
    "Grosmimi": {
        "persona": "Sarah Kim",
        "bio": "Mom of 2 | Honest baby product reviews | LA based",
        "platform": "Instagram",
        "followers": 12500,
        "avg_views": 4800,
        "recent_30d_views": 8200,  # LT (under 50K)
        "content_transcript": (
            "Okay moms, let me show you this cup my daughter has been obsessed with. "
            "It's the Grosmimi PPSU straw cup and honestly the suction is perfect for "
            "her age. She just turned 14 months and she went from the bottle to this "
            "so smoothly. The PPSU material is BPA-free which was a huge deal for me. "
            "I also got their baby bottle for my younger one and the anti-colic system "
            "actually works! Highly recommend for moms transitioning from breastfeeding."
        ),
        "content_caption": "#grosmimi #ppsu #strawcup #babycup #momlife #toddlermom",
        "expected_form": "influencer-gifting",
        "expected_keywords": ["grosmimi", "ppsu", "straw cup", "baby bottle"],
    },
    "CHA&MOM": {
        "persona": "Emily Torres",
        "bio": "Skincare mama | Clean beauty for babies | Portland OR",
        "platform": "TikTok",
        "followers": 8900,
        "avg_views": 3200,
        "recent_30d_views": 5100,  # LT
        "content_transcript": (
            "Let me talk about this baby cream I've been using on my son's eczema patches. "
            "It's the PS Cream by CHA&MOM with Phyto Seline and it's been a game changer. "
            "His skin was so dry and flaky but after two weeks of this moisturizer it's so "
            "much better. The ingredients are super clean, no parabens, no fragrance. "
            "I've tried like 5 different baby skincare lotions and this one is by far the best. "
            "The texture is thick but absorbs quickly. My pediatrician even approved it."
        ),
        "content_caption": "#chamom #babyskincare #eczema #pscream #babylotion #cleanskincare",
        "expected_form": "influencer-gifting-chamom",
        "expected_keywords": ["cream", "skincare", "moisturizer", "cha&mom"],
    },
    "Naeiae": {
        "persona": "Jessica Park",
        "bio": "BLW mom | Organic baby food only | Denver CO",
        "platform": "Instagram",
        "followers": 6700,
        "avg_views": 2100,
        "recent_30d_views": 3400,  # LT
        "content_transcript": (
            "Snack time review! These organic pop rice puffs from Naeiae are my go-to for "
            "on-the-go snacking. My 10 month old just started baby led weaning and these "
            "dissolve so easily. No added sugar, no artificial flavors. I also tried their "
            "teething wafers which are great for sore gums. The rice puff texture is perfect "
            "for little fingers to grab. Way better than the mainstream baby snacks that are "
            "loaded with sodium. Naeiae uses organic Korean rice which I love."
        ),
        "content_caption": "#naeiae #babysnacks #ricepuff #blw #organicbaby #babyledweaning",
        "expected_form": "influencer-gifting-naeiae",
        "expected_keywords": ["rice puff", "snack", "naeiae", "teething"],
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────────
def log(msg):   print(msg)
def ok(msg):    print(f"  [PASS] {msg}")
def fail(msg):  print(f"  [FAIL] {msg}")
def info(msg):  print(f"  [INFO] {msg}")
def warn(msg):  print(f"  [WARN] {msg}")
def sep():      print("=" * 78)
def sep2():     print("-" * 78)


def make_test_email(brand_key):
    ts = datetime.now().strftime("%m%d%H%M%S")
    rnd = "".join(random.choices(string.ascii_lowercase, k=3))
    return f"outreach_{brand_key.lower().replace('&', '')}_{ts}_{rnd}@{TEST_EMAIL_DOMAIN}"


def make_test_ig(brand_key):
    ts = datetime.now().strftime("%m%d%H%M")
    return f"test_{brand_key.lower().replace('&', '')}_{ts}"


def http_request(method, url, payload=None, headers=None, timeout=30):
    """Simple HTTP request returning (status_code, parsed_json_or_text)."""
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def at_headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


def at_create(table_id, fields):
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}"
    return http_request("POST", url, payload={"fields": fields, "typecast": True}, headers=at_headers())


def at_get(table_id, formula, max_records=10):
    safe = urllib.parse.quote(formula)
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}?filterByFormula={safe}&maxRecords={max_records}"
    return http_request("GET", url, headers=at_headers())


def at_delete(table_id, record_id):
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}/{record_id}"
    return http_request("DELETE", url, headers=at_headers())


# ─── Test Steps ───────────────────────────────────────────────────────────────

class BrandTest:
    """Runs a single brand's outreach test and collects detailed logs."""

    def __init__(self, brand_name, config, run_ts):
        self.brand = brand_name
        self.cfg = config
        self.run_ts = run_ts
        self.email = make_test_email(brand_name)
        self.ig = make_test_ig(brand_name)
        self.creator_id = None
        self.content_id = None
        self.conv_id = None
        self.logs = []
        self.results = {}
        self.status = "pending"

    def _log(self, phase, msg, data=None):
        entry = {
            "ts": datetime.now().isoformat(),
            "brand": self.brand,
            "phase": phase,
            "msg": msg,
        }
        if data:
            entry["data"] = data
        self.logs.append(entry)
        info(f"[{self.brand}] {phase}: {msg}")

    def step1_read_dashboard_config(self):
        """Read current Daily Config from Pathlight PROD."""
        self._log("CONFIG", "Reading Airtable Daily Config...")
        # Get the most recent config row (sorted by Date desc)
        status, body = at_get(AT_DAILY_CONFIG, "TRUE()", max_records=1)
        if status != 200 or not body.get("records"):
            self._log("CONFIG", f"FAILED to read Daily Config (HTTP {status})", body)
            return None
        rec = body["records"][0]
        fields = rec.get("fields", {})
        config_summary = {
            "record_id": rec["id"],
            "Date": fields.get("Date", "unknown"),
            "High Touch Req (R30D Views)": fields.get("High Touch Req (R30D Views)", "unknown"),
            "High Touch Count": fields.get("High Touch Count", 0),
            "Low Touch Count": fields.get("Low Touch Count", 0),
            "Creators Contacted": fields.get("Creators Contacted", 0),
            "Active Outreach Template": fields.get("Active Outreach Template", []),
            "Active Creator Form": fields.get("Active Creator Form", []),
            "Active Content Guidelines": fields.get("Active Content Guidelines", []),
        }
        self._log("CONFIG", "Dashboard config loaded", config_summary)
        self.results["config"] = config_summary
        return config_summary

    def step2_seed_creator(self, dry_run=False):
        """Create test Creator record."""
        fields = {
            "Email": self.email,
            "Username": self.ig,
            "Name": self.cfg["persona"],
            "Platform": self.cfg["platform"],
            "Followers": self.cfg["followers"],
            "Avg Views": self.cfg["avg_views"],
            "Recent 30-Day Views": self.cfg["recent_30d_views"],
            "Outreach Status": "Not Started",
            "Partnership Status": "New",
            "Outreach Type": "Low Touch",
            "Source": "Dual Test",
            "Syncly Synced": True,
            "Profile URL": f"https://{'instagram' if self.cfg['platform'] == 'Instagram' else 'tiktok'}.com/{self.ig}",
        }
        self._log("SEED", f"Creating Creator: {self.ig} ({self.email})", fields)
        if dry_run:
            self._log("SEED", "DRY RUN - skipping AT create")
            self.creator_id = "rec_DRYRUN_creator"
            return True
        status, body = at_create(AT_CREATORS, fields)
        if status in (200, 201):
            self.creator_id = body["id"]
            self._log("SEED", f"Creator created: {self.creator_id}")
            self.results["creator_id"] = self.creator_id
            self.results["creator_fields"] = fields
            return True
        else:
            self._log("SEED", f"FAILED (HTTP {status})", body)
            return False

    def step3_seed_content(self, dry_run=False):
        """Create test Content record with brand-specific transcript."""
        post_url = f"https://www.instagram.com/reel/{self.ig}_brandtest/"
        fields = {
            "Post URL": post_url,
            "Platform": self.cfg["platform"],
            "Post Date": datetime.now().strftime("%Y-%m-%d"),
            "Summary": f"{self.brand} product review by {self.cfg['persona']}",
            "Text": self.cfg["content_transcript"],
            "Caption": self.cfg["content_caption"],
            "Content Status": "Pending",
            "Views": self.cfg["avg_views"],
            "Likes": int(self.cfg["avg_views"] * 0.08),
            "Comments": int(self.cfg["avg_views"] * 0.01),
            "Creator": [self.creator_id] if self.creator_id and not self.creator_id.startswith("rec_DRYRUN") else [],
        }
        self._log("SEED", f"Creating Content with {self.brand} transcript ({len(self.cfg['content_transcript'])} chars)", {
            "post_url": post_url,
            "transcript_preview": self.cfg["content_transcript"][:120] + "...",
            "keywords_expected": self.cfg["expected_keywords"],
        })
        if dry_run:
            self._log("SEED", "DRY RUN - skipping AT create")
            self.content_id = "rec_DRYRUN_content"
            return True
        status, body = at_create(AT_CONTENT, fields)
        if status in (200, 201):
            self.content_id = body["id"]
            self._log("SEED", f"Content created: {self.content_id}")
            self.results["content_id"] = self.content_id
            return True
        else:
            self._log("SEED", f"FAILED (HTTP {status})", body)
            return False

    def step4_trigger_draft_gen(self, dry_run=False):
        """PROD Draft Gen uses 30-min schedule (no webhook). Log that trigger is passive."""
        self._log("TRIGGER", f"PROD Draft Gen polls every 30 min (schedule trigger)", {
            "workflow_id": DRAFT_GEN_WF_ID,
            "n8n_url": f"{N8N_BASE_URL}/workflow/{DRAFT_GEN_WF_ID}",
            "creator_id": self.creator_id,
            "note": "Either wait for next poll or manually trigger in n8n UI",
        })
        if dry_run:
            self._log("TRIGGER", "DRY RUN - skipping")
            return True
        self.results["trigger_status"] = "passive_schedule"
        self.results["trigger_note"] = "PROD uses 30-min schedule poll. Manually trigger in n8n UI for immediate execution."
        return True

    def step5_poll_for_draft(self, max_wait=120, poll_interval=10, dry_run=False):
        """Poll Creator record for Outreach Status change, then fetch Conversation draft."""
        if dry_run:
            self._log("POLL", "DRY RUN - skipping draft poll")
            self.results["draft_found"] = False
            return False

        if not self.creator_id:
            self._log("POLL", "No creator_id - cannot poll")
            self.results["draft_found"] = False
            return False

        self._log("POLL", f"Polling Creator {self.creator_id} for status change (max {max_wait}s, every {poll_interval}s)...")
        start = time.time()
        attempt = 0

        while time.time() - start < max_wait:
            attempt += 1
            # Check Creator's Outreach Status
            url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CREATORS}/{self.creator_id}"
            status, body = http_request("GET", url, headers=at_headers())
            if status != 200:
                self._log("POLL", f"Attempt {attempt}: API error ({status}), waiting {poll_interval}s...")
                time.sleep(poll_interval)
                continue

            fields = body.get("fields", {})
            outreach_status = fields.get("Outreach Status", "Not Started")
            conv_ids = fields.get("Conversation", [])

            if outreach_status != "Not Started" and conv_ids:
                # Found! Now fetch the Conversation record
                conv_id = conv_ids[0]
                conv_url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}/{conv_id}"
                c_status, c_body = http_request("GET", conv_url, headers=at_headers())
                c_fields = c_body.get("fields", {}) if c_status == 200 else {}

                self.conv_id = conv_id
                draft_data = {
                    "conv_id": conv_id,
                    "creator_outreach_status": outreach_status,
                    "subject": c_fields.get("Subject", ""),
                    "body_preview": (c_fields.get("Message Content", "") or "")[:500],
                    "body_full_length": len(c_fields.get("Message Content", "") or ""),
                    "status": c_fields.get("Status", ""),
                    "direction": c_fields.get("Direction", ""),
                    "channel": c_fields.get("Channel", ""),
                    "form_link_present": any(
                        link in (c_fields.get("Message Content", "") or "")
                        for link in ["influencer-gifting", "influencer-gifting-chamom", "influencer-gifting-naeiae", "influencer-gifting-ht"]
                    ),
                    "all_conv_fields": {k: str(v)[:200] for k, v in c_fields.items()},
                    "all_creator_fields": {k: str(v)[:200] for k, v in fields.items()},
                }
                self._log("POLL", f"Draft FOUND after {attempt} attempts ({int(time.time()-start)}s)", draft_data)
                self.results["draft"] = draft_data
                self.results["draft_found"] = True
                self.results["poll_time_sec"] = int(time.time() - start)

                # Check which form link is in the email
                body_text = fields.get("Message Content", "") or ""
                for form_key, form_path in [
                    ("Grosmimi", "influencer-gifting"),
                    ("High Touch", "influencer-gifting-ht"),
                    ("CHA&MOM", "influencer-gifting-chamom"),
                    ("Naeiae", "influencer-gifting-naeiae"),
                ]:
                    if form_path in body_text and form_key != "Grosmimi":
                        self.results["detected_form"] = form_path
                        break
                    elif "influencer-gifting" in body_text and "chamom" not in body_text and "naeiae" not in body_text and "ht" not in body_text:
                        self.results["detected_form"] = "influencer-gifting"
                        break
                else:
                    self.results["detected_form"] = "none_found"

                return True

            self._log("POLL", f"Attempt {attempt}: no draft yet, waiting {poll_interval}s...")
            time.sleep(poll_interval)

        self._log("POLL", f"TIMEOUT after {max_wait}s ({attempt} attempts)")
        self.results["draft_found"] = False
        self.results["poll_time_sec"] = max_wait
        return False

    def step6_verify(self):
        """Verify the draft matches expected brand."""
        if not self.results.get("draft_found"):
            self._log("VERIFY", "No draft to verify")
            self.status = "no_draft"
            return

        draft = self.results.get("draft", {})
        body_text = draft.get("body_preview", "").lower()
        checks = []

        # Check brand keywords in email body
        for kw in self.cfg["expected_keywords"]:
            found = kw.lower() in body_text
            checks.append({"check": f"Keyword '{kw}' in body", "result": "PASS" if found else "MISS"})

        # Check form link
        expected_form = self.cfg["expected_form"]
        actual_form = self.results.get("detected_form", "none")
        form_match = expected_form in actual_form or actual_form in expected_form
        checks.append({"check": f"Form link = {expected_form}", "result": "PASS" if form_match else f"FAIL (got: {actual_form})"})

        # Check subject is non-empty
        has_subject = bool(draft.get("subject", "").strip())
        checks.append({"check": "Subject non-empty", "result": "PASS" if has_subject else "FAIL"})

        self.results["verification"] = checks
        all_pass = all(c["result"] == "PASS" for c in checks)
        self.status = "pass" if all_pass else "partial"
        self._log("VERIFY", f"{'ALL PASS' if all_pass else 'SOME ISSUES'}", checks)

    def cleanup(self):
        """Delete test records."""
        deleted = []
        for label, table, rid in [
            ("Creator", AT_CREATORS, self.creator_id),
            ("Content", AT_CONTENT, self.content_id),
            ("Conversation", AT_CONVERSATIONS, self.conv_id),
        ]:
            if rid and rid.startswith("rec") and not rid.startswith("rec_DRYRUN"):
                status, _ = at_delete(table, rid)
                result = "OK" if status == 200 else f"HTTP {status}"
                deleted.append(f"{label}: {rid} ({result})")
                self._log("CLEANUP", f"Deleted {label}: {rid} ({result})")
        return deleted


# ─── HTML Report ──────────────────────────────────────────────────────────────

def generate_html_report(tests, run_ts, dashboard_config):
    """Generate side-by-side comparison HTML report."""

    def esc(s):
        if not s:
            return ""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def status_badge(s):
        colors = {"pass": "#15803d", "partial": "#d97706", "no_draft": "#dc2626", "pending": "#6b7280"}
        c = colors.get(s, "#6b7280")
        return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">{esc(s).upper()}</span>'

    brands = list(tests.keys())
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Outreach Brand Test - {run_ts}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; color:#1e293b; padding:20px; font-size:13px; }}
  h1 {{ font-size:20px; margin-bottom:4px; }}
  h2 {{ font-size:15px; margin:20px 0 8px; color:#475569; }}
  h3 {{ font-size:13px; margin:12px 0 6px; color:#64748b; }}
  .meta {{ font-size:11px; color:#94a3b8; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat({len(brands)}, 1fr); gap:12px; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:14px; }}
  .card h3 {{ margin-top:0; }}
  .brand-header {{ font-size:14px; font-weight:700; margin-bottom:8px; }}
  .field {{ margin:4px 0; }}
  .field-key {{ font-size:11px; color:#94a3b8; text-transform:uppercase; }}
  .field-val {{ font-size:12px; margin-top:1px; }}
  .check-pass {{ color:#15803d; }}
  .check-fail {{ color:#dc2626; }}
  .check-miss {{ color:#d97706; }}
  pre {{ background:#f1f5f9; padding:10px; border-radius:6px; font-size:11px; white-space:pre-wrap; word-break:break-all; max-height:300px; overflow-y:auto; }}
  .config-box {{ background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:14px; margin-bottom:16px; }}
  .config-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:8px; font-size:12px; }}
  .log-box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; margin-top:8px; max-height:400px; overflow-y:auto; }}
  .log-entry {{ font-size:11px; color:#64748b; padding:2px 0; border-bottom:1px solid #f1f5f9; }}
  .log-phase {{ font-weight:600; color:#475569; display:inline-block; width:70px; }}
</style></head><body>
<h1>3-Brand Outreach Pipeline Test</h1>
<div class="meta">Run: {esc(run_ts)} | All Low Touch | HiL=on (draft mode)</div>
"""

    # Dashboard Config section
    if dashboard_config:
        html += '<div class="config-box"><h3>Dashboard Config (shared)</h3><div class="config-grid">'
        for k, v in dashboard_config.items():
            if k == "record_id":
                continue
            html += f'<div><span class="field-key">{esc(k)}</span><br><strong>{esc(str(v))}</strong></div>'
        html += '</div></div>'

    # Brand comparison grid
    html += '<h2>Brand Comparison</h2><div class="grid">'

    for brand in brands:
        t = tests[brand]
        r = t.results
        html += f'<div class="card"><div class="brand-header">{esc(brand)} {status_badge(t.status)}</div>'

        # Creator info
        html += f'''<div class="field"><span class="field-key">Creator</span>
            <div class="field-val">{esc(t.cfg["persona"])} (@{esc(t.ig)})<br>
            {esc(t.cfg["platform"])} | {t.cfg["followers"]:,} followers | {t.cfg["recent_30d_views"]:,} R30D views<br>
            <span style="font-size:10px;color:#94a3b8;">{esc(t.email)}</span></div></div>'''

        # Content seed
        html += f'''<div class="field"><span class="field-key">Content Transcript (seed)</span>
            <div class="field-val" style="font-size:11px;color:#64748b;">{esc(t.cfg["content_transcript"][:200])}...</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px;">Expected keywords: {esc(", ".join(t.cfg["expected_keywords"]))}</div></div>'''

        # Draft result
        if r.get("draft_found"):
            d = r["draft"]
            html += f'''<div class="field"><span class="field-key">AI Draft (generated)</span>
                <div class="field-val"><strong>Subject:</strong> {esc(d.get("subject", ""))}<br>
                <strong>Form link:</strong> {esc(r.get("detected_form", "?"))}<br>
                <strong>Poll time:</strong> {r.get("poll_time_sec", "?")}s<br>
                <strong>Body length:</strong> {d.get("body_full_length", 0)} chars</div></div>
                <div class="field"><span class="field-key">Email Body Preview</span>
                <pre>{esc(d.get("body_preview", ""))}</pre></div>'''
        else:
            html += '<div class="field"><span class="field-key">AI Draft</span><div class="field-val check-fail">No draft found (timeout or error)</div></div>'

        # Verification
        if r.get("verification"):
            html += '<div class="field"><span class="field-key">Verification</span><div class="field-val">'
            for c in r["verification"]:
                cls = "check-pass" if c["result"] == "PASS" else ("check-miss" if c["result"] == "MISS" else "check-fail")
                html += f'<div class="{cls}">{esc(c["check"])}: {esc(c["result"])}</div>'
            html += '</div></div>'

        # Logs
        html += '<div class="field"><span class="field-key">Execution Log</span><div class="log-box">'
        for entry in t.logs:
            html += f'<div class="log-entry"><span class="log-phase">{esc(entry["phase"])}</span> {esc(entry["msg"])}'
            if entry.get("data") and isinstance(entry["data"], dict):
                html += f'<br><span style="font-size:10px;color:#94a3b8;margin-left:70px;">{esc(json.dumps(entry["data"], ensure_ascii=False)[:300])}</span>'
            html += '</div>'
        html += '</div></div>'

        html += '</div>'  # card

    html += '</div>'  # grid

    # Full JSON log
    html += '<h2>Raw Test Data (JSON)</h2><pre>'
    raw = {}
    for brand in brands:
        t = tests[brand]
        raw[brand] = {
            "status": t.status,
            "email": t.email,
            "ig": t.ig,
            "creator_id": t.creator_id,
            "content_id": t.content_id,
            "conv_id": t.conv_id,
            "results": t.results,
            "logs": t.logs,
        }
    html += esc(json.dumps(raw, indent=2, ensure_ascii=False, default=str))
    html += '</pre></body></html>'

    return html


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="3-Brand Parallel Outreach Test")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no AT/n8n calls")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep test data after run")
    parser.add_argument("--brand", type=str, help="Test single brand (grosmimi/chamom/naeiae)")
    parser.add_argument("--poll-timeout", type=int, default=1800, help="Max seconds to wait for draft (default 30min for PROD schedule)")
    args = parser.parse_args()

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    sep()
    log(f"3-Brand Outreach Pipeline Test")
    log(f"Run: {run_ts} | Mode: {'DRY RUN' if args.dry_run else 'LIVE'} | Cleanup: {'No' if args.no_cleanup else 'Yes'}")
    sep()

    # Select brands
    if args.brand:
        brand_map = {"grosmimi": "Grosmimi", "chamom": "CHA&MOM", "chaenmom": "CHA&MOM", "naeiae": "Naeiae"}
        bk = brand_map.get(args.brand.lower())
        if not bk:
            fail(f"Unknown brand: {args.brand}. Use grosmimi/chamom/naeiae")
            sys.exit(1)
        brands_to_test = {bk: BRAND_CONFIGS[bk]}
    else:
        brands_to_test = BRAND_CONFIGS

    # Env check
    missing = []
    for var in ["AIRTABLE_API_KEY", "N8N_API_KEY"]:
        if not os.getenv(var):
            missing.append(var)
    if missing:
        fail(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Initialize tests
    tests = {}
    for brand, cfg in brands_to_test.items():
        tests[brand] = BrandTest(brand, cfg, run_ts)

    # Step 1: Read dashboard config (once, shared)
    sep2()
    log("STEP 1: Read Dashboard Config")
    dashboard_config = list(tests.values())[0].step1_read_dashboard_config()

    # Step 2: Seed creators
    sep2()
    log("STEP 2: Seed Creators (parallel)")
    for brand, t in tests.items():
        t.step2_seed_creator(dry_run=args.dry_run)

    # Step 3: Seed content
    sep2()
    log("STEP 3: Seed Content (parallel)")
    for brand, t in tests.items():
        t.step3_seed_content(dry_run=args.dry_run)

    # Step 4: Trigger Draft Gen (once — schedule poll finds all seeded creators)
    sep2()
    log("STEP 4: Trigger Draft Generation (single n8n execution)")
    first_test = list(tests.values())[0]
    first_test.step4_trigger_draft_gen(dry_run=args.dry_run)
    # Copy trigger result to all tests
    for brand, t in tests.items():
        if t != first_test:
            t.results["trigger_status"] = first_test.results.get("trigger_status")
            t.results["trigger_response"] = first_test.results.get("trigger_response")

    if not args.dry_run:
        info(f"PROD Draft Gen is schedule-based (30-min poll). Manually trigger at:")
        info(f"  {N8N_BASE_URL}/workflow/{DRAFT_GEN_WF_ID}")
        info(f"  Or wait for next automatic poll cycle.")
        info("Waiting 10s before polling...")
        time.sleep(10)

    # Step 5: Poll for drafts
    sep2()
    log("STEP 5: Poll for AI Drafts")
    for brand, t in tests.items():
        t.step5_poll_for_draft(max_wait=args.poll_timeout, dry_run=args.dry_run)

    # Step 6: Verify
    sep2()
    log("STEP 6: Verify Results")
    for brand, t in tests.items():
        t.step6_verify()

    # Summary
    sep()
    log("RESULTS SUMMARY")
    sep2()
    for brand, t in tests.items():
        status_str = {"pass": "PASS", "partial": "PARTIAL", "no_draft": "NO DRAFT", "pending": "PENDING"}.get(t.status, t.status)
        draft_subject = t.results.get("draft", {}).get("subject", "n/a")
        detected_form = t.results.get("detected_form", "n/a")
        poll_time = t.results.get("poll_time_sec", "n/a")
        log(f"  {brand:12s} | {status_str:10s} | Form: {detected_form:30s} | Poll: {poll_time}s")
        log(f"               | Subject: {draft_subject[:60]}")
        sep2()

    # Generate report
    report_html = generate_html_report(tests, run_ts, dashboard_config)
    report_path = os.path.join(TMP_DIR, f"report_{run_ts}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    log(f"\nHTML Report: {report_path}")

    # Save JSON
    json_path = os.path.join(TMP_DIR, f"data_{run_ts}.json")
    raw = {}
    for brand, t in tests.items():
        raw[brand] = {
            "status": t.status, "email": t.email, "ig": t.ig,
            "creator_id": t.creator_id, "content_id": t.content_id,
            "conv_id": t.conv_id, "results": t.results,
        }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False, default=str)
    log(f"JSON Data:   {json_path}")

    # Cleanup
    if not args.dry_run and not args.no_cleanup:
        sep2()
        log("CLEANUP")
        for brand, t in tests.items():
            t.cleanup()

    sep()
    all_pass = all(t.status == "pass" for t in tests.values())
    log(f"Overall: {'ALL PASS' if all_pass else 'ISSUES FOUND'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
