"""
build_apify_report.py
====================
Generates a beautiful HTML email report for the Apify+SNS daily pipeline.
Reads .tmp/usa_llm_highlights.json and .tmp/apify_sns_summary.json.
Writes .tmp/apify_report.html

Usage:
    python tools/build_apify_report.py
    python tools/build_apify_report.py --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIGHLIGHTS_PATH  = PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json"
SNS_SUMMARY_PATH = PROJECT_ROOT / ".tmp" / "apify_sns_summary.json"
OUTPUT_PATH      = PROJECT_ROOT / ".tmp" / "apify_report.html"

# Maps each pipeline step to the output file it produces (for last-run detection)
STEP_OUTPUT_FILES = {
    "pipeline": PROJECT_ROOT / "Data Storage" / "apify",          # directory
    "orders":   PROJECT_ROOT / ".tmp" / "polar_data" / "q10_influencer_orders.json",
    "migrate":  PROJECT_ROOT / ".tmp" / "migrate_result.txt",
    "sns":      PROJECT_ROOT / ".tmp" / "apify_sns_summary.json",
    "llm":      PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json",
}

KST = timezone(timedelta(hours=9))


import subprocess as _subprocess


def gh_last_run_kst(workflow: str) -> tuple[str | None, str | None]:
    """Return (last_run_kst, status) for the most recent GitHub Actions run of a workflow."""
    try:
        result = _subprocess.run(
            ["gh", "run", "list", f"--workflow={workflow}", "--limit=1",
             "--json", "createdAt,conclusion"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None, None
        runs = json.loads(result.stdout)
        if not runs:
            return None, None
        r = runs[0]
        created = r.get("createdAt", "")
        conclusion = r.get("conclusion", "unknown")
        # Parse ISO8601 UTC → KST
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        kst_str = dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        return kst_str, conclusion
    except Exception:
        return None, None


# Cache workflow run times (call gh once per workflow, not per step)
_WF_CACHE: dict[str, tuple] = {}

def _wf_info(workflow: str) -> tuple[str | None, str | None]:
    if workflow not in _WF_CACHE:
        _WF_CACHE[workflow] = gh_last_run_kst(workflow)
    return _WF_CACHE[workflow]


def file_mtime_kst(path: Path) -> str | None:
    """Return last-modified time in KST as 'YYYY-MM-DD HH:MM KST', or None."""
    try:
        if path.is_dir():
            files = list(path.glob("*.json"))
            if not files:
                return None
            path = max(files, key=lambda f: f.stat().st_mtime)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=KST)
        return mtime.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return None


def infer_status(step: str, given: str) -> str:
    """If GitHub Actions didn't set the status, infer from GH Actions run result."""
    if given.lower() not in ("unknown", ""):
        return given
    _, conclusion = _wf_info("apify_daily.yml")
    if conclusion in ("success",):
        return "success"
    if conclusion in ("failure", "cancelled"):
        return "failure"
    return "unknown"


# ── Badge ─────────────────────────────────────────────────────────────────────

def badge(status: str) -> str:
    s = (status or "unknown").lower()
    if s == "success":
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#D1FAE5;color:#065F46;">&#10003; SUCCESS</span>'
        )
    elif s in ("failure", "failed"):
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#FEE2E2;color:#991B1B;">&#10007; FAILED</span>'
        )
    else:
        return (
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-family:\'Courier New\',monospace;font-weight:700;'
            'letter-spacing:0.5px;background:#E5E7EB;color:#6B7280;">&mdash; UNKNOWN</span>'
        )


# ── Order → product mapping ───────────────────────────────────────────────────

import re as _re

def _build_order_map() -> dict:
    """Build {username_lower: [product_title, ...]} from influencer orders."""
    orders_path = PROJECT_ROOT / ".tmp" / "polar_data" / "q10_influencer_orders.json"
    if not orders_path.exists():
        return {}
    try:
        data   = json.loads(orders_path.read_text(encoding="utf-8"))
        orders = data.get("orders", [])
    except Exception:
        return {}

    mapping: dict[str, list[str]] = {}
    handle_re = _re.compile(r"(?:IG|TikTok|Instagram|tiktok)[:\s]+@?([\w.]+)", _re.IGNORECASE)

    for o in orders:
        note  = o.get("note", "") or ""
        items = o.get("line_items", [])
        if not items:
            continue
        products = [li["title"] for li in items if li.get("title")]
        if not products:
            continue

        handles = [m.group(1).lower().strip() for m in handle_re.finditer(note)]
        for handle in handles:
            if handle not in mapping:
                mapping[handle] = []
            for p in products:
                if p not in mapping[handle]:
                    mapping[handle].append(p)

    return mapping


