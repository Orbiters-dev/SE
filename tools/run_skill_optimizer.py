#!/usr/bin/env python3
"""
run_skill_optimizer.py -- ORBI Skill Optimizer

Reads .claude/skills/, uses Claude API to generate concrete improvement proposals
for each skill, and emails them daily.

Mandatory skills (always included): amazon-ppc-agent, golmani, syncly-crawler
Other skills: included if any of their files changed in the last N days.

Usage:
    python tools/run_skill_optimizer.py                  # propose + email
    python tools/run_skill_optimizer.py --dry-run        # no email
    python tools/run_skill_optimizer.py --preview        # save HTML to .tmp/
    python tools/run_skill_optimizer.py --model sonnet   # use Sonnet
    python tools/run_skill_optimizer.py --all            # include all skills
    python tools/run_skill_optimizer.py --days 30        # changed-within window
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
SKILLS_DIR    = PROJECT_ROOT / ".claude" / "skills"
TMP_DIR       = PROJECT_ROOT / ".tmp"
RECIPIENT     = os.getenv("COMMUNICATOR_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER        = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

MODEL_MAP = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-6",
}

# Always include these skills regardless of recent changes
MANDATORY_SKILLS = {"amazon-ppc-agent", "golmani", "syncly-crawler", "appster", "shopify-ui-expert"}

MAX_FILE_BYTES = 12_288   # 12 KB per skill file
MAX_REFS_PER_SKILL = 3    # max reference files to include per skill


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------

def get_recently_changed_skills(days: int = 14) -> set[str]:
    """Return skill names whose files were modified in the last N days (non-bulk commits)."""
    result = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--pretty=format:%H",
         "--", ".claude/skills/**"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    hashes = [h.strip() for h in result.stdout.strip().split("\n") if h.strip()]

    changed: set[str] = set()
    for h in hashes:
        files_result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", h],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        all_files = [f.strip() for f in files_result.stdout.strip().split("\n") if f.strip()]
        if len(all_files) > 25:
            continue  # bulk commit
        for f in all_files:
            p = Path(f)
            if p.parts and p.parts[0] == ".claude" and len(p.parts) >= 3 and p.parts[1] == "skills":
                changed.add(p.parts[2])
    return changed


def collect_skills(days: int = 14, include_all: bool = False) -> list[str]:
    """Return sorted list of skill names to analyze."""
    if include_all:
        return sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())

    recently_changed = get_recently_changed_skills(days)
    selected = MANDATORY_SKILLS | recently_changed
    # Filter to skills that actually exist
    existing = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir()}
    return sorted(selected & existing)


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_skill_context(skill_name: str) -> dict[str, str]:
    """
    Load SKILL.md + up to MAX_REFS_PER_SKILL reference files for a skill.
    Returns {relative_path: content_or_warning}.
    """
    skill_dir = SKILLS_DIR / skill_name
    files: dict[str, str] = {}

    # SKILL.md (always)
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        size = skill_md.stat().st_size
        if size > MAX_FILE_BYTES:
            files[f".claude/skills/{skill_name}/SKILL.md"] = f"[SKIPPED: {size} bytes > {MAX_FILE_BYTES}]"
        else:
            files[f".claude/skills/{skill_name}/SKILL.md"] = skill_md.read_text(encoding="utf-8", errors="replace")

    # Reference files (up to MAX_REFS_PER_SKILL, sorted by size asc to fit more)
    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        ref_files = sorted(refs_dir.glob("*.md"), key=lambda p: p.stat().st_size)
        loaded = 0
        for ref in ref_files:
            if loaded >= MAX_REFS_PER_SKILL:
                files[f".claude/skills/{skill_name}/references/{ref.name}"] = "[SKIPPED: ref cap reached]"
                continue
            size = ref.stat().st_size
            if size > MAX_FILE_BYTES:
                files[f".claude/skills/{skill_name}/references/{ref.name}"] = f"[SKIPPED: {size} bytes]"
            else:
                files[f".claude/skills/{skill_name}/references/{ref.name}"] = ref.read_text(encoding="utf-8", errors="replace")
                loaded += 1

    return files


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an ORBI Skill Optimizer. ORBI runs a WAT (Workflows/Agents/Tools) framework
where Claude Code skills define how the AI agent behaves for specific domains.

Given one or more skill files, generate concrete improvement proposals as a JSON array.
Each proposal must specify an exact text change (original -> replacement).

Rules:
- Only suggest changes you are CONFIDENT about
- Focus on: trigger keyword gaps, outdated tool references, missing capabilities, unclear instructions
- For SKILL.md: improve description, when-to-use, trigger keywords, tool references
- For reference/*.md: update outdated data, add missing edge cases, fix wrong values
- Maximum 3 proposals per skill (prioritize highest impact)
- If a skill looks complete and up-to-date, return 0 proposals for it
- NEVER suggest restructuring entire files — only targeted additions/edits

Response format (JSON array only, no markdown fences):
[
  {
    "id": 1,
    "skill": "amazon-ppc-agent",
    "file": ".claude/skills/amazon-ppc-agent/SKILL.md",
    "issue": "Missing trigger keyword for ACOS analysis",
    "rationale": "Users ask about ACOS frequently but 'ACOS 분석' is not in trigger list",
    "original": "- diagnosing campaign issues",
    "replacement": "- diagnosing campaign issues (ACOS 분석, ROAS 분석)"
  }
]
"""


