#!/usr/bin/env python3
"""
CFO Financial Review Harness
Reference: https://www.anthropic.com/engineering/harness-design-long-running-apps

Architecture:
  CFO (Orchestrator) → Golmani (Generator) → Auditor (Evaluator) → loop

  CFO writes directive.json
  → Golmani queries DataKeeper, produces golmani_output.json
  → Auditor independently cross-checks, produces audit_report.json
  → CFO reviews: APPROVE or send correction_request.json to Golmani
  → Max 3 iterations, then CFO makes final call

Usage:
  # Full orchestration (CFO → Golmani → Auditor loop):
  python tools/cfo_harness.py --task "3-statement model Q1 2026"
  python tools/cfo_harness.py --task "Grosmimi P&L Feb 2026"

  # Audit only (Auditor reviews existing Golmani output):
  python tools/cfo_harness.py --audit-file "Data Storage/golmani/output.json"

  # Show session status:
  python tools/cfo_harness.py --status --session <session_id>
"""

import anthropic
import json
import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
PYTHON = r"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe"
MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 3
SESSIONS_DIR = Path(".tmp/cfo_sessions")
OUTPUT_DIR = Path("Data Storage/cfo")


# --------------------------------------------------------------------------- #
# DataKeeper tool for Golmani
# --------------------------------------------------------------------------- #
GOLMANI_TOOLS = [
    {
        "name": "query_datakeeper",
        "description": (
            "Query ORBI's DataKeeper for financial data. "
            "Returns list of rows from the specified table."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": (
                        "Table name. Options: shopify_orders_daily, amazon_sales_daily, "
                        "amazon_ads_daily, meta_ads_daily, google_ads_daily, ga4_daily, "
                        "klaviyo_daily, amazon_sales_sku_daily, amazon_ads_keywords, "
                        "content_posts, influencer_orders"
                    ),
                },
                "days": {"type": "integer", "description": "Lookback days (e.g. 30, 90)"},
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                "brand": {"type": "string", "description": "Filter by brand name"},
                "limit": {"type": "integer", "description": "Max rows to return"},
            },
            "required": ["table"],
        },
    }
]


def _run_datakeeper(table: str, **kwargs) -> list:
    """Execute a DataKeeper query via subprocess and return rows."""
    params_json = json.dumps({k: v for k, v in kwargs.items() if v is not None})
    script = f"""
import sys, json
sys.path.insert(0, 'tools')
from data_keeper_client import DataKeeper
dk = DataKeeper()
params = {params_json}
rows = dk.get("{table}", **params)
print(json.dumps(rows[:200]))
"""
    result = subprocess.run(
        [PYTHON, "-c", script],
        capture_output=True,
        text=True,
        cwd=".",
    )
    if result.returncode != 0:
        return [{"error": result.stderr[:500]}]
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return [{"error": "Failed to parse DataKeeper output"}]


