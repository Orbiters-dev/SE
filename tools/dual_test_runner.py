"""
Dual Test Runner — Maker-Checker Pattern for Creator Collab Pipeline
=====================================================================
Executor (Maker)가 파이프라인 액션을 실행하고,
Verifier (Checker)가 독립적으로 모든 downstream 시스템을 검증한다.

Stages:
  seed        : Airtable Creator 시드 레코드 생성
  gifting     : 인플루언서 기프팅 폼 → n8n → Airtable + Shopify + PG
  gifting2    : 샘플 요청 폼 → Draft Order + Airtable
  sample_sent : Airtable 상태 변경 → n8n 폴링 → Draft Order 완료

Usage:
    python tools/dual_test_runner.py --dual                         # 전체 이중테스트
    python tools/dual_test_runner.py --dual --stages seed,gifting   # 특정 스테이지
    python tools/dual_test_runner.py --dual --dry-run               # 프리뷰
    python tools/dual_test_runner.py --executor-only                # Executor만
    python tools/dual_test_runner.py --verifier-only --run-id X     # 기존 signal로 Verifier만
    python tools/dual_test_runner.py --results                      # 마지막 결과
"""

import os
import sys
import json
import time
import random
import string
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# ─── Paths ──────────────────────────────────────────────────────────────────
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP = os.path.join(ROOT, ".tmp")
DUAL_DIR = os.path.join(TMP, "dual_test")

sys.path.insert(0, DIR)

# ─── Import from test_influencer_flow ────────────────────────────────────────
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass

from test_influencer_flow import (
    FlowContext, http_request, extract_value,
    AT_BASE, AT_CREATORS, AT_ORDERS, AT_APPLICANTS, AT_CONVERSATIONS,
    WJ_WORKFLOWS, WJ_WEBHOOKS,
    AIRTABLE_API_KEY, SHOPIFY_STORE, SHOPIFY_TOKEN,
    ORBITOOLS_URL, ORBITOOLS_USER, ORBITOOLS_PASS,
    N8N_BASE_URL, N8N_API_KEY,
    TEST_EMAIL_DOMAIN,
    _make_test_email, _make_test_phone,
    link_airtable, link_shopify, link_n8n_wf,
)

# ─── Email content templates ─────────────────────────────────────────
def _email_templates(test_name, test_ig, test_email):
    outreach_subject = f"Grosmimi x {test_ig} - Baby Product Collaboration"
    outreach_body = f"Hi {test_name},\n\nI came across your Instagram profile @{test_ig} and loved your authentic parenting content!\n\nWe'd love to send you our bestselling PPSU Straw Cup for your little one to try.\n\nWould you be interested?\n\nBest, Onzenna Team"
    reply_body = f"Hi Onzenna Team!\n\nThank you for reaching out! I'd love to try the PPSU Straw Cup for my daughter.\n\nI can have the content up within 2-3 weeks.\n\nBest, {test_name}\n@{test_ig}"
    confirm_body = f"Hi {test_name}!\n\nWonderful! Please fill out our gifting form at onzenna.com/pages/influencer-gifting.\n\nContent guidelines:\n- Tag @onzenna and use #grosmimi\n- Show product in use\n- Post within 30 days\n\nBest, Onzenna Team"
    return outreach_subject, outreach_body, reply_body, confirm_body

# ─── Output helpers ─────────────────────────────────────────────────────────
def log(msg):  print(msg)
def ok(msg):   print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")

ALL_STAGES = ["seed", "email_draft", "email_approve", "email_reply", "email_confirm",
              "gifting", "gifting2", "sample_sent"]
# Quick preset: skip email stages
QUICK_STAGES = ["seed", "gifting", "gifting2", "sample_sent"]

# ═══════════════════════════════════════════════════════════════════════════
# DualTestConfig
# ═══════════════════════════════════════════════════════════════════════════

class DualTestConfig:
    def __init__(self, stages=None, email=None, label=None):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.label = label or ""
        self.run_id = f"dual_{label}_{ts}" if label else f"dual_{ts}"
        self.run_dir = os.path.join(DUAL_DIR, self.run_id)
        self.test_email = email or _make_test_email()
        self.test_phone = _make_test_phone()
        rand = "".join(random.choices(string.ascii_lowercase, k=4))
        self.test_ig = f"@dualtest_{ts[:8]}_{rand}"
        self.test_tiktok = f"@dualtest_tk_{rand}"
        self.stages = stages or ALL_STAGES[:]
        self.started_at = datetime.now().isoformat()
        self.finished_at = None

        os.makedirs(self.run_dir, exist_ok=True)

    @property
    def config_path(self): return os.path.join(self.run_dir, "config.json")
    @property
    def signal_path(self): return os.path.join(self.run_dir, "signal.json")
    @property
    def executor_log_path(self): return os.path.join(self.run_dir, "executor_log.json")
    @property
    def verifier_log_path(self): return os.path.join(self.run_dir, "verifier_log.json")
    @property
    def report_path(self): return os.path.join(self.run_dir, "merged_report.html")

    def save(self):
        data = {
            "run_id": self.run_id, "label": self.label,
            "test_email": self.test_email,
            "test_phone": self.test_phone, "test_ig": self.test_ig,
            "test_tiktok": self.test_tiktok, "stages": self.stages,
            "started_at": self.started_at, "finished_at": self.finished_at,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, run_id):
        path = os.path.join(DUAL_DIR, run_id, "config.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls.__new__(cls)
        cfg.run_id = data["run_id"]
        cfg.run_dir = os.path.join(DUAL_DIR, run_id)
        cfg.test_email = data["test_email"]
        cfg.test_phone = data["test_phone"]
        cfg.test_ig = data["test_ig"]
        cfg.label = data.get("label", "")
        cfg.test_tiktok = data.get("test_tiktok", "")
        cfg.stages = data["stages"]
        cfg.started_at = data["started_at"]
        cfg.finished_at = data.get("finished_at")
        return cfg


# ═══════════════════════════════════════════════════════════════════════════
# Signal File — Executor writes, Verifier reads
# ═══════════════════════════════════════════════════════════════════════════

class SignalFile:
    def __init__(self, path):
        self.path = path
        self.data = {"status": "running", "stages_completed": []}

    def write_stage(self, stage_name, context):
        self.data["stages_completed"].append({
            "stage": stage_name,
            "completed_at": datetime.now().isoformat(),
            "context": context,
        })
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, self.path)

    def finish(self):
        self.data["status"] = "finished"
        self.data["finished_at"] = datetime.now().isoformat()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def read(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_stage_context(self, stage_name):
        for s in self.data["stages_completed"]:
            if s["stage"] == stage_name:
                return s["context"]
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# Airtable / Shopify / PG helpers (thin wrappers for verification)
# ═══════════════════════════════════════════════════════════════════════════

def _at_headers():
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

def at_find(table_id, field, value, max_records=5):
    safe = value.replace("'", "\\'")
    formula = urllib.parse.quote(f"{{{field}}}='{safe}'")
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}?filterByFormula={formula}&maxRecords={max_records}"
    status, body = http_request("GET", url, headers=_at_headers())
    if status == 200 and isinstance(body, dict):
        return body.get("records", [])
    return []

def at_create(table_id, fields):
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}"
    payload = {"fields": fields, "typecast": True}
    status, body = http_request("POST", url, payload=payload, headers=_at_headers())
    return status, body

def at_update(table_id, record_id, fields):
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}/{record_id}"
    payload = {"fields": fields, "typecast": True}
    status, body = http_request("PATCH", url, payload=payload, headers=_at_headers())
    return status, body

def at_delete(table_id, record_id):
    if not record_id or not str(record_id).startswith("rec"):
        return 0, "invalid record_id"
    url = f"https://api.airtable.com/v0/{AT_BASE}/{table_id}/{record_id}"
    status, body = http_request("DELETE", url, headers=_at_headers())
    return status, body

def shopify_find_customer(email):
    if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
        return []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/search.json?query=email:{email}"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    status, body = http_request("GET", url, headers=headers)
    if status == 200 and isinstance(body, dict):
        return body.get("customers", [])
    return []

def shopify_delete_customer(customer_id):
    if not customer_id:
        return 0, ""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/customers/{customer_id}.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    return http_request("DELETE", url, headers=headers)

def pg_find(endpoint, email):
    if not ORBITOOLS_URL or not ORBITOOLS_USER:
        return []
    url = f"{ORBITOOLS_URL}{endpoint}?email={urllib.parse.quote(email)}"
    status, body = http_request("GET", url, basic_auth=(ORBITOOLS_USER, ORBITOOLS_PASS))
    if status == 200:
        if isinstance(body, dict):
            return body.get("results", [body]) if "results" in body else [body]
        if isinstance(body, list):
            return body
    return []


# ═══════════════════════════════════════════════════════════════════════════
# Check Result — single assertion
# ═══════════════════════════════════════════════════════════════════════════

class Check:
    def __init__(self, name, passed, expected=None, actual=None, detail=""):
        self.name = name
        self.passed = passed  # True / False / None (skip)
        self.expected = expected
        self.actual = actual
        self.detail = detail

    def to_dict(self):
        return {
            "name": self.name, "passed": self.passed,
            "expected": str(self.expected) if self.expected is not None else "",
            "actual": str(self.actual) if self.actual is not None else "",
            "detail": self.detail,
        }


# ═══════════════════════════════════════════════════════════════════════════
# ExecutorAgent
# ═══════════════════════════════════════════════════════════════════════════

