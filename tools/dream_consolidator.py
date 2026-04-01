#!/usr/bin/env python3
"""
Dream Consolidator — Proactive memory consolidation engine.
Inspired by Claude Code's "Dream System" (autoDream).

4-Phase Cycle:
  1. Orient  — Read current memory state
  2. Gather  — Collect new signals (errors, logs, git, GH Actions)
  3. Consolidate — Deduplicate, rank, archive stale entries
  4. Prune   — Keep mistakes.md under 200 lines, rotate logs

Usage:
    python tools/dream_consolidator.py                # Full consolidation
    python tools/dream_consolidator.py --dry-run      # Preview only, no writes
    python tools/dream_consolidator.py --status       # Show current state
    python tools/dream_consolidator.py --force         # Ignore lock timer

Trigger: GitHub Actions cron (PST 23:00) or manual.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
MEMORY = ROOT / "memory"
MISTAKES = MEMORY / "mistakes.md"
MISTAKES_ARCHIVE = MEMORY / "mistakes_archive.md"
OPERATIONAL_SUMMARY = MEMORY / "operational_summary.md"
DREAM_LOCK = MEMORY / ".dream-lock"
DAILY_LOG_DIR = MEMORY / "daily_log"
ERROR_LOG = Path(os.path.expanduser(
    "~/.claude/projects/c--Users-wjcho-Desktop-WJ-Test1/memory/error_log.jsonl"
))

MAX_MISTAKES_LINES = 200
LOCK_COOLDOWN_HOURS = 20
ERROR_LOG_MAX_ENTRIES = 500
DAILY_LOG_RETAIN_DAYS = 30
STALE_DAYS = 30  # Archive mistakes not seen in 30 days


# ═════════════════════════════════════════════════════════════════════════════
# Lock Management
# ═════════════════════════════════════════════════════════════════════════════

def check_lock(force=False):
    """Return True if we can proceed, False if locked."""
    if force:
        return True
    if not DREAM_LOCK.exists():
        return True
    try:
        last_run = datetime.fromisoformat(DREAM_LOCK.read_text().strip())
        elapsed = datetime.now() - last_run
        return elapsed > timedelta(hours=LOCK_COOLDOWN_HOURS)
    except Exception:
        return True


def update_lock():
    """Update the lock file with current timestamp."""
    DREAM_LOCK.write_text(datetime.now().isoformat())


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1: Orient
# ═════════════════════════════════════════════════════════════════════════════

def orient():
    """Read current memory state, return stats."""
    stats = {
        "mistakes_lines": 0,
        "mistakes_entries": 0,
        "error_log_entries": 0,
        "daily_log_files": 0,
        "daily_log_entries": 0,
    }

    # Count mistakes.md
    if MISTAKES.exists():
        content = MISTAKES.read_text(encoding="utf-8")
        stats["mistakes_lines"] = len(content.split("\n"))
        stats["mistakes_entries"] = len(re.findall(r"### M-\d+", content))

    # Count error_log.jsonl
    if ERROR_LOG.exists():
        try:
            with open(ERROR_LOG, "r", encoding="utf-8") as f:
                stats["error_log_entries"] = sum(1 for _ in f)
        except Exception:
            pass

    # Count daily logs
    if DAILY_LOG_DIR.exists():
        log_files = list(DAILY_LOG_DIR.glob("*.jsonl"))
        stats["daily_log_files"] = len(log_files)
        for lf in log_files:
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    stats["daily_log_entries"] += sum(1 for _ in f)
            except Exception:
                pass

    return stats


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2: Gather
# ═════════════════════════════════════════════════════════════════════════════

def gather():
    """Collect signals from error log and daily logs."""
    signals = {
        "error_frequency": Counter(),
        "recent_errors": [],
        "tool_usage": Counter(),
        "daily_actions_7d": 0,
    }

    # Error frequency from error_log.jsonl
    if ERROR_LOG.exists():
        try:
            with open(ERROR_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        cat = entry.get("category", "unknown")
                        signals["error_frequency"][cat] += 1
                        # Recent (last 7 days)
                        ts = entry.get("timestamp", "")
                        if ts:
                            try:
                                dt = datetime.fromisoformat(ts)
                                if datetime.now() - dt < timedelta(days=7):
                                    signals["recent_errors"].append(entry)
                            except Exception:
                                pass
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    # Daily log stats (last 7 days)
    if DAILY_LOG_DIR.exists():
        cutoff = datetime.now() - timedelta(days=7)
        for lf in DAILY_LOG_DIR.glob("*.jsonl"):
            try:
                date_str = lf.stem  # YYYY-MM-DD
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date >= cutoff:
                    with open(lf, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                entry = json.loads(line.strip())
                                signals["tool_usage"][entry.get("tool", "?")] += 1
                                signals["daily_actions_7d"] += 1
                            except json.JSONDecodeError:
                                pass
            except (ValueError, Exception):
                pass

    return signals


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3: Consolidate
# ═════════════════════════════════════════════════════════════════════════════

def consolidate(signals, dry_run=False):
    """Generate operational summary and identify stale mistakes."""
    results = {"archived": 0, "summary_generated": False}

    # Generate operational summary
    summary_lines = [
        f"# Operational Summary",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Error trends
    if signals["error_frequency"]:
        summary_lines.append("## Error Trends (All Time)")
        for cat, count in signals["error_frequency"].most_common(10):
            summary_lines.append(f"- {cat}: {count}")
        summary_lines.append("")

    # Recent error count
    recent_count = len(signals["recent_errors"])
    summary_lines.append(f"## Last 7 Days")
    summary_lines.append(f"- Errors: {recent_count}")
    summary_lines.append(f"- Total actions: {signals['daily_actions_7d']}")

    # Tool usage
    if signals["tool_usage"]:
        summary_lines.append("")
        summary_lines.append("## Tool Usage (7d)")
        for tool, count in signals["tool_usage"].most_common(8):
            summary_lines.append(f"- {tool}: {count}")

    summary_text = "\n".join(summary_lines)

    if not dry_run:
        OPERATIONAL_SUMMARY.write_text(summary_text, encoding="utf-8")
        results["summary_generated"] = True

    print(f"[dream] Operational summary: {len(summary_lines)} lines")

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Phase 4: Prune
# ═════════════════════════════════════════════════════════════════════════════

def prune(dry_run=False):
    """Keep files within size limits."""
    results = {"mistakes_pruned": False, "errors_rotated": False, "logs_cleaned": 0}

    # Prune mistakes.md if over limit
    if MISTAKES.exists():
        content = MISTAKES.read_text(encoding="utf-8")
        lines = content.split("\n")
        if len(lines) > MAX_MISTAKES_LINES:
            print(f"[dream] mistakes.md has {len(lines)} lines (limit: {MAX_MISTAKES_LINES})")

            # Split into sections by ### M-XXX
            sections = re.split(r'(?=### M-\d+)', content)
            header = sections[0] if sections else ""
            entries = sections[1:] if len(sections) > 1 else []

            if entries:
                # Keep newest half, archive oldest half
                midpoint = len(entries) // 2
                keep = entries[midpoint:]
                archive = entries[:midpoint]

                if not dry_run:
                    # Write archive
                    archive_header = f"# Archived Mistakes (by Dream Consolidator)\n"
                    archive_header += f"# Archived on: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                    existing_archive = ""
                    if MISTAKES_ARCHIVE.exists():
                        existing_archive = MISTAKES_ARCHIVE.read_text(encoding="utf-8")
                    MISTAKES_ARCHIVE.write_text(
                        archive_header + "".join(archive) + "\n" + existing_archive,
                        encoding="utf-8"
                    )

                    # Rewrite mistakes.md with kept entries
                    MISTAKES.write_text(header + "".join(keep), encoding="utf-8")
                    results["mistakes_pruned"] = True

                print(f"[dream] Archived {len(archive)} entries, kept {len(keep)}")

    # Rotate error_log.jsonl if over limit
    if ERROR_LOG.exists():
        try:
            with open(ERROR_LOG, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            if len(all_lines) > ERROR_LOG_MAX_ENTRIES:
                keep_lines = all_lines[-ERROR_LOG_MAX_ENTRIES:]
                if not dry_run:
                    with open(ERROR_LOG, "w", encoding="utf-8") as f:
                        f.writelines(keep_lines)
                    results["errors_rotated"] = True
                print(f"[dream] Rotated error_log: {len(all_lines)} → {len(keep_lines)}")
        except Exception as e:
            print(f"[dream] Error rotating error_log: {e}")

    # Clean old daily logs
    if DAILY_LOG_DIR.exists():
        cutoff = datetime.now() - timedelta(days=DAILY_LOG_RETAIN_DAYS)
        for lf in DAILY_LOG_DIR.glob("*.jsonl"):
            try:
                file_date = datetime.strptime(lf.stem, "%Y-%m-%d")
                if file_date < cutoff:
                    if not dry_run:
                        lf.unlink()
                    results["logs_cleaned"] += 1
                    print(f"[dream] Cleaned old log: {lf.name}")
            except (ValueError, Exception):
                pass

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Dream Consolidator — Proactive Memory Maintenance")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--force", action="store_true", help="Ignore lock timer")
    parser.add_argument("--status", action="store_true", help="Show current state only")
    args = parser.parse_args()

    print(f"[dream] Dream Consolidator starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check lock
    if not check_lock(force=args.force):
        print("[dream] Locked — last run was less than 20 hours ago. Use --force to override.")
        sys.exit(0)

    # Phase 1: Orient
    print("\n[dream] Phase 1: Orient")
    stats = orient()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if args.status:
        sys.exit(0)

    # Phase 2: Gather
    print("\n[dream] Phase 2: Gather")
    signals = gather()
    print(f"  error categories: {len(signals['error_frequency'])}")
    print(f"  recent errors (7d): {len(signals['recent_errors'])}")
    print(f"  daily actions (7d): {signals['daily_actions_7d']}")

    # Phase 3: Consolidate
    print("\n[dream] Phase 3: Consolidate")
    consolidate_results = consolidate(signals, dry_run=args.dry_run)

    # Phase 4: Prune
    print("\n[dream] Phase 4: Prune")
    prune_results = prune(dry_run=args.dry_run)

    # Update lock
    if not args.dry_run:
        update_lock()

    # Summary
    mode = "DRY RUN" if args.dry_run else "COMPLETE"
    print(f"\n[dream] === Dream {mode} ===")
    print(f"  Summary generated: {consolidate_results.get('summary_generated', False)}")
    print(f"  Mistakes pruned: {prune_results.get('mistakes_pruned', False)}")
    print(f"  Errors rotated: {prune_results.get('errors_rotated', False)}")
    print(f"  Old logs cleaned: {prune_results.get('logs_cleaned', 0)}")


if __name__ == "__main__":
    main()
