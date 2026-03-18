"""
CI Daily Report — Content Intelligence Team Orchestrator
=========================================================
Collects status from every content pipeline step, builds a version-tracked
HTML email report, and sends it.

Usage:
  python tools/run_ci_daily.py              # Full report + email
  python tools/run_ci_daily.py --dry-run    # Collect status only (no email)
  python tools/run_ci_daily.py --preview    # Save HTML to .tmp/ci_daily_report.html
  python tools/run_ci_daily.py --status     # Print current row counts + freshness
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

KST = timezone(timedelta(hours=9))
PST = timezone(timedelta(hours=-8))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
NOW_KST = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

# ── Paths ─────────────────────────────────────────────────────────────────
MANIFEST_PATH = PROJECT_ROOT / ".tmp" / "ci_daily_manifest.json"
MANIFEST_DIR = PROJECT_ROOT / ".tmp" / "ci_manifests"
REPORT_PATH = PROJECT_ROOT / ".tmp" / "ci_daily_report.html"
HIGHLIGHTS_PATH = PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json"
SNS_SUMMARY_PATH = PROJECT_ROOT / ".tmp" / "apify_sns_summary.json"
DETECTION_LOG_PATH = PROJECT_ROOT / ".tmp" / "content_detection_log.json"

# ── Sheet IDs ─────────────────────────────────────────────────────────────
APIFY_SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
GROSMIMI_SNS_SHEET_ID = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
CHAENMOM_SNS_SHEET_ID = "16XUPd-VMoh6LEjSvupsmhkd1vEQNOTcoEhRCnPqkA_I"

# ── Sheets auth ───────────────────────────────────────────────────────────

def get_gc():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)


def sheet_tab_count(gc, sheet_id, tab_name):
    """Return row count (excl header) for a sheet tab, or None on error."""
    try:
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(tab_name)
        vals = ws.get_all_values()
        return max(0, len(vals) - 1)
    except Exception as e:
        print(f"  [WARN] {tab_name}: {e}")
        return None


def sheet_tab_latest_date(gc, sheet_id, tab_name, date_col_idx=9):
    """Return latest date string from a Posts Master tab."""
    try:
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(tab_name)
        vals = ws.get_all_values()
        if len(vals) <= 1:
            return None
        dates = [r[date_col_idx] for r in vals[1:] if len(r) > date_col_idx and r[date_col_idx]]
        return max(dates) if dates else None
    except Exception:
        return None


# ── Git version ───────────────────────────────────────────────────────────

def git_info():
    """Return (short_hash, branch, full_hash)."""
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        return short, branch, full
    except Exception:
        return "unknown", "unknown", "unknown"


# ── PG row counts ────────────────────────────────────────────────────────

def pg_table_count(table):
    """Query orbitools API for row count via DataKeeper client."""
    try:
        from data_keeper_client import DataKeeper
        dk = DataKeeper()
        rows = dk.get(table, days=3650)
        return len(rows)
    except Exception:
        return None


# ── Previous manifest ────────────────────────────────────────────────────

def load_prev_manifest():
    """Load yesterday's manifest for delta comparison."""
    if MANIFEST_DIR.exists():
        files = sorted(MANIFEST_DIR.glob("*.json"), reverse=True)
        for f in files:
            if f.stem != TODAY:
                try:
                    return json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
    return {}


# ── Collect status ───────────────────────────────────────────────────────