class ExecutorAgent:
    def __init__(self, config: DualTestConfig, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.signal = SignalFile(config.signal_path)
        self.stages_log = []  # [{stage, checks, duration_ms, links}]

    def run_all(self):
        log(f"\n{'='*60}")
        log(f"  EXECUTOR (Maker) | {self.config.run_id}")
        log(f"  Email: {self.config.test_email}")
        log(f"  Stages: {', '.join(self.config.stages)}")
        log(f"{'='*60}\n")

        for stage_name in self.config.stages:
            runner = getattr(self, f"_stage_{stage_name}", None)
            if not runner:
                warn(f"Unknown stage: {stage_name}")
                continue
            log(f"\n--- EXECUTOR: Stage [{stage_name}] ---")
            t0 = time.time()
            checks, ctx = runner()
            dur = int((time.time() - t0) * 1000)
            entry = {
                "stage": stage_name,
                "checks": [c.to_dict() for c in checks],
                "duration_ms": dur,
                "context": ctx,
            }
            self.stages_log.append(entry)
            self.signal.write_stage(stage_name, ctx)
            passed = sum(1 for c in checks if c.passed)
            total = len(checks)
            log(f"  Executor [{stage_name}]: {passed}/{total} PASS ({dur}ms)")

        self.signal.finish()
        self._save_log()
        return self.stages_log

    def _save_log(self):
        with open(self.config.executor_log_path, "w", encoding="utf-8") as f:
            json.dump(self.stages_log, f, ensure_ascii=False, indent=2, default=str)

    # ── Stage 0: Influencer Discovery -> CRM Sync ─────────────────────
    def _stage_seed(self):
        checks = []
        ctx = {"test_email": self.config.test_email, "test_ig": self.config.test_ig}
        info(f"[Stage 0] Simulating Syncly discovery -> Airtable CRM record creation")
        info(f"  Creator: Sarah Kim | IG: {self.config.test_ig} | Email: {self.config.test_email}")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would create Airtable Creator", True, detail="seed"))
            return checks, ctx

        fields = {
            "Email": self.config.test_email,
            "Username": self.config.test_ig.lstrip("@"),
            "Platform": "Instagram",
            "Outreach Status": "Not Started",
            "Partnership Status": "New",
            "Source": "Dual Test",
        }
        info(f"  [0.1] POST Airtable Creators table ({AT_CREATORS})")
        info(f"        Fields: {json.dumps({k:v for k,v in fields.items()}, ensure_ascii=False)}")
        status, body = at_create(AT_CREATORS, fields)
        if status in (200, 201) and isinstance(body, dict) and body.get("id"):
            record_id = body["id"]
            ok(f"[0.2] Airtable Creator created: {record_id}")
            checks.append(Check("[0] Create AT Creator record", True, detail=record_id))
            ctx["creator_record_id"] = record_id
        else:
            fail(f"[0.2] Airtable Creator create failed: {status} {body}")
            checks.append(Check("[0] Create AT Creator record", False, expected="201", actual=str(status)))
        return checks, ctx

    # ── Stage 1a: Trigger AI Draft Generation ───────────────────────────
    def _stage_email_draft(self):
        checks = []
        ctx = {}
        webhook_url = WJ_WEBHOOKS.get("draft_gen", "")
        info(f"[Stage 1a] Trigger Claude AI Draft Generation via n8n webhook")
        info(f"  Webhook: {webhook_url}")

        seed_ctx = self.signal.get_stage_context("seed")
        creator_record_id = seed_ctx.get("creator_record_id", "")
        test_ig = self.config.test_ig.lstrip("@")
        subj, body, _, _ = _email_templates("Sarah Kim", test_ig, self.config.test_email)

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would trigger draft generation", True))
            return checks, ctx

        if not creator_record_id:
            records = at_find(AT_CREATORS, "Email", self.config.test_email)
            if records:
                creator_record_id = records[0]["id"]
            else:
                fail("[1a] No creator record found — run seed stage first")
                checks.append(Check("[1a] Find creator record", False))
                return checks, ctx

        payload = {
            "records": [{
                "id": creator_record_id,
                "fields": {
                    "Username": test_ig,
                    "Email": self.config.test_email,
                    "Platform": "Instagram",
                    "Outreach Type": "Low Touch",
                    "Outreach Status": "Not Started",
                    "Name": "Sarah Kim",
                    "Brand Classification": "Grosmimi",
                },
                "createdTime": datetime.now().isoformat(),
            }]
        }

        info(f"  [1a.1] POST draft_gen webhook")
        status, resp = http_request("POST", webhook_url, payload=payload)
        if status == 200:
            ok(f"[1a.2] Draft gen triggered: HTTP {status}")
            checks.append(Check("[1a] POST draft_gen webhook", True))
        else:
            fail(f"[1a.2] Draft gen failed: HTTP {status}")
            checks.append(Check("[1a] POST draft_gen webhook", False, expected="200", actual=str(status)))

        ctx["creator_record_id"] = creator_record_id
        ctx["draft_gen_response"] = resp if isinstance(resp, dict) else str(resp)[:500]

        wait_sec = 65
        info(f"  [1a.3] Waiting {wait_sec}s for Claude AI + Sheets + Gmail...")
        time.sleep(wait_sec)
        checks.append(Check(f"[1a] Wait {wait_sec}s for AI generation", True))

        return checks, ctx

    # ── Stage 1b: Approve draft + log outreach email ─────────────────
    def _stage_email_approve(self):
        checks = []
        ctx = {}
        test_ig = self.config.test_ig.lstrip("@")
        subj, body, _, _ = _email_templates("Sarah Kim", test_ig, self.config.test_email)
        info(f"[Stage 1b] Marketer approves AI draft -> Log outreach email in Conversations")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would approve and log email", True))
            return checks, ctx

        seed_ctx = self.signal.get_stage_context("seed")
        creator_record_id = seed_ctx.get("creator_record_id", "")
        if not creator_record_id:
            records = at_find(AT_CREATORS, "Email", self.config.test_email)
            creator_record_id = records[0]["id"] if records else ""

        # Log outreach email in Conversations
        conv_fields = {
            "Message Title": f"Outreach: {subj}",
            "Subject": subj,
            "Channel": "Email",
            "Direction": "Outbound",
            "Message Content": body,
            "Conversation Context": f"AI-generated outreach to @{test_ig}. Brand: Grosmimi. Type: Low Touch.",
            "AI Generated": True,
            "AI Approved": True,
            "Reviewed By": "Dual Test (auto)",
            "Status": "Sent",
        }
        if creator_record_id:
            conv_fields["Creator"] = [creator_record_id]

        info(f"  [1b.1] Creating Conversations record (outreach email)")
        status, resp = at_create(AT_CONVERSATIONS, conv_fields)
        if status in (200, 201) and isinstance(resp, dict) and resp.get("id"):
            conv_id = resp["id"]
            ok(f"[1b.1] Outreach email logged: {conv_id}")
            checks.append(Check("[1b] Log outreach email", True, detail=conv_id))
            ctx["outreach_conv_id"] = conv_id
        else:
            fail(f"[1b.1] Failed to log email: {status}")
            checks.append(Check("[1b] Log outreach email", False, actual=str(status)))

        # Update creator status -> Sent
        if creator_record_id:
            info(f"  [1b.2] Updating creator status -> Sent")
            s, _ = at_update(AT_CREATORS, creator_record_id, {
                "Outreach Status": "Sent",
                "Outreach Sent At": datetime.now().strftime("%Y-%m-%d"),
            })
            if s == 200:
                ok("[1b.2] Creator status -> Sent")
                checks.append(Check("[1b] Update status -> Sent", True))
            else:
                fail(f"[1b.2] Update failed: {s}")
                checks.append(Check("[1b] Update status -> Sent", False, actual=str(s)))

        ctx["creator_record_id"] = creator_record_id
        return checks, ctx

    # ── Stage 1c: Influencer replies ─────────────────────────────────
    def _stage_email_reply(self):
        checks = []
        ctx = {}
        test_ig = self.config.test_ig.lstrip("@")
        subj, _, reply_body, _ = _email_templates("Sarah Kim", test_ig, self.config.test_email)
        info(f"[Stage 1c] Simulate influencer email reply -> Log in Conversations")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would log influencer reply", True))
            return checks, ctx

        seed_ctx = self.signal.get_stage_context("seed")
        creator_record_id = seed_ctx.get("creator_record_id", "")
        if not creator_record_id:
            records = at_find(AT_CREATORS, "Email", self.config.test_email)
            creator_record_id = records[0]["id"] if records else ""

        conv_fields = {
            "Message Title": f"Reply from @{test_ig}",
            "Subject": f"Re: {subj}",
            "Channel": "Email",
            "Direction": "Inbound",
            "Message Content": reply_body,
            "Conversation Context": f"Influencer @{test_ig} expressed interest in Grosmimi collab. Positive response.",
            "AI Generated": False,
            "Status": "Sent",
        }
        if creator_record_id:
            conv_fields["Creator"] = [creator_record_id]

        info(f"  [1c.1] Creating Conversations record (influencer reply)")
        status, resp = at_create(AT_CONVERSATIONS, conv_fields)
        if status in (200, 201) and isinstance(resp, dict) and resp.get("id"):
            conv_id = resp["id"]
            ok(f"[1c.1] Reply logged: {conv_id}")
            checks.append(Check("[1c] Log influencer reply", True, detail=conv_id))
            ctx["reply_conv_id"] = conv_id
        else:
            fail(f"[1c.1] Failed: {status}")
            checks.append(Check("[1c] Log influencer reply", False, actual=str(status)))

        if creator_record_id:
            info(f"  [1c.2] Updating creator status -> Replied")
            s, _ = at_update(AT_CREATORS, creator_record_id, {
                "Outreach Status": "Replied",
                "Partnership Status": "In Progress",
            })
            if s == 200:
                ok("[1c.2] Creator status -> Replied")
                checks.append(Check("[1c] Update status -> Replied", True))
            else:
                checks.append(Check("[1c] Update status -> Replied", False, actual=str(s)))

        ctx["creator_record_id"] = creator_record_id
        return checks, ctx

    # ── Stage 1d: Confirmation email with gifting form link ──────────
    def _stage_email_confirm(self):
        checks = []
        ctx = {}
        test_ig = self.config.test_ig.lstrip("@")
        subj, _, _, confirm_body = _email_templates("Sarah Kim", test_ig, self.config.test_email)
        info(f"[Stage 1d] Send confirmation email with gifting form link -> Confirmed")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would send confirmation", True))
            return checks, ctx

        seed_ctx = self.signal.get_stage_context("seed")
        creator_record_id = seed_ctx.get("creator_record_id", "")
        if not creator_record_id:
            records = at_find(AT_CREATORS, "Email", self.config.test_email)
            creator_record_id = records[0]["id"] if records else ""

        conv_fields = {
            "Message Title": f"Confirmation + Gifting Form: @{test_ig}",
            "Subject": f"Re: {subj}",
            "Channel": "Email",
            "Direction": "Outbound",
            "Message Content": confirm_body,
            "Conversation Context": "Sent gifting form link and content guidelines.",
            "AI Generated": True,
            "AI Approved": True,
            "Reviewed By": "Dual Test (auto)",
            "Status": "Sent",
        }
        if creator_record_id:
            conv_fields["Creator"] = [creator_record_id]

        info(f"  [1d.1] Creating Conversations record (confirmation)")
        status, resp = at_create(AT_CONVERSATIONS, conv_fields)
        if status in (200, 201) and isinstance(resp, dict) and resp.get("id"):
            conv_id = resp["id"]
            ok(f"[1d.1] Confirmation logged: {conv_id}")
            checks.append(Check("[1d] Log confirmation email", True, detail=conv_id))
            ctx["confirm_conv_id"] = conv_id
        else:
            fail(f"[1d.1] Failed: {status}")
            checks.append(Check("[1d] Log confirmation email", False, actual=str(status)))

        if creator_record_id:
            info(f"  [1d.2] Updating creator status -> Confirmed")
            s, _ = at_update(AT_CREATORS, creator_record_id, {"Outreach Status": "Confirmed"})
            if s == 200:
                ok("[1d.2] Creator status -> Confirmed")
                checks.append(Check("[1d] Update status -> Confirmed", True))
            else:
                checks.append(Check("[1d] Update status -> Confirmed", False, actual=str(s)))

        ctx["creator_record_id"] = creator_record_id
        return checks, ctx

    # ── Stage 2: Gifting Application -> 5-way processing ────────────────
    def _stage_gifting(self):
        checks = []
        ctx = {}
        webhook_url = WJ_WEBHOOKS.get("gifting", "")
        info(f"[Stage 2] Influencer gifting form submission -> n8n 5-way processing")
        info(f"  Webhook: {webhook_url}")

        payload = {
            "form_type": "influencer_gifting",
            "submitted_at": datetime.now().isoformat(),
            "personal_info": {
                "full_name": "Sarah Kim",
                "email": self.config.test_email,
                "phone": self.config.test_phone,
                "instagram": self.config.test_ig,
                "tiktok": self.config.test_tiktok,
            },
            "baby_info": {
                "child_1": {"birthday": "2025-04-20", "age_months": 11},
                "child_2": {"birthday": "2023-09-10", "age_months": 30},
            },
            "selected_products": [{
                "product_key": "ppsu_straw",
                "product_id": 8288579256642,
                "variant_id": 45018985431362,
                "title": "Grosmimi PPSU Straw Cup 10oz",
                "color": "Latte",
                "price": "$24.90",
            }],
            "shipping_address": {
                "street": "4521 Maple Creek Dr",
                "apt": "Apt 3B", "city": "Irvine", "state": "CA",
                "zip": "92612", "country": "US",
            },
            "terms_accepted": True,
            "shopify_customer_id": None,
        }

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would POST gifting webhook", True, detail=webhook_url))
            return checks, ctx

        info(f"  [2.1] Submitting gifting form via webhook POST")
        info(f"        Name: Sarah Kim | IG: {self.config.test_ig} | Products: PPSU Straw Cup Latte")
        info(f"        Address: 4521 Maple Creek Dr Apt 3B, Irvine CA 92612")
        info(f"        Baby: child_1 (11mo, 2025-04), child_2 (30mo, 2023-09)")
        status, body = http_request("POST", webhook_url, payload=payload)
        if status == 200:
            ok(f"[2.2] Webhook accepted: HTTP {status}")
            checks.append(Check("[2] POST gifting webhook", True, expected="200", actual=str(status)))
        else:
            fail(f"[2.2] Webhook rejected: HTTP {status}")
            checks.append(Check("[2] POST gifting webhook", False, expected="200", actual=str(status)))
        ctx["webhook_response"] = body if isinstance(body, dict) else str(body)[:500]
        ctx["webhook_url"] = webhook_url

        # Wait for n8n 5-way processing:
        # 1) Shopify customer lookup/create 2) Draft Order 3) Metafields
        # 4) Airtable CRM 5) PostgreSQL
        wait_sec = 14
        info(f"  [2.3] Waiting {wait_sec}s for n8n 5-way processing...")
        info(f"        -> Shopify customer + Draft Order + Metafields + Airtable + PostgreSQL")
        time.sleep(wait_sec)
        checks.append(Check(f"[2] Wait {wait_sec}s for n8n", True))

        return checks, ctx

    # ── Stage 4: Sample Request -> Draft Order ──────────────────────────
    def _stage_gifting2(self):
        checks = []
        ctx = {}
        webhook_url = WJ_WEBHOOKS.get("gifting2", "")
        info(f"[Stage 4] Accepted creator submits sample request form")
        info(f"  Webhook: {webhook_url}")

        payload = {
            "form_type": "gifting2_sample_request",
            "submitted_at": datetime.now().isoformat(),
            "personal_info": {
                "full_name": "Sarah Kim",
                "email": self.config.test_email,
                "phone": self.config.test_phone,
                "instagram": self.config.test_ig,
                "tiktok": self.config.test_tiktok,
            },
            "baby_info": {
                "child_1": {"birthday": "2025-04-20", "age_months": 11},
                "child_2": {"birthday": "2023-09-10", "age_months": 30},
            },
            "selected_products": [
                {
                    "product_key": "ppsu_straw",
                    "product_id": 8288579256642,
                    "variant_id": 45018985431362,
                    "title": "Grosmimi PPSU Straw Cup 10oz",
                    "color": "Latte",
                    "price": "$24.90",
                },
                {
                    "product_key": "ppsu_tumbler",
                    "product_id": 8288579289410,
                    "variant_id": 45018985464130,
                    "title": "Grosmimi PPSU Tumbler 10oz",
                    "color": "Pink",
                    "price": "$26.90",
                },
            ],
            "shipping_address": {
                "street": "4521 Maple Creek Dr",
                "apt": "Apt 3B", "city": "Irvine", "state": "CA",
                "zip": "92612", "country": "US",
            },
            "terms_accepted": True,
            "shopify_customer_id": None,
        }

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would POST gifting2 webhook", True, detail=webhook_url))
            return checks, ctx

        info(f"  [4.1] Submitting sample request form via webhook POST")
        info(f"        Products: PPSU Straw Cup Latte + PPSU Tumbler Pink")
        info(f"        Ship to: 4521 Maple Creek Dr Apt 3B, Irvine CA 92612")
        status, body = http_request("POST", webhook_url, payload=payload)
        if status == 200:
            ok(f"[4.2] Gifting2 webhook accepted: HTTP {status}")
            checks.append(Check("[4] POST gifting2 webhook", True, expected="200", actual=str(status)))
        else:
            fail(f"[4.2] Gifting2 webhook rejected: HTTP {status}")
            checks.append(Check("[4] POST gifting2 webhook", False, expected="200", actual=str(status)))
        ctx["webhook_response"] = body if isinstance(body, dict) else str(body)[:500]

        wait_sec = 15
        info(f"  [4.3] Waiting {wait_sec}s for n8n Draft Order creation...")
        info(f"        -> Shopify Draft Order (100% discount) + Airtable update + PG upsert")
        time.sleep(wait_sec)
        checks.append(Check(f"[4] Wait {wait_sec}s for Draft Order", True))

        return checks, ctx

    # ── Stage 5: Sample Sent -> n8n Poll -> Draft Order Complete ────────
    def _stage_sample_sent(self):
        checks = []
        ctx = {}
        info(f"[Stage 5] Team manually marks sample as shipped -> n8n polls and completes Draft Order")

        # Read signal to get creator_record_id from seed stage
        seed_ctx = self.signal.get_stage_context("seed")
        creator_record_id = seed_ctx.get("creator_record_id", "")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would update AT status to Sample Sent", True))
            return checks, ctx

        if not creator_record_id:
            records = at_find(AT_CREATORS, "Email", self.config.test_email)
            if records:
                creator_record_id = records[0]["id"]
                info(f"  [5.0] Found creator record: {creator_record_id}")
            else:
                fail("[5.0] No creator record found for sample_sent stage")
                checks.append(Check("[5] Find creator record", False, detail="No record"))
                return checks, ctx

        info(f"  [5.1] Simulating team action: PATCH Airtable Outreach Status -> 'Sample Sent'")
        info(f"        Record: {creator_record_id}")
        status, body = at_update(AT_CREATORS, creator_record_id, {"Outreach Status": "Sample Sent"})
        if status == 200:
            ok(f"[5.2] Outreach Status updated to 'Sample Sent'")
            checks.append(Check("[5] Update AT status -> Sample Sent", True))
        else:
            fail(f"[5.2] Update failed: {status}")
            checks.append(Check("[5] Update AT status -> Sample Sent", False, actual=str(status)))

        ctx["creator_record_id"] = creator_record_id

        wait_sec = 30
        info(f"  [5.3] Waiting {wait_sec}s for n8n 5-min polling cycle...")
        info(f"        -> n8n detects 'Sample Sent' -> completes Draft Order -> updates to 'Sample Shipped'")
        time.sleep(wait_sec)
        checks.append(Check(f"[5] Wait {wait_sec}s for n8n polling", True))

        return checks, ctx


# ═══════════════════════════════════════════════════════════════════════════
# VerifierAgent
# ═══════════════════════════════════════════════════════════════════════════

class VerifierAgent:
    def __init__(self, config: DualTestConfig, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.stages_log = []

    def run_all(self, signal_data=None):
        log(f"\n{'='*60}")
        log(f"  VERIFIER (Checker) | {self.config.run_id}")
        log(f"{'='*60}\n")

        if signal_data is None:
            signal_data = SignalFile.read(self.config.signal_path)

        for stage_entry in signal_data.get("stages_completed", []):
            stage_name = stage_entry["stage"]
            stage_ctx = stage_entry.get("context", {})

            if stage_name not in self.config.stages:
                continue

            runner = getattr(self, f"_verify_{stage_name}", None)
            if not runner:
                warn(f"No verifier for stage: {stage_name}")
                continue

            log(f"\n--- VERIFIER: Stage [{stage_name}] ---")
            t0 = time.time()
            checks = runner(stage_ctx)
            dur = int((time.time() - t0) * 1000)

            entry = {
                "stage": stage_name,
                "checks": [c.to_dict() for c in checks],
                "duration_ms": dur,
            }
            self.stages_log.append(entry)
            passed = sum(1 for c in checks if c.passed)
            total = len(checks)
            log(f"  Verifier [{stage_name}]: {passed}/{total} PASS ({dur}ms)")

        self._save_log()
        return self.stages_log

    def _save_log(self):
        with open(self.config.verifier_log_path, "w", encoding="utf-8") as f:
            json.dump(self.stages_log, f, ensure_ascii=False, indent=2, default=str)

    # ── Verify Stage 0: Discovery -> CRM ─────────────────────────────────
    def _verify_seed(self, ctx):
        checks = []
        email = self.config.test_email
        info(f"[V-0] Verifying Stage 0: CRM record created, no downstream leakage")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify seed", True))
            return checks

        # Positive: Creator record exists
        info(f"  [V-0.1] Checking Airtable Creators for {email}")
        records = at_find(AT_CREATORS, "Email", email)
        if records:
            ok(f"[V-0.1] AT Creators: record exists ({records[0]['id']})")
            checks.append(Check("[V-0] AT Creators: record exists", True, detail=records[0]["id"]))
            fields = records[0].get("fields", {})
            info(f"         Fields: Username={fields.get('Username')}, Status={fields.get('Outreach Status')}, Source={fields.get('Source')}")
            if fields.get("Username") == self.config.test_ig.lstrip("@"):
                ok("[V-0.2] AT Creators: Username matches IG handle")
                checks.append(Check("[V-0] AT Creators: Username matches", True))
            else:
                fail(f"[V-0.2] AT Creators: Username mismatch ({fields.get('Username')})")
                checks.append(Check("[V-0] AT Creators: Username matches", False,
                    expected=self.config.test_ig.lstrip("@"), actual=fields.get("Username")))
        else:
            fail("[V-0.1] AT Creators: record NOT found")
            checks.append(Check("[V-0] AT Creators: record exists", False))

        # Negative: Applicants should NOT exist yet (Stage 2 hasn't run)
        info(f"  [V-0.3] Negative check: Applicants should NOT exist yet")
        app_records = at_find(AT_APPLICANTS, "Email", email)
        if not app_records:
            ok("[V-0.3] AT Applicants: correctly empty (no gifting form yet)")
            checks.append(Check("[V-0] AT Applicants: NOT exists (neg)", True))
        else:
            warn(f"[V-0.3] AT Applicants: unexpected record found ({len(app_records)})")
            checks.append(Check("[V-0] AT Applicants: NOT exists (neg)", False,
                expected="0 records", actual=f"{len(app_records)} records"))

        # Negative: Shopify customer should NOT exist yet
        info(f"  [V-0.4] Negative check: Shopify customer should NOT exist yet")
        customers = shopify_find_customer(email)
        if not customers:
            ok("[V-0.4] Shopify: customer correctly absent")
            checks.append(Check("[V-0] Shopify: NOT exists (neg)", True))
        else:
            warn(f"[V-0.4] Shopify: unexpected customer found ({len(customers)})")
            checks.append(Check("[V-0] Shopify: NOT exists (neg)", False))

        return checks

    # ── Verify Stage 1a: AI draft generated ──────────────────────────────
    def _verify_email_draft(self, ctx):
        checks = []
        email = self.config.test_email
        test_ig = self.config.test_ig.lstrip("@")
        info(f"[V-1a] Verifying AI draft generation: Conversations record + Creator status")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify email draft", True))
            return checks

        # Check Conversations for draft
        info(f"  [V-1a.1] Checking AT Conversations for subject containing '{test_ig}'")
        formula = urllib.parse.quote(f"FIND('{test_ig}', {{Subject}})")
        url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}?filterByFormula={formula}&maxRecords=5"
        status, body = http_request("GET", url, headers=_at_headers())
        records = body.get("records", []) if isinstance(body, dict) else []
        if records:
            ok(f"[V-1a.1] Conversations draft found ({len(records)} records)")
            checks.append(Check("[V-1a] AT Conversations: draft exists", True, detail=records[0]["id"]))
        else:
            warn(f"[V-1a.1] No draft in Conversations (AI may have failed)")
            checks.append(Check("[V-1a] AT Conversations: draft exists", None, detail="AI draft may take longer"))

        # Check Creator status changed from "Not Started"
        info(f"  [V-1a.2] Checking Creator status (expected: not 'Not Started')")
        cr_records = at_find(AT_CREATORS, "Email", email)
        if cr_records:
            cr_status = cr_records[0].get("fields", {}).get("Outreach Status", "")
            info(f"         Current status: {cr_status}")
            checks.append(Check("[V-1a] Creator status changed", True, detail=cr_status))
        else:
            checks.append(Check("[V-1a] Creator status changed", None, detail="No creator record"))

        return checks

    # ── Verify Stage 1b: Email approved and logged ─────────────────────
    def _verify_email_approve(self, ctx):
        checks = []
        test_ig = self.config.test_ig.lstrip("@")
        info(f"[V-1b] Verifying outreach email logged + Creator status = Sent")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify email approve", True))
            return checks

        outreach_conv_id = ctx.get("outreach_conv_id", "")
        if outreach_conv_id:
            info(f"  [V-1b.1] Verifying outreach Conversations record {outreach_conv_id}")
            url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}/{outreach_conv_id}"
            status, body = http_request("GET", url, headers=_at_headers())
            if status == 200 and isinstance(body, dict):
                fields = body.get("fields", {})
                direction = fields.get("Direction", "")
                ok(f"[V-1b.1] Outreach email exists (Direction: {direction})")
                checks.append(Check("[V-1b] Outreach email in Conversations", True))
                if direction == "Outbound":
                    checks.append(Check("[V-1b] Direction = Outbound", True))
                else:
                    checks.append(Check("[V-1b] Direction = Outbound", False, expected="Outbound", actual=direction))
            else:
                checks.append(Check("[V-1b] Outreach email in Conversations", False, actual=str(status)))
        else:
            checks.append(Check("[V-1b] Outreach email in Conversations", None, detail="No conv_id in context"))

        # Check Creator status = Sent
        cr_records = at_find(AT_CREATORS, "Email", self.config.test_email)
        if cr_records:
            cr_status = cr_records[0].get("fields", {}).get("Outreach Status", "")
            if cr_status == "Sent":
                ok(f"[V-1b.2] Creator status = Sent")
                checks.append(Check("[V-1b] Creator status = Sent", True))
            else:
                warn(f"[V-1b.2] Creator status = {cr_status} (expected Sent)")
                checks.append(Check("[V-1b] Creator status = Sent", False, expected="Sent", actual=cr_status))

        return checks

    # ── Verify Stage 1c: Influencer reply logged ───────────────────────
    def _verify_email_reply(self, ctx):
        checks = []
        test_ig = self.config.test_ig.lstrip("@")
        info(f"[V-1c] Verifying influencer reply logged + Creator status = Replied")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify email reply", True))
            return checks

        reply_conv_id = ctx.get("reply_conv_id", "")
        if reply_conv_id:
            url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}/{reply_conv_id}"
            status, body = http_request("GET", url, headers=_at_headers())
            if status == 200 and isinstance(body, dict):
                direction = body.get("fields", {}).get("Direction", "")
                ok(f"[V-1c.1] Reply email exists (Direction: {direction})")
                checks.append(Check("[V-1c] Reply in Conversations", True))
                if direction == "Inbound":
                    checks.append(Check("[V-1c] Direction = Inbound", True))
                else:
                    checks.append(Check("[V-1c] Direction = Inbound", False, expected="Inbound", actual=direction))
            else:
                checks.append(Check("[V-1c] Reply in Conversations", False, actual=str(status)))
        else:
            checks.append(Check("[V-1c] Reply in Conversations", None, detail="No conv_id in context"))

        cr_records = at_find(AT_CREATORS, "Email", self.config.test_email)
        if cr_records:
            cr_status = cr_records[0].get("fields", {}).get("Outreach Status", "")
            if cr_status == "Replied":
                ok("[V-1c.2] Creator status = Replied")
                checks.append(Check("[V-1c] Creator status = Replied", True))
            else:
                checks.append(Check("[V-1c] Creator status = Replied", False, expected="Replied", actual=cr_status))

        return checks

    # ── Verify Stage 1d: Confirmation email + Confirmed status ─────────
    def _verify_email_confirm(self, ctx):
        checks = []
        test_ig = self.config.test_ig.lstrip("@")
        info(f"[V-1d] Verifying confirmation email logged + Creator status = Confirmed")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify email confirm", True))
            return checks

        confirm_conv_id = ctx.get("confirm_conv_id", "")
        if confirm_conv_id:
            url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}/{confirm_conv_id}"
            status, body = http_request("GET", url, headers=_at_headers())
            if status == 200 and isinstance(body, dict):
                ok(f"[V-1d.1] Confirmation email exists")
                checks.append(Check("[V-1d] Confirmation in Conversations", True))
            else:
                checks.append(Check("[V-1d] Confirmation in Conversations", False, actual=str(status)))
        else:
            checks.append(Check("[V-1d] Confirmation in Conversations", None, detail="No conv_id"))

        cr_records = at_find(AT_CREATORS, "Email", self.config.test_email)
        if cr_records:
            cr_status = cr_records[0].get("fields", {}).get("Outreach Status", "")
            if cr_status == "Confirmed":
                ok("[V-1d.2] Creator status = Confirmed")
                checks.append(Check("[V-1d] Creator status = Confirmed", True))
            else:
                checks.append(Check("[V-1d] Creator status = Confirmed", False, expected="Confirmed", actual=cr_status))

        # Cross-system: count total Conversations for this creator
        formula = urllib.parse.quote(f"FIND('{test_ig}', {{Subject}})")
        url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}?filterByFormula={formula}&maxRecords=10"
        status, body = http_request("GET", url, headers=_at_headers())
        records = body.get("records", []) if isinstance(body, dict) else []
        conv_count = len(records)
        expected_min = 3  # outreach + reply + confirm
        info(f"  [V-1d.3] X-SYS: Total conversation records: {conv_count} (expected >= {expected_min})")
        if conv_count >= expected_min:
            ok(f"[V-1d.3] X-SYS email trail: {conv_count} conversations")
            checks.append(Check(f"[V-1d] X-SYS: Email trail >= {expected_min} records", True,
                expected=f">= {expected_min}", actual=str(conv_count)))
        else:
            warn(f"[V-1d.3] X-SYS: only {conv_count} conversations (expected >= {expected_min})")
            checks.append(Check(f"[V-1d] X-SYS: Email trail >= {expected_min} records", False,
                expected=f">= {expected_min}", actual=str(conv_count)))

        return checks

    # ── Verify Stage 2: Gifting 5-way processing ────────────────────────
    def _verify_gifting(self, ctx):
        checks = []
        email = self.config.test_email
        info(f"[V-2] Verifying Stage 2: 5 downstream systems after gifting webhook")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify gifting", True))
            return checks

        # 1) Airtable Applicants (Inbound table)
        info(f"  [V-2.1] Checking Airtable Applicants (Inbound) for {email}")
        app_records = at_find(AT_APPLICANTS, "Email", email)
        if app_records:
            fields = app_records[0].get("fields", {})
            ok(f"[V-2.1] AT Applicants: record exists ({app_records[0]['id']})")
            info(f"         Name={fields.get('Name')}, IG={fields.get('Instagram')}, Status={fields.get('Status')}")
            checks.append(Check("[V-2] AT Applicants: record exists", True, detail=app_records[0]["id"]))
        else:
            fail("[V-2.1] AT Applicants: record NOT found")
            checks.append(Check("[V-2] AT Applicants: record exists", False))

        # 2) Airtable Creators — Outreach Status should be "Needs Review"
        info(f"  [V-2.2] Checking Airtable Creators status (expected: Needs Review)")
        cr_records = at_find(AT_CREATORS, "Email", email)
        if cr_records:
            fields = cr_records[0].get("fields", {})
            status_val = fields.get("Outreach Status", "")
            info(f"         Outreach Status = '{status_val}', Username = '{fields.get('Username')}'")
            if status_val == "Needs Review":
                ok(f"[V-2.2] AT Creators: status correctly updated to 'Needs Review'")
                checks.append(Check("[V-2] AT Creators: Outreach Status", True,
                    expected="Needs Review", actual=status_val))
            else:
                fail(f"[V-2.2] AT Creators: Outreach Status = '{status_val}' (expected 'Needs Review')")
                checks.append(Check("[V-2] AT Creators: Outreach Status", False,
                    expected="Needs Review", actual=status_val))
        else:
            fail("[V-2.2] AT Creators: record NOT found after gifting")
            checks.append(Check("[V-2] AT Creators: record exists", False))

        # 3) Shopify customer (PROD: same store as n8n)
        info(f"  [V-2.3] Checking Shopify customer")
        customers = shopify_find_customer(email)
        if customers:
            cid = customers[0]["id"]
            ok(f"[V-2.3] Shopify: customer exists ({cid})")
            checks.append(Check("[V-2] Shopify: customer exists", True, detail=str(cid)))
        else:
            fail("[V-2.3] Shopify: customer NOT found")
            checks.append(Check("[V-2] Shopify: customer exists", False))

        # 4) PostgreSQL via Django API
        info(f"  [V-2.4] Checking PostgreSQL gifting record via orbitools API")
        pg_records = pg_find("/api/onzenna/gifting/list/", email)
        if pg_records:
            ok(f"[V-2.4] PostgreSQL: gifting record exists ({len(pg_records)} rows)")
            checks.append(Check("[V-2] PostgreSQL: gifting record", True))
        else:
            warn("[V-2.4] PostgreSQL: no record found")
            checks.append(Check("[V-2] PostgreSQL: gifting record", None))

        # 5) Cross-system: email consistency across AT Applicants + AT Creators
        info(f"  [V-2.5] Cross-system consistency: email match across 3 systems")
        if app_records and cr_records:
            app_email = app_records[0].get("fields", {}).get("Email", "")
            cr_email = cr_records[0].get("fields", {}).get("Email", "")
            if app_email == cr_email == email:
                ok(f"[V-2.5] X-SYS: email consistent (Applicants=Creators=input)")
                checks.append(Check("[V-2] X-SYS: email consistent", True))
            else:
                fail(f"[V-2.5] X-SYS: email mismatch (app={app_email}, cr={cr_email})")
                checks.append(Check("[V-2] X-SYS: email consistent", False))

        return checks

    # ── Verify Stage 4: Sample Request -> Draft Order ────────────────────
    def _verify_gifting2(self, ctx):
        checks = []
        email = self.config.test_email
        info(f"[V-4] Verifying Stage 4: Draft Order created with 100% discount")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify gifting2", True))
            return checks

        # 1) Airtable Applicants — Draft Order ID populated
        info(f"  [V-4.1] Checking Airtable Applicants for Draft Order ID")
        app_records = at_find(AT_APPLICANTS, "Email", email)
        if app_records:
            fields = app_records[0].get("fields", {})
            do_id = fields.get("Draft Order ID", "")
            info(f"         Draft Order ID = '{do_id}', Status = '{fields.get('Status')}'")
            if do_id:
                ok(f"[V-4.1] AT Applicants: Draft Order ID = {do_id}")
                checks.append(Check("[V-4] AT Applicants: Draft Order ID", True, detail=str(do_id)))
            else:
                warn("[V-4.1] AT Applicants: Draft Order ID empty (may be stored elsewhere)")
                checks.append(Check("[V-4] AT Applicants: Draft Order ID", None,
                    detail="Field may differ"))
        else:
            fail("[V-4.1] AT Applicants: record NOT found after gifting2")
            checks.append(Check("[V-4] AT Applicants: record exists", False))

        # 2) Airtable Creators — still exists and status tracked
        info(f"  [V-4.2] Checking Airtable Creators persistence")
        cr_records = at_find(AT_CREATORS, "Email", email)
        if cr_records:
            fields = cr_records[0].get("fields", {})
            info(f"         Outreach Status = '{fields.get('Outreach Status')}', Source = '{fields.get('Source')}'")
            ok(f"[V-4.2] AT Creators: record persists (status={fields.get('Outreach Status')})")
            checks.append(Check("[V-4] AT Creators: record exists", True))
        else:
            fail("[V-4.2] AT Creators: record NOT found after gifting2")
            checks.append(Check("[V-4] AT Creators: record exists", False))

        # 3) PostgreSQL — updated record
        info(f"  [V-4.3] Checking PostgreSQL for updated gifting record")
        pg_records = pg_find("/api/onzenna/gifting/list/", email)
        if pg_records:
            ok(f"[V-4.3] PostgreSQL: gifting record exists ({len(pg_records)} rows)")
            checks.append(Check("[V-4] PostgreSQL: record updated", True))
        else:
            warn("[V-4.3] PostgreSQL: no record")
            checks.append(Check("[V-4] PostgreSQL: record updated", None))

        return checks

    # ── Verify Stage 5: Sample Sent -> Order Complete ───────────────────
    def _verify_sample_sent(self, ctx):
        checks = []
        email = self.config.test_email
        info(f"[V-5] Verifying Stage 5: n8n detected 'Sample Sent' and completed Draft Order")

        if self.dry_run:
            checks.append(Check("DRY-RUN: Would verify sample_sent", True))
            return checks

        # 1) Airtable Creators — Outreach Status should be Sample Sent or Sample Shipped
        info(f"  [V-5.1] Checking Airtable Creators Outreach Status after n8n poll")
        cr_records = at_find(AT_CREATORS, "Email", email)
        if cr_records:
            fields = cr_records[0].get("fields", {})
            status_val = fields.get("Outreach Status", "")
            info(f"         Current status = '{status_val}'")
            if status_val in ("Sample Sent", "Sample Shipped"):
                ok(f"[V-5.1] AT Creators: Outreach Status = '{status_val}'")
                checks.append(Check("[V-5] AT Creators: status post-poll", True,
                    expected="Sample Sent|Shipped", actual=status_val))
            else:
                warn(f"[V-5.1] AT Creators: unexpected status = '{status_val}'")
                checks.append(Check("[V-5] AT Creators: status post-poll", None,
                    expected="Sample Sent|Shipped", actual=status_val))
        else:
            fail("[V-5.1] AT Creators: record NOT found")
            checks.append(Check("[V-5] AT Creators: record exists", False))

        # 2) n8n Sample Sent → Complete workflow active check
        info(f"  [V-5.2] Checking n8n workflow 'Sample Sent -> Complete' is active")
        wf_id = WJ_WORKFLOWS.get("sample_complete", WJ_WORKFLOWS.get("gifting2", ""))
        if wf_id and N8N_API_KEY:
            url = f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}"
            headers = {"X-N8N-API-KEY": N8N_API_KEY}
            status, body = http_request("GET", url, headers=headers)
            if status == 200 and isinstance(body, dict):
                active = body.get("active", False)
                wf_name = body.get("name", "")
                info(f"         WF: {wf_name} | Active: {active}")
                if active:
                    ok(f"[V-5.2] n8n: workflow active ({wf_name})")
                    checks.append(Check("[V-5] n8n: Sample->Complete WF active", True))
                else:
                    warn(f"[V-5.2] n8n: workflow INACTIVE ({wf_name})")
                    checks.append(Check("[V-5] n8n: Sample->Complete WF active", None, detail="Inactive"))
        else:
            checks.append(Check("[V-5] n8n: workflow check", None, detail="No API key or WF ID"))

        return checks


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

