#!/usr/bin/env python3
"""
Flow Auditor — Pathlight PROD Workflow Continuous Tester
========================================================
Pipeliner(빌더)가 수정한 n8n Pathlight 워크플로우를 독립적으로 검증.
Harness 구조로 지속 실행, 실패 시 즉시 보고.

Usage:
    python tools/flow_auditor.py --audit                   # Full audit (all 11 WFs)
    python tools/flow_auditor.py --health                  # Quick liveness check
    python tools/flow_auditor.py --structural              # Node structure only
    python tools/flow_auditor.py --audit --workflows draft_gen,reply_handler
    python tools/flow_auditor.py --audit --executions 10   # Execution history
    python tools/flow_auditor.py --snapshot                # Save current state
    python tools/flow_auditor.py --diff --before snap1 --after snap2
    python tools/flow_auditor.py --watch --interval 300    # Continuous mode
    python tools/flow_auditor.py --results                 # Last results
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
TMP = ROOT / ".tmp" / "flow_audit"
TMP.mkdir(parents=True, exist_ok=True)

# ─── Env ─────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(DIR))
JEEHOO_ENV = Path("/Volumes/Orbiters/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/Jeehoo/.env")
try:
    from env_loader import load_env
    load_env()
except ImportError:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
# Fallback: load from Jeehoo .env if key vars still missing
if not os.getenv("N8N_API_KEY") and JEEHOO_ENV.exists():
    for line in JEEHOO_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in ("N8N_API_KEY", "N8N_BASE_URL", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP") and not os.getenv(k):
                os.environ[k] = v

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
ORBITOOLS_URL = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "admin")
SHOPIFY_STORE = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ─── Pathlight Workflow Registry ─────────────────────────────────────────────
PATHLIGHT_WFS = {
    "approval_send":    {"id": "jf9uxkPww2xeCr82",     "name": "Outreach - Approval Send",       "expect_active": True},
    "draft_gen":        {"id": "fwwOeLiDLSnR77E1",      "name": "Outreach - Draft Generation",    "expect_active": True},
    "fulfillment":      {"id": "ufMPgU6cjwuzLM0y",      "name": "Shopify Fulfillment -> PG",      "expect_active": True},
    "manychat":         {"id": "fsrnGT7aPn5jfVQ5m7I8C", "name": "ManyChat Automation",            "expect_active": True},
    "syncly_data":      {"id": "l86XnrL1JPFOMSA4GOoYy", "name": "Syncly Data Processing",        "expect_active": True},
    "mode_switcher":    {"id": "OQGl3EVBTxathqSg",      "name": "Mode Switcher",                  "expect_active": True},
    "daily_config":     {"id": "nTUJqlaKT61Di5A6",      "name": "Daily Config Row",               "expect_active": True},
    "docuseal":         {"id": "HeJtfn0m3PJoPzg0",      "name": "Docuseal Contracting",           "expect_active": True},
    "reply_handler":    {"id": "K99grtW9iWq8V79f",      "name": "Outreach - Reply Handler",       "expect_active": True},
    "paypal":           {"id": "FRNxtYh8SfMu9Q5E",      "name": "PayPal Payment",                 "expect_active": False},
    "content_tracking": {"id": "jH3YKdFFRupaIyQW",      "name": "Content Tracking",               "expect_active": False},
}

# ─── PROD references (should appear) & WJ TEST refs (should NOT appear) ─────
PROD_REFS = {
    "orbitools": "orbitools.orbiters.co.kr",
    "shopify": "mytoddie.myshopify.com",
    "n8n": "n8n.orbiters.co.kr",
    "gmail_sender": "affiliates@onzenna.com",
    "airtable_base": "app3Vnmh7hLAVsevE",
}
WJ_TEST_REFS = {
    "airtable_base": "appT2gLRR0PqMFgII",
    "shopify": "toddie-4080.myshopify.com",
}

SECRET_PATTERNS = [
    re.compile(r'(api[_-]?key|apikey)\s*[:=]\s*["\']?[\w-]{32,}', re.I),
    re.compile(r'bearer\s+[\w.-]{32,}', re.I),
    re.compile(r'(password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']{12,}', re.I),
]

RISKY_NODE_TYPES = {"httpRequest", "code", "anthropic", "gmail", "googleSheets", "googleDrive"}


# ═════════════════════════════════════════════════════════════════════════════
# Check dataclass
# ═════════════════════════════════════════════════════════════════════════════
class Check:
    def __init__(self, name, passed=None, expected=None, actual=None, detail="", severity="MEDIUM"):
        self.name = name
        self.passed = passed
        self.expected = expected
        self.actual = actual
        self.detail = detail
        self.severity = severity

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
            "severity": self.severity,
        }


# ═════════════════════════════════════════════════════════════════════════════
# HTTP helpers
# ═════════════════════════════════════════════════════════════════════════════
def n8n_get(path, timeout=15):
    url = f"{N8N_BASE_URL}/api/v1{path}"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_API_KEY})
    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def http_get(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout)
        return {"status": resp.status, "body": resp.read().decode("utf-8", errors="replace")[:2000]}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": str(e)}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def orbitools_get(path, timeout=10):
    import base64
    creds = base64.b64encode(f"{ORBITOOLS_USER}:{ORBITOOLS_PASS}".encode()).decode()
    return http_get(f"{ORBITOOLS_URL}{path}", headers={"Authorization": f"Basic {creds}"}, timeout=timeout)


# ═════════════════════════════════════════════════════════════════════════════
# Structural Validator
# ═════════════════════════════════════════════════════════════════════════════
class StructuralValidator:
    def validate(self, wf_key, wf_data):
        checks = []
        nodes = wf_data.get("nodes", [])
        conns = wf_data.get("connections", {})
        real_nodes = [n for n in nodes if "stickyNote" not in n.get("type", "")]

        # 1. Has trigger
        triggers = [n for n in real_nodes if "trigger" in n.get("type", "").lower() or "Trigger" in n.get("name", "")]
        checks.append(Check("has_trigger", len(triggers) > 0, ">0", len(triggers),
                           f"Triggers: {[t['name'] for t in triggers]}", "CRITICAL"))

        # 2. Orphan nodes
        connected = set()
        for src, conn_map in conns.items():
            connected.add(src)
            for output_key, output_links in conn_map.items():
                if isinstance(output_links, list):
                    for link_group in output_links:
                        if isinstance(link_group, list):
                            for link in link_group:
                                if isinstance(link, dict):
                                    connected.add(link.get("node", ""))
        trigger_names = {t["name"] for t in triggers}
        all_names = {n["name"] for n in real_nodes}
        orphans = all_names - connected - trigger_names
        checks.append(Check("no_orphan_nodes", len(orphans) == 0, 0, len(orphans),
                           f"Orphans: {list(orphans)[:5]}" if orphans else "", "HIGH"))

        # 3. Disabled nodes
        disabled = [n["name"] for n in real_nodes if n.get("disabled")]
        checks.append(Check("no_disabled_nodes", len(disabled) == 0, 0, len(disabled),
                           f"Disabled: {disabled[:5]}" if disabled else "", "MEDIUM"))

        # 4. Error handling
        has_error_trigger = any("errorTrigger" in n.get("type", "") for n in nodes)
        risky_count = sum(1 for n in real_nodes if n.get("type", "").split(".")[-1] in RISKY_NODE_TYPES)
        unprotected = [n["name"] for n in real_nodes
                       if n.get("type", "").split(".")[-1] in RISKY_NODE_TYPES
                       and not n.get("onError")]
        checks.append(Check("error_handling", has_error_trigger or risky_count == 0,
                           True, has_error_trigger,
                           f"Risky nodes: {risky_count}, unprotected: {len(unprotected)}", "MEDIUM"))

        # 5. Node count sanity
        checks.append(Check("node_count", len(real_nodes) > 1, ">1", len(real_nodes), "", "CRITICAL"))

        # 6. Security scan
        wf_str = json.dumps(wf_data.get("nodes", []), ensure_ascii=False)
        secret_hits = []
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(wf_str):
                secret_hits.append(m.group()[:40] + "...")
        checks.append(Check("no_secret_leak", len(secret_hits) == 0, 0, len(secret_hits),
                           f"Found: {secret_hits[:3]}" if secret_hits else "", "CRITICAL"))

        # 7. WJ TEST references in PROD
        wj_test_found = []
        for label, ref in WJ_TEST_REFS.items():
            if ref in wf_str:
                wj_test_found.append(f"{label}={ref}")
        checks.append(Check("no_wj_test_refs", len(wj_test_found) == 0, 0, len(wj_test_found),
                           f"WJ TEST refs in PROD: {wj_test_found}" if wj_test_found else "", "HIGH"))

        return checks


# ═════════════════════════════════════════════════════════════════════════════
# Live Probe
# ═════════════════════════════════════════════════════════════════════════════
class LiveProbe:
    def check_health(self):
        checks = []

        # n8n server
        r = http_get(f"{N8N_BASE_URL}/healthz")
        checks.append(Check("n8n_server", r.get("status") == 200, 200, r.get("status"),
                           r.get("error", ""), "CRITICAL"))

        # orbitools API
        r = orbitools_get("/api/")
        checks.append(Check("orbitools_api", r.get("status") in (200, 301, 302, 404), "2xx/3xx",
                           r.get("status"), r.get("error", ""), "CRITICAL"))

        # Shopify API
        if SHOPIFY_TOKEN:
            r = http_get(f"https://{SHOPIFY_STORE}/admin/api/2024-01/shop.json",
                        headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})
            checks.append(Check("shopify_api", r.get("status") == 200, 200, r.get("status"),
                               r.get("error", ""), "HIGH"))

        return checks

    def check_workflow(self, wf_key, wf_meta):
        checks = []
        wf_id = wf_meta["id"]
        expect_active = wf_meta["expect_active"]

        wf = n8n_get(f"/workflows/{wf_id}")
        if "error" in wf:
            checks.append(Check(f"{wf_key}_reachable", False, True, False, wf["error"], "CRITICAL"))
            return checks

        actual_active = wf.get("active", False)
        checks.append(Check(f"{wf_key}_active", actual_active == expect_active,
                           expect_active, actual_active, "", "CRITICAL" if expect_active else "INFO"))

        # Last execution
        execs = n8n_get(f"/executions?workflowId={wf_id}&limit=1&status=success")
        if not execs.get("error") and execs.get("data"):
            last = execs["data"][0]
            started = last.get("startedAt", "")
            checks.append(Check(f"{wf_key}_last_exec", True, "exists", started[:19], "", "INFO"))
        elif expect_active:
            checks.append(Check(f"{wf_key}_last_exec", False, "exists", "none", "No recent successful execution", "HIGH"))

        return checks


# ═════════════════════════════════════════════════════════════════════════════
# Execution Auditor
# ═════════════════════════════════════════════════════════════════════════════
class ExecutionAuditor:
    def audit(self, wf_key, wf_id, limit=5):
        checks = []
        execs = n8n_get(f"/executions?workflowId={wf_id}&limit={limit}")
        if execs.get("error"):
            checks.append(Check(f"{wf_key}_exec_fetch", False, "ok", execs["error"], "", "HIGH"))
            return checks

        data = execs.get("data", [])
        if not data:
            checks.append(Check(f"{wf_key}_has_executions", False, ">0", 0, "No executions found", "MEDIUM"))
            return checks

        # Success rate
        statuses = [e.get("status") for e in data]
        success_count = statuses.count("success")
        total = len(statuses)
        rate = success_count / total if total else 0
        checks.append(Check(f"{wf_key}_success_rate", rate >= 0.5, ">=50%",
                           f"{success_count}/{total} ({rate*100:.0f}%)",
                           f"Statuses: {statuses}", "HIGH" if rate < 0.5 else "INFO"))

        # Error patterns — fetch individual execution detail for actual error info
        errors = [e for e in data if e.get("status") != "success"]
        if errors:
            error_msgs = []
            for e in errors[:3]:
                exec_id = e.get("id")
                msg = "unknown"
                if exec_id:
                    detail = n8n_get(f"/executions/{exec_id}?includeData=true")
                    if not detail.get("error"):
                        result_data = detail.get("data", {}).get("resultData", {})
                        err_obj = result_data.get("error", {})
                        last_node = result_data.get("lastNodeExecuted", "")
                        if isinstance(err_obj, dict) and err_obj.get("message"):
                            err_text = err_obj["message"]
                            if last_node:
                                msg = f"{last_node}: {err_text}"
                            else:
                                msg = err_text
                error_msgs.append(msg[:100])
            checks.append(Check(f"{wf_key}_error_patterns", False, "no errors",
                               f"{len(errors)} failures", f"Errors: {error_msgs}", "MEDIUM"))

        return checks


# ═════════════════════════════════════════════════════════════════════════════
# Report Generator
# ═════════════════════════════════════════════════════════════════════════════
class ReportGenerator:
    def generate(self, run_id, results, duration_sec):
        summary = {"total_workflows": len(results), "passed": 0, "failed": 0, "skipped": 0}
        alerts = []

        for wf_key, wf_result in results.items():
            all_checks = []
            for category, checks in wf_result.items():
                all_checks.extend(checks)
            failed = [c for c in all_checks if c.passed is False]
            if failed:
                summary["failed"] += 1
                for c in failed:
                    if c.severity in ("CRITICAL", "HIGH"):
                        alerts.append({"severity": c.severity, "workflow": wf_key, "message": f"{c.name}: {c.detail or c.actual}"})
            else:
                summary["passed"] += 1

        health = "HEALTHY" if summary["failed"] == 0 else "DEGRADED" if summary["failed"] <= 2 else "CRITICAL"
        summary["health"] = health

        report = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_sec": round(duration_sec, 1),
            "summary": summary,
            "workflows": {k: {cat: [c.to_dict() for c in checks] for cat, checks in v.items()} for k, v in results.items()},
            "alerts": alerts,
        }
        return report

    def generate_html(self, report):
        s = report["summary"]
        health_color = {"HEALTHY": "#22c55e", "DEGRADED": "#f59e0b", "CRITICAL": "#ef4444"}[s["health"]]

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Flow Audit Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #0f172a; color: #e2e8f0; }}
.header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
.badge {{ padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 14px; }}
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
.summary-card {{ background: #1e293b; padding: 16px; border-radius: 12px; text-align: center; }}
.summary-card .num {{ font-size: 32px; font-weight: 700; }}
.wf-card {{ background: #1e293b; border-radius: 12px; margin-bottom: 12px; overflow: hidden; }}
.wf-header {{ padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }}
.wf-body {{ padding: 12px 16px; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #334155; font-size: 13px; }}
th {{ color: #94a3b8; font-weight: 600; }}
.pass {{ color: #22c55e; }} .fail {{ color: #ef4444; }} .skip {{ color: #94a3b8; }}
.alert {{ background: #7f1d1d; border-radius: 8px; padding: 10px 14px; margin: 6px 0; font-size: 13px; }}
.alert-high {{ background: #78350f; }}
</style></head><body>
<div class="header">
  <h1>Flow Auditor Report</h1>
  <div>
    <span class="badge" style="background:{health_color};color:#000">{s['health']}</span>
    <span style="margin-left:12px;color:#94a3b8">{report['run_id']} | {report['timestamp'][:19]} | {report['duration_sec']}s</span>
  </div>
</div>
<div class="summary">
  <div class="summary-card"><div class="num">{s['total_workflows']}</div><div>Total</div></div>
  <div class="summary-card"><div class="num pass">{s['passed']}</div><div>Passed</div></div>
  <div class="summary-card"><div class="num fail">{s['failed']}</div><div>Failed</div></div>
  <div class="summary-card"><div class="num skip">{s['skipped']}</div><div>Skipped</div></div>
</div>
"""
        # Alerts
        if report["alerts"]:
            html += "<h2>Alerts</h2>\n"
            for a in report["alerts"]:
                cls = "alert" if a["severity"] == "CRITICAL" else "alert alert-high"
                html += f'<div class="{cls}"><strong>[{a["severity"]}]</strong> {a["workflow"]}: {a["message"]}</div>\n'

        # Per-workflow
        html += "<h2>Workflow Results</h2>\n"
        for wf_key, categories in report["workflows"].items():
            all_checks = [c for checks in categories.values() for c in checks]
            failed = sum(1 for c in all_checks if not c["passed"])
            status_class = "fail" if failed else "pass"
            status_text = f"{failed} FAIL" if failed else "PASS"

            html += f"""<div class="wf-card">
<div class="wf-header"><strong>{wf_key}</strong> <span class="{status_class}">{status_text}</span></div>
<div class="wf-body">"""
            for cat, checks in categories.items():
                if not checks:
                    continue
                html += f"<h4 style='margin:8px 0 4px;color:#94a3b8'>{cat}</h4><table><tr><th>Check</th><th>Status</th><th>Expected</th><th>Actual</th><th>Detail</th></tr>\n"
                for c in checks:
                    cls = "pass" if c["passed"] else "fail" if c["passed"] is False else "skip"
                    icon = "✅" if c["passed"] else "❌" if c["passed"] is False else "⏭"
                    html += f'<tr><td>{c["name"]}</td><td class="{cls}">{icon}</td><td>{c["expected"]}</td><td>{c["actual"]}</td><td>{c["detail"][:120]}</td></tr>\n'
                html += "</table>\n"
            html += "</div></div>\n"

        html += "<footer style='text-align:center;color:#475569;margin-top:24px'>Generated by Flow Auditor | Pathlight PROD</footer></body></html>"
        return html