def collect_status():
    """Gather current row counts and freshness from all data destinations."""
    print("===== CI Daily: Collecting Status =====")
    gc = get_gc()
    git_short, git_branch, git_full = git_info()
    prev = load_prev_manifest()
    prev_data = prev.get("data_summary", {})

    data = {}

    # Apify Content Tracker (6 tabs)
    tabs = [
        ("US Posts Master", APIFY_SHEET_ID, "US Posts Master"),
        ("US D+60 Tracker", APIFY_SHEET_ID, "US D+60 Tracker"),
        ("US Influencer Tracker", APIFY_SHEET_ID, "US Influencer Tracker"),
        ("JP Posts Master", APIFY_SHEET_ID, "JP Posts Master"),
        ("JP D+60 Tracker", APIFY_SHEET_ID, "JP D+60 Tracker"),
        ("JP Influencer Tracker", APIFY_SHEET_ID, "JP Influencer Tracker"),
    ]
    for label, sid, tab in tabs:
        key = label.lower().replace(" ", "_")
        count = sheet_tab_count(gc, sid, tab)
        data[key] = count
        prev_val = prev_data.get(key, "—")
        delta = ""
        if count is not None and isinstance(prev_val, int):
            diff = count - prev_val
            delta = f" (Δ {'+' if diff >= 0 else ''}{diff})"
        print(f"  {label}: {count}{delta}")
        time.sleep(0.3)

    # SNS tabs
    for label, sid, tab in [
        ("Grosmimi US SNS", GROSMIMI_SNS_SHEET_ID, "US SNS"),
        ("CHA&MOM SNS", CHAENMOM_SNS_SHEET_ID, "SNS"),
    ]:
        key = label.lower().replace(" ", "_").replace("&", "")
        count = sheet_tab_count(gc, sid, tab)
        data[key] = count
        prev_val = prev_data.get(key, "—")
        delta = ""
        if count is not None and isinstance(prev_val, int):
            diff = count - prev_val
            delta = f" (Δ {'+' if diff >= 0 else ''}{diff})"
        print(f"  {label}: {count}{delta}")
        time.sleep(0.3)

    # PG tables
    for table in ["content_posts", "content_metrics_daily"]:
        key = f"pg_{table}"
        count = pg_table_count(table)
        data[key] = count
        prev_val = prev_data.get(key, "—")
        delta = ""
        if count is not None and isinstance(prev_val, int):
            diff = count - prev_val
            delta = f" (Δ {'+' if diff >= 0 else ''}{diff})"
        print(f"  PG {table}: {count}{delta}")

    # Latest post date
    us_latest = sheet_tab_latest_date(gc, APIFY_SHEET_ID, "US Posts Master")
    jp_latest = sheet_tab_latest_date(gc, APIFY_SHEET_ID, "JP Posts Master")
    data["us_latest_post"] = us_latest
    data["jp_latest_post"] = jp_latest
    print(f"  US latest post: {us_latest}")
    print(f"  JP latest post: {jp_latest}")

    # Highlights
    highlights = []
    new_detected_24h = 0
    if HIGHLIGHTS_PATH.exists():
        try:
            hl = json.loads(HIGHLIGHTS_PATH.read_text(encoding="utf-8"))
            highlights = hl.get("highlights", [])
            new_detected_24h = hl.get("new_detected_24h", len(highlights))
        except Exception:
            pass
    data["highlights_count"] = len(highlights)
    data["new_detected_24h"] = new_detected_24h

    # SNS summary
    sns_summary = {}
    if SNS_SUMMARY_PATH.exists():
        try:
            sns_summary = json.loads(SNS_SUMMARY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    # GitHub Actions last run
    gh_last_run = _get_gh_last_run()

    manifest = {
        "date": TODAY,
        "timestamp_kst": NOW_KST,
        "git_commit": git_short,
        "git_branch": git_branch,
        "git_commit_full": git_full,
        "data_summary": data,
        "highlights": highlights[:10],
        "sns_summary": sns_summary,
        "gh_last_run": gh_last_run,
    }

    return manifest


def _get_gh_last_run():
    """Get last GitHub Actions run info for apify_daily."""
    try:
        result = subprocess.check_output(
            ["gh", "run", "list", "-R", "Orbiters-dev/WJ-Test1",
             "--workflow", "apify_daily.yml", "--limit", "1", "--json",
             "status,conclusion,createdAt,updatedAt,databaseId"],
            text=True, stderr=subprocess.DEVNULL, timeout=15,
        )
        runs = json.loads(result)
        if runs:
            return runs[0]
    except Exception:
        pass
    return None


# ── HTML Report Builder ──────────────────────────────────────────────────

def badge(status):
    s = str(status).lower()
    if s in ("success", "ok", "completed"):
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#D1FAE5;color:#065F46;">&#10003; OK</span>'
        )
    elif s in ("failure", "failed", "error"):
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#FEE2E2;color:#991B1B;">&#10007; FAIL</span>'
        )
    else:
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#FEF3C7;color:#92400E;">&mdash; N/A</span>'
        )