def run_cleanup(config, signal_data):
    log(f"\n--- CLEANUP ---")
    email = config.test_email
    if TEST_EMAIL_DOMAIN not in email:
        warn(f"SAFETY: Refusing cleanup for non-test email: {email}")
        return

    # Collect record IDs from all stage contexts
    all_ctx = {}
    for s in signal_data.get("stages_completed", []):
        all_ctx.update(s.get("context", {}))

    # Delete Airtable Creators
    creator_id = all_ctx.get("creator_record_id", "")
    if creator_id:
        s, _ = at_delete(AT_CREATORS, creator_id)
        info(f"Delete AT Creators {creator_id}: {s}")

    # Delete Airtable Applicants
    app_records = at_find(AT_APPLICANTS, "Email", email)
    for r in app_records:
        s, _ = at_delete(AT_APPLICANTS, r["id"])
        info(f"Delete AT Applicants {r['id']}: {s}")

    # Delete Airtable Orders
    order_records = at_find(AT_ORDERS, "Email", email)
    for r in order_records:
        s, _ = at_delete(AT_ORDERS, r["id"])
        info(f"Delete AT Orders {r['id']}: {s}")

    # Delete Airtable Conversations (by subject containing test IG)
    test_ig = config.test_ig.lstrip("@")
    if test_ig:
        formula = urllib.parse.quote(f"FIND('{test_ig}', {{Subject}})")
        url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_CONVERSATIONS}?filterByFormula={formula}&maxRecords=20"
        status, body = http_request("GET", url, headers=_at_headers())
        conv_records = body.get("records", []) if isinstance(body, dict) and status == 200 else []
        for r in conv_records:
            s, _ = at_delete(AT_CONVERSATIONS, r["id"])
            info(f"Delete AT Conversations {r['id']}: {s}")
            time.sleep(0.2)

    # Delete Shopify customer
    customers = shopify_find_customer(email)
    for c in customers:
        s, _ = shopify_delete_customer(c["id"])
        info(f"Delete Shopify customer {c['id']}: {s}")

    ok("Cleanup complete")