# ── Highlights ────────────────────────────────────────────────────────────────

def build_highlights_section(highlights: list) -> str:
    if not highlights:
        return ""

    order_map = _build_order_map()

    rows_html = ""
    for i, h in enumerate(highlights):
        username   = h.get("username", "")
        nickname   = h.get("nickname", "") or username
        url        = h.get("url", "")
        date_str   = h.get("date", "")
        views      = h.get("views", 0)
        hashtags   = h.get("hashtags", "")

        # products from order map
        products = order_map.get(username, [])
        prod_html = ""
        if products:
            prod_list = " &middot; ".join(
                f'<span style="background:#E0F2FE;color:#0369A1;padding:1px 6px;'
                f'border-radius:3px;font-size:9px;font-weight:600;">{p}</span>'
                for p in products[:2]
            )
            prod_html = f'<div style="margin-top:4px;">{prod_list}</div>'

        # top hashtags (first 4)
        hash_html = ""
        if hashtags:
            tags = [t.strip() for t in hashtags.replace(",", " ").split() if t.startswith("#")][:4]
            if tags:
                hash_html = (
                    '<div style="margin-top:3px;">'
                    + " ".join(
                        f'<span style="font-size:9px;color:#6B7280;font-family:\'Courier New\',monospace;">{t}</span>'
                        for t in tags
                    )
                    + "</div>"
                )

        link_html = (
            f'<a href="{url}" style="font-size:11px;font-family:\'Courier New\',monospace;'
            f'color:#1E3A5F;text-decoration:none;background:#EBF2FF;padding:2px 7px;'
            f'border-radius:4px;white-space:nowrap;">view&#8599;</a>'
            if url else ""
        )

        bg = "#FFFEF0" if i < 3 else "#FFFFFF"
        medal = ["🥇","🥈","🥉"][i] if i < 3 else f"#{i+1}"

        rows_html += f"""
        <tr style="background:{bg};border-bottom:1px solid #F0EFEC;">
          <td style="padding:10px 8px;font-size:16px;text-align:center;width:32px;">{medal}</td>
          <td style="padding:10px 8px;">
            <div style="font-size:12px;font-weight:700;color:#0A1628;">@{username}</div>
            <div style="font-size:10px;color:#6B7280;">{nickname}</div>
            {prod_html}
            {hash_html}
          </td>
          <td style="padding:10px 6px;text-align:center;white-space:nowrap;">
            <div style="font-family:'Courier New',monospace;font-size:14px;font-weight:700;
                        color:#F59E0B;">{views:,}</div>
            <div style="font-size:9px;color:#9CA3AF;">views</div>
          </td>
          <td style="padding:10px 6px;font-size:10px;color:#9CA3AF;
                     font-family:'Courier New',monospace;text-align:center;white-space:nowrap;">{date_str}</td>
          <td style="padding:10px 8px;text-align:right;">{link_html}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="margin-bottom:8px;">
        <span style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                     color:#9CA3AF;font-family:'Courier New',monospace;">&#11088; Today's Highlights</span>
        <span style="font-size:10px;color:#C9A84C;font-family:'Courier New',monospace;
                     margin-left:8px;">{len(highlights)} posts uploaded in the last 24h &middot; sorted by views</span>
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#F59E0B18;">
            <th style="padding:6px 8px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;width:32px;">#</th>
            <th style="padding:6px 8px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:left;">CREATOR &middot; PRODUCT &middot; TAGS</th>
            <th style="padding:6px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">VIEWS</th>
            <th style="padding:6px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">DATE</th>
            <th style="padding:6px 8px;width:60px;"></th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


# ── Pipeline Status ───────────────────────────────────────────────────────────

def build_pipeline_section(statuses: dict) -> str:
    steps = [
        ("pipeline", "Apify Crawl"),
        ("orders",   "Fetch Influencer Orders"),
        ("migrate",  "Syncly Migration"),
        ("sns",      "Grosmimi SNS Sync"),
        ("llm",      "USA_LLM Update"),
    ]
    # Get actual GH Actions run time (single call, cached)
    wf_last_run, _ = _wf_info("apify_daily.yml")

    rows = ""
    for i, (key, name) in enumerate(steps):
        status = infer_status(key, statuses.get(key, "unknown"))
        last_run = wf_last_run  # use GH Actions actual run time for all steps
        ts_html = (
            f'<span style="font-size:10px;color:#9CA3AF;font-family:\'Courier New\',monospace;'
            f'margin-left:8px;">Last run: {last_run}</span>'
            if last_run else
            '<span style="font-size:10px;color:#D1D5DB;font-family:\'Courier New\',monospace;'
            'margin-left:8px;">No data found</span>'
        )
        bg = "#FAFAF9" if i % 2 == 0 else "#F0EFEC"
        rows += f"""
        <tr>
          <td style="padding:10px 14px;font-size:13px;color:#374151;background:{bg};
                     border-bottom:1px solid #E9E7E4;">
            {name}{ts_html}
          </td>
          <td style="padding:10px 14px;text-align:right;background:{bg};
                     border-bottom:1px solid #E9E7E4;white-space:nowrap;">{badge(status)}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;
                  margin-bottom:10px;">Pipeline Status</div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        {rows}
      </table>
    </div>"""


# ── Stat cards ────────────────────────────────────────────────────────────────

def build_stat_card(label: str, value: str, sub: str = "") -> str:
    sub_html = (
        f'<div style="font-size:10px;color:#9CA3AF;margin-top:3px;">{sub}</div>'
        if sub else ""
    )
    return f"""
    <td style="padding:0 5px;">
      <div style="background:#FFFFFF;border:1px solid #E9E7E4;border-radius:8px;
                  padding:16px 12px;text-align:center;">
        <div style="font-family:'Courier New',monospace;font-size:26px;font-weight:700;
                    color:#0A1628;line-height:1;">{value}</div>
        <div style="font-size:11px;color:#6B7280;margin-top:5px;line-height:1.4;">{label}</div>
        {sub_html}
      </div>
    </td>"""


def build_stats_section(sns: dict, llm: dict, total_creators: int) -> str:
    # Shipped stats (from sync_sns_tab_grosmimi)
    total        = sns.get("total_influencers", 0)
    shipped_24h  = sns.get("new_24h", sns.get("new_count", 0))
    shipped_7d   = sns.get("new_7d", 0)
    shipped_30d  = sns.get("new_30d", 0)
    upd_c        = sns.get("update_count", 0)

    # Content detected stats (from update_usa_llm)
    content_24h  = llm.get("new_content_24h", 0)
    content_7d   = llm.get("new_content_7d", 0)
    content_30d  = llm.get("new_content_30d", 0)
    highlights_count = len(llm.get("highlights", []))

    wf_ts, _ = _wf_info("apify_daily.yml")
    ts_html = (
        f'<span style="font-size:10px;color:#9CA3AF;font-family:\'Courier New\',monospace;'
        f'margin-left:6px;">as of {wf_ts}</span>' if wf_ts else ""
    )

    def section_label(title):
        return (
            f'<div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;'
            f'color:#9CA3AF;font-family:\'Courier New\',monospace;margin-bottom:10px;">'
            f'{title} {ts_html}</div>'
        )

    return f"""
    <div style="margin-bottom:24px;">
      {section_label("Grosmimi US SNS &mdash; Newly Shipped")}
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr>
          {build_stat_card("Total Influencers", str(total))}
          {build_stat_card("Shipped · 24h", str(shipped_24h))}
          {build_stat_card("Shipped · 7d", str(shipped_7d))}
          {build_stat_card("Shipped · 30d", str(shipped_30d))}
          {build_stat_card("Updated", str(upd_c))}
        </tr>
      </table>
    </div>

    <div style="margin-bottom:24px;">
      {section_label("New Content Detected (USA_LLM)")}
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr>
          {build_stat_card("Creators Tracked", str(total_creators))}
          {build_stat_card("Content · 24h", str(content_24h), "new posts found")}
          {build_stat_card("Content · 7d", str(content_7d))}
          {build_stat_card("Content · 30d", str(content_30d))}
          {build_stat_card("Highlights Today", str(highlights_count), "first detected")}
        </tr>
      </table>
    </div>"""


# ── Links ─────────────────────────────────────────────────────────────────────

def build_links_section(repo: str, run_id: str) -> str:
    def link_btn(label: str, url: str, color: str = "#1E3A5F") -> str:
        return (
            f'<a href="{url}" style="display:inline-block;padding:9px 16px;'
            f'background:{color};color:#FFFFFF;text-decoration:none;'
            f'border-radius:6px;font-size:12px;font-weight:600;'
            f'font-family:\'Courier New\',monospace;letter-spacing:0.3px;'
            f'margin:4px 4px 4px 0;">{label} &#8599;</a>'
        )

    sns_url   = "https://docs.google.com/spreadsheets/d/1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
    apify_url = "https://docs.google.com/spreadsheets/d/1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
    actions_url = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    return f"""
    <div style="padding-top:16px;border-top:1px solid #E9E7E4;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;
                  margin-bottom:10px;">Quick Links</div>
      {link_btn("Grosmimi SNS", sns_url)}
      {link_btn("Apify Sheet", apify_url)}
      {link_btn("Actions Log", actions_url, "#374151") if actions_url else ""}
    </div>"""


# ── Ranking section (reuses build_ranking_dashboard logic) ───────────────────

MEDAL = ["🥇", "🥈", "🥉"]

def _fmt(n: int) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(n)

def _rank_row(rank: int, p: dict, accent: str) -> str:
    medal = MEDAL[rank - 1] if rank <= 3 else f"#{rank}"
    url   = p["url"]
    link  = (
        f'<a href="{url}" style="font-size:11px;font-family:\'Courier New\',monospace;'
        f'color:#1E3A5F;text-decoration:none;background:#EBF2FF;padding:2px 7px;'
        f'border-radius:4px;white-space:nowrap;">view&#8599;</a>' if url else ""
    )
    bg   = "#FFFEF0" if rank <= 3 else "#FFFFFF"
    foll = _fmt(p["followers"]) if p["followers"] else "—"
    return f"""
    <tr style="background:{bg};border-bottom:1px solid #F0EFEC;">
      <td style="padding:9px 6px;font-size:16px;text-align:center;width:30px;">{medal}</td>
      <td style="padding:9px 7px;">
        <div style="font-size:12px;font-weight:700;color:#0A1628;">@{p['username']}</div>
        <div style="font-size:10px;color:#6B7280;">{p['nickname'] or p['username']}</div>
      </td>
      <td style="padding:9px 5px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#374151;">{foll}</div>
        <div style="font-size:9px;color:#9CA3AF;">followers</div>
      </td>
      <td style="padding:9px 5px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:14px;font-weight:700;color:{accent};">{_fmt(p['views'])}</div>
        <div style="font-size:9px;color:#9CA3AF;">views</div>
      </td>
      <td style="padding:9px 5px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#374151;">{_fmt(p['likes'])}</div>
        <div style="font-size:9px;color:#9CA3AF;">likes</div>
      </td>
      <td style="padding:9px 5px;font-size:10px;color:#9CA3AF;font-family:'Courier New',monospace;
                 text-align:center;white-space:nowrap;">{p['date'] or '—'}</td>
      <td style="padding:9px 7px;text-align:right;">{link}</td>
    </tr>"""

def _ranking_block(title: str, emoji: str, posts: list, accent: str) -> str:
    if not posts:
        return ""
    rows = "".join(_rank_row(i+1, p, accent) for i, p in enumerate(posts))
    return f"""
    <div style="margin-bottom:24px;">
      <div style="margin-bottom:7px;">
        <span style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                     color:#9CA3AF;font-family:'Courier New',monospace;">{emoji} {title}</span>
        <span style="font-size:10px;color:#C9A84C;font-family:'Courier New',monospace;
                     margin-left:8px;">Top {len(posts)} posts</span>
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:{accent}15;">
            <th style="padding:6px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:center;width:30px;">#</th>
            <th style="padding:6px 7px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:left;">CREATOR</th>
            <th style="padding:6px 5px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:center;">FOLLOWERS</th>
            <th style="padding:6px 5px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:center;">VIEWS</th>
            <th style="padding:6px 5px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:center;">LIKES</th>
            <th style="padding:6px 5px;font-size:9px;color:#9CA3AF;font-weight:600;letter-spacing:1px;text-align:center;">DATE</th>
            <th style="padding:6px 7px;width:55px;"></th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""