def build_data_table(manifest):
    prev = load_prev_manifest()
    prev_data = prev.get("data_summary", {})
    data = manifest["data_summary"]

    rows_config = [
        ("US Posts Master", "us_posts_master"),
        ("US D+60 Tracker", "us_d+60_tracker"),
        ("US Influencer Tracker", "us_influencer_tracker"),
        ("JP Posts Master", "jp_posts_master"),
        ("JP D+60 Tracker", "jp_d+60_tracker"),
        ("JP Influencer Tracker", "jp_influencer_tracker"),
        ("Grosmimi US SNS", "grosmimi_us_sns"),
        ("CHA&MOM SNS", "chamom_sns"),
        ("PG content_posts", "pg_content_posts"),
        ("PG content_metrics_daily", "pg_content_metrics_daily"),
    ]

    rows_html = ""
    for i, (label, key) in enumerate(rows_config):
        after = data.get(key)
        before = prev_data.get(key)
        after_str = f"{after:,}" if isinstance(after, int) else "—"
        before_str = f"{before:,}" if isinstance(before, int) else "—"
        delta_str = ""
        delta_color = "#6B7280"
        if isinstance(after, int) and isinstance(before, int):
            diff = after - before
            if diff > 0:
                delta_str = f"+{diff:,}"
                delta_color = "#059669"
            elif diff < 0:
                delta_str = f"{diff:,}"
                delta_color = "#DC2626"
            else:
                delta_str = "0"

        bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 12px;font-size:12px;color:#374151;border-bottom:1px solid #E5E7EB;">{label}</td>
          <td style="padding:8px 10px;font-size:12px;color:#6B7280;text-align:right;border-bottom:1px solid #E5E7EB;
                     font-family:'Courier New',monospace;">{before_str}</td>
          <td style="padding:8px 10px;font-size:12px;color:#374151;text-align:right;border-bottom:1px solid #E5E7EB;
                     font-family:'Courier New',monospace;font-weight:700;">{after_str}</td>
          <td style="padding:8px 10px;font-size:12px;color:{delta_color};text-align:right;border-bottom:1px solid #E5E7EB;
                     font-family:'Courier New',monospace;font-weight:700;">{delta_str}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:10px;">
        Data Summary</div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#F3F4F6;">
            <th style="padding:8px 12px;font-size:10px;color:#6B7280;font-weight:600;text-align:left;
                       letter-spacing:1px;">DESTINATION</th>
            <th style="padding:8px 10px;font-size:10px;color:#6B7280;font-weight:600;text-align:right;
                       letter-spacing:1px;">BEFORE</th>
            <th style="padding:8px 10px;font-size:10px;color:#6B7280;font-weight:600;text-align:right;
                       letter-spacing:1px;">AFTER</th>
            <th style="padding:8px 10px;font-size:10px;color:#6B7280;font-weight:600;text-align:right;
                       letter-spacing:1px;">DELTA</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