def generate_proposals(skills: list[str], file_contexts: dict[str, dict[str, str]], model: str) -> list[dict]:
    """Single Claude API call for all skills. Returns list of proposal dicts."""
    if not ANTHROPIC_KEY:
        print("WARNING: ANTHROPIC_API_KEY not set -- skipping proposal generation")
        return []

    # Build user message
    skill_blocks = []
    for skill in skills:
        ctx = file_contexts.get(skill, {})
        block = f"=== SKILL: {skill} ===\n"
        for path, content in ctx.items():
            block += f"\n--- {path} ---\n{content}\n"
        skill_blocks.append(block)

    user_msg = "Generate improvement proposals for these skills:\n\n" + "\n\n".join(skill_blocks)

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model=MODEL_MAP[model],
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences robustly
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        raw = raw[first_newline + 1:] if first_newline != -1 else raw[3:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        proposals = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse proposals JSON: {e}")
        print(f"Raw response (first 500 chars): {raw[:500]}")
        return []

    if not isinstance(proposals, list):
        return []
    return proposals


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

PROPOSALS_PATH = TMP_DIR / "skill_proposals_latest.json"
EXECUTE_KEYWORDS = {"적용", "apply", "execute", "yes", "go", "approve"}


def save_proposals(proposals: list[dict], skill_count: int,
                   email_message_id: str = "", email_sent_at: str = "") -> Path:
    TMP_DIR.mkdir(exist_ok=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill_count": skill_count,
        "proposals": proposals,
        "executed": False,
    }
    if email_message_id:
        data["email_message_id"] = email_message_id
        data["email_sent_at"] = email_sent_at
    PROPOSALS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return PROPOSALS_PATH


# ---------------------------------------------------------------------------
# Execute proposals (apply text changes to skill files)
# ---------------------------------------------------------------------------

def execute_proposals(proposals: list[dict]) -> list[int]:
    """Apply proposals to skill files. Returns list of applied proposal IDs."""
    applied = []
    changed_files = []

    for p in proposals:
        pid = p.get("id", "?")
        file_rel = p.get("file", "")
        original = p.get("original", "")
        replacement = p.get("replacement", "")

        if not file_rel or not original or original == "FILE_NOT_EXISTS":
            print(f"  #{pid}: SKIP — missing file/original")
            continue

        file_path = PROJECT_ROOT / file_rel
        if not file_path.exists():
            print(f"  #{pid}: SKIP — file not found: {file_rel}")
            continue

        # Refuse to touch .env or secrets
        if any(part in file_rel for part in [".env", "credentials/", "secrets"]):
            print(f"  #{pid}: SKIP — protected path: {file_rel}")
            continue

        text = file_path.read_text(encoding="utf-8", errors="replace")
        if original not in text:
            print(f"  #{pid}: SKIP — original text not found in {file_rel}")
            continue

        new_text = text.replace(original, replacement, 1)
        diff_lines = list(difflib.unified_diff(
            text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{file_rel}", tofile=f"b/{file_rel}",
        ))
        print(f"\n  #{pid}: {p.get('issue', '')} [{file_rel}]")
        print("".join(diff_lines) if diff_lines else "  (no diff)")

        file_path.write_text(new_text, encoding="utf-8")
        applied.append(pid)
        if file_rel not in changed_files:
            changed_files.append(file_rel)
        print(f"  APPLIED #{pid}")

    if applied and changed_files:
        applied_str = ",".join(str(i) for i in applied)
        try:
            subprocess.run(["git", "add"] + changed_files, cwd=str(PROJECT_ROOT), check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat(skills): optimizer apply proposals #{applied_str}"],
                cwd=str(PROJECT_ROOT), check=True,
            )
            print(f"\nCommitted: proposals #{applied_str}")
        except subprocess.CalledProcessError as e:
            print(f"WARNING: git commit failed: {e}")

    return applied


# ---------------------------------------------------------------------------
# Check-execute: poll Gmail for "적용" reply and auto-apply
# ---------------------------------------------------------------------------

def check_and_execute() -> None:
    """Poll Gmail for a reply containing an execute keyword, then apply all proposals."""
    if not PROPOSALS_PATH.exists():
        print("[check-execute] No skill_proposals_latest.json found.")
        return

    data = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))

    if data.get("executed"):
        print("[check-execute] Already executed. Skipping.")
        return

    sent_at_str = data.get("email_sent_at", "")
    if not sent_at_str:
        print("[check-execute] No email_sent_at recorded. Skipping.")
        return

    proposals = data.get("proposals", [])
    if not proposals:
        print("[check-execute] No proposals to execute.")
        return

    try:
        sent_at = datetime.fromisoformat(sent_at_str)
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
    except ValueError:
        sent_at = None

    # Search Gmail for replies
    sys.path.insert(0, str(Path(__file__).parent))
    from send_gmail import search_emails

    query = f'subject:"[ORBI Skills]" from:{RECIPIENT} newer_than:3d'
    print(f"[check-execute] Gmail query: {query}")
    messages = search_emails(query, max_results=10)

    if not messages:
        print("[check-execute] No reply emails found.")
        return

    found = False
    for msg in messages:
        # Check timing
        if sent_at:
            try:
                from email.utils import parsedate_to_datetime
                msg_date = parsedate_to_datetime(msg.get("date", ""))
                if msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)
                if msg_date < sent_at:
                    continue
            except Exception:
                pass

        body_lower = (msg.get("body", "") + " " + msg.get("snippet", "")).lower().strip()
        for kw in EXECUTE_KEYWORDS:
            if kw in body_lower.split() or body_lower.startswith(kw):
                print(f"[check-execute] Found '{kw}' in reply — applying proposals")
                found = True
                break
        if found:
            break

    if not found:
        print("[check-execute] No execute reply detected.")
        return

    print(f"\n[check-execute] Applying {len(proposals)} proposals...")
    applied = execute_proposals(proposals)

    if applied:
        data["executed"] = True
        data["executed_at"] = datetime.now(timezone.utc).isoformat()
        PROPOSALS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Send confirmation email
        applied_str = ", ".join(f"#{i}" for i in applied)
        conf_html = f"""<html><body style="font-family:sans-serif;padding:24px;">
<h3>✅ Skill Optimizer — Applied {len(applied)} proposals</h3>
<p>Proposals {applied_str} were applied and committed.</p>
<ul>{"".join(f"<li>#{p['id']} {p.get('skill','')}: {p.get('issue','')}</li>" for p in proposals if p.get("id") in applied)}</ul>
</body></html>"""
        conf_path = TMP_DIR / "skill_optimizer_confirmation.html"
        conf_path.write_text(conf_html, encoding="utf-8")
        date_str = datetime.now().strftime("%Y-%m-%d")
        try:
            subprocess.run(
                [sys.executable, str(Path(__file__).parent / "send_gmail.py"),
                 "--to", RECIPIENT, "--sender", SENDER,
                 "--subject", f"[ORBI Skills] APPLIED {len(applied)} proposals -- {date_str}",
                 "--body-file", str(conf_path)],
                check=True,
            )
            print("[check-execute] Confirmation email sent.")
        except Exception as e:
            print(f"[check-execute] Confirmation email failed: {e}")
    else:
        print("[check-execute] No proposals were applicable.")


