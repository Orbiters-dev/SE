"""
Syncly Daily Update Email
Sends a rich summary email after daily Syncly export + sync.
Includes: new posts (last 24h), influencer status (new/existing),
metrics (comments/likes/views), links, US/JP separation.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

import gspread
from google.oauth2.service_account import Credentials

from send_gmail import send_email

SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
SA_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Posts Master headers (1-indexed row 1)
# Post ID | URL | Platform | Username | Nickname | Followers | Content | Hashtags | Theme | Brand | Product | Sentiment | Post Date
PM_COL = {
    "post_id": 0, "url": 1, "platform": 2,
    "username": 3, "nickname": 4, "followers": 5,
    "content": 6, "hashtags": 7,
    "theme": 8, "brand": 9, "product": 10,
    "sentiment": 11, "post_date": 12,
}

# D+60 Tracker headers (2-header-row sheet)
# Post ID | URL | Username | Post Date | Brand | D+ Days | Curr Cmt | Curr Like | Curr View | D+0 Cmt | ...
TR_COL = {
    "post_id": 0, "url": 1, "username": 2, "post_date": 3,
    "brand": 4, "d_days": 5, "curr_cmt": 6, "curr_like": 7, "curr_view": 8,
}

RECIPIENTS = [
    "wj.choi@orbiters.co.kr",
    "jh.jeon@orbiters.co.kr",
    "mj.lee@orbiters.co.kr",
]

TAB_GIDS = {
    "US Posts Master": "1472162449",
    "US D+60 Tracker": "199526745",
    "US Influencer Tracker": "1593954988",
    "JP Posts Master": "842545840",
    "JP D+60 Tracker": "295191381",
    "JP Influencer Tracker": "331042723",
}


def _authorize():
    sa_path = SA_PATH
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def _safe_int(val):
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _parse_date(val):
    """Try common date formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def get_region_data(sh, region):
    """Get posts master + tracker data for a region. Return structured data."""
    pm_tab = f"{region} Posts Master"
    tr_tab = f"{region} D+60 Tracker"

    # --- Posts Master ---
    try:
        pm_ws = sh.worksheet(pm_tab)
        pm_rows = pm_ws.get_all_values()
    except Exception as e:
        print(f"[WARN] {pm_tab}: {e}")
        pm_rows = []

    # --- D+60 Tracker ---
    try:
        tr_ws = sh.worksheet(tr_tab)
        tr_rows = tr_ws.get_all_values()
    except Exception as e:
        print(f"[WARN] {tr_tab}: {e}")
        tr_rows = []

    # Parse Posts Master (skip header row 0)
    all_usernames = set()
    posts = []
    for row in pm_rows[1:]:
        if len(row) <= PM_COL["post_date"]:
            continue
        username = row[PM_COL["username"]].strip()
        all_usernames.add(username.lower())
        posts.append({
            "post_id": row[PM_COL["post_id"]].strip(),
            "url": row[PM_COL["url"]].strip(),
            "platform": row[PM_COL["platform"]].strip(),
            "username": username,
            "nickname": row[PM_COL["nickname"]].strip(),
            "followers": row[PM_COL["followers"]].strip(),
            "brand": row[PM_COL["brand"]].strip() if len(row) > PM_COL["brand"] else "",
            "content": row[PM_COL["content"]].strip()[:120] if len(row) > PM_COL["content"] else "",
            "post_date": row[PM_COL["post_date"]].strip(),
        })

    # Parse D+60 Tracker (skip 2 header rows)
    tracker_map = {}
    for row in tr_rows[2:]:
        if len(row) <= TR_COL["curr_view"]:
            continue
        pid = row[TR_COL["post_id"]].strip()
        tracker_map[pid] = {
            "d_days": row[TR_COL["d_days"]].strip(),
            "curr_cmt": row[TR_COL["curr_cmt"]].strip(),
            "curr_like": row[TR_COL["curr_like"]].strip(),
            "curr_view": row[TR_COL["curr_view"]].strip(),
        }

    return {
        "posts": posts,
        "tracker": tracker_map,
        "all_usernames": all_usernames,
        "pm_total": len(pm_rows) - 1 if pm_rows else 0,
        "tr_total": len(tr_rows) - 2 if tr_rows else 0,
    }