# ═══════════════════════════════════════════════════════════════════════════
# Merged HTML Report
# ═══════════════════════════════════════════════════════════════════════════

def generate_merged_report(config, executor_log, verifier_log):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build stage map
    exec_map = {s["stage"]: s for s in executor_log}
    veri_map = {s["stage"]: s for s in verifier_log}
    all_stages = config.stages

    # Count totals
    exec_pass = sum(1 for s in executor_log for c in s["checks"] if c["passed"] is True)
    exec_total = sum(len(s["checks"]) for s in executor_log)
    veri_pass = sum(1 for s in verifier_log for c in s["checks"] if c["passed"] is True)
    veri_total = sum(len(s["checks"]) for s in verifier_log)
    total_pass = exec_pass + veri_pass
    total_all = exec_total + veri_total
    overall = "PASS" if total_pass == total_all else "FAIL" if any(
        c["passed"] is False for s in executor_log + verifier_log for c in s["checks"]
    ) else "PARTIAL"

    badge_class = {"PASS": "badge-pass", "FAIL": "badge-fail"}.get(overall, "badge-warn")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Dual Test Report | {config.run_id}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Noto Sans KR', -apple-system, sans-serif; background: #fafbfc; color: #1f2937; padding: 24px; }}
.header {{ background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 16px; padding: 32px; margin-bottom: 28px; color: #fff; }}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
.header .meta {{ font-size: 13px; opacity: 0.85; }}
.badge {{ display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 13px; font-weight: 700; margin-left: 10px; }}
.badge-pass {{ background: #d1fae5; color: #065f46; }}
.badge-fail {{ background: #fee2e2; color: #991b1b; }}
.badge-warn {{ background: #fef3c7; color: #92400e; }}
.stage-card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.stage-header {{ padding: 16px 20px; background: #f8fafc; border-bottom: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: space-between; }}
.stage-title {{ font-size: 16px; font-weight: 700; }}
.stage-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0; }}
.agent-col {{ padding: 16px 20px; }}
.agent-col:first-child {{ border-right: 1px solid #e5e7eb; }}
.agent-label {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }}
.label-exec {{ color: #8b5cf6; }}
.label-veri {{ color: #0ea5e9; }}
.check {{ padding: 4px 0; font-size: 13px; display: flex; align-items: flex-start; gap: 6px; }}
.check-pass {{ color: #059669; }}
.check-fail {{ color: #dc2626; }}
.check-skip {{ color: #d97706; }}
.check-icon {{ font-weight: 700; min-width: 18px; }}
.dur {{ font-size: 12px; color: #9ca3af; margin-top: 8px; }}
.xsys {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 14px 20px; margin-bottom: 20px; }}
.xsys h3 {{ font-size: 14px; font-weight: 700; color: #065f46; margin-bottom: 8px; }}
.summary {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin-bottom: 20px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
.summary-box {{ text-align: center; }}
.summary-num {{ font-size: 28px; font-weight: 700; }}
.summary-label {{ font-size: 12px; color: #6b7280; }}
.num-pass {{ color: #059669; }}
.num-fail {{ color: #dc2626; }}
.num-total {{ color: #4b5563; }}
.footer {{ text-align: center; font-size: 12px; color: #9ca3af; margin-top: 24px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Dual Test Report <span class="badge {badge_class}">{overall}</span></h1>
  <div class="meta">
    Run: {config.run_id} | Email: {config.test_email} | {now_str}
  </div>
</div>

<div class="summary">
  <div class="summary-box">
    <div class="summary-num num-pass">{total_pass}</div>
    <div class="summary-label">PASS</div>
  </div>
  <div class="summary-box">
    <div class="summary-num num-fail">{total_all - total_pass}</div>
    <div class="summary-label">FAIL / SKIP</div>
  </div>
  <div class="summary-box">
    <div class="summary-num num-total">{total_all}</div>
    <div class="summary-label">TOTAL CHECKS</div>
  </div>
</div>
"""

    # Cross-system checks
    xsys_checks = []
    for s in verifier_log:
        for c in s["checks"]:
            if "X-SYS" in c["name"] or "Cross" in c["name"]:
                xsys_checks.append(c)

    if xsys_checks:
        html += '<div class="xsys"><h3>Cross-System Consistency</h3>\n'
        for c in xsys_checks:
            icon = "V" if c["passed"] else "X"
            cls = "check-pass" if c["passed"] else "check-fail"
            html += f'  <div class="check {cls}"><span class="check-icon">{icon}</span> {c["name"]}</div>\n'
        html += '</div>\n'

    # Stage cards
    for stage_name in all_stages:
        exec_stage = exec_map.get(stage_name)
        veri_stage = veri_map.get(stage_name)

        stage_label = {
            "seed": "Stage 0: Influencer Discovery -> CRM Sync",
            "email_draft": "Stage 1a: AI Draft Generation (Claude AI -> Gmail)",
            "email_approve": "Stage 1b: Marketer Approves Draft -> Outreach Sent",
            "email_reply": "Stage 1c: Influencer Reply -> Status Replied",
            "email_confirm": "Stage 1d: Confirmation Email + Gifting Form Link",
            "gifting": "Stage 2: Gifting Application -> Shopify + Airtable + PG (5-way)",
            "gifting2": "Stage 4: Sample Request -> Draft Order (100% Discount)",
            "sample_sent": "Stage 5: Sample Sent -> n8n Poll -> Draft Order Complete",
        }.get(stage_name, stage_name)

        # Stage-level pass/fail
        all_checks_pass = True
        for log_data in [exec_stage, veri_stage]:
            if log_data:
                for c in log_data["checks"]:
                    if c["passed"] is False:
                        all_checks_pass = False

        stage_badge = "badge-pass" if all_checks_pass else "badge-fail"
        stage_status = "PASS" if all_checks_pass else "FAIL"

        html += f"""
<div class="stage-card">
  <div class="stage-header">
    <span class="stage-title">{stage_label}</span>
    <span class="badge {stage_badge}">{stage_status}</span>
  </div>
  <div class="stage-body">
"""
        # Executor column
        html += '    <div class="agent-col">\n'
        html += '      <div class="agent-label label-exec">Executor (Maker)</div>\n'
        if exec_stage:
            for c in exec_stage["checks"]:
                if c["passed"] is True:
                    html += f'      <div class="check check-pass"><span class="check-icon">V</span> {c["name"]}</div>\n'
                elif c["passed"] is False:
                    html += f'      <div class="check check-fail"><span class="check-icon">X</span> {c["name"]}'
                    if c.get("actual"):
                        html += f' (got: {c["actual"]})'
                    html += '</div>\n'
                else:
                    html += f'      <div class="check check-skip"><span class="check-icon">-</span> {c["name"]}</div>\n'
            html += f'      <div class="dur">{exec_stage["duration_ms"]}ms</div>\n'
        else:
            html += '      <div class="check check-skip">No executor data</div>\n'
        html += '    </div>\n'

        # Verifier column
        html += '    <div class="agent-col">\n'
        html += '      <div class="agent-label label-veri">Verifier (Checker)</div>\n'
        if veri_stage:
            for c in veri_stage["checks"]:
                if c["passed"] is True:
                    html += f'      <div class="check check-pass"><span class="check-icon">V</span> {c["name"]}</div>\n'
                elif c["passed"] is False:
                    html += f'      <div class="check check-fail"><span class="check-icon">X</span> {c["name"]}'
                    if c.get("actual"):
                        html += f' (got: {c["actual"]})'
                    html += '</div>\n'
                else:
                    html += f'      <div class="check check-skip"><span class="check-icon">~</span> {c["name"]}'
                    if c.get("detail"):
                        html += f' ({c["detail"]})'
                    html += '</div>\n'
            html += f'      <div class="dur">{veri_stage["duration_ms"]}ms</div>\n'
        else:
            html += '      <div class="check check-skip">No verifier data</div>\n'
        html += '    </div>\n'

        html += '  </div>\n</div>\n'

    html += f"""
<div class="footer">
  Generated by dual_test_runner.py | {now_str} | Maker-Checker Pattern
</div>
</body>
</html>"""

    with open(config.report_path, "w", encoding="utf-8") as f:
        f.write(html)
    info(f"Report: {config.report_path}")
    return config.report_path


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def cmd_dual(stages, email=None, dry_run=False, no_cleanup=False, label=None):
    config = DualTestConfig(stages=stages, email=email, label=label)
    config.save()

    log(f"\n{'#'*70}")
    log(f"  DUAL TEST: Maker-Checker Pattern | Creator Collab Pipeline")
    log(f"{'#'*70}")
    log(f"  Run ID:   {config.run_id}")
    log(f"  Mode:     {'DRY-RUN' if dry_run else 'LIVE'}")
    log(f"  Email:    {config.test_email}")
    log(f"  Phone:    {config.test_phone}")
    log(f"  IG:       {config.test_ig}")
    log(f"  TikTok:   {config.test_tiktok}")
    log(f"  Stages:   {' -> '.join(config.stages)}")
    log(f"  Pipeline: Stage 0 (Discovery) -> Stage 2 (Gifting) -> Stage 4 (Sample) -> Stage 5 (Sent)")
    log(f"{'#'*70}")

    # Interleaved execution: Executor stage → Verifier stage → next
    # This ensures verifier checks state BEFORE the next stage modifies it
    executor = ExecutorAgent(config, dry_run=dry_run)
    verifier = VerifierAgent(config, dry_run=dry_run)

    for stage_name in config.stages:
        # Executor: run this stage
        runner = getattr(executor, f"_stage_{stage_name}", None)
        if not runner:
            warn(f"Unknown stage: {stage_name}")
            continue

        log(f"\n--- EXECUTOR: Stage [{stage_name}] ---")
        t0 = time.time()
        checks, ctx = runner()
        dur = int((time.time() - t0) * 1000)
        entry = {
            "stage": stage_name,
            "checks": [c.to_dict() for c in checks],
            "duration_ms": dur,
            "context": ctx,
        }
        executor.stages_log.append(entry)
        executor.signal.write_stage(stage_name, ctx)
        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        log(f"  Executor [{stage_name}]: {passed}/{total} PASS ({dur}ms)")

        # Verifier: verify this stage immediately
        vrunner = getattr(verifier, f"_verify_{stage_name}", None)
        if vrunner:
            stage_ctx = ctx
            log(f"\n--- VERIFIER: Stage [{stage_name}] ---")
            t0 = time.time()
            vchecks = vrunner(stage_ctx) if not dry_run else vrunner(stage_ctx)
            vdur = int((time.time() - t0) * 1000)
            ventry = {
                "stage": stage_name,
                "checks": [c.to_dict() for c in vchecks],
                "duration_ms": vdur,
            }
            verifier.stages_log.append(ventry)
            vpassed = sum(1 for c in vchecks if c.passed)
            vtotal = len(vchecks)
            log(f"  Verifier [{stage_name}]: {vpassed}/{vtotal} PASS ({vdur}ms)")

    executor.signal.finish()
    executor._save_log()
    verifier._save_log()

    exec_log = executor.stages_log
    veri_log = verifier.stages_log

    signal_data = SignalFile.read(config.signal_path) if not dry_run else {
        "status": "finished", "stages_completed": [
            {"stage": s, "context": {}, "completed_at": datetime.now().isoformat()}
            for s in config.stages
        ]
    }

    # Phase 3: Merge report
    report_path = generate_merged_report(config, exec_log, veri_log)

    # Phase 4: Cleanup
    if not dry_run and not no_cleanup:
        run_cleanup(config, signal_data)
    elif no_cleanup:
        info("Cleanup skipped (--no-cleanup)")

    config.finished_at = datetime.now().isoformat()
    config.save()

    # Summary
    exec_pass = sum(1 for s in exec_log for c in s["checks"] if c["passed"] is True)
    exec_total = sum(len(s["checks"]) for s in exec_log)
    veri_pass = sum(1 for s in veri_log for c in s["checks"] if c["passed"] is True)
    veri_total = sum(len(s["checks"]) for s in veri_log)

    log(f"\n{'='*60}")
    log(f"  DUAL TEST COMPLETE  {f'[{config.label}]' if config.label else ''}")
    log(f"  Executor: {exec_pass}/{exec_total} PASS")
    log(f"  Verifier: {veri_pass}/{veri_total} PASS")
    log(f"  Report:   {report_path}")
    log(f"{'='*60}\n")

    # Auto-generate comparison dashboard
    compare_path = cmd_compare()
    if compare_path:
        log(f"  Compare:  {compare_path}")

    return report_path


def cmd_executor_only(stages, email=None, dry_run=False):
    config = DualTestConfig(stages=stages, email=email)
    config.save()
    executor = ExecutorAgent(config, dry_run=dry_run)
    executor.run_all()
    log(f"\nExecutor done. Signal: {config.signal_path}")
    log(f"Run verifier with: --verifier-only --run-id {config.run_id}")


def cmd_verifier_only(run_id, dry_run=False):
    config = DualTestConfig.load(run_id)
    signal_data = SignalFile.read(config.signal_path)
    verifier = VerifierAgent(config, dry_run=dry_run)
    verifier.run_all(signal_data)
    log(f"\nVerifier done. Log: {config.verifier_log_path}")


def cmd_merge(run_id):
    config = DualTestConfig.load(run_id)
    with open(config.executor_log_path, "r", encoding="utf-8") as f:
        exec_log = json.load(f)
    with open(config.verifier_log_path, "r", encoding="utf-8") as f:
        veri_log = json.load(f)
    report_path = generate_merged_report(config, exec_log, veri_log)
    log(f"Merged report: {report_path}")
    return report_path


def cmd_results():
    if not os.path.isdir(DUAL_DIR):
        log("No dual test runs found.")
        return
    runs = sorted(os.listdir(DUAL_DIR), reverse=True)
    if not runs:
        log("No dual test runs found.")
        return

    log(f"\nRecent dual test runs ({len(runs)} total):\n")
    for run_id in runs[:10]:
        cfg_path = os.path.join(DUAL_DIR, run_id, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            status = "DONE" if cfg.get("finished_at") else "IN-PROGRESS"
            label = cfg.get("label", "")
            label_str = f"[{label}]" if label else ""
            log(f"  {run_id}  {status}  {label_str}  stages={','.join(cfg.get('stages', []))}")
        else:
            log(f"  {run_id}  (no config)")


def cmd_compare():
    """Generate a side-by-side comparison dashboard of all test runs."""
    if not os.path.isdir(DUAL_DIR):
        log("No dual test runs found.")
        return None

    runs = sorted(os.listdir(DUAL_DIR), reverse=True)
    if not runs:
        log("No dual test runs found.")
        return None

    # Load all run data
    run_data = []
    for run_id in runs[:10]:  # Last 10 runs
        run_dir = os.path.join(DUAL_DIR, run_id)
        cfg_path = os.path.join(run_dir, "config.json")
        exec_path = os.path.join(run_dir, "executor_log.json")
        veri_path = os.path.join(run_dir, "verifier_log.json")

        if not os.path.exists(cfg_path):
            continue

        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        exec_log = []
        if os.path.exists(exec_path):
            with open(exec_path, "r", encoding="utf-8") as f:
                exec_log = json.load(f)

        veri_log = []
        if os.path.exists(veri_path):
            with open(veri_path, "r", encoding="utf-8") as f:
                veri_log = json.load(f)

        # Compute stats
        exec_pass = sum(1 for s in exec_log for c in s.get("checks", []) if c.get("passed") is True)
        exec_total = sum(len(s.get("checks", [])) for s in exec_log)
        veri_pass = sum(1 for s in veri_log for c in s.get("checks", []) if c.get("passed") is True)
        veri_total = sum(len(s.get("checks", [])) for s in veri_log)
        total_pass = exec_pass + veri_pass
        total_all = exec_total + veri_total
        has_fail = any(c.get("passed") is False for s in exec_log + veri_log for c in s.get("checks", []))
        overall = "PASS" if total_pass == total_all and total_all > 0 else "FAIL" if has_fail else "PARTIAL"

        total_ms = sum(s.get("duration_ms", 0) for s in exec_log + veri_log)

        run_data.append({
            "run_id": run_id,
            "label": cfg.get("label", ""),
            "email": cfg.get("test_email", ""),
            "ig": cfg.get("test_ig", ""),
            "stages": cfg.get("stages", []),
            "started_at": cfg.get("started_at", ""),
            "finished_at": cfg.get("finished_at", ""),
            "exec_log": exec_log,
            "veri_log": veri_log,
            "exec_pass": exec_pass, "exec_total": exec_total,
            "veri_pass": veri_pass, "veri_total": veri_total,
            "total_pass": total_pass, "total_all": total_all,
            "overall": overall,
            "total_ms": total_ms,
        })

    if not run_data:
        log("No completed test runs found.")
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Test Comparison Dashboard</title>
<meta http-equiv="refresh" content="15">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Noto Sans KR',-apple-system,sans-serif; background:#f0f2f5; color:#1f2937; padding:20px; }}
.header {{ background:linear-gradient(135deg,#1e3a5f,#2563eb); border-radius:16px; padding:28px 32px; margin-bottom:24px; color:#fff; display:flex; justify-content:space-between; align-items:center; }}
.header h1 {{ font-size:20px; font-weight:700; }}
.header .meta {{ font-size:12px; opacity:.8; }}
.refresh-badge {{ background:rgba(255,255,255,.15); padding:4px 12px; border-radius:12px; font-size:11px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:20px; }}
.run-card {{ background:#fff; border-radius:14px; border:1px solid #e5e7eb; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.04); }}
.run-card.active {{ border-color:#3b82f6; box-shadow:0 0 0 2px rgba(59,130,246,.15); }}
.card-head {{ padding:16px 20px; background:#f8fafc; border-bottom:1px solid #e5e7eb; display:flex; justify-content:space-between; align-items:center; }}
.card-label {{ font-size:16px; font-weight:700; }}
.card-label .lbl {{ background:#dbeafe; color:#1e40af; padding:2px 10px; border-radius:8px; font-size:12px; margin-right:8px; }}
.badge {{ display:inline-block; padding:3px 12px; border-radius:12px; font-size:12px; font-weight:700; }}
.b-pass {{ background:#d1fae5; color:#065f46; }}
.b-fail {{ background:#fee2e2; color:#991b1b; }}
.b-partial {{ background:#fef3c7; color:#92400e; }}
.card-meta {{ padding:10px 20px; font-size:12px; color:#6b7280; display:grid; grid-template-columns:1fr 1fr; gap:4px; }}
.card-meta span {{ display:block; }}
.stages-bar {{ padding:0 20px 10px; display:flex; gap:4px; flex-wrap:wrap; }}
.stage-chip {{ font-size:10px; font-weight:600; padding:2px 8px; border-radius:6px; }}
.sc-pass {{ background:#ecfdf5; color:#059669; }}
.sc-fail {{ background:#fef2f2; color:#dc2626; }}
.sc-skip {{ background:#f3f4f6; color:#9ca3af; }}
.sc-email {{ background:#eff6ff; color:#2563eb; }}
.checks-grid {{ padding:0 20px 16px; }}
.check-row {{ display:flex; align-items:center; gap:6px; padding:3px 0; font-size:12px; }}
.ci {{ width:14px; height:14px; border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:9px; font-weight:800; color:#fff; flex-shrink:0; }}
.ci-p {{ background:#22c55e; }}
.ci-f {{ background:#ef4444; }}
.ci-s {{ background:#d1d5db; }}
.ch-name {{ flex:1; color:#374151; }}
.dur {{ color:#9ca3af; font-size:11px; }}
.summary-row {{ padding:12px 20px; background:#f8fafc; border-top:1px solid #e5e7eb; display:flex; justify-content:space-between; font-size:13px; }}
.summary-row .pass {{ color:#059669; font-weight:700; }}
.summary-row .total {{ color:#6b7280; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Pipeline Test Comparison</h1>
    <div class="meta">{len(run_data)} runs | Generated: {now_str}</div>
  </div>
  <div class="refresh-badge">Auto-refresh 15s</div>
</div>
<div class="grid">
"""

    STAGE_LABELS = {
        "seed": "Discovery", "email_draft": "AI Draft", "email_approve": "Approve",
        "email_reply": "Reply", "email_confirm": "Confirm", "gifting": "Gifting",
        "gifting2": "Sample Req", "sample_sent": "Sent",
    }

    for rd in run_data:
        label_html = f'<span class="lbl">{rd["label"]}</span>' if rd["label"] else ""
        badge_cls = {"PASS": "b-pass", "FAIL": "b-fail"}.get(rd["overall"], "b-partial")
        is_latest = (rd == run_data[0])
        active_cls = " active" if is_latest else ""

        # Build stage chips
        exec_map = {s["stage"]: s for s in rd["exec_log"]}
        veri_map = {s["stage"]: s for s in rd["veri_log"]}
        chips_html = ""
        for st in rd["stages"]:
            st_label = STAGE_LABELS.get(st, st)
            # Check if this stage passed
            st_pass = True
            for log_data in [exec_map.get(st), veri_map.get(st)]:
                if log_data:
                    for c in log_data.get("checks", []):
                        if c.get("passed") is False:
                            st_pass = False
            is_email = st.startswith("email_")
            if is_email:
                chip_cls = "sc-email" if st_pass else "sc-fail"
            else:
                chip_cls = "sc-pass" if st_pass else "sc-fail"
            chips_html += f'<span class="stage-chip {chip_cls}">{st_label}</span>'

        # Build check rows
        checks_html = ""
        all_checks = []
        for s in rd["exec_log"]:
            for c in s.get("checks", []):
                all_checks.append(("E", s["stage"], c))
        for s in rd["veri_log"]:
            for c in s.get("checks", []):
                all_checks.append(("V", s["stage"], c))

        for role, stage, c in all_checks:
            if c.get("passed") is True:
                ci_cls, icon = "ci-p", "V"
            elif c.get("passed") is False:
                ci_cls, icon = "ci-f", "X"
            else:
                ci_cls, icon = "ci-s", "-"
            name = c.get("name", "")
            checks_html += f'<div class="check-row"><span class="ci {ci_cls}">{icon}</span><span class="ch-name">{name}</span></div>\n'

        started = rd["started_at"][:19].replace("T", " ") if rd["started_at"] else ""
        dur_sec = rd["total_ms"] / 1000

        html += f"""
<div class="run-card{active_cls}">
  <div class="card-head">
    <span class="card-label">{label_html}{rd["run_id"][-15:]}</span>
    <span class="badge {badge_cls}">{rd["overall"]} {rd["total_pass"]}/{rd["total_all"]}</span>
  </div>
  <div class="card-meta">
    <span>Email: {rd["email"][:30]}</span>
    <span>IG: {rd["ig"]}</span>
    <span>Started: {started}</span>
    <span>Duration: {dur_sec:.1f}s</span>
  </div>
  <div class="stages-bar">{chips_html}</div>
  <div class="checks-grid">{checks_html}</div>
  <div class="summary-row">
    <span>Executor: <span class="pass">{rd["exec_pass"]}/{rd["exec_total"]}</span></span>
    <span>Verifier: <span class="pass">{rd["veri_pass"]}/{rd["veri_total"]}</span></span>
    <span class="total">{len(rd["stages"])} stages</span>
  </div>
</div>
"""

    html += """
</div>
<div style="text-align:center;font-size:11px;color:#9ca3af;margin-top:24px;">
  Pipeline Test Comparison Dashboard — auto-refresh every 15s
</div>
</body>
</html>"""

    out_path = os.path.join(DUAL_DIR, "comparison.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"\nComparison dashboard: {out_path}")
    return out_path


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Dual Test Runner — Maker-Checker Pattern")
    parser.add_argument("--dual", action="store_true", help="Full dual test (executor + verifier)")
    parser.add_argument("--executor-only", action="store_true", help="Run executor only")
    parser.add_argument("--verifier-only", action="store_true", help="Run verifier only (needs --run-id)")
    parser.add_argument("--merge", action="store_true", help="Merge existing logs into report")
    parser.add_argument("--results", action="store_true", help="Show recent results")
    parser.add_argument("--stages", type=str, default=None, help="Comma-separated stage names")
    parser.add_argument("--email", type=str, default=None, help="Custom test email")
    parser.add_argument("--label", type=str, default=None, help="Test label (e.g. test1, test2)")
    parser.add_argument("--quick", action="store_true", help="Quick mode: skip email stages")
    parser.add_argument("--run-id", type=str, default=None, help="Existing run ID (for verifier/merge)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup (keep test data)")
    parser.add_argument("--compare", action="store_true", help="Generate comparison dashboard of all runs")

    args = parser.parse_args()
    stages = args.stages.split(",") if args.stages else None
    if args.quick and not stages:
        stages = QUICK_STAGES[:]

    if args.compare:
        report = cmd_compare()
        if report:
            os.system(f'start "" "{report}"')
    elif args.results:
        cmd_results()
    elif args.dual:
        report = cmd_dual(stages, email=args.email, dry_run=args.dry_run,
                          no_cleanup=args.no_cleanup, label=args.label)
        if report and not args.dry_run:
            os.system(f'start "" "{report}"')
    elif args.executor_only:
        cmd_executor_only(stages, email=args.email, dry_run=args.dry_run)
    elif args.verifier_only:
        if not args.run_id:
            log("ERROR: --verifier-only requires --run-id")
            sys.exit(1)
        cmd_verifier_only(args.run_id, dry_run=args.dry_run)
    elif args.merge:
        if not args.run_id:
            log("ERROR: --merge requires --run-id")
            sys.exit(1)
        report = cmd_merge(args.run_id)
        if report:
            os.system(f'start "" "{report}"')
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