def build_rankings_section(posts: list) -> str:
    if not posts:
        return ""
    today  = date.today()

    def top10(since=None):
        f = [p for p in posts if p["views"] > 0]
        if since:
            f = [p for p in f if p.get("date_obj") and p["date_obj"] >= since]
        seen = {}
        for p in f:
            k = p["url"] or f"{p['username']}_{p['date']}"
            if k not in seen or p["views"] > seen[k]["views"]:
                seen[k] = p
        return sorted(seen.values(), key=lambda x: x["views"], reverse=True)[:10]

    r7   = _ranking_block("Last 7 Days",  "🔥", top10(today - timedelta(days=7)),  "#EF4444")
    r30  = _ranking_block("Last 30 Days", "📈", top10(today - timedelta(days=30)), "#F59E0B")
    rall = _ranking_block("All-Time Best","👑", top10(),                            "#6366F1")

    return f"""
    <div style="padding-top:20px;border-top:1px solid #E9E7E4;margin-bottom:0;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:18px;">
        Content Rankings &middot; 🇺🇸 US Posts Master
      </div>
      {r7}{r30}{rall}
    </div>"""


def _load_us_posts_for_rankings() -> list:
    """Load US Posts Master silently; return [] on any error."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        from build_ranking_dashboard import load_posts
        return load_posts("US Posts Master")
    except Exception as e:
        print(f"[WARN] Could not load US posts for rankings: {e}")
        return []


# ── HTML assembly ─────────────────────────────────────────────────────────────

def build_html(
    date_str: str,
    highlights: list,
    total_creators: int,
    sns_summary: dict,
    llm_data: dict,
    statuses: dict,
    repo: str = "",
    run_id: str = "",
) -> str:
    highlights_html = build_highlights_section(highlights)
    pipeline_html   = build_pipeline_section(statuses)
    stats_html      = build_stats_section(sns_summary, llm_data, total_creators)

    # Load US posts for rankings (graceful fallback if sheets unavailable)
    us_posts       = _load_us_posts_for_rankings()
    rankings_html  = build_rankings_section(us_posts)

    links_html      = build_links_section(repo, run_id)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Apify+SNS Daily Report</title>
</head>
<body style="margin:0;padding:0;background:#EFEFEB;font-family:-apple-system,BlinkMacSystemFont,
             'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#EFEFEB;padding:24px 0;">
  <tr>
    <td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;border-top:3px solid #C9A84C;">

        <!-- HEADER -->
        <tr>
          <td style="background:#0A1628;padding:28px 32px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                               color:#C9A84C;font-family:'Courier New',monospace;
                               margin-bottom:6px;">Grosmimi &middot; Daily Report</div>
                  <div style="font-size:22px;font-weight:700;color:#FFFFFF;
                               font-family:Georgia,serif;line-height:1.2;">
                    Apify <span style="color:#C9A84C;">+</span> SNS Intelligence
                  </div>
                </td>
                <td style="text-align:right;vertical-align:top;">
                  <div style="font-family:'Courier New',monospace;font-size:12px;
                               color:#8899AA;line-height:1.6;">
                    {date_str}<br>
                    <span style="color:#4A6080;font-size:10px;">KST 08:00 AUTO</span>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="background:#F5F4F1;padding:28px 32px;">
            {highlights_html}
            {pipeline_html}
            {stats_html}
            {rankings_html}
            {links_html}
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#0A1628;padding:14px 32px;">
            <div style="font-size:10px;color:#4A6080;font-family:'Courier New',monospace;
                        letter-spacing:0.5px;">
              ORBI Systems &middot; Automated Pipeline Report &middot; Do not reply
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pipeline", default=os.environ.get("PIPELINE_OUTCOME", "unknown"))
    parser.add_argument("--orders",   default=os.environ.get("ORDERS_OUTCOME",   "unknown"))
    parser.add_argument("--migrate",  default=os.environ.get("MIGRATE_OUTCOME",  "unknown"))
    parser.add_argument("--sns",      default=os.environ.get("SNS_OUTCOME",      "unknown"))
    parser.add_argument("--llm",      default=os.environ.get("LLM_OUTCOME",      "unknown"))
    args = parser.parse_args()

    highlights, total_creators, llm_data = [], 0, {}
    if HIGHLIGHTS_PATH.exists():
        try:
            llm_data       = json.loads(HIGHLIGHTS_PATH.read_text(encoding="utf-8"))
            highlights     = llm_data.get("highlights", [])
            total_creators = llm_data.get("total_creators", 0)
        except Exception as e:
            print(f"[WARN] Could not load highlights: {e}")

    sns_summary = {}
    if SNS_SUMMARY_PATH.exists():
        try:
            sns_summary = json.loads(SNS_SUMMARY_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not load SNS summary: {e}")

    statuses = {
        "pipeline": args.pipeline,
        "orders":   args.orders,
        "migrate":  args.migrate,
        "sns":      args.sns,
        "llm":      args.llm,
    }

    date_str = datetime.now(tz=KST).strftime("%Y-%m-%d")
    repo     = os.environ.get("GITHUB_REPOSITORY", "")
    run_id   = os.environ.get("GITHUB_RUN_ID", "")

    html = build_html(
        date_str=date_str,
        highlights=highlights,
        total_creators=total_creators,
        sns_summary=sns_summary,
        llm_data=llm_data,
        statuses=statuses,
        repo=repo,
        run_id=run_id,
    )

    if args.dry_run:
        sys.stdout.buffer.write(html.encode("utf-8"))
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(html, encoding="utf-8")
        print(f"[build_apify_report] HTML written -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