def classify_posts(data, cutoff_date):
    """
    Split posts into:
    - new_posts: posted within last 1 day (by Post Date)
    - updated_posts: older posts that got metric updates today
    Also tag each post as new_influencer or existing.
    """
    new_posts = []
    existing_posts_with_metrics = []

    # Collect all usernames that appeared before cutoff
    early_usernames = set()
    for p in data["posts"]:
        pd = _parse_date(p["post_date"])
        if pd and pd < cutoff_date:
            early_usernames.add(p["username"].lower())

    for p in data["posts"]:
        pd = _parse_date(p["post_date"])
        if not pd:
            continue

        pid = p["post_id"]
        metrics = data["tracker"].get(pid, {})
        p["metrics"] = metrics
        p["parsed_date"] = pd
        p["is_new_influencer"] = p["username"].lower() not in early_usernames

        if pd >= cutoff_date:
            new_posts.append(p)
        else:
            # Include older posts that have active tracking (d_days <= 60)
            d_days = _safe_int(metrics.get("d_days", "999"))
            if d_days <= 60 and (_safe_int(metrics.get("curr_view", "0")) > 0
                                or _safe_int(metrics.get("curr_like", "0")) > 0):
                existing_posts_with_metrics.append(p)

    new_posts.sort(key=lambda x: x["parsed_date"], reverse=True)
    existing_posts_with_metrics.sort(
        key=lambda x: _safe_int(x["metrics"].get("curr_view", "0")), reverse=True
    )

    return new_posts, existing_posts_with_metrics[:15]  # top 15 active existing


def _fmt_number(val):
    n = _safe_int(val)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _post_row_html(p, idx):
    """Build a single post row for the email table."""
    m = p.get("metrics", {})
    badge = ('<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:10px;'
             'font-size:11px;font-weight:bold">NEW</span>')
    existing_badge = ('<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:10px;'
                      'font-size:11px">Existing</span>')

    inf_badge = badge if p.get("is_new_influencer") else existing_badge
    brand_tag = p.get("brand", "-") or "-"
    platform = p.get("platform", "").capitalize()

    url = p.get("url", "")
    link_html = f'<a href="{url}" style="color:#1a73e8;text-decoration:none">View Post</a>' if url else "-"

    # Content preview (truncated)
    content_preview = p.get("content", "")[:80]
    if len(p.get("content", "")) > 80:
        content_preview += "..."

    views = _fmt_number(m.get("curr_view", "0"))
    likes = _fmt_number(m.get("curr_like", "0"))
    comments = _fmt_number(m.get("curr_cmt", "0"))
    d_days = m.get("d_days", "-")

    row_bg = "#ffffff" if idx % 2 == 0 else "#fafafa"

    return f"""
    <tr style="background:{row_bg}">
        <td style="padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top">
            <div style="font-weight:600;font-size:13px;color:#222">@{p['username']}</div>
            <div style="font-size:11px;color:#888;margin-top:2px">{p.get('nickname', '')} | {platform} | {p.get('followers', '-')} followers</div>
            <div style="font-size:11px;color:#666;margin-top:4px">{content_preview}</div>
        </td>
        <td style="padding:10px 8px;border-bottom:1px solid #eee;text-align:center;vertical-align:top">
            {inf_badge}
            <div style="font-size:11px;color:#888;margin-top:4px">{brand_tag}</div>
        </td>
        <td style="padding:10px 8px;border-bottom:1px solid #eee;text-align:center;vertical-align:top;font-size:12px">
            <div style="margin-bottom:2px" title="Views"><strong>{views}</strong> views</div>
            <div style="margin-bottom:2px" title="Likes"><strong>{likes}</strong> likes</div>
            <div title="Comments"><strong>{comments}</strong> comments</div>
            <div style="font-size:10px;color:#aaa;margin-top:4px">D+{d_days}</div>
        </td>
        <td style="padding:10px 8px;border-bottom:1px solid #eee;text-align:center;vertical-align:top;font-size:12px">
            <div>{p.get('post_date', '-')}</div>
            <div style="margin-top:6px">{link_html}</div>
        </td>
    </tr>"""


def _section_html(title, posts, color, region_flag, empty_msg="No posts in this period."):
    """Build a section (new posts or active existing) for one region."""
    if not posts:
        return f"""
        <div style="margin:16px 0">
            <h4 style="color:{color};font-size:14px;margin:0 0 8px">{region_flag} {title}</h4>
            <p style="color:#999;font-size:13px;padding:8px 12px;background:#f9f9f9;border-radius:4px">{empty_msg}</p>
        </div>"""

    rows_html = ""
    for i, p in enumerate(posts):
        rows_html += _post_row_html(p, i)

    return f"""
    <div style="margin:20px 0">
        <h4 style="color:{color};font-size:14px;margin:0 0 10px">{region_flag} {title} ({len(posts)})</h4>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
            <tr style="background:#f5f5f5">
                <th style="padding:8px 12px;text-align:left;font-size:12px;color:#555">Influencer</th>
                <th style="padding:8px 8px;text-align:center;font-size:12px;color:#555">Status</th>
                <th style="padding:8px 8px;text-align:center;font-size:12px;color:#555">Metrics</th>
                <th style="padding:8px 8px;text-align:center;font-size:12px;color:#555">Date / Link</th>
            </tr>
            {rows_html}
        </table>
    </div>"""


