#!/usr/bin/env python3
"""
Coordinator — Universal Multi-Agent Orchestration Engine.
Inspired by Claude Code's Coordinator Mode.

Provides a shared protocol for all multi-agent workflows:
  - WorkUnit tracking (phases, status, agent roles)
  - Shared scratchpad (JSONL append-only)
  - YAML workflow templates
  - Status reporting

Usage:
    python tools/coordinator.py start --workflow cfo_review --params '{"task": "Q2 P&L"}'
    python tools/coordinator.py status --id cfo-20260401-001
    python tools/coordinator.py scratchpad --id cfo-20260401-001
    python tools/coordinator.py history --days 7
    python tools/coordinator.py list
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp" / "coordinator"
TEMPLATES_DIR = ROOT / "workflows" / "coordinator_templates"


# ═════════════════════════════════════════════════════════════════════════════
# Data Models
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class WorkUnit:
    id: str
    workflow: str
    phase: str
    agent_role: str
    status: str = "pending"           # pending, running, done, failed
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""
    error: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Workflow:
    id: str
    template: str
    params: dict
    status: str = "running"           # running, completed, failed
    current_phase: str = ""
    iteration: int = 0
    max_iterations: int = 2
    created_at: str = ""
    completed_at: str = ""
    work_units: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "template": self.template,
            "params": self.params,
            "status": self.status,
            "current_phase": self.current_phase,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "work_units_count": len(self.work_units),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Workflow Manager
# ═════════════════════════════════════════════════════════════════════════════

class CoordinatorEngine:
    def __init__(self):
        TMP.mkdir(parents=True, exist_ok=True)

    def _workflow_dir(self, workflow_id):
        d = TMP / workflow_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_file(self, workflow_id):
        return self._workflow_dir(workflow_id) / "state.json"

    def _scratchpad_file(self, workflow_id):
        return self._workflow_dir(workflow_id) / "scratchpad.jsonl"

    # ─── Start ─────────────────────────────────────────────────────────────
    def start_workflow(self, template_name, params=None):
        """Initialize a new workflow from template."""
        params = params or {}
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow_id = f"{template_name}_{ts}"

        wf = Workflow(
            id=workflow_id,
            template=template_name,
            params=params,
            created_at=datetime.now().isoformat(),
        )

        # Load template if exists
        template_file = TEMPLATES_DIR / f"{template_name}.yml"
        if template_file.exists():
            try:
                import yaml  # noqa: F811
                with open(template_file, "r", encoding="utf-8") as f:
                    tmpl = yaml.safe_load(f)
                wf.max_iterations = tmpl.get("max_iterations", 2)
            except ImportError:
                # No yaml module, use defaults
                pass
            except Exception:
                pass

        # Save state
        self._save_state(wf)

        print(f"[coordinator] Started workflow: {workflow_id}")
        print(f"  template: {template_name}")
        print(f"  max_iterations: {wf.max_iterations}")
        return workflow_id

    # ─── Phase Management ──────────────────────────────────────────────────
    def start_phase(self, workflow_id, phase, agent_role, input_data=None):
        """Start a new phase/work unit in a workflow."""
        wf = self._load_state(workflow_id)
        if not wf:
            print(f"[coordinator] Workflow {workflow_id} not found")
            return None

        wu = WorkUnit(
            id=f"{workflow_id}_{phase}_{wf.iteration}",
            workflow=workflow_id,
            phase=phase,
            agent_role=agent_role,
            status="running",
            input_data=input_data or {},
            created_at=datetime.now().isoformat(),
        )

        wf.current_phase = phase
        wf.work_units.append(wu.to_dict())
        self._save_state(wf)

        return wu.id

    def complete_phase(self, workflow_id, phase, output_data=None, error=None):
        """Mark a phase as completed."""
        wf = self._load_state(workflow_id)
        if not wf:
            return

        for wu in wf.work_units:
            if wu.get("phase") == phase and wu.get("status") == "running":
                wu["status"] = "failed" if error else "done"
                wu["output_data"] = output_data or {}
                wu["completed_at"] = datetime.now().isoformat()
                if error:
                    wu["error"] = str(error)
                break

        self._save_state(wf)

    def complete_workflow(self, workflow_id, status="completed"):
        """Mark the entire workflow as completed."""
        wf = self._load_state(workflow_id)
        if not wf:
            return

        wf.status = status
        wf.completed_at = datetime.now().isoformat()
        self._save_state(wf)
        print(f"[coordinator] Workflow {workflow_id} → {status}")

    # ─── Scratchpad ────────────────────────────────────────────────────────
    def append_scratchpad(self, workflow_id, entry):
        """Append a finding/note to the shared scratchpad."""
        sp = self._scratchpad_file(workflow_id)
        record = {
            "ts": datetime.now().isoformat(),
            **entry,
        }
        with open(sp, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_scratchpad(self, workflow_id):
        """Read all scratchpad entries."""
        sp = self._scratchpad_file(workflow_id)
        if not sp.exists():
            return []
        entries = []
        with open(sp, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass
        return entries

    # ─── Status & History ──────────────────────────────────────────────────
    def get_status(self, workflow_id):
        """Get current state of a workflow."""
        wf = self._load_state(workflow_id)
        if not wf:
            return None
        return wf.to_dict()

    def list_workflows(self):
        """List all workflows."""
        workflows = []
        if TMP.exists():
            for d in sorted(TMP.iterdir()):
                if d.is_dir():
                    state_file = d / "state.json"
                    if state_file.exists():
                        try:
                            data = json.loads(state_file.read_text(encoding="utf-8"))
                            workflows.append({
                                "id": data.get("id", d.name),
                                "template": data.get("template", "?"),
                                "status": data.get("status", "?"),
                                "created": data.get("created_at", "?")[:16],
                                "phases": data.get("work_units_count", 0),
                            })
                        except Exception:
                            pass
        return workflows

    def get_history(self, days=7):
        """Get recent workflow runs."""
        cutoff = datetime.now() - timedelta(days=days)
        history = []
        for wf in self.list_workflows():
            try:
                created = datetime.fromisoformat(wf["created"][:16] if "T" in wf["created"] else wf["created"])
                if created >= cutoff:
                    history.append(wf)
            except Exception:
                history.append(wf)  # Include if can't parse date
        return history

    # ─── Internal ──────────────────────────────────────────────────────────
    def _save_state(self, wf):
        state_file = self._state_file(wf.id)
        data = wf.to_dict()
        data["work_units"] = wf.work_units  # Keep full list
        state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_state(self, workflow_id):
        state_file = self._state_file(workflow_id)
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            wf = Workflow(
                id=data["id"],
                template=data.get("template", ""),
                params=data.get("params", {}),
                status=data.get("status", "running"),
                current_phase=data.get("current_phase", ""),
                iteration=data.get("iteration", 0),
                max_iterations=data.get("max_iterations", 2),
                created_at=data.get("created_at", ""),
                completed_at=data.get("completed_at", ""),
                work_units=data.get("work_units", []),
            )
            return wf
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Coordinator — Multi-Agent Orchestration Engine")
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="Start a new workflow")
    p_start.add_argument("--workflow", "-w", required=True, help="Template name")
    p_start.add_argument("--params", "-p", default="{}", help="JSON params")

    # status
    p_status = sub.add_parser("status", help="Get workflow status")
    p_status.add_argument("--id", required=True, help="Workflow ID")

    # scratchpad
    p_sp = sub.add_parser("scratchpad", help="Read scratchpad")
    p_sp.add_argument("--id", required=True, help="Workflow ID")

    # list
    sub.add_parser("list", help="List all workflows")

    # history
    p_hist = sub.add_parser("history", help="Recent workflows")
    p_hist.add_argument("--days", type=int, default=7, help="Lookback days")

    args = parser.parse_args()
    engine = CoordinatorEngine()

    if args.command == "start":
        params = json.loads(args.params) if args.params else {}
        wf_id = engine.start_workflow(args.workflow, params)
        print(json.dumps({"workflow_id": wf_id}, indent=2))

    elif args.command == "status":
        status = engine.get_status(args.id)
        if status:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        else:
            print(f"Workflow {args.id} not found")

    elif args.command == "scratchpad":
        entries = engine.read_scratchpad(args.id)
        for e in entries:
            print(json.dumps(e, ensure_ascii=False))

    elif args.command == "list":
        workflows = engine.list_workflows()
        if workflows:
            for wf in workflows:
                print(f"  {wf['id']}  [{wf['status']}]  {wf['template']}  ({wf['created']})")
        else:
            print("  No workflows found")

    elif args.command == "history":
        history = engine.get_history(args.days)
        print(f"Workflows in last {args.days} days: {len(history)}")
        for wf in history:
            print(f"  {wf['id']}  [{wf['status']}]")


if __name__ == "__main__":
    main()
