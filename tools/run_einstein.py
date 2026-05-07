#!/usr/bin/env python3
"""
Einstein (아인슈타인) — Auto-Audit Health Check Agent
Collects data from GitHub Actions, mistakes.md, session summaries, and git log.
Analyzes patterns, finds issues, and sends a Teams report.

Usage:
    python tools/run_einstein.py --mode weekly --dry-run
    python tools/run_einstein.py --mode daily
    python tools/run_einstein.py --mode weekly --no-teams
"""

import sys
import os
import re
import json
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent

# --- Paths ---
# mistakes.md can be in two locations: local .claude memory or project memory/
MISTAKES_PATHS = [
    Path(os.path.expanduser("~")) / ".claude" / "projects"
    / "z--ORBI-CLAUDE-0223-ORBITERS-CLAUDE-ORBITERS-CLAUDE------"
    / "memory" / "mistakes.md",
    PROJECT_ROOT / "memory" / "mistakes.md",
]

SESSION_DIRS = [
    Path(os.path.expanduser("~")) / ".claude" / "projects"
    / "z--ORBI-CLAUDE-0223-ORBITERS-CLAUDE-ORBITERS-CLAUDE------"
    / "memory",
    PROJECT_ROOT / "memory",
]


def load_env():
    """Load .env file."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # Manual parse
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def run_cmd(cmd, timeout=60):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(PROJECT_ROOT)
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[ERROR] {e}"


# ============================================================
# Data Collectors
# ============================================================

def collect_github_actions(days=7):
    """Collect GitHub Actions run data via gh CLI."""
    output = run_cmd(f'gh run list --limit 200 --json "workflowName,conclusion,createdAt,updatedAt"')
    if output.startswith("[ERROR]") or not output:
        return None

    try:
        runs = json.loads(output)
    except json.JSONDecodeError:
        return None

    cutoff = datetime.utcnow() - timedelta(days=days)
    workflow_stats = defaultdict(lambda: {"success": 0, "failure": 0, "other": 0, "total": 0})

    for run in runs:
        created = run.get("createdAt", "")
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            continue

        if dt < cutoff:
            continue

        name = run.get("workflowName", "Unknown")
        conclusion = run.get("conclusion", "").lower()
        workflow_stats[name]["total"] += 1

        if conclusion == "success":
            workflow_stats[name]["success"] += 1
        elif conclusion in ("failure", "timed_out"):
            workflow_stats[name]["failure"] += 1
        else:
            workflow_stats[name]["other"] += 1

    return dict(workflow_stats)


def collect_mistakes(days=7):
    """Parse mistakes.md for entries."""
    mistakes_path = None
    for p in MISTAKES_PATHS:
        if p.exists():
            mistakes_path = p
            break

    if not mistakes_path:
        return None

    try:
        content = mistakes_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    entries = []
    current = None
    cutoff = datetime.now() - timedelta(days=days)

    in_template = False
    for line in content.split("\n"):
        # Stop parsing at Template section
        if re.match(r"^##\s+Template", line):
            in_template = True
            if current:
                entries.append(current)
                current = None
            continue
        if in_template:
            continue

        # Match ### M-0XX: title
        m = re.match(r"^### (M-\d+):\s*(.+)", line)
        if m:
            if current:
                entries.append(current)
            current = {"id": m.group(1), "title": m.group(2), "agent": "", "date": "", "lines": []}
            continue

        if current:
            current["lines"].append(line)
            # Extract agent
            am = re.match(r"^-\s*\*\*에이전트\*\*:\s*(.+)", line)
            if am:
                current["agent"] = am.group(1).strip()
            # Extract date
            dm = re.match(r"^-\s*\*\*날짜\*\*:\s*(\d{4}-\d{2}-\d{2})", line)
            if dm:
                current["date"] = dm.group(1).strip()

    if current:
        entries.append(current)

    # Filter by date if needed
    recent = []
    all_entries = []
    for e in entries:
        all_entries.append(e)
        if e["date"]:
            try:
                entry_dt = datetime.strptime(e["date"], "%Y-%m-%d")
                if entry_dt >= cutoff:
                    recent.append(e)
            except ValueError:
                pass

    return {"recent": recent, "all": all_entries}


def collect_sessions(days=7):
    """Read recent session summary files."""
    sessions = []
    cutoff = datetime.now() - timedelta(days=days)

    for session_dir in SESSION_DIRS:
        if not session_dir.exists():
            continue
        for f in session_dir.glob("session_*.md"):
            # Extract date from filename
            m = re.search(r"session_(\d{8})\.md", f.name)
            if not m:
                continue
            try:
                dt = datetime.strptime(m.group(1), "%Y%m%d")
            except ValueError:
                continue

            if dt < cutoff:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            sessions.append({
                "date": m.group(1),
                "file": f.name,
                "content": content,
            })

    # Deduplicate by date
    seen = set()
    unique = []
    for s in sessions:
        if s["date"] not in seen:
            seen.add(s["date"])
            unique.append(s)

    return sorted(unique, key=lambda x: x["date"], reverse=True)


def collect_git_log(days=7):
    """Collect git log for recent activity."""
    output = run_cmd(f'git log --since="{days} days ago" --oneline --name-only --all')
    if output.startswith("[ERROR]") or not output:
        return None

    commits = []
    current_commit = None
    tool_changes = defaultdict(int)

    for line in output.split("\n"):
        if not line.strip():
            continue
        # Commit line: hash message
        m = re.match(r"^([0-9a-f]{7,}) (.+)$", line)
        if m:
            current_commit = {"hash": m.group(1), "message": m.group(2), "files": []}
            commits.append(current_commit)
        elif current_commit and "/" in line:
            current_commit["files"].append(line.strip())
            if line.strip().startswith("tools/"):
                tool_name = line.strip().split("/")[1] if "/" in line.strip() else line.strip()
                tool_changes[tool_name] += 1

    return {"commits": commits, "tool_changes": dict(tool_changes), "total_commits": len(commits)}


# ============================================================
# Analysis
# ============================================================

def analyze_repeat_errors(mistakes_data):
    """Find agents with 2+ errors (repeat pattern)."""
    if not mistakes_data:
        return []

    agent_counts = defaultdict(list)
    for e in mistakes_data.get("all", []):
        if e["agent"]:
            agent_counts[e["agent"]].append(e)

    repeats = []
    for agent, entries in agent_counts.items():
        if len(entries) >= 2:
            repeats.append({
                "agent": agent,
                "count": len(entries),
                "latest": max((e["date"] for e in entries if e["date"]), default=""),
                "ids": [e["id"] for e in entries],
            })

    return sorted(repeats, key=lambda x: x["count"], reverse=True)


def analyze_actions_failures(actions_data):
    """Find workflows with >30% failure rate."""
    if not actions_data:
        return []

    warnings = []
    for name, stats in actions_data.items():
        total = stats["total"]
        if total == 0:
            continue
        fail_rate = stats["failure"] / total
        if fail_rate > 0.3:
            warnings.append({
                "workflow": name,
                "failure_rate": fail_rate,
                "failures": stats["failure"],
                "total": total,
            })

    return sorted(warnings, key=lambda x: x["failure_rate"], reverse=True)


def analyze_incomplete_tasks(sessions):
    """Extract incomplete tasks from sessions."""
    if not sessions:
        return []

    tasks = []
    keywords = ["미완료", "대기", "확인 필요", "확인 대기", "pending"]

    for s in sessions:
        in_incomplete_section = False
        for line in s["content"].split("\n"):
            line_stripped = line.strip()
            # Track if we're in the incomplete section
            if re.match(r"^#{2,3}\s.*미완료", line_stripped):
                in_incomplete_section = True
                continue
            if re.match(r"^#{2,3}\s", line_stripped) and in_incomplete_section:
                in_incomplete_section = False

            # Capture items in incomplete section or lines with keywords
            if in_incomplete_section and line_stripped.startswith("-"):
                clean = re.sub(r"^[-*\s]+", "", line_stripped)
                if clean and len(clean) > 5:
                    tasks.append({"date": s["date"], "task": clean[:120]})
            elif not in_incomplete_section:
                line_lower = line_stripped.lower()
                if any(kw in line_lower for kw in keywords):
                    if line_stripped.startswith("-"):
                        clean = re.sub(r"^[-*\s]+", "", line_stripped)
                        if clean and len(clean) > 5:
                            tasks.append({"date": s["date"], "task": clean[:120]})

    return tasks


def analyze_agent_activity(git_data, actions_data):
    """Map tool changes to agents and summarize activity."""
    if not git_data:
        return []

    # Map tool files to agent names
    TOOL_AGENT_MAP = {
        "amazon_ppc": "아마존 퍼포마",
        "run_amazon": "아마존 퍼포마",
        "ppc_": "아마존 퍼포마",
        "rakuten_": "쿠텐이",
        "kse_": "마존이/쿠텐이",
        "twitter_": "트위터 부대",
        "tweet": "트위터 부대",
        "soukantoku": "트위터 부대",
        "meta_": "메타 에이전트",
        "fetch_meta": "메타 에이전트",
        "gmail_rag": "이메일 지니",
        "influencer_": "인플루언서 매니저",
        "scout_": "인플루언서 매니저",
        "sync_sns": "CI 팀장",
        "fetch_apify": "CI 팀장",
        "run_ci_": "CI 팀장",
        "data_keeper": "데이터 키퍼",
        "run_kpi": "골만이",
        "kpi_": "골만이",
        "polar_": "골만이",
        "deploy_onzenna": "앱스터",
        "run_communicator": "커뮤니케이터",
        "shopify_tester": "UI테스터",
        "dual_test": "파이프라이너",
        "test_influencer": "파이프라이너",
        "run_einstein": "아인슈타인",
    }

    agent_commits = defaultdict(int)

    for tool_file, count in git_data.get("tool_changes", {}).items():
        matched = False
        for pattern, agent in TOOL_AGENT_MAP.items():
            if pattern in tool_file:
                agent_commits[agent] += count
                matched = True
                break
        if not matched:
            agent_commits["기타"] += count

    # Add actions success rates
    result = []
    for agent, commits in sorted(agent_commits.items(), key=lambda x: x[1], reverse=True):
        result.append({"agent": agent, "commits": commits})

    return result


# ============================================================
# Report Builder
# ============================================================

def build_report(mode, actions_data, mistakes_data, sessions, git_data):
    """Build the full analysis report."""
    today = datetime.now().strftime("%Y-%m-%d")
    days = 7 if mode == "weekly" else 1
    mode_label = "주간 헬스체크" if mode == "weekly" else "일일 미니체크"

    # Run analyses
    repeat_errors = analyze_repeat_errors(mistakes_data)
    action_failures = analyze_actions_failures(actions_data)
    incomplete = analyze_incomplete_tasks(sessions)
    agent_activity = analyze_agent_activity(git_data, actions_data)

    # Determine overall health
    has_critical = len(action_failures) > 0
    has_warnings = len(repeat_errors) > 0 or len(incomplete) > 3
    if has_critical:
        health_badge = "RED"
        health_icon = "&#x1F534;"
    elif has_warnings:
        health_badge = "YELLOW"
        health_icon = "&#x1F7E1;"
    else:
        health_badge = "GREEN"
        health_icon = "&#x1F7E2;"

    # --- Build sections ---
    sections = []

    # Header
    header = f"Einstein {mode_label} | {today} | {health_icon} {health_badge}"

    # Good things
    good = []
    if actions_data:
        total_runs = sum(s["total"] for s in actions_data.values())
        total_success = sum(s["success"] for s in actions_data.values())
        if total_runs > 0:
            rate = total_success / total_runs * 100
            good.append(f"GitHub Actions 전체 성공률: {rate:.0f}% ({total_success}/{total_runs})")

        # Highlight perfect workflows
        perfect = [name for name, s in actions_data.items() if s["total"] > 0 and s["failure"] == 0]
        if perfect and len(perfect) <= 8:
            good.append(f"무결점 워크플로우: {', '.join(perfect[:5])}" + (f" 외 {len(perfect)-5}개" if len(perfect) > 5 else ""))

    if git_data:
        good.append(f"최근 {days}일 커밋: {git_data['total_commits']}건")

    if mistakes_data:
        recent_count = len(mistakes_data.get("recent", []))
        total_count = len(mistakes_data.get("all", []))
        if recent_count == 0:
            good.append(f"최근 {days}일 신규 실수 0건 (누적 {total_count}건)")
        else:
            good.append(f"오답노트 시스템 작동 중 (누적 {total_count}건)")

    sections.append(("Good", good))

    # Warnings
    warnings = []
    for af in action_failures:
        pct = af["failure_rate"] * 100
        warnings.append(f"{af['workflow']}: 실패율 {pct:.0f}% ({af['failures']}/{af['total']})")

    for re_err in repeat_errors:
        warnings.append(
            f"{re_err['agent']}: 반복 에러 {re_err['count']}회 "
            f"({', '.join(re_err['ids'][-3:])})"
        )

    if mistakes_data:
        recent = mistakes_data.get("recent", [])
        if recent:
            for e in recent[:3]:
                warnings.append(f"[{e['id']}] {e['agent']}: {e['title'][:60]}")

    if not warnings:
        warnings.append("특이사항 없음")

    sections.append(("Warning", warnings))

    # Suggestions
    suggestions = []
    for af in action_failures:
        suggestions.append(f"{af['workflow']} 워크플로우 로그 확인 및 안정화 필요")

    for re_err in repeat_errors:
        if re_err["count"] >= 3:
            suggestions.append(f"{re_err['agent']} 에이전트 근본 원인 분석 권장 (누적 {re_err['count']}건)")

    if incomplete:
        suggestions.append(f"미완료 작업 {len(incomplete)}건 확인 필요")

    if not suggestions:
        suggestions.append("현재 시스템 안정. 유지 관리 모드")

    sections.append(("Suggestion", suggestions))

    # Ideas (weekly only)
    if mode == "weekly":
        ideas = []
        if actions_data and len(actions_data) > 15:
            ideas.append("워크플로우 수 많음 — 유사 워크플로우 통합 검토")
        if mistakes_data and len(mistakes_data.get("all", [])) > 40:
            ideas.append("오답노트 50건 돌파 임박 — 카테고리별 요약 정리 권장")
        if not ideas:
            ideas.append("시스템 건강 — 새로운 자동화 기회 탐색 가능")
        sections.append(("Idea", ideas))

    # Incomplete tasks
    if incomplete and mode == "weekly":
        task_lines = []
        for t in incomplete[:5]:
            task_lines.append(f"[{t['date']}] {t['task']}")
        sections.append(("Incomplete", task_lines))

    # Agent activity table
    activity_lines = []
    if agent_activity:
        for a in agent_activity[:10]:
            activity_lines.append(f"{a['agent']}: 커밋 {a['commits']}건")
    sections.append(("Activity", activity_lines))

    return header, sections


def format_plain_text(header, sections):
    """Format as plain text for dry-run."""
    lines = [f"\n{'='*60}", header, "=" * 60, ""]

    section_icons = {
        "Good": "[OK]",
        "Warning": "[!!]",
        "Suggestion": "[>>]",
        "Idea": "[**]",
        "Incomplete": "[..]",
        "Activity": "[~~]",
    }

    section_titles = {
        "Good": "잘된 것",
        "Warning": "주의",
        "Suggestion": "제안",
        "Idea": "아이디어",
        "Incomplete": "미완료 작업",
        "Activity": "에이전트 활동 요약",
    }

    for key, items in sections:
        icon = section_icons.get(key, "")
        title = section_titles.get(key, key)
        lines.append(f"{icon} {title}")
        for item in items:
            lines.append(f"  - {item}")
        lines.append("")

    return "\n".join(lines)


def build_teams_card(header, sections):
    """Build Teams Adaptive Card JSON (Power Automate compatible)."""
    # Power Automate workflow expects a specific format
    # Build a simple text body since the webhook is a Power Automate trigger
    section_icons = {
        "Good": "&#x2705;",
        "Warning": "&#x26A0;&#xFE0F;",
        "Suggestion": "&#x1F4A1;",
        "Idea": "&#x1F3AF;",
        "Incomplete": "&#x1F4CB;",
        "Activity": "&#x1F4CA;",
    }

    section_titles = {
        "Good": "잘된 것",
        "Warning": "주의",
        "Suggestion": "제안",
        "Idea": "아이디어",
        "Incomplete": "미완료 작업",
        "Activity": "에이전트 활동 요약",
    }

    body_parts = [f"**{header}**\n"]

    for key, items in sections:
        icon = section_icons.get(key, "")
        title = section_titles.get(key, key)
        body_parts.append(f"\n{icon} **{title}**")
        for item in items:
            body_parts.append(f"- {item}")

    body_text = "\n".join(body_parts)

    # Power Automate webhook format
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": header,
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True
                        },
                    ]
                }
            }
        ]
    }

    # Add sections as text blocks
    card_body = payload["attachments"][0]["content"]["body"]

    for key, items in sections:
        icon = section_icons.get(key, "")
        title = section_titles.get(key, key)

        card_body.append({
            "type": "TextBlock",
            "text": f"{icon} **{title}**",
            "weight": "Bolder",
            "spacing": "Medium",
            "wrap": True
        })

        bullet_text = "\n".join(f"- {item}" for item in items)
        card_body.append({
            "type": "TextBlock",
            "text": bullet_text,
            "wrap": True,
            "spacing": "Small"
        })

    return payload


def send_teams(payload):
    """Send payload to Teams webhook."""
    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL_SEEUN", "")
    if not webhook_url:
        print("[SKIP] TEAMS_WEBHOOK_URL_SEEUN not set")
        return False

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[TEAMS] Sent. Status: {status}")
            if status >= 400:
                print(f"[TEAMS] Response: {body[:200]}")
                return False
            return True
    except urllib.error.HTTPError as e:
        print(f"[TEAMS] HTTP Error {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
        return False
    except Exception as e:
        print(f"[TEAMS] Error: {e}")
        return False


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Einstein Auto-Audit Health Check")
    parser.add_argument("--mode", choices=["weekly", "daily"], default="weekly",
                        help="weekly (7 days) or daily (1 day)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print report without sending")
    parser.add_argument("--no-teams", action="store_true",
                        help="Skip Teams send")
    args = parser.parse_args()

    load_env()

    days = 7 if args.mode == "weekly" else 1
    print(f"[Einstein] Mode: {args.mode} | Days: {days} | Dry-run: {args.dry_run}")

    # Collect data
    print("[1/4] Collecting GitHub Actions data...")
    actions_data = collect_github_actions(days)
    if actions_data:
        total = sum(s["total"] for s in actions_data.values())
        print(f"  -> {len(actions_data)} workflows, {total} runs")
    else:
        print("  -> GitHub Actions data unavailable (gh CLI missing or not authenticated)")

    print("[2/4] Parsing mistakes.md...")
    mistakes_data = collect_mistakes(days)
    if mistakes_data:
        print(f"  -> {len(mistakes_data['all'])} total entries, {len(mistakes_data['recent'])} recent")
    else:
        print("  -> mistakes.md not found")

    print("[3/4] Reading session summaries...")
    sessions = collect_sessions(days)
    print(f"  -> {len(sessions)} session(s) found")

    print("[4/4] Collecting git log...")
    git_data = collect_git_log(days)
    if git_data:
        print(f"  -> {git_data['total_commits']} commits, {len(git_data['tool_changes'])} tool files changed")
    else:
        print("  -> Git log unavailable")

    # Build report
    print("\n[Analysis] Building report...")
    header, sections = build_report(args.mode, actions_data, mistakes_data, sessions, git_data)

    # Print plain text
    plain = format_plain_text(header, sections)
    print(plain)

    # Send to Teams
    if args.dry_run or args.no_teams:
        print("[SKIP] Teams send skipped (dry-run or --no-teams)")
    else:
        print("\n[Sending] Teams webhook...")
        card = build_teams_card(header, sections)
        success = send_teams(card)
        if success:
            print("[DONE] Report sent to Teams.")
        else:
            print("[FAIL] Teams send failed.")

    print("\n[Einstein] Complete.")


if __name__ == "__main__":
    main()