# ═════════════════════════════════════════════════════════════════════════════
# Main Orchestrator
# ═════════════════════════════════════════════════════════════════════════════
class FlowAuditor:
    def __init__(self, workflows=None, executions=5):
        self.workflows = workflows or list(PATHLIGHT_WFS.keys())
        self.executions = executions
        self.structural = StructuralValidator()
        self.probe = LiveProbe()
        self.exec_auditor = ExecutionAuditor()
        self.reporter = ReportGenerator()

    def run_health(self):
        """Quick liveness check only"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"health_{ts}"
        start = time.time()

        print(f"\n{'='*60}")
        print(f"  Flow Auditor — Health Check")
        print(f"  Run ID: {run_id}")
        print(f"{'='*60}\n")

        # Infrastructure
        infra_checks = self.probe.check_health()
        for c in infra_checks:
            icon = "✅" if c.passed else "❌"
            print(f"  {icon} {c.name}: {c.actual} {c.detail}")

        # Per-workflow liveness
        print()
        results = {}
        for wf_key in self.workflows:
            meta = PATHLIGHT_WFS[wf_key]
            wf_checks = self.probe.check_workflow(wf_key, meta)
            results[wf_key] = {"liveness": wf_checks}
            for c in wf_checks:
                icon = "✅" if c.passed else "❌" if c.passed is False else "⏭"
                print(f"  {icon} {c.name}: {c.actual}")

        duration = time.time() - start
        failed = sum(1 for r in results.values() for c in r["liveness"] if c.passed is False)
        print(f"\n{'='*60}")
        print(f"  Health: {'HEALTHY' if failed == 0 else 'DEGRADED'} | {duration:.1f}s | {failed} issues")
        print(f"{'='*60}\n")
        return results

    def run_structural(self):
        """Structural validation only (no external API calls besides n8n)"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"structural_{ts}"
        print(f"\n  Flow Auditor — Structural Validation | {run_id}\n")

        results = {}
        for wf_key in self.workflows:
            meta = PATHLIGHT_WFS[wf_key]
            wf_data = n8n_get(f"/workflows/{meta['id']}")
            if "error" in wf_data:
                print(f"  ❌ {wf_key}: Failed to fetch — {wf_data['error']}")
                continue
            checks = self.structural.validate(wf_key, wf_data)
            results[wf_key] = {"structural": checks}
            failed = [c for c in checks if c.passed is False]
            icon = "❌" if failed else "✅"
            print(f"  {icon} {wf_key} ({len(checks)} checks, {len(failed)} failed)")
            for c in failed:
                print(f"      [{c.severity}] {c.name}: {c.detail}")

        return results

    def run_audit(self):
        """Full audit: structural + liveness + execution"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"audit_{ts}"
        run_dir = TMP / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        snap_dir = run_dir / "snapshot"
        snap_dir.mkdir(exist_ok=True)

        start = time.time()
        print(f"\n{'='*60}")
        print(f"  Flow Auditor — Full Audit")
        print(f"  Run ID: {run_id}")
        print(f"  Workflows: {len(self.workflows)}")
        print(f"  Executions to check: {self.executions}")
        print(f"{'='*60}\n")

        # Infrastructure health
        print("  [1/4] Infrastructure health...")
        infra_checks = self.probe.check_health()
        for c in infra_checks:
            icon = "✅" if c.passed else "❌"
            print(f"    {icon} {c.name}: {c.actual}")

        results = {}
        for wf_key in self.workflows:
            meta = PATHLIGHT_WFS[wf_key]
            print(f"\n  [WF] {wf_key} ({meta['name']})...")
            wf_result = {}

            # Fetch workflow
            wf_data = n8n_get(f"/workflows/{meta['id']}")
            if "error" in wf_data:
                print(f"    ❌ Cannot fetch: {wf_data['error']}")
                results[wf_key] = {"error": [Check(f"{wf_key}_fetch", False, "ok", wf_data["error"], "", "CRITICAL")]}
                continue

            # Save snapshot
            with open(snap_dir / f"{wf_key}.json", "w") as f:
                json.dump(wf_data, f, ensure_ascii=False, indent=2)

            # Structural
            print("    [2/4] Structural validation...")
            struct_checks = self.structural.validate(wf_key, wf_data)
            wf_result["structural"] = struct_checks
            failed_s = [c for c in struct_checks if c.passed is False]
            print(f"    {'❌' if failed_s else '✅'} {len(struct_checks)} checks, {len(failed_s)} failed")

            # Liveness
            print("    [3/4] Liveness probe...")
            live_checks = self.probe.check_workflow(wf_key, meta)
            wf_result["liveness"] = live_checks
            failed_l = [c for c in live_checks if c.passed is False]
            print(f"    {'❌' if failed_l else '✅'} {len(live_checks)} checks, {len(failed_l)} failed")

            # Execution audit (only for active workflows)
            if meta["expect_active"]:
                print("    [4/4] Execution audit...")
                exec_checks = self.exec_auditor.audit(wf_key, meta["id"], self.executions)
                wf_result["execution"] = exec_checks
                failed_e = [c for c in exec_checks if c.passed is False]
                print(f"    {'❌' if failed_e else '✅'} {len(exec_checks)} checks, {len(failed_e)} failed")

            results[wf_key] = wf_result

        duration = time.time() - start

        # Generate reports
        report = self.reporter.generate(run_id, results, duration)
        with open(run_dir / "report.json", "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        html = self.reporter.generate_html(report)
        html_path = run_dir / "report.html"
        with open(html_path, "w") as f:
            f.write(html)

        # Summary
        s = report["summary"]
        print(f"\n{'='*60}")
        print(f"  Audit Complete: {s['health']}")
        print(f"  Passed: {s['passed']} | Failed: {s['failed']} | Duration: {duration:.1f}s")
        if report["alerts"]:
            print(f"  Alerts: {len(report['alerts'])}")
            for a in report["alerts"][:5]:
                print(f"    [{a['severity']}] {a['workflow']}: {a['message'][:80]}")
        print(f"  Report: {html_path}")
        print(f"{'='*60}\n")

        return report

    def run_snapshot(self):
        """Save current workflow state for later diff"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = TMP / f"snapshot_{ts}"
        snap_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n  Saving snapshot to {snap_dir}...")
        for wf_key in self.workflows:
            meta = PATHLIGHT_WFS[wf_key]
            wf_data = n8n_get(f"/workflows/{meta['id']}")
            if "error" not in wf_data:
                with open(snap_dir / f"{wf_key}.json", "w") as f:
                    json.dump(wf_data, f, ensure_ascii=False, indent=2)
                print(f"  ✅ {wf_key}: {len(wf_data.get('nodes',[]))} nodes")
            else:
                print(f"  ❌ {wf_key}: {wf_data['error']}")

        print(f"  Snapshot saved: {snap_dir}\n")
        return str(snap_dir)

    def run_diff(self, before_dir, after_dir):
        """Compare two snapshots"""
        before_path = Path(before_dir) if os.path.isabs(before_dir) else TMP / before_dir
        after_path = Path(after_dir) if os.path.isabs(after_dir) else TMP / after_dir

        print(f"\n  Diff: {before_path.name} vs {after_path.name}\n")

        for wf_key in self.workflows:
            bf = before_path / f"{wf_key}.json"
            af = after_path / f"{wf_key}.json"
            if not bf.exists() or not af.exists():
                print(f"  ⏭ {wf_key}: missing in one snapshot")
                continue

            before_wf = json.loads(bf.read_text())
            after_wf = json.loads(af.read_text())

            b_nodes = {n["name"]: n for n in before_wf.get("nodes", [])}
            a_nodes = {n["name"]: n for n in after_wf.get("nodes", [])}

            added = set(a_nodes) - set(b_nodes)
            removed = set(b_nodes) - set(a_nodes)
            modified = []
            for name in set(a_nodes) & set(b_nodes):
                if json.dumps(a_nodes[name], sort_keys=True) != json.dumps(b_nodes[name], sort_keys=True):
                    modified.append(name)

            if added or removed or modified:
                print(f"  🔄 {wf_key}:")
                for n in added:
                    print(f"      + {n}")
                for n in removed:
                    print(f"      - {n}")
                for n in modified:
                    print(f"      ~ {n}")
            else:
                print(f"  ✅ {wf_key}: no changes")

    def run_watch(self, interval=300):
        """Continuous monitoring mode"""
        print(f"\n  Flow Auditor — Watch Mode (interval: {interval}s)")
        print(f"  Press Ctrl+C to stop\n")

        cycle = 0
        while True:
            cycle += 1
            print(f"\n  --- Cycle {cycle} ({datetime.now().strftime('%H:%M:%S')}) ---")

            if cycle % 1 == 0:  # Every cycle: health
                self.run_health()
            if cycle % 6 == 0:  # Every ~30min: structural
                self.run_structural()
            if cycle % 24 == 0:  # Every ~2hr: full audit
                self.run_audit()

            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n  Watch stopped.\n")
                break

    def show_results(self):
        """Show most recent audit results"""
        runs = sorted(TMP.glob("audit_*"), key=lambda p: p.name, reverse=True)
        if not runs:
            print("  No audit results found.")
            return

        latest = runs[0]
        report_file = latest / "report.json"
        if report_file.exists():
            report = json.loads(report_file.read_text())
            s = report["summary"]
            print(f"\n  Latest: {report['run_id']}")
            print(f"  Time: {report['timestamp'][:19]}")
            print(f"  Health: {s['health']} | Passed: {s['passed']} | Failed: {s['failed']}")
            if report.get("alerts"):
                print(f"  Alerts:")
                for a in report["alerts"]:
                    print(f"    [{a['severity']}] {a['workflow']}: {a['message'][:80]}")
            html_file = latest / "report.html"
            if html_file.exists():
                print(f"  HTML: {html_file}")
        else:
            print(f"  Found run dir but no report.json: {latest}")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Flow Auditor — Pathlight PROD Workflow Tester")
    parser.add_argument("--audit", action="store_true", help="Full audit (structural + liveness + execution)")
    parser.add_argument("--health", action="store_true", help="Quick liveness check")
    parser.add_argument("--structural", action="store_true", help="Structural validation only")
    parser.add_argument("--snapshot", action="store_true", help="Save current WF state")
    parser.add_argument("--diff", action="store_true", help="Compare two snapshots")
    parser.add_argument("--before", help="Before snapshot dir (for --diff)")
    parser.add_argument("--after", help="After snapshot dir (for --diff)")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=300, help="Watch interval in seconds")
    parser.add_argument("--workflows", help="Comma-separated workflow keys to audit")
    parser.add_argument("--executions", type=int, default=5, help="Number of executions to check")
    parser.add_argument("--results", action="store_true", help="Show most recent results")
    parser.add_argument("--write-rollback", action="store_true", help="Write rollback signal for a failed WF")
    parser.add_argument("--execute-rollback", action="store_true", help="Execute rollback from signal file")
    parser.add_argument("--workflow", help="Workflow key for --write-rollback")
    parser.add_argument("--reason", help="Reason for --write-rollback")
    parser.add_argument("--snapshot-dir", help="Snapshot dir for --write-rollback")

    args = parser.parse_args()

    wf_list = args.workflows.split(",") if args.workflows else None
    auditor = FlowAuditor(workflows=wf_list, executions=args.executions)

    exit_code = 0

    if args.write_rollback:
        if not args.workflow or not args.reason or not args.snapshot_dir:
            print("  --write-rollback requires --workflow, --reason, --snapshot-dir")
            sys.exit(1)
        signal_path = write_rollback_signal(args.workflow, args.reason, args.snapshot_dir)
        print(f"  Rollback signal written: {signal_path}")
    elif args.execute_rollback:
        ok = execute_rollback()
        exit_code = 0 if ok else 1
    elif args.health:
        results = auditor.run_health()
        failed = sum(1 for r in results.values() for c in r["liveness"] if c.passed is False)
        if failed > 0:
            exit_code = 1
    elif args.structural:
        auditor.run_structural()
    elif args.snapshot:
        auditor.run_snapshot()
    elif args.diff:
        if not args.before or not args.after:
            print("  --diff requires --before and --after")
            sys.exit(1)
        auditor.run_diff(args.before, args.after)
    elif args.watch:
        auditor.run_watch(args.interval)
    elif args.results:
        auditor.show_results()
    elif args.audit:
        report = auditor.run_audit()
        if report and report.get("summary", {}).get("health") != "HEALTHY":
            exit_code = 1
    else:
        parser.print_help()

    sys.exit(exit_code)


