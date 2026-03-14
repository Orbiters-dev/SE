"""
build_ranking_dashboard.py
==========================
Reads Posts Master tabs from Apify test sheet.
Generates TOP 10 ranking dashboard per region (US / JP separate).

Usage:
    python tools/build_ranking_dashboard.py              # US only (default)
    python tools/build_ranking_dashboard.py --region jp
    python tools/build_ranking_dashboard.py --region all
    python tools/build_ranking_dashboard.py --no-email
"""

import argparse
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env
load_env()

import gspread
from google.oauth2.service_account import Credentials

APIFY_SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
OUTPUT_PATH = PROJECT_ROOT / ".tmp" / "ranking_dashboard.html"
KST = timezone(timedelta(hours=9))

REGION_TABS = {
    "us": ("US Posts Master", "🇺🇸", "United States"),
    "jp": ("JP Posts Master", "🇯🇵", "Japan"),
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_posts(tab_name: str) -> list[dict]:
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(APIFY_SHEET_ID).worksheet(tab_name)
    vals = ws.get_all_values()
    if not vals:
        return []

    h = vals[0]
    def ci(name):
        try: return h.index(name)
        except ValueError: return None

    def to_int(v):
        try: return int(str(v).replace(",", "").strip())
        except Exception: return 0

    def parse_date(v):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try: return datetime.strptime(v.strip(), fmt).date()
            except Exception: pass
        return None

    url_col  = ci("URL")
    user_col = ci("Username")
    nick_col = ci("Nickname")
    date_col = ci("Post Date")
    view_col = ci("Views")
    like_col = ci("Likes")
    comm_col = ci("Comments")
    foll_col = ci("Followers")

    posts = []
    for row in vals[1:]:
        def get(col):
            return row[col] if col is not None and col < len(row) else ""

        username = get(user_col).lower().strip()
        if not username:
            continue

        url = get(url_col)
        if url.startswith("=HYPERLINK("):
            try: url = url.split('"')[1]
            except Exception: pass

        raw_date = get(date_col)
        posts.append({
            "username":  username,
            "nickname":  get(nick_col),
            "url":       url,
            "date":      raw_date,
            "date_obj":  parse_date(raw_date),
            "views":     to_int(get(view_col)),
            "likes":     to_int(get(like_col)),
            "comments":  to_int(get(comm_col)),
            "followers": to_int(get(foll_col)),
        })
    return posts


# ── Ranking logic ─────────────────────────────────────────────────────────────

def top_n_by_views(posts: list[dict], n: int = 10, since: date | None = None) -> list[dict]:
    filtered = [p for p in posts if p["views"] > 0]
    if since:
        filtered = [p for p in filtered if p["date_obj"] and p["date_obj"] >= since]
    seen = {}
    for p in filtered:
        key = p["url"] or f"{p['username']}_{p['date']}"
        if key not in seen or p["views"] > seen[key]["views"]:
            seen[key] = p
    return sorted(seen.values(), key=lambda x: x["views"], reverse=True)[:n]


def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ── HTML builders ─────────────────────────────────────────────────────────────

MEDAL = ["🥇", "🥈", "🥉"]

def rank_row(rank: int, post: dict, accent: str) -> str:
    medal = MEDAL[rank - 1] if rank <= 3 else f"#{rank}"
    url   = post["url"]
    link  = (
        f'<a href="{url}" style="font-size:11px;font-family:\'Courier New\',monospace;'
        f'color:#1E3A5F;text-decoration:none;background:#EBF2FF;padding:2px 7px;'
        f'border-radius:4px;white-space:nowrap;">view&#8599;</a>'
        if url else ""
    )
    foll  = fmt_num(post["followers"]) if post["followers"] else "—"
    views = fmt_num(post["views"])
    likes = fmt_num(post["likes"])
    bg    = "#FFFEF0" if rank <= 3 else "#FFFFFF"
    nick  = post["nickname"] or post["username"]

    return f"""
    <tr style="background:{bg};border-bottom:1px solid #F0EFEC;">
      <td style="padding:10px 8px;font-size:17px;text-align:center;width:32px;">{medal}</td>
      <td style="padding:10px 8px;">
        <div style="font-size:13px;font-weight:700;color:#0A1628;">@{post['username']}</div>
        <div style="font-size:11px;color:#6B7280;">{nick}</div>
      </td>
      <td style="padding:10px 6px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#374151;">{foll}</div>
        <div style="font-size:9px;color:#9CA3AF;">followers</div>
      </td>
      <td style="padding:10px 6px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:15px;font-weight:700;
                    color:{accent};">{views}</div>
        <div style="font-size:9px;color:#9CA3AF;">views</div>
      </td>
      <td style="padding:10px 6px;text-align:center;white-space:nowrap;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#374151;">{likes}</div>
        <div style="font-size:9px;color:#9CA3AF;">likes</div>
      </td>
      <td style="padding:10px 6px;font-size:10px;color:#9CA3AF;font-family:'Courier New',monospace;
                 text-align:center;white-space:nowrap;">{post['date'] or '—'}</td>
      <td style="padding:10px 8px;text-align:right;">{link}</td>
    </tr>"""


def ranking_table_html(title: str, emoji: str, posts: list[dict],
                       accent: str, sub: str = "") -> str:
    if not posts:
        return f"""
        <div style="margin-bottom:24px;">
          <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                      color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:8px;">
            {emoji} {title}
          </div>
          <div style="color:#9CA3AF;font-size:12px;padding:10px 0;">No data available.</div>
        </div>"""

    rows = "".join(rank_row(i + 1, p, accent) for i, p in enumerate(posts))
    return f"""
    <div style="margin-bottom:28px;">
      <div style="margin-bottom:8px;">
        <span style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                     color:#9CA3AF;font-family:'Courier New',monospace;">{emoji} {title}</span>
        {"<span style='font-size:10px;color:#C9A84C;font-family:\"Courier New\",monospace;margin-left:8px;'>" + sub + "</span>" if sub else ""}
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:{accent}18;">
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;width:32px;">#</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:left;">CREATOR</th>
            <th style="padding:7px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">FOLLOWERS</th>
            <th style="padding:7px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">VIEWS</th>
            <th style="padding:7px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">LIKES</th>
            <th style="padding:7px 6px;font-size:9px;color:#9CA3AF;font-weight:600;
                       letter-spacing:1px;text-align:center;">DATE</th>
            <th style="padding:7px 8px;width:60px;"></th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def build_region_section(posts: list[dict], region_label: str) -> str:
    today     = date.today()
    posts_7d  = top_n_by_views(posts, n=10, since=today - timedelta(days=7))
    posts_30d = top_n_by_views(posts, n=10, since=today - timedelta(days=30))
    posts_all = top_n_by_views(posts, n=10)

    t7  = ranking_table_html("Last 7 Days",  "🔥", posts_7d,  "#EF4444",
                             sub=f"Top {len(posts_7d)} posts")
    t30 = ranking_table_html("Last 30 Days", "📈", posts_30d, "#F59E0B",
                             sub=f"Top {len(posts_30d)} posts")
    tal = ranking_table_html("All-Time Best","👑", posts_all, "#6366F1",
                             sub=f"Top {len(posts_all)} posts")

    return f"""
    <div style="margin-bottom:8px;padding:14px 20px;background:#0A1628;border-radius:8px;">
      <span style="font-size:13px;font-weight:700;color:#C9A84C;
                   font-family:'Courier New',monospace;letter-spacing:1px;">
        {region_label}
      </span>
      <span style="font-size:10px;color:#4A6080;margin-left:10px;font-family:'Courier New',monospace;">
        {len(posts)} posts total
      </span>
    </div>
    <div style="margin-bottom:32px;">
      {t7}{t30}{tal}
    </div>"""


def build_inline_rankings_html(posts: list[dict], region_label: str = "🇺🇸 US Posts") -> str:
    """Compact ranking section to embed inside the daily report email."""
    today     = date.today()
    posts_7d  = top_n_by_views(posts, n=10, since=today - timedelta(days=7))
    posts_30d = top_n_by_views(posts, n=10, since=today - timedelta(days=30))
    posts_all = top_n_by_views(posts, n=10)

    t7  = ranking_table_html("Last 7 Days",  "🔥", posts_7d,  "#EF4444",
                             sub=f"Top {len(posts_7d)}")
    t30 = ranking_table_html("Last 30 Days", "📈", posts_30d, "#F59E0B",
                             sub=f"Top {len(posts_30d)}")
    tal = ranking_table_html("All-Time Best","👑", posts_all, "#6366F1",
                             sub=f"Top {len(posts_all)}")

    return f"""
    <div style="padding-top:20px;border-top:1px solid #E9E7E4;margin-bottom:0;">
      <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                  color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:16px;">
        Content Rankings · {region_label}
      </div>
      {t7}{t30}{tal}
    </div>"""


# ── Full standalone HTML ──────────────────────────────────────────────────────

def build_dashboard_html(region_sections_html: str, generated_at: str,
                         region_title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Content Ranking Dashboard</title>
</head>
<body style="margin:0;padding:0;background:#EFEFEB;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EFEFEB;padding:24px 0;">
  <tr><td align="center">
    <table width="660" cellpadding="0" cellspacing="0"
           style="max-width:660px;width:100%;border-top:3px solid #C9A84C;">
      <tr>
        <td style="background:#0A1628;padding:28px 32px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td>
              <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                           color:#C9A84C;font-family:'Courier New',monospace;margin-bottom:6px;">
                Grosmimi · {region_title} · Content Rankings
              </div>
              <div style="font-size:22px;font-weight:700;color:#FFFFFF;
                           font-family:Georgia,serif;line-height:1.2;">
                Top Posts <span style="color:#C9A84C;">Dashboard</span>
              </div>
            </td>
            <td style="text-align:right;vertical-align:top;">
              <div style="font-family:'Courier New',monospace;font-size:11px;
                           color:#8899AA;line-height:1.7;">
                {generated_at}<br>
                <span style="color:#4A6080;font-size:10px;">Apify Posts Master</span>
              </div>
            </td>
          </tr></table>
        </td>
      </tr>
      <tr>
        <td style="background:#F5F4F1;padding:28px 32px;">
          {region_sections_html}
          <div style="padding-top:16px;border-top:1px solid #E9E7E4;">
            <a href="https://docs.google.com/spreadsheets/d/1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
               style="display:inline-block;padding:9px 16px;background:#1E3A5F;color:#FFFFFF;
                      text-decoration:none;border-radius:6px;font-size:12px;font-weight:600;
                      font-family:'Courier New',monospace;margin-right:8px;">Apify Sheet &#8599;</a>
            <a href="https://docs.google.com/spreadsheets/d/1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
               style="display:inline-block;padding:9px 16px;background:#1E3A5F;color:#FFFFFF;
                      text-decoration:none;border-radius:6px;font-size:12px;font-weight:600;
                      font-family:'Courier New',monospace;">Grosmimi SNS &#8599;</a>
          </div>
        </td>
      </tr>
      <tr>
        <td style="background:#0A1628;padding:14px 32px;">
          <div style="font-size:10px;color:#4A6080;font-family:'Courier New',monospace;">
            ORBI Systems &middot; Content Intelligence &middot; Do not reply
          </div>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body></html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us", choices=["us", "jp", "all"])
    parser.add_argument("--no-email", action="store_true")
    parser.add_argument("--to", default="wj.choi@orbiters.co.kr")
    args = parser.parse_args()

    regions = list(REGION_TABS.items()) if args.region == "all" else [(args.region, REGION_TABS[args.region])]

    sections_html = ""
    region_title  = ""

    for region_key, (tab_name, flag, label) in regions:
        print(f"[{region_key.upper()}] Loading {tab_name}...")
        posts = load_posts(tab_name)
        print(f"    {len(posts)} posts loaded")
        if len(regions) == 1:
            # Single region: no sub-header needed, just the tables
            today = date.today()
            t7  = ranking_table_html("Last 7 Days",  "🔥",
                                     top_n_by_views(posts, 10, today - timedelta(days=7)),
                                     "#EF4444", sub=f"Top 10 posts")
            t30 = ranking_table_html("Last 30 Days", "📈",
                                     top_n_by_views(posts, 10, today - timedelta(days=30)),
                                     "#F59E0B", sub=f"Top 10 posts")
            tal = ranking_table_html("All-Time Best","👑",
                                     top_n_by_views(posts, 10),
                                     "#6366F1", sub=f"Top 10 posts")
            sections_html = t7 + t30 + tal
            region_title  = f"{flag} {label}"
        else:
            sections_html += build_region_section(posts, f"{flag} {label}")
            region_title   = "US &amp; JP"

    generated_at = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M KST")
    html = build_dashboard_html(sections_html, generated_at, region_title)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard written -> {OUTPUT_PATH}")

    if args.no_email:
        print("(--no-email: skipping)")
        return

    import subprocess
    today_str   = datetime.now(tz=KST).strftime("%Y-%m-%d")
    region_str  = args.region.upper()
    subprocess.run([
        sys.executable, str(PROJECT_ROOT / "tools" / "send_gmail.py"),
        "--to", args.to,
        "--subject", f"[Grosmimi] Content Ranking Dashboard {today_str} ({region_str})",
        "--body-file", str(OUTPUT_PATH),
    ], check=True)
    print("Email sent!")


if __name__ == "__main__":
    main()
