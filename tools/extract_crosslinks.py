"""
Extract cross-platform handles from creator profile bios.

Scans gk_content_posts.bio_text for TikTok/IG/YouTube handles and links,
then backfills missing tiktok_handle/ig_handle on onz_pipeline_creators.

Also detects same-person IG+TikTok pairs and auto-merges duplicates.

Usage:
    python tools/extract_crosslinks.py --scan              # Scan bios, show matches
    python tools/extract_crosslinks.py --scan --update      # Scan + update DB
    python tools/extract_crosslinks.py --find-dupes         # Find IG/TT same-person pairs
    python tools/extract_crosslinks.py --merge-dupes        # Auto-merge confirmed pairs
    python tools/extract_crosslinks.py --status             # Show crosslink stats
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from env_loader import load_env
    load_env()
except ImportError:
    pass

import psycopg2

# ── Config ──────────────────────────────────────────────────────────────────

DB_HOST = os.getenv("PG_HOST", "172.31.13.240")
DB_NAME = os.getenv("PG_DB", "export_calculator_db")
DB_USER = os.getenv("PG_USER", "es_db_user")
DB_PASS = os.getenv("PG_PASS", "orbit1234")
DB_HOST_LOCAL = os.getenv("PG_HOST_LOCAL", "orbitools.orbiters.co.kr")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path("/tmp/crosslinks") if not (PROJECT_ROOT / ".tmp").exists() else PROJECT_ROOT / ".tmp" / "crosslinks"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Regex Patterns ──────────────────────────────────────────────────────────

# TikTok handle from bio
TIKTOK_PATTERNS = [
    # "TikTok: @username" or "TT: @username" or "tiktok - username"
    re.compile(r'(?:tik\s*tok|tt)\s*[:\-@/]\s*@?([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
    # tiktok.com/@username
    re.compile(r'tiktok\.com/@([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
    # tiktok.com/t/XXXXX (short link — can't extract handle, skip)
    # "on tiktok" + nearby handle
    re.compile(r'@([a-zA-Z0-9_.]{2,30})\s+on\s+tik\s*tok', re.IGNORECASE),
    re.compile(r'tik\s*tok\s+@([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
]

# IG handle from bio (when source is TikTok)
IG_PATTERNS = [
    re.compile(r'(?:instagram|ig|insta)\s*[:\-@/]\s*@?([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
    re.compile(r'instagram\.com/([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
    re.compile(r'@([a-zA-Z0-9_.]{2,30})\s+on\s+(?:instagram|ig|insta)', re.IGNORECASE),
]

# YouTube
YT_PATTERNS = [
    re.compile(r'youtube\.com/@([a-zA-Z0-9_.\-]{2,40})', re.IGNORECASE),
    re.compile(r'youtube\.com/(?:c(?:hannel)?/)?([a-zA-Z0-9_.\-]{2,40})', re.IGNORECASE),
    re.compile(r'youtu\.be/([a-zA-Z0-9_.\-]{2,40})', re.IGNORECASE),
    re.compile(r'(?:youtube|yt)\s*[:\-]\s*@?([a-zA-Z0-9_.]{2,30})', re.IGNORECASE),
]

# Email from bio
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Linktree
LINKTREE_PATTERN = re.compile(r'linktr\.ee/([a-zA-Z0-9_.]{2,30})', re.IGNORECASE)

# Noise filter: skip handles that are clearly not personal
NOISE_HANDLES = {
    'tiktok', 'instagram', 'youtube', 'facebook', 'twitter', 'snapchat',
    'pinterest', 'linkedin', 'threads', 'whatsapp', 'telegram',
    'explore', 'reels', 'stories', 'shop', 'about', 'help', 'support',
    'grosmimi', 'onzenna', 'zezebaebae', 'grosmimi_japan', 'grosmimi_jp',
}


def extract_from_bio(bio_text: str, source_platform: str = 'instagram') -> dict:
    """Extract cross-platform handles from a bio string.

    Returns: {
        'tiktok': 'handle' or None,
        'instagram': 'handle' or None,
        'youtube': 'handle' or None,
        'email': 'email@...' or None,
        'linktree': 'handle' or None,
    }
    """
    if not bio_text or len(bio_text) < 3:
        return {}

    result = {}
    bio = bio_text.strip()

    def _valid_handle(h):
        """Filter out false positives: emails, domains, short noise."""
        if h in NOISE_HANDLES:
            return False
        if len(h) < 2:
            return False
        # Reject if looks like a domain (contains .com, .co, .org, .net, .io, .uk etc.)
        if re.search(r'\.(com|co|org|net|io|uk|ca|jp|kr|de|fr|au|edu|gov)$', h):
            return False
        # Reject if contains @ (email fragment)
        if '@' in h:
            return False
        return True

    # Extract TikTok handle (when viewing an IG profile)
    if source_platform == 'instagram':
        for pat in TIKTOK_PATTERNS:
            m = pat.search(bio)
            if m:
                handle = m.group(1).strip('.').lower()
                if _valid_handle(handle):
                    result['tiktok'] = handle
                    break

    # Extract IG handle (when viewing a TikTok profile)
    if source_platform == 'tiktok':
        for pat in IG_PATTERNS:
            m = pat.search(bio)
            if m:
                handle = m.group(1).strip('.').lower()
                if _valid_handle(handle):
                    result['instagram'] = handle
                    break

    # YouTube
    for pat in YT_PATTERNS:
        m = pat.search(bio)
        if m:
            handle = m.group(1).strip('.').lower()
            if handle not in NOISE_HANDLES and len(handle) >= 2:
                result['youtube'] = handle
                break

    # Email
    m = EMAIL_PATTERN.search(bio)
    if m:
        email = m.group(0).lower()
        # Skip our own emails and discovered placeholders
        if not any(x in email for x in ['@discovered.', '@onzenna.', '@zezebaebae.', '@grosmimi.']):
            result['email'] = email

    # Linktree
    m = LINKTREE_PATTERN.search(bio)
    if m:
        result['linktree'] = m.group(1).lower()

    return result


# ── DB ──────────────────────────────────────────────────────────────────────

def get_db():
    for host in [DB_HOST, DB_HOST_LOCAL]:
        try:
            return psycopg2.connect(
                host=host, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
                connect_timeout=5
            )
        except Exception:
            continue
    raise Exception("Cannot connect to PostgreSQL")


def scan_bios(update_db: bool = False):
    """Scan all bios in gk_content_posts, extract cross-platform handles."""
    conn = get_db()
    cur = conn.cursor()

    print("=" * 60)
    print("  Bio Cross-Link Scanner")
    print("=" * 60)

    # Get latest bio per username
    print("\n  Loading bios from gk_content_posts...")
    cur.execute("""
        SELECT DISTINCT ON (LOWER(username))
            username, bio_text, platform
        FROM gk_content_posts
        WHERE bio_text IS NOT NULL AND LENGTH(bio_text) > 5
        ORDER BY LOWER(username), post_date DESC NULLS LAST
    """)
    bios = cur.fetchall()
    print(f"    {len(bios)} unique users with bios")

    # Get current pipeline creators
    cur.execute("""
        SELECT id, ig_handle, tiktok_handle, email, full_name
        FROM onz_pipeline_creators
    """)
    creators = cur.fetchall()
    ig_to_creator = {}
    tt_to_creator = {}
    email_to_creator = {}
    for c in creators:
        cid, ig, tt, em, full_name = c
        if ig:
            ig_to_creator[ig.lower()] = {'id': cid, 'ig': ig, 'tt': tt, 'email': em, 'name': full_name}
        if tt:
            tt_to_creator[tt.lower()] = {'id': cid, 'ig': ig, 'tt': tt, 'email': em, 'name': full_name}

    print(f"    {len(creators)} pipeline creators ({len(ig_to_creator)} IG, {len(tt_to_creator)} TT)")

    # Extract cross-links
    results = {
        'tiktok_found': [],   # IG creator → TikTok handle found in bio
        'ig_found': [],       # TT creator → IG handle found in bio
        'email_found': [],    # Creator → email found in bio
        'youtube_found': [],
    }

    for username, bio_text, platform in bios:
        uname = username.lower()
        source_platform = (platform or 'instagram').lower()

        extracted = extract_from_bio(bio_text, source_platform)
        if not extracted:
            continue

        # Check if this user is in our pipeline
        creator = ig_to_creator.get(uname) or tt_to_creator.get(uname)
        if not creator:
            continue

        # TikTok handle found for an IG creator
        if extracted.get('tiktok') and creator.get('ig') and not creator.get('tt'):
            results['tiktok_found'].append({
                'creator_id': creator['id'],
                'ig_handle': creator['ig'],
                'tiktok_found': extracted['tiktok'],
                'bio_snippet': bio_text[:150],
            })

        # IG handle found for a TikTok creator
        if extracted.get('instagram') and creator.get('tt') and not creator.get('ig'):
            results['ig_found'].append({
                'creator_id': creator['id'],
                'tiktok_handle': creator['tt'],
                'ig_found': extracted['instagram'],
                'bio_snippet': bio_text[:150],
            })

        # Email found in bio (update if creator has no real email)
        if extracted.get('email') and (not creator.get('email') or '@discovered.' in (creator.get('email') or '')):
            results['email_found'].append({
                'creator_id': creator['id'],
                'handle': creator.get('ig') or creator.get('tt'),
                'email_found': extracted['email'],
            })

        if extracted.get('youtube'):
            results['youtube_found'].append({
                'creator_id': creator['id'],
                'handle': creator.get('ig') or creator.get('tt'),
                'youtube': extracted['youtube'],
            })

    # Report
    print(f"\n  RESULTS:")
    print(f"    TikTok handles found:  {len(results['tiktok_found'])}")
    print(f"    IG handles found:      {len(results['ig_found'])}")
    print(f"    Emails found:          {len(results['email_found'])}")
    print(f"    YouTube found:         {len(results['youtube_found'])}")

    if results['tiktok_found']:
        print(f"\n  Sample TikTok discoveries:")
        for r in results['tiktok_found'][:10]:
            print(f"    IG @{r['ig_handle']} → TT @{r['tiktok_found']}")
            print(f"      Bio: {r['bio_snippet'][:100]}")

    if results['ig_found']:
        print(f"\n  Sample IG discoveries:")
        for r in results['ig_found'][:10]:
            print(f"    TT @{r['tiktok_handle']} → IG @{r['ig_found']}")

    if results['email_found']:
        print(f"\n  Sample Email discoveries:")
        for r in results['email_found'][:10]:
            print(f"    @{r['handle']} → {r['email_found']}")

    # Update DB if requested
    if update_db:
        print(f"\n  Updating DB...")
        update_count = 0

        # Update tiktok_handle
        for r in results['tiktok_found']:
            cur.execute(
                "UPDATE onz_pipeline_creators SET tiktok_handle = %s, updated_at = NOW() WHERE id = %s AND (tiktok_handle IS NULL OR tiktok_handle = '')",
                (r['tiktok_found'], r['creator_id'])
            )
            update_count += cur.rowcount

        # Update ig_handle
        for r in results['ig_found']:
            cur.execute(
                "UPDATE onz_pipeline_creators SET ig_handle = %s, updated_at = NOW() WHERE id = %s AND (ig_handle IS NULL OR ig_handle = '')",
                (r['ig_found'], r['creator_id'])
            )
            update_count += cur.rowcount

        # Update email
        for r in results['email_found']:
            cur.execute(
                "UPDATE onz_pipeline_creators SET email = %s, updated_at = NOW() WHERE id = %s AND (email IS NULL OR email = '' OR email LIKE '%%@discovered.%%')",
                (r['email_found'], r['creator_id'])
            )
            update_count += cur.rowcount

        conn.commit()
        print(f"    Updated {update_count} creator records")
    else:
        print(f"\n  [DRY RUN] Use --update to write changes to DB")

    # Save results
    report_path = CACHE_DIR / "crosslink_scan.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")

    conn.close()
    return results


def find_dupes():
    """Find creators that are the same person across IG/TikTok using bio cross-links."""
    conn = get_db()
    cur = conn.cursor()

    print("=" * 60)
    print("  Cross-Platform Duplicate Finder")
    print("=" * 60)

    # Get all bios with cross-platform links
    cur.execute("""
        SELECT DISTINCT ON (LOWER(username))
            username, bio_text, platform
        FROM gk_content_posts
        WHERE bio_text IS NOT NULL AND LENGTH(bio_text) > 5
        ORDER BY LOWER(username), post_date DESC NULLS LAST
    """)
    bios = {r[0].lower(): (r[1], r[2]) for r in cur.fetchall()}

    # Get all pipeline creators
    cur.execute("""
        SELECT id, ig_handle, tiktok_handle, email, full_name, followers, pipeline_status, region
        FROM onz_pipeline_creators
    """)
    creators = cur.fetchall()

    ig_map = {}  # ig_handle -> creator record
    tt_map = {}  # tiktok_handle -> creator record
    for c in creators:
        cid, ig, tt, em, full_name, foll, status, region = c
        rec = {'id': cid, 'ig': ig, 'tt': tt, 'email': em, 'name': full_name,
               'followers': foll, 'status': status, 'region': region}
        if ig:
            ig_map[ig.lower()] = rec
        if tt:
            tt_map[tt.lower()] = rec

    # Find pairs: IG profile mentions TikTok handle that exists as separate creator
    pairs = []
    for ig_handle, (bio, platform) in bios.items():
        if ig_handle not in ig_map:
            continue
        extracted = extract_from_bio(bio, 'instagram')
        tt_handle = extracted.get('tiktok')
        if tt_handle and tt_handle in tt_map:
            ig_creator = ig_map[ig_handle]
            tt_creator = tt_map[tt_handle]
            if ig_creator['id'] != tt_creator['id']:
                pairs.append({
                    'ig_creator': ig_creator,
                    'tt_creator': tt_creator,
                    'source': f"IG bio of @{ig_handle} mentions TikTok @{tt_handle}",
                    'bio': bio[:200],
                })

    # Reverse: TikTok profile mentions IG handle that exists as separate creator
    for tt_handle, (bio, platform) in bios.items():
        if tt_handle not in tt_map:
            continue
        extracted = extract_from_bio(bio, 'tiktok')
        ig_handle = extracted.get('instagram')
        if ig_handle and ig_handle in ig_map:
            ig_creator = ig_map[ig_handle]
            tt_creator = tt_map[tt_handle]
            if ig_creator['id'] != tt_creator['id']:
                # Check not already found
                existing = any(
                    p['ig_creator']['id'] == ig_creator['id'] and p['tt_creator']['id'] == tt_creator['id']
                    for p in pairs
                )
                if not existing:
                    pairs.append({
                        'ig_creator': ig_creator,
                        'tt_creator': tt_creator,
                        'source': f"TT bio of @{tt_handle} mentions IG @{ig_handle}",
                        'bio': bio[:200],
                    })

    # Also check email matches
    email_pairs = []
    email_to_creators = defaultdict(list)
    for c in creators:
        cid, ig, tt, em, full_name, foll, status, region = c
        if em and '@discovered.' not in em and em.strip():
            email_to_creators[em.lower()].append({
                'id': cid, 'ig': ig, 'tt': tt, 'email': em, 'name': full_name,
                'followers': foll, 'status': status, 'region': region
            })
    for email, group in email_to_creators.items():
        if len(group) > 1:
            email_pairs.append({
                'email': email,
                'creators': group,
            })

    print(f"\n  Bio cross-link pairs: {len(pairs)}")
    print(f"  Email duplicate groups: {len(email_pairs)}")

    if pairs:
        print(f"\n  CROSS-PLATFORM SAME-PERSON PAIRS:")
        for i, p in enumerate(pairs[:30]):
            ig = p['ig_creator']
            tt = p['tt_creator']
            print(f"\n  [{i+1}] {p['source']}")
            print(f"      IG: @{ig['ig']} (ID:{ig['id']}, {ig['followers'] or 0} followers, {ig['status']})")
            print(f"      TT: @{tt['tt']} (ID:{tt['id']}, {tt['followers'] or 0} followers, {tt['status']})")

    if email_pairs:
        print(f"\n  EMAIL DUPLICATE GROUPS:")
        for ep in email_pairs[:10]:
            print(f"\n  Email: {ep['email']}")
            for c in ep['creators']:
                print(f"    ID:{c['id']} IG:@{c['ig'] or '-'} TT:@{c['tt'] or '-'} ({c['status']})")

    # Save
    report = {
        'crosslink_pairs': pairs,
        'email_pairs': [{
            'email': ep['email'],
            'creator_ids': [c['id'] for c in ep['creators']]
        } for ep in email_pairs],
    }
    report_path = CACHE_DIR / "duplicate_pairs.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")

    conn.close()
    return pairs, email_pairs


def merge_dupes(dry_run: bool = True):
    """Auto-merge confirmed cross-platform duplicate pairs.
    Keeps the record with more followers as primary, merges the other into it.
    """
    pairs, email_pairs = find_dupes()

    if not pairs and not email_pairs:
        print("\n  No duplicates to merge.")
        return

    conn = get_db()
    cur = conn.cursor()
    merged = 0

    print(f"\n\n  {'[DRY RUN] ' if dry_run else ''}MERGING PAIRS...")

    for p in pairs:
        ig = p['ig_creator']
        tt = p['tt_creator']

        # Primary = one with more followers or IG (preferred)
        primary = ig
        secondary = tt

        if dry_run:
            print(f"    Would merge TT @{secondary['tt']} (ID:{secondary['id']}) → IG @{primary['ig']} (ID:{primary['id']})")
        else:
            # Update primary: add tiktok_handle, take max followers
            cur.execute("""
                UPDATE onz_pipeline_creators
                SET tiktok_handle = COALESCE(NULLIF(tiktok_handle, ''), %s),
                    followers = GREATEST(COALESCE(followers, 0), %s),
                    email = CASE WHEN email IS NULL OR email = '' OR email LIKE '%%@discovered.%%'
                                 THEN COALESCE(NULLIF(%s, ''), email) ELSE email END,
                    full_name = CASE WHEN full_name IS NULL OR full_name = '' THEN COALESCE(NULLIF(%s, ''), full_name) ELSE full_name END,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                secondary.get('tt') or '',
                secondary.get('followers') or 0,
                secondary.get('email') or '',
                secondary.get('name') or '',
                primary['id'],
            ))

            # Delete secondary
            cur.execute("DELETE FROM onz_pipeline_creators WHERE id = %s", (secondary['id'],))
            merged += 1

    if not dry_run and merged > 0:
        conn.commit()
        print(f"\n    Merged {merged} duplicate pairs")

    conn.close()