# ---------------------------------------------------------------------------
# HTML email
# ---------------------------------------------------------------------------

SEVERITY_ICON = {"SKILL.md": "🔵", "references": "🟡"}
SKILL_ICON = {
    "amazon-ppc-agent": "📊",
    "golmani": "💼",
    "syncly-crawler": "🕷️",
    "appster": "📱",
    "shopify-ui-expert": "🛒",
    "kpi-monthly": "📈",
}

def build_email(proposals: list[dict], skill_count: int, date_str: str) -> str:
    by_skill: dict[str, list[dict]] = {}
    for p in proposals:
        sk = p.get("skill", "unknown")
        by_skill.setdefault(sk, []).append(p)

    cards = ""
    for skill, skill_props in by_skill.items():
        icon = SKILL_ICON.get(skill, "🔧")
        mandatory_badge = " <span style='background:#e8f5e9;color:#2e7d32;font-size:11px;padding:2px 6px;border-radius:10px;'>필수</span>" if skill in MANDATORY_SKILLS else ""
        cards += f"""
        <div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;margin-bottom:20px;overflow:hidden;">
          <div style="background:#f5f5f5;padding:12px 16px;border-bottom:1px solid #e0e0e0;">
            <strong style="font-size:15px;">{icon} {skill}</strong>{mandatory_badge}
            <span style="float:right;color:#666;font-size:13px;">{len(skill_props)} proposals</span>
          </div>"""
        for p in skill_props:
            pid = p.get("id", "?")
            file_short = Path(p.get("file", "")).name
            issue = p.get("issue", "")
            rationale = p.get("rationale", "")
            orig = p.get("original", "")
            repl = p.get("replacement", "")
            cards += f"""
          <div style="padding:14px 16px;border-bottom:1px solid #f0f0f0;">
            <div style="font-weight:600;margin-bottom:4px;">#{pid} — {issue}</div>
            <div style="color:#555;font-size:13px;margin-bottom:8px;">{file_short} · {rationale}</div>
            <table style="width:100%;font-size:12px;font-family:monospace;">
              <tr>
                <td style="background:#ffeef0;padding:6px 8px;border-radius:4px 4px 0 0;color:#b71c1c;white-space:pre-wrap;word-break:break-all;">- {orig}</td>
              </tr>
              <tr>
                <td style="background:#e6ffed;padding:6px 8px;border-radius:0 0 4px 4px;color:#1b5e20;white-space:pre-wrap;word-break:break-all;">+ {repl}</td>
              </tr>
            </table>
          </div>"""
        cards += "\n        </div>"

    mandatory_note = ", ".join(sorted(MANDATORY_SKILLS))
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9f9f9;padding:24px;color:#333;">
  <div style="max-width:680px;margin:0 auto;">
    <div style="background:#1a237e;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
      <h2 style="margin:0;font-size:18px;">🧠 ORBI Skill Optimizer</h2>
      <div style="opacity:0.8;font-size:13px;margin-top:4px;">{date_str} · {skill_count} skills analyzed · {len(proposals)} proposals</div>
    </div>
    <div style="background:#e8eaf6;padding:10px 16px;font-size:13px;color:#3949ab;">
      필수 포함: {mandatory_note}
    </div>
    <div style="background:#fff;padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;">
      {cards if proposals else '<p style="color:#888;text-align:center;">No proposals generated — all skills look up-to-date.</p>'}
    </div>
    <div style="text-align:center;color:#999;font-size:12px;margin-top:16px;">
      ORBI Skill Optimizer · auto-generated
    </div>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Send email
