"""
build_ranking_dashboard.py
==========================
Reads US Posts Master from Apify test sheet.
Generates TOP 10 ranking dashboard:
  - Last 7 days  (by views)
  - Last 30 days (by views)
  - All-time     (by views)

Saves .tmp/ranking_dashboard.html and emails it.

Usage:
    python tools/build_ranking_dashboard.py
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


# ── Data loading ──────────────────────────────────────────────────────────────

def load_posts() -> list[dict]:
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(APIFY_SHEET_ID).worksheet("US Posts Master")
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
        post_date = parse_date(raw_date)

        posts.append({
            "username":  username,
            "nickname":  get(nick_col),
            "url":       url,
            "date":      raw_date,
            "date_obj":  post_date,
            "views":     to_int(get(view_col)),
            "likes":     to_int(get(like_col)),
            "comments":  to_int(get(comm_col)),
            "followers": to_int(get(foll_col)),
        })

    return posts


# ── Ranking logic ─────────────────────────────────────────────────────────────

def top10_by_views(posts: list[dict], since: date | None = None) -> list[dict]:
    filtered = [p for p in posts if p["views"] > 0]
    if since:
        filtered = [p for p in filtered if p["date_obj"] and p["date_obj"] >= since]
    # deduplicate by URL, keep highest view count
    seen = {}
    for p in filtered:
        url = p["url"] or f"{p['username']}_{p['date']}"
        if url not in seen or p["views"] > seen[url]["views"]:
            seen[url] = p
    ranked = sorted(seen.values(), key=lambda x: x["views"], reverse=True)
    return ranked[:10]


def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ── HTML builders ─────────────────────────────────────────────────────────────

MEDAL = ["🥇", "🥈", "🥉"]

def rank_row(rank: int, post: dict, highlight_color: str) -> str:
    medal = MEDAL[rank - 1] if rank <= 3 else f"#{rank}"
    url   = post["url"]
    link  = (
        f'<a href="{url}" style="font-size:11px;font-family:\'Courier New\',monospace;'
        f'color:#1E3A5F;text-decoration:none;background:#EBF2FF;padding:2px 8px;'
        f'border-radius:4px;">view&nbsp;post&nbsp;&#8599;</a>'
        if url else ""
    )
    foll  = fmt_num(post["followers"]) if post["followers"] else "—"
    views = fmt_num(post["views"])
    likes = fmt_num(post["likes"])
    date  = post["date"] or "—"
    nick  = post["nickname"] or post["username"]

    bg = "#FFFEF0" if rank <= 3 else "#FFFFFF"

    return f"""
    <tr style="background:{bg};border-bottom:1px solid #F0EFEC;">
      <td style="padding:11px 10px;font-size:18px;text-align:center;width:36px;">{medal}</td>
      <td style="padding:11px 8px;">
        <div style="font-size:13px;font-weight:700;color:#0A1628;">@{post['username']}</div>
        <div style="font-size:11px;color:#6B7280;">{nick}</div>
      </td>
      <td style="padding:11px 8px;text-align:center;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#4B5563;">{foll}</div>
        <div style="font-size:9px;color:#9CA3AF;margin-top:1px;">followers</div>
      </td>
      <td style="padding:11px 8px;text-align:center;">
        <div style="font-family:'Courier New',monospace;font-size:15px;font-weight:700;
                    color:{highlight_color};">{views}</div>
        <div style="font-size:9px;color:#9CA3AF;margin-top:1px;">views</div>
      </td>
      <td style="padding:11px 8px;text-align:center;">
        <div style="font-family:'Courier New',monospace;font-size:11px;color:#4B5563;">{likes}</div>
        <div style="font-size:9px;color:#9CA3AF;margin-top:1px;">likes</div>
      </td>
      <td style="padding:11px 8px;font-size:10px;color:#9CA3AF;font-family:'Courier New',monospace;
                 text-align:center;">{date}</td>
      <td style="padding:11px 10px;text-align:right;">{link}</td>
    </tr>"""


def ranking_table(title: str, emoji: str, posts: list[dict],
                  accent: str, sub: str = "") -> str:
    if not posts:
        return f"""
        <div style="margin-bottom:28px;">
          <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                      color:#9CA3AF;font-family:'Courier New',monospace;margin-bottom:6px;">
            {emoji} {title}
          </div>
          <div style="color:#9CA3AF;font-size:12px;padding:12px 0;">No data available.</div>
        </div>"""

    rows = "".join(rank_row(i + 1, p, accent) for i, p in enumerate(posts))

    return f"""
    <div style="margin-bottom:32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <span style="font-size:10px;letter-spacing:2px;text-transform:uppercase;
                         color:#9CA3AF;font-family:'Courier New',monospace;">{emoji} {title}</span>
            {"<span style='font-size:10px;color:#C9A84C;font-family:\"Courier New\",monospace;margin-left:8px;'>" + sub + "</span>" if sub else ""}
          </td>
        </tr>
      </table>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;margin-top:8px;
                    border:1px solid #E9E7E4;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:{accent}10;">
            <th style="padding:7px 10px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:center;width:36px;">#</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:left;">CREATOR</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:center;">FOLLOWERS</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:center;">VIEWS</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:center;">LIKES</th>
            <th style="padding:7px 8px;font-size:9px;color:#9CA3AF;
                       font-weight:600;letter-spacing:1px;text-align:center;">DATE</th>
            <th style="padding:7px 10px;width:80px;"></th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def build_dashboard_html(posts_7d, posts_30d, posts_all, generated_at: str) -> str:
    t7  = ranking_table("Last 7 Days",  "🔥", posts_7d,  "#EF4444",
                        sub=f"Top {len(posts_7d)} posts")
    t30 = ranking_table("Last 30 Days", "📈", posts_30d, "#F59E0B",
                        sub=f"Top {len(posts_30d)} posts")
    tal = ranking_table("All-Time Best","👑", posts_all, "#6366F1",
                        sub=f"Top {len(posts_all)} posts")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Grosmimi Content Ranking Dashboard</title>