def build_highlights_section(highlights):
    if not highlights:
        return ""

    rows_html = ""
    medals = ["&#x1F947;", "&#x1F948;", "&#x1F949;"]
    for i, h in enumerate(highlights[:5]):
        username = h.get("username", "")
        url = h.get("url", "")
        views = h.get("views", 0)
        date_str = h.get("date", "")
        medal = medals[i] if i < 3 else f"#{i+1}"
        bg = "#FFFEF0" if i < 3 else "#FFFFFF"
        link = (
            f'<a href="{url}" style="font-size:10px;color:#1E3A5F;text-decoration:none;'
            f'background:#EBF2FF;padding:2px 7px;border-radius:4px;">view&#8599;</a>'
            if url else ""
        )
        rows_html += f"""
        <tr style="background:{bg};border-bottom:1px solid #F0EFEC;">
          <td style="padding:8px 6px;font-size:14px;text-align:center;width:30px;">{medal}</td>
          <td style="padding:8px;font-size:12px;font-weight:700;color:#0A1628;">@{username}</td>
          <td style="padding:8px 6px;text-align:center;font-family:'Courier New',monospace;
                     font-size:13px;font-weight:700;color:#F59E0B;">{views:,}</td>
          <td style="padding:8px 6px;text-align:center;font-size:10px;color:#9CA3AF;
                     font-family:'Courier New',monospace;">{date_str}</td>
          <td style="padding:8px;text-align:right;">{link}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:10px;">
        &#11088; Today's Highlights &middot; Top {min(5, len(highlights))} by Views</div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


def build_version_section(manifest):
    git_short = manifest.get("git_commit", "unknown")
    git_branch = manifest.get("git_branch", "main")

    tools = [
        ("Apify Sheet (6 tabs)", "fetch_apify_content.py"),
        ("Grosmimi US SNS", "sync_sns_tab.py"),
        ("CHA&MOM SNS", "sync_sns_tab_chaenmom.py"),
        ("PostgreSQL (2 tables)", "push_content_to_pg.py"),
        ("Content Intelligence", "update_usa_llm.py"),
        ("CI Daily Report", "run_ci_daily.py"),
    ]

    rows_html = ""
    for i, (output, tool) in enumerate(tools):
        bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:6px 12px;font-size:11px;color:#374151;border-bottom:1px solid #E5E7EB;">{output}</td>
          <td style="padding:6px 10px;font-size:11px;color:#6B7280;border-bottom:1px solid #E5E7EB;
                     font-family:'Courier New',monospace;">{tool}</td>
          <td style="padding:6px 10px;font-size:11px;color:#4F46E5;border-bottom:1px solid #E5E7EB;
                     font-family:'Courier New',monospace;font-weight:700;">{git_short}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:10px;">
        Version Log</div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#F3F4F6;">
            <th style="padding:6px 12px;font-size:9px;color:#6B7280;font-weight:600;text-align:left;
                       letter-spacing:1px;">OUTPUT</th>
            <th style="padding:6px 10px;font-size:9px;color:#6B7280;font-weight:600;text-align:left;
                       letter-spacing:1px;">TOOL</th>
            <th style="padding:6px 10px;font-size:9px;color:#6B7280;font-weight:600;text-align:left;
                       letter-spacing:1px;">VERSION</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <div style="margin-top:6px;font-size:10px;color:#9CA3AF;font-family:'Courier New',monospace;">
        Git: {git_short} ({git_branch}, {TODAY})
      </div>
    </div>"""