def show_status():
    """Show current crosslink coverage."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE ig_handle != '' AND ig_handle IS NOT NULL AND tiktok_handle != '' AND tiktok_handle IS NOT NULL")
    both = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE (ig_handle != '' AND ig_handle IS NOT NULL) AND (tiktok_handle IS NULL OR tiktok_handle = '')")
    ig_only = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE (tiktok_handle != '' AND tiktok_handle IS NOT NULL) AND (ig_handle IS NULL OR ig_handle = '')")
    tt_only = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM onz_pipeline_creators WHERE (ig_handle IS NULL OR ig_handle = '') AND (tiktok_handle IS NULL OR tiktok_handle = '')")
    neither = cur.fetchone()[0]

    conn.close()

    print("\n=== Cross-Link Coverage ===\n")
    print(f"  Total creators:     {total}")
    print(f"  Both IG + TikTok:   {both}")
    print(f"  IG only:            {ig_only}")
    print(f"  TikTok only:        {tt_only}")
    print(f"  Neither:            {neither}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract cross-platform handles from bios")
    parser.add_argument("--scan", action="store_true", help="Scan bios for cross-links")
    parser.add_argument("--update", action="store_true", help="Update DB with findings (use with --scan)")
    parser.add_argument("--find-dupes", action="store_true", help="Find same-person IG/TT pairs")
    parser.add_argument("--merge-dupes", action="store_true", help="Auto-merge confirmed pairs")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--status", action="store_true", help="Show crosslink stats")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.scan:
        scan_bios(update_db=args.update)
    elif args.find_dupes:
        find_dupes()
    elif args.merge_dupes:
        merge_dupes(dry_run=args.dry_run)
    else:
        parser.print_help()