def _handle_tool_call(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return the result as a string."""
    if tool_name == "query_datakeeper":
        table = tool_input.pop("table")
        rows = _run_datakeeper(table, **tool_input)
        return json.dumps(rows[:50], ensure_ascii=False)  # cap for context
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# --------------------------------------------------------------------------- #
# System Prompts
# --------------------------------------------------------------------------- #
CFO_SYSTEM = """You are the CFO of ORBI (Orbiters Co., Ltd.), a Korean DTC e-commerce company managing 10 brands (Grosmimi ~60%, Naeiae ~15%, CHA&MOM, Alpremio, others) across 5 channels (Shopify D2C, Amazon FBA/FBM, TikTok Shop, TargetPlus, B2B/Faire).

Your role: Orchestrate financial analysis. You direct Golmani (VP of Financial Modeling) and independently verify all outputs through an AICPA/KICPA-certified Auditor. You do NOT produce financial models yourself.

Responsibilities:
1. Interpret the user's financial request
2. Write a precise directive for Golmani: what to compute, required data sources, output format, acceptance criteria
3. Review Golmani's output against the Auditor's findings
4. If audit finds issues: write specific correction requests for Golmani
5. Sign off only when numbers are internally consistent and audit passes

Output format for directives and decisions: JSON.
Be concise. IB-level precision. Korean/English bilingual."""

GOLMANI_SYSTEM = """You are 골만이 — Goldman Sachs senior analyst. VP of Financial Modeling at ORBI.

ORBI context:
- 10 brands: Grosmimi (~60% rev), Naeiae (~15%), CHA&MOM, Alpremio, others
- 5 channels: Shopify D2C, Amazon FBA/FBM (3 sellers), TikTok Shop, B2B/Faire
- Entity flow: ORBI Korea → LFU (exporter) → FLT (US importer) → WBF (3PL)
- P&L basis: Gross Revenue → CM0 (after COGS) → CM1 (after platform fees) → CM2 (after fulfillment) → CM3 (after ads + seeding)
- COGS: landed cost = FOB × 1.15, barcode-matched per SKU
- Key price event: Grosmimi price increase March 1, 2025

Rules:
- Always cite the DataKeeper table and date range for every number
- State all assumptions explicitly
- Output a structured JSON summary of all key numbers (for the Auditor to review)
- Include the full period used (date_from, date_to) in output
- Gross revenue, not net, is the P&L starting point (discounts are a separate marketing cost line)
- When the CFO sends a correction request, address each point and re-output the corrected JSON

Use the query_datakeeper tool to fetch data. Produce a golmani_output JSON with:
{
  "task": "...",
  "period": {"start": "...", "end": "..."},
  "data_sources": [...],
  "financials": {...},
  "key_metrics": {...},
  "assumptions": [...],
  "caveats": [...]
}"""

AUDITOR_SYSTEM = """You are 감사관 — a dual-certified accountant (AICPA + KICPA) acting as independent auditor for ORBI's financial reports.

You receive Golmani's financial output JSON and independently cross-check it.

Your audit checklist (check ALL that apply):

A — ARITHMETIC
- Subtotals sum to totals (Revenue components → Total Revenue, etc.)
- Formula chains: Gross Profit = Revenue - COGS, EBITDA = EBIT + D&A, etc.
- Percentages consistent with underlying numbers (e.g., gross margin % = gross profit / revenue)

B — CROSS-TABLE CONSISTENCY
- Same metric appearing in multiple places must match (e.g., Shopify revenue in P&L vs channel breakdown)
- Totals across brands must equal grand total
- Ad spend in P&L must match ad spend in channel breakdown

C — PERIOD CONSISTENCY
- Same date range used throughout (state the range explicitly)
- YoY / MoM comparisons use correct base periods

D — SIGN CONVENTIONS
- Costs/expenses consistently positive or negative throughout
- Margins correctly computed (positive = profitable)

E — ACCOUNTING STANDARDS (GAAP / K-GAAP)
- Revenue recognition: gross vs net (platform fees)
- COGS: inventory cost basis, not retail
- Operating vs non-operating income correctly classified

F — MATERIALITY & SANITY
- Grosmimi gross margin should be ~68-72% (flag if outside 60-80%)
- Amazon ACOS should be 15-35% (flag if outside 10-50%)
- MER (total ad spend / total revenue) should be 10-25%
- Any number >2x or <0.5x vs typical monthly level should be flagged

Output a structured JSON audit_report:
{
  "status": "PASS" | "WARN" | "FAIL",
  "summary": "one-line verdict",
  "findings": [
    {
      "id": "F001",
      "severity": "CRITICAL" | "MAJOR" | "MINOR" | "INFO",
      "category": "A|B|C|D|E|F",
      "section": "...",
      "description": "...",
      "expected": "...",
      "actual": "...",
      "correction_needed": "..."
    }
  ],
  "corrections_required": ["F001", "F002", ...]
}

CRITICAL/MAJOR findings → status FAIL (CFO must request correction)
Only MINOR/INFO findings → status WARN (CFO decides)
No findings → status PASS"""


# --------------------------------------------------------------------------- #
# Agent runners
# --------------------------------------------------------------------------- #
client = anthropic.Anthropic()


def run_cfo_directive(task: str, session_dir: Path) -> dict:
    """CFO interprets the task and writes a directive for Golmani."""
    print("\n[CFO] Creating directive...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=CFO_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Task request: {task}\n\n"
                    "Write a directive for Golmani as JSON:\n"
                    "{\n"
                    '  "task_summary": "...",\n'
                    '  "required_data": ["table1", "table2", ...],\n'
                    '  "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
                    '  "brand_filter": null | "BrandName",\n'
                    '  "required_outputs": [...],\n'
                    '  "acceptance_criteria": [...]\n'
                    "}"
                ),
            }
        ],
    )

    text = response.content[0].text
    # Extract JSON from response
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        directive = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        directive = {"task_summary": task, "raw_cfo_response": text}

    directive_path = session_dir / "directive.json"
    directive_path.write_text(json.dumps(directive, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → Saved to {directive_path}")
    return directive


def run_golmani(directive: dict, session_dir: Path, correction_request: dict | None = None) -> dict:
    """Golmani executes the financial task using DataKeeper."""
    print("\n[Golmani] Running financial analysis...")

    messages = []
    if correction_request:
        user_content = (
            f"CFO directive: {json.dumps(directive, ensure_ascii=False)}\n\n"
            f"CORRECTION REQUEST from CFO:\n{json.dumps(correction_request, ensure_ascii=False)}\n\n"
            "Please address all correction points and output the revised golmani_output JSON."
        )
    else:
        user_content = (
            f"CFO directive: {json.dumps(directive, ensure_ascii=False)}\n\n"
            "Execute this analysis. Use query_datakeeper to fetch the required data, "
            "then output the golmani_output JSON."
        )

    messages.append({"role": "user", "content": user_content})

    # Agentic loop for tool use
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8096,
            system=GOLMANI_SYSTEM,
            tools=GOLMANI_TOOLS,
            messages=messages,
        )

        # Collect assistant response
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({json.dumps(block.input)[:80]}...)")
                    result = _handle_tool_call(block.name, dict(block.input))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    # Extract the golmani_output JSON from the final response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    output = {}
    try:
        start = final_text.index("{")
        end = final_text.rindex("}") + 1
        output = json.loads(final_text[start:end])
    except (ValueError, json.JSONDecodeError):
        output = {"raw_golmani_response": final_text}

    output_path = session_dir / "golmani_output.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → Saved to {output_path}")
    return output


def run_auditor(golmani_output: dict, session_dir: Path) -> dict:
    """Auditor independently cross-checks Golmani's output."""
    print("\n[Auditor] Running independent audit...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=AUDITOR_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Golmani's financial output to audit:\n\n"
                    f"{json.dumps(golmani_output, indent=2, ensure_ascii=False)}\n\n"
                    "Perform a full audit and output the audit_report JSON."
                ),
            }
        ],
    )

    text = response.content[0].text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        audit_report = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        audit_report = {"status": "WARN", "raw_auditor_response": text, "findings": []}

    # Number the findings file by iteration
    existing = list(session_dir.glob("audit_report_*.json"))
    iteration = len(existing) + 1
    report_path = session_dir / f"audit_report_{iteration}.json"
    report_path.write_text(
        json.dumps(audit_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → Status: {audit_report.get('status', '?')} | Findings: {len(audit_report.get('findings', []))}")
    print(f"  → Saved to {report_path}")
    return audit_report


def run_cfo_decision(
    directive: dict,
    golmani_output: dict,
    audit_report: dict,
    iteration: int,
    session_dir: Path,
) -> dict:
    """CFO reviews the audit report and decides: approve or request corrections."""
    print(f"\n[CFO] Reviewing audit report (iteration {iteration})...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=CFO_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Original directive:\n{json.dumps(directive, ensure_ascii=False)}\n\n"
                    f"Golmani's output summary:\n{json.dumps(golmani_output, ensure_ascii=False)[:3000]}\n\n"
                    f"Auditor's findings:\n{json.dumps(audit_report, indent=2, ensure_ascii=False)}\n\n"
                    f"Iteration: {iteration}/{MAX_ITERATIONS}\n\n"
                    "Decision options:\n"
                    '1. APPROVE: {"decision": "APPROVE", "comment": "..."}\n'
                    '2. REVISE: {"decision": "REVISE", "corrections": [{"finding_id": "F001", "instruction": "..."}]}\n'
                    "3. ESCALATE (only if max iterations reached): "
                    '{"decision": "ESCALATE", "reason": "...", "partial_output": true}\n\n'
                    + (
                        "Max iterations reached — make a final APPROVE or ESCALATE decision."
                        if iteration >= MAX_ITERATIONS
                        else "Decide based on the audit findings."
                    )
                ),
            }
        ],
    )

    text = response.content[0].text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        decision = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        decision = {"decision": "ESCALATE", "reason": "CFO failed to produce structured decision", "raw": text}

    decision_path = session_dir / f"cfo_decision_{iteration}.json"
    decision_path.write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → Decision: {decision.get('decision', '?')}")
    return decision