</head>
<body style="margin:0;padding:0;background:#EFEFEB;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#EFEFEB;padding:24px 0;">
  <tr>
    <td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%;border-top:3px solid #C9A84C;">

        <!-- HEADER -->
        <tr>
          <td style="background:#0A1628;padding:28px 32px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                               color:#C9A84C;font-family:'Courier New',monospace;
                               margin-bottom:6px;">Grosmimi US &middot; Content Rankings</div>
                  <div style="font-size:22px;font-weight:700;color:#FFFFFF;
                               font-family:Georgia,serif;line-height:1.2;">
                    Top Posts <span style="color:#C9A84C;">Dashboard</span>
                  </div>
                </td>
                <td style="text-align:right;vertical-align:top;">
                  <div style="font-family:'Courier New',monospace;font-size:11px;
                               color:#8899AA;line-height:1.7;">
                    {generated_at}<br>
                    <span style="color:#4A6080;font-size:10px;">Apify US Posts Master</span>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="background:#F5F4F1;padding:28px 32px;">
            {t7}
            {t30}
            {tal}

            <!-- LINKS -->
            <div style="padding-top:16px;border-top:1px solid #E9E7E4;">
              <a href="https://docs.google.com/spreadsheets/d/1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
                 style="display:inline-block;padding:9px 16px;background:#1E3A5F;
                        color:#FFFFFF;text-decoration:none;border-radius:6px;font-size:12px;
                        font-weight:600;font-family:'Courier New',monospace;margin-right:8px;">
                Apify Sheet &#8599;
              </a>
              <a href="https://docs.google.com/spreadsheets/d/1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
                 style="display:inline-block;padding:9px 16px;background:#1E3A5F;
                        color:#FFFFFF;text-decoration:none;border-radius:6px;font-size:12px;
                        font-weight:600;font-family:'Courier New',monospace;">
                Grosmimi SNS &#8599;
              </a>
            </div>
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#0A1628;padding:14px 32px;">
            <div style="font-size:10px;color:#4A6080;font-family:'Courier New',monospace;">
              ORBI Systems &middot; Content Intelligence &middot; Do not reply
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-email", action="store_true", help="Build HTML only, skip email")
    parser.add_argument("--to", default="wj.choi@orbiters.co.kr")
    args = parser.parse_args()

    print("[1] Loading US Posts Master from Apify sheet...")
    posts = load_posts()
    print(f"    {len(posts)} posts loaded")

    today = date.today()
    d7    = today - timedelta(days=7)
    d30   = today - timedelta(days=30)

    print("[2] Ranking...")
    posts_7d  = top10_by_views(posts, since=d7)
    posts_30d = top10_by_views(posts, since=d30)
    posts_all = top10_by_views(posts, since=None)

    print(f"    7d: {len(posts_7d)}  |  30d: {len(posts_30d)}  |  all-time: {len(posts_all)}")

    generated_at = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M KST")
    html = build_dashboard_html(posts_7d, posts_30d, posts_all, generated_at)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"[3] Dashboard written -> {OUTPUT_PATH}")

    if args.no_email:
        print("    (--no-email: skipping send)")
        return

    import subprocess
    today_str = datetime.now(tz=KST).strftime("%Y-%m-%d")
    subprocess.run([
        sys.executable, str(PROJECT_ROOT / "tools" / "send_gmail.py"),
        "--to", args.to,
        "--subject", f"[Grosmimi] Content Ranking Dashboard {today_str}",
        "--body-file", str(OUTPUT_PATH),
    ], check=True)
    print("[4] Email sent!")


if __name__ == "__main__":
    main()