# ---------------------------------------------------------------------------

def send_email(html: str, date_str: str, proposal_count: int) -> str:
    """Send proposal email. Returns Gmail message ID (or '' on failure)."""
    TMP_DIR.mkdir(exist_ok=True)
    tmp_html = TMP_DIR / "skill_optimizer_preview.html"
    tmp_html.write_text(html, encoding="utf-8")
    subject = f"[ORBI Skills] {proposal_count} proposals -- {date_str}"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "send_gmail.py"),
         "--to", RECIPIENT,
         "--sender", SENDER,
         "--subject", subject,
         "--body-file", str(tmp_html)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(result.stdout)
        raise RuntimeError(f"send_gmail failed: {result.stderr}")
    print(result.stdout, end="")
    match = re.search(r"Message ID:\s*(\S+)", result.stdout)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ORBI Skill Optimizer")
    parser.add_argument("--dry-run",       action="store_true", help="No email")
    parser.add_argument("--preview",       action="store_true", help="Save HTML to .tmp/")
    parser.add_argument("--model",         default="haiku",     help="haiku or sonnet")
    parser.add_argument("--days",          type=int, default=14, help="Changed-within window for non-mandatory skills")
    parser.add_argument("--all",           action="store_true", help="Include all skills")
    parser.add_argument("--check-execute", action="store_true", help="Poll Gmail for reply and auto-apply")
    args = parser.parse_args()

    if args.check_execute:
        check_and_execute()
        return

    if args.model not in MODEL_MAP:
        print(f"ERROR: --model must be one of: {', '.join(MODEL_MAP)}")
        sys.exit(1)

    print("=== ORBI Skill Optimizer ===")
    skills = collect_skills(days=args.days, include_all=args.all)
    mandatory_present = sorted(MANDATORY_SKILLS & set(skills))
    optional_present  = sorted(set(skills) - MANDATORY_SKILLS)
    print(f"Skills to analyze: {len(skills)}")
    print(f"  Mandatory: {mandatory_present}")
    if optional_present:
        print(f"  Recently changed: {optional_present}")

    # Load file contexts
    file_contexts: dict[str, dict[str, str]] = {}
    for skill in skills:
        file_contexts[skill] = load_skill_context(skill)
    total_files = sum(len(v) for v in file_contexts.values())
    print(f"Loaded {total_files} file(s) across {len(skills)} skills")

    proposals = generate_proposals(skills, file_contexts, model=args.model)
    print(f"Generated {len(proposals)} proposals")

    if not proposals and not args.dry_run:
        print("No proposals. Exiting.")
        return

    # Save without message ID first (will update after sending)
    save_proposals(proposals, skill_count=len(skills))
    print("Saved to .tmp/skill_proposals_latest.json")

    date_str = datetime.now().strftime("%Y-%m-%d")
    html = build_email(proposals, skill_count=len(skills), date_str=date_str)

    if args.preview or args.dry_run:
        preview_path = TMP_DIR / "skill_optimizer_preview.html"
        TMP_DIR.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        print(f"Preview saved to {preview_path}")

    if args.dry_run:
        print("[dry-run] Email not sent.")
        return

    msg_id = send_email(html, date_str, proposal_count=len(proposals))
    sent_at = datetime.now(timezone.utc).isoformat()
    # Re-save with message ID for check-execute to use
    save_proposals(proposals, skill_count=len(skills),
                   email_message_id=msg_id, email_sent_at=sent_at)
    print("Skill proposal email sent.")


if __name__ == "__main__":
    main()