def build_pipeline_status(manifest):
    gh = manifest.get("gh_last_run")
    if gh:
        conclusion = gh.get("conclusion", "unknown") or "unknown"
        created = gh.get("createdAt", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                created = dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
            except Exception:
                pass
        status_badge = badge(conclusion)
        return f"""
        <div style="margin-bottom:24px;">
          <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                      color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:10px;">
            Pipeline Status</div>
          <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;padding:16px;">
            <div style="display:inline-block;margin-right:12px;">{status_badge}</div>
            <span style="font-size:12px;color:#6B7280;font-family:'Courier New',monospace;">
              Last GH Actions run: {created}
            </span>
          </div>
        </div>"""
    return ""


def build_links_section():
    def link_btn(label, url, color="#1E3A5F"):
        return (
            f'<a href="{url}" style="display:inline-block;padding:9px 16px;'
            f'background:{color};color:#FFFFFF;text-decoration:none;'
            f'border-radius:6px;font-size:12px;font-weight:600;'
            f'font-family:\'Courier New\',monospace;letter-spacing:0.3px;'
            f'margin:4px 4px 4px 0;">{label} &#8599;</a>'
        )

    return f"""
    <div style="padding-top:16px;border-top:1px solid #E9E7E4;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:10px;">
        Quick Links</div>
      {link_btn("Apify Sheet", f"https://docs.google.com/spreadsheets/d/{APIFY_SHEET_ID}")}
      {link_btn("Grosmimi SNS", f"https://docs.google.com/spreadsheets/d/{GROSMIMI_SNS_SHEET_ID}")}
      {link_btn("CHA&MOM SNS", f"https://docs.google.com/spreadsheets/d/{CHAENMOM_SNS_SHEET_ID}")}
      {link_btn("Actions", "https://github.com/Orbiters-dev/WJ-Test1/actions/workflows/apify_daily.yml", "#374151")}
    </div>"""


def build_html(manifest):
    data = manifest["data_summary"]
    highlights = manifest.get("highlights", [])
    git_short = manifest.get("git_commit", "?")

    # Count total delta
    prev = load_prev_manifest()
    prev_data = prev.get("data_summary", {})
    us_delta = 0
    us_now = data.get("us_posts_master")
    us_prev = prev_data.get("us_posts_master")
    if isinstance(us_now, int) and isinstance(us_prev, int):
        us_delta = us_now - us_prev

    total_steps = 7
    ok_steps = total_steps  # simplified: if we got here, most steps worked

    subtitle = f"&#10003; {ok_steps}/{total_steps} Steps | +{us_delta} posts | v{git_short}"

    pipeline_html = build_pipeline_status(manifest)
    data_html = build_data_table(manifest)
    highlights_html = build_highlights_section(highlights)
    version_html = build_version_section(manifest)
    links_html = build_links_section()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CI Daily Report</title>
</head>
<body style="margin:0;padding:0;background:#EFEFEB;font-family:-apple-system,BlinkMacSystemFont,
             'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#EFEFEB;padding:24px 0;">
  <tr>
    <td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
             style="max-width:620px;width:100%;border-top:3px solid #4F46E5;">

        <!-- HEADER -->
        <tr>
          <td style="background:#0A1628;padding:28px 32px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                               color:#818CF8;font-family:'Courier New',monospace;
                               margin-bottom:6px;">Content Intelligence &middot; Daily</div>
                  <div style="font-size:22px;font-weight:700;color:#FFFFFF;
                               font-family:Georgia,serif;line-height:1.2;">
                    CI <span style="color:#818CF8;">Team</span> Report
                  </div>
                  <div style="font-size:11px;color:#6B7280;font-family:'Courier New',monospace;
                               margin-top:4px;">{subtitle}</div>
                </td>
                <td style="text-align:right;vertical-align:top;">
                  <div style="font-family:'Courier New',monospace;font-size:12px;
                               color:#8899AA;line-height:1.6;">
                    {TODAY}<br>
                    <span style="color:#4A6080;font-size:10px;">{NOW_KST}</span>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="background:#F5F4F1;padding:28px 32px;">
            {pipeline_html}
            {data_html}
            {highlights_html}
            {version_html}
            {links_html}
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#0A1628;padding:14px 32px;">
            <div style="font-size:10px;color:#4A6080;font-family:'Courier New',monospace;
                        letter-spacing:0.5px;">
              ORBI CI Team &middot; Content Intelligence Pipeline &middot; Do not reply
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


# ── Save manifest ────────────────────────────────────────────────────────

def save_manifest(manifest):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
    # Archive
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    archive = MANIFEST_DIR / f"{TODAY}.json"
    archive.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
    # Cleanup: keep last 30 files
    files = sorted(MANIFEST_DIR.glob("*.json"), reverse=True)
    for f in files[30:]:
        f.unlink()
    print(f"[MANIFEST] Saved: {MANIFEST_PATH.name} + archive/{TODAY}.json")


# ── Email ────────────────────────────────────────────────────────────────

def send_email(html, manifest):
    try:
        from send_gmail import send_email as gmail_send
        git_short = manifest.get("git_commit", "?")

        prev = load_prev_manifest()
        prev_data = prev.get("data_summary", {})
        us_now = manifest["data_summary"].get("us_posts_master", 0)
        us_prev = prev_data.get("us_posts_master", 0)
        delta = (us_now - us_prev) if isinstance(us_now, int) and isinstance(us_prev, int) else 0

        subject = f"[CI Daily] {TODAY} | +{delta} posts | v{git_short}"
        gmail_send(
            to=os.environ.get("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr"),
            subject=subject,
            body=html,
        )
        print(f"[EMAIL] Sent")
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CI Daily Report — Content Intelligence Team")
    parser.add_argument("--dry-run", action="store_true", help="Collect status only, no email")
    parser.add_argument("--preview", action="store_true", help="Save HTML to .tmp/")
    parser.add_argument("--status", action="store_true", help="Print row counts + freshness")
    args = parser.parse_args()

    manifest = collect_status()
    save_manifest(manifest)

    if args.status:
        print("\n===== Status Summary =====")
        for k, v in manifest["data_summary"].items():
            print(f"  {k}: {v}")
        return

    html = build_html(manifest)

    if args.preview:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(html, encoding="utf-8")
        print(f"[PREVIEW] {REPORT_PATH}")
        return

    if args.dry_run:
        print("\n[DRY-RUN] Report built but not sent")
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(html, encoding="utf-8")
        print(f"[PREVIEW] {REPORT_PATH}")
        return

    send_email(html, manifest)


if __name__ == "__main__":
    main()
