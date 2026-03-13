"""
build_apify_report.py
====================
Generates a beautiful HTML email report for the Apify+SNS daily pipeline.
Reads .tmp/usa_llm_highlights.json and .tmp/apify_sns_summary.json.
Writes .tmp/apify_report.html

Usage:
    python tools/build_apify_report.py
    python tools/build_apify_report.py --dry-run   # print HTML to stdout
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIGHLIGHTS_PATH = PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json"
SNS_SUMMARY_PATH = PROJECT_ROOT / ".tmp" / "apify_sns_summary.json"
OUTPUT_PATH = PROJECT_ROOT / ".tmp" / "apify_report.html"


# ── Status badge helpers ─────────────────────────────────────────────────────

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


# ── Section builders ─────────────────────────────────────────────────────────

def build_highlights_section(highlights: list) -> str:
    if not highlights:
        return ""

    items_html = ""
    for h in highlights:
        reasons_html = "".join(
            f'<div style="font-size:12px;color:#92400E;margin-top:3px;">&#9658; {r}</div>'
            for r in h.get("reasons", [])
        )
        url = h.get("url", "")
        link_html = (
            f'<a href="{url}" style="display:inline-block;margin-top:6px;'
            f'font-size:11px;font-family:\'Courier New\',monospace;color:#92400E;'
            f'text-decoration:underline;">&rarr; view post</a>'
            if url else ""
        )
        username = h.get("username", "")
        nickname = h.get("nickname", "")
        date_str = h.get("date", "")
        views = h.get("views", 0)
        nick_html = (
            f'<span style="font-size:12px;color:#92400E;margin-left:6px;">({nickname})</span>'
            if nickname else ""
        )

        items_html += f"""
        <div style="background:rgba(255,255,255,0.55);border-radius:6px;padding:12px 14px;margin-bottom:8px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <span style="font-size:14px;font-weight:700;color:#78350F;">@{username}</span>
                {nick_html}
                <span style="font-size:11px;color:#B45309;margin-left:8px;font-family:'Courier New',monospace;">{date_str}</span>
                {reasons_html}
                {link_html}
              </td>
              <td style="text-align:right;vertical-align:top;white-space:nowrap;padding-left:12px;">
                <span style="font-family:'Courier New',monospace;font-size:15px;font-weight:700;color:#78350F;">{views:,}</span>
                <div style="font-size:10px;color:#B45309;text-align:right;">views</div>
              </td>
            </tr>
          </table>
        </div>"""

    return f"""
    <div style="background:linear-gradient(135deg,#FEF3C7,#FDE68A);border-left:4px solid #D97706;
                border-radius:8px;padding:20px 22px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
        <tr>
          <td>
            <span style="font-size:16px;margin-right:6px;">&#11088;</span>
            <span style="font-size:13px;font-weight:700;letter-spacing:1.5px;color:#78350F;
                         text-transform:uppercase;font-family:'Courier New',monospace;">
              Highlights &middot; {len(highlights)}&#44148; &#44048;&#51648;
            </span>
          </td>
        </tr>
      </table>
      {items_html}
    </div>"""


def build_pipeline_section(statuses: dict) -> str:
    steps = [
        ("Apify Crawl",       statuses.get("pipeline", "unknown")),
        ("Fetch Orders",      statuses.get("orders",   "unknown")),
        ("Syncly Migration",  statuses.get("migrate",  "unknown")),
        ("Grosmimi SNS Sync", statuses.get("sns",      "unknown")),
        ("USA_LLM Update",    statuses.get("llm",      "unknown")),
    ]
    rows = ""
    for i, (name, status) in enumerate(steps):
        bg = "#FAFAF9" if i % 2 == 0 else "#F0EFEC"
        rows += f"""
        <tr>
          <td style="padding:10px 14px;font-size:13px;color:#374151;background:{bg};
                     border-bottom:1px solid #E9E7E4;">{name}</td>
          <td style="padding:10px 14px;text-align:right;background:{bg};
                     border-bottom:1px solid #E9E7E4;">{badge(status)}</td>
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


def build_stats_section(sns: dict, highlights_count: int, total_creators: int) -> str:
    total = sns.get("total_influencers", 0)
    new_c = sns.get("new_count", 0)
    with_c = sns.get("with_content", 0)
    upd_c = sns.get("update_count", 0)

    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;
                  margin-bottom:10px;">Grosmimi US SNS Tab</div>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr>
          {build_stat_card("Total Influencers", str(total))}
          {build_stat_card("신규 추가", str(new_c), f"링크 있음 {with_c}명")}
          {build_stat_card("기존 업데이트", str(upd_c))}
        </tr>
      </table>
    </div>

    <div style="margin-bottom:24px;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;
                  margin-bottom:10px;">USA_LLM</div>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr>
          {build_stat_card("크리에이터", str(total_creators))}
          {build_stat_card("하이라이트", str(highlights_count), "감지된 포스트")}
          <td style="padding:0 5px;"></td>
        </tr>
      </table>
    </div>"""


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


# ── Main builder ─────────────────────────────────────────────────────────────

def build_html(
    date_str: str,
    highlights: list,
    total_creators: int,
    sns_summary: dict,
    statuses: dict,
    repo: str = "",
    run_id: str = "",
) -> str:
    highlights_html = build_highlights_section(highlights)
    pipeline_html   = build_pipeline_section(statuses)
    stats_html      = build_stats_section(sns_summary, len(highlights), total_creators)
    links_html      = build_links_section(repo, run_id)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Apify+SNS Daily Report</title>
</head>
<body style="margin:0;padding:0;background:#EFEFEB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">

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


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print HTML to stdout")
    parser.add_argument("--pipeline", default=os.environ.get("PIPELINE_OUTCOME", "unknown"))
    parser.add_argument("--orders",   default=os.environ.get("ORDERS_OUTCOME",   "unknown"))
    parser.add_argument("--migrate",  default=os.environ.get("MIGRATE_OUTCOME",  "unknown"))
    parser.add_argument("--sns",      default=os.environ.get("SNS_OUTCOME",      "unknown"))
    parser.add_argument("--llm",      default=os.environ.get("LLM_OUTCOME",      "unknown"))
    args = parser.parse_args()

    highlights, total_creators = [], 0
    if HIGHLIGHTS_PATH.exists():
        try:
            d = json.loads(HIGHLIGHTS_PATH.read_text(encoding="utf-8"))
            highlights     = d.get("highlights", [])
            total_creators = d.get("total_creators", 0)
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

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    repo     = os.environ.get("GITHUB_REPOSITORY", "")
    run_id   = os.environ.get("GITHUB_RUN_ID", "")

    html = build_html(
        date_str=date_str,
        highlights=highlights,
        total_creators=total_creators,
        sns_summary=sns_summary,
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