# ─── Rollback Signal ────────────────────────────────────────────────────────
def write_rollback_signal(wf_key, reason, snapshot_dir):
    """Write a rollback signal file for a failed workflow."""
    meta = PATHLIGHT_WFS.get(wf_key)
    if not meta:
        print(f"  Unknown workflow key: {wf_key}")
        sys.exit(1)
    signal = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workflow": wf_key,
        "workflow_id": meta["id"],
        "workflow_name": meta["name"],
        "reason": reason,
        "snapshot_dir": snapshot_dir,
        "status": "PENDING",
    }
    signal_path = TMP / "rollback_signal.json"
    signal_path.write_text(json.dumps(signal, indent=2, ensure_ascii=False))
    return signal_path


def execute_rollback(signal_path=None):
    """Execute rollback: restore workflow from snapshot."""
    signal_path = signal_path or TMP / "rollback_signal.json"
    if not signal_path.exists():
        print(f"  No rollback signal found at {signal_path}")
        return False

    signal = json.loads(signal_path.read_text())
    if signal["status"] != "PENDING":
        print(f"  Rollback signal status is '{signal['status']}', not PENDING. Skipping.")
        return False

    wf_key = signal["workflow"]
    wf_id = signal["workflow_id"]
    snap_dir = Path(signal["snapshot_dir"])
    if not snap_dir.is_absolute():
        snap_dir = TMP / snap_dir
    snap_file = snap_dir / f"{wf_key}.json"

    if not snap_file.exists():
        print(f"  Snapshot not found: {snap_file}")
        return False

    wf_data = json.loads(snap_file.read_text())
    payload = {
        "name": wf_data["name"],
        "nodes": wf_data["nodes"],
        "connections": wf_data["connections"],
        "settings": wf_data.get("settings", {}),
    }

    print(f"  Rolling back {wf_key} ({wf_id}) from {snap_file}...")
    url = f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=SSL_CTX) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Rollback OK: {result.get('name', 'unknown')}")
    except urllib.error.URLError as e:
        print(f"  Rollback FAILED: {e}")
        return False

    # Mark signal as executed
    signal["status"] = "EXECUTED"
    signal["executed_at"] = datetime.now(timezone.utc).isoformat()
    signal_path.write_text(json.dumps(signal, indent=2, ensure_ascii=False))
    print(f"  Signal updated: {signal_path}")
    return True


if __name__ == "__main__":
    main()