def build_email_body(us_data, jp_data, cutoff_date):
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    us_new, us_active = classify_posts(us_data, cutoff_date)
    jp_new, jp_active = classify_posts(jp_data, cutoff_date)

    total_new = len(us_new) + len(jp_new)
    total_tracked = us_data["tr_total"] + jp_data["tr_total"]

    # Summary badges
    summary_html = f"""
    <div style="display:flex;gap:12px;margin-bottom:20px">
        <div style="flex:1;background:#e8f5e9;border-radius:8px;padding:14px 16px;text-align:center">
            <div style="font-size:24px;font-weight:700;color:#2e7d32">{total_new}</div>
            <div style="font-size:11px;color:#666;margin-top:2px">New Posts (since {cutoff_str})</div>
        </div>
        <div style="flex:1;background:#e3f2fd;border-radius:8px;padding:14px 16px;text-align:center">
            <div style="font-size:24px;font-weight:700;color:#1565c0">{total_tracked}</div>
            <div style="font-size:11px;color:#666;margin-top:2px">Total Tracked</div>
        </div>
        <div style="flex:1;background:#fff3e0;border-radius:8px;padding:14px 16px;text-align:center">
            <div style="font-size:24px;font-weight:700;color:#e65100">{us_data['pm_total'] + jp_data['pm_total']}</div>
            <div style="font-size:11px;color:#666;margin-top:2px">Total Posts</div>
        </div>
    </div>"""

    # US section
    us_section = ""
    us_section += _section_html("New Posts", us_new, "#1565c0", "US", "No new US posts today.")
    if us_active:
        us_section += _section_html("Top Active Posts (by views)", us_active, "#37474f", "US")

    # JP section
    jp_section = ""
    jp_section += _section_html("New Posts", jp_new, "#c62828", "JP", "No new JP posts today.")
    if jp_active:
        jp_section += _section_html("Top Active Posts (by views)", jp_active, "#37474f", "JP")

    # Tab links
    tab_links = ""
    for tab_name, gid in TAB_GIDS.items():
        tab_links += f'<a href="{SHEET_URL}#gid={gid}" style="color:#1a73e8;text-decoration:none;font-size:12px;margin-right:12px">{tab_name}</a> '

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:720px;margin:0 auto">
        <div style="background:linear-gradient(135deg,#1a1f2e,#2d3548);color:white;padding:24px 28px;border-radius:10px 10px 0 0">
            <h2 style="margin:0;font-size:20px;font-weight:700">ONZENNA Affiliates Tracker</h2>
            <p style="margin:6px 0 0;opacity:0.7;font-size:13px">Daily Content Update - {today}</p>
        </div>

        <div style="background:white;padding:24px 28px;border:1px solid #e5e5e5;border-top:none">
            {summary_html}

            <hr style="border:none;border-top:1px solid #eee;margin:20px 0">

            {us_section}

            <hr style="border:none;border-top:2px solid #e0e0e0;margin:24px 0">

            {jp_section}

            <div style="margin-top:28px;text-align:center">
                <a href="{SHEET_URL}" style="display:inline-block;background:#1a73e8;color:white;
                   padding:12px 36px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">
                    Open Full Spreadsheet
                </a>
            </div>

            <div style="margin-top:16px;text-align:center">
                {tab_links}
            </div>
        </div>

        <div style="background:#f5f5f5;padding:12px 28px;border:1px solid #e5e5e5;border-top:none;
             border-radius:0 0 10px 10px;font-size:11px;color:#999;text-align:center">
            Automated daily report | Sent to: {', '.join(RECIPIENTS)}
        </div>
    </div>
    """


def main():
    print("[EMAIL] Connecting to Google Sheets...")
    sh = _authorize()

    print("[EMAIL] Fetching US data...")
    us_data = get_region_data(sh, "US")
    print(f"[EMAIL] US: {us_data['pm_total']} posts, {us_data['tr_total']} tracked")

    print("[EMAIL] Fetching JP data...")
    jp_data = get_region_data(sh, "JP")
    print(f"[EMAIL] JP: {jp_data['pm_total']} posts, {jp_data['tr_total']} tracked")

    cutoff_date = (datetime.now() - timedelta(days=1)).date()
    body = build_email_body(us_data, jp_data, cutoff_date)

    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"[Syncly] ONZENNA Affiliates Daily Update - {today}"

    to_str = ", ".join(RECIPIENTS)
    print(f"[EMAIL] Sending to {to_str}...")
    send_email(to=to_str, subject=subject, body_html=body)
    print("[EMAIL] Done")


if __name__ == "__main__":
    main()