# --------------------------------------------------------------------------- #
# Main harness loop
# --------------------------------------------------------------------------- #
def run_full_harness(task: str) -> Path:
    """Full CFO → Golmani → Auditor → CFO loop."""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"CFO Harness Session: {session_id}")
    print(f"Task: {task}")
    print(f"{'='*60}")

    # Step 1: CFO creates directive
    directive = run_cfo_directive(task, session_dir)

    correction_request = None
    golmani_output = None

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Iteration {iteration}/{MAX_ITERATIONS} ---")

        # Step 2: Golmani executes
        golmani_output = run_golmani(directive, session_dir, correction_request)

        # Step 3: Auditor reviews
        audit_report = run_auditor(golmani_output, session_dir)

        # Step 4: CFO decides
        decision = run_cfo_decision(directive, golmani_output, audit_report, iteration, session_dir)

        if decision.get("decision") == "APPROVE":
            print(f"\n[CFO] ✓ APPROVED after {iteration} iteration(s)")
            break

        if decision.get("decision") == "ESCALATE":
            print(f"\n[CFO] ⚠ ESCALATED — partial output accepted with caveats")
            break

        if decision.get("decision") == "REVISE" and iteration < MAX_ITERATIONS:
            correction_request = decision
            print(f"\n[CFO] → Sending corrections to Golmani...")

    # Save final output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final_path = OUTPUT_DIR / f"cfo_review_{session_id}.json"
    final_output = {
        "session_id": session_id,
        "task": task,
        "directive": directive,
        "final_golmani_output": golmani_output,
        "final_audit_status": audit_report.get("status"),
        "final_audit_findings": audit_report.get("findings", []),
        "cfo_decision": decision,
        "timestamp": datetime.now().isoformat(),
    }
    final_path.write_text(json.dumps(final_output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[CFO Harness] Final report saved: {final_path}")
    return final_path


def run_audit_only(audit_file: str) -> dict:
    """Audit an existing Golmani output file."""
    file_path = Path(audit_file)
    if not file_path.exists():
        print(f"ERROR: File not found: {audit_file}")
        sys.exit(1)

    golmani_output = json.loads(file_path.read_text(encoding="utf-8"))

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Audit-Only Session: {session_id}")
    print(f"Auditing: {audit_file}")
    print(f"{'='*60}")

    audit_report = run_auditor(golmani_output, session_dir)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"audit_{session_id}.json"
    out_path.write_text(json.dumps(audit_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAudit report saved: {out_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"AUDIT STATUS: {audit_report.get('status')}")
    print(f"Summary: {audit_report.get('summary', '')}")
    findings = audit_report.get("findings", [])
    for f in findings:
        sev = f.get("severity", "?")
        desc = f.get("description", "")[:80]
        print(f"  [{sev}] {f.get('id', '?')}: {desc}")
    print(f"{'='*60}")

    return audit_report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CFO Financial Review Harness")
    parser.add_argument("--task", type=str, help="Financial task for full CFO → Golmani → Auditor loop")
    parser.add_argument("--audit-file", type=str, help="Path to existing Golmani output JSON to audit")
    parser.add_argument("--session", type=str, help="Session ID for status check")
    parser.add_argument("--status", action="store_true", help="Show session status")
    args = parser.parse_args()

    if args.task:
        run_full_harness(args.task)
    elif args.audit_file:
        run_audit_only(args.audit_file)
    elif args.status and args.session:
        session_dir = SESSIONS_DIR / args.session
        if session_dir.exists():
            for f in sorted(session_dir.iterdir()):
                print(f"  {f.name}")
        else:
            print(f"Session not found: {args.session}")
    else:
        parser.print_help()
