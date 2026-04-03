"""Import a specific weekly batch from cleaned Syncly Excel files.

Reads from Z drive Excel files (exported by export_syncly_clean.py).
Only imports creators with real email, 제휴 상태 blank, not blacklisted.
Deletes existing @discovered.* placeholders for the same week.

Usage:
    python tools/import_syncly_batch.py --week 2026-01-28
    python tools/import_syncly_batch.py --week 2026-01-28 --dry-run
    python tools/import_syncly_batch.py --week 2026-03-18 --clean-only
"""

import os, sys, argparse, re
from datetime import date, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'export_calculator.settings.production')
try:
    import django
    django.setup()
    from onzenna.models import PipelineCreator, PipelineConfig
    DJANGO_OK = True
except Exception:
    DJANGO_OK = False

PROJECT_ROOT = os.path.dirname(DIR)

# Excel file locations
CREATORS_XLSX = os.path.join(
    "Z:", os.sep, "Orbiters", "ORBI CLAUDE_0223", "ORBITERS CLAUDE",
    "ORBITERS CLAUDE", "Shared", "ONZ Creator Collab", "\uc81c\uac08\ub7c9",
    "syncly_creators_clean.xlsx"
)
OUTPUT_XLSX = os.path.join(
    "Z:", os.sep, "Orbiters", "ORBI CLAUDE_0223", "ORBITERS CLAUDE",
    "ORBITERS CLAUDE", "Shared", "ONZ Creator Collab", "\uc81c\uac08\ub7c9",
    "syncly_output_clean.xlsx"
)

# EC2 fallback paths
if not os.path.exists(CREATORS_XLSX):
    CREATORS_XLSX = os.path.join(PROJECT_ROOT, "Data Storage", "syncly_creators_clean.xlsx")
    OUTPUT_XLSX = os.path.join(PROJECT_ROOT, "Data Storage", "syncly_output_clean.xlsx")


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 6 and raw.isdigit():
            return date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:6]))
        elif "-" in raw:
            parts = raw.split("-")
            if len(parts) == 3:
                y = int(parts[0])
                if y < 100:
                    y += 2000
                return date(y, int(parts[1]), int(parts[2]))
    except Exception:
        pass
    return None


def week_dates(week_start_str):
    d = parse_date(week_start_str)
    if not d:
        return []
    return [d + timedelta(days=i) for i in range(7)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True, help="Week start date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clean-only", action="store_true", help="Only delete placeholders")
    args = parser.parse_args()

    target_dates = week_dates(args.week)
    if not target_dates:
        print(f"Invalid week date: {args.week}")
        return

    print(f"Target week: {target_dates[0]} to {target_dates[-1]}", flush=True)

    # Step 1: Clean @discovered.* placeholders for this week
    if DJANGO_OK:
        placeholders = PipelineCreator.objects.filter(
            email__icontains="@discovered.",
            pipeline_status="Not Started",
            initial_discovery_date__gte=target_dates[0],
            initial_discovery_date__lte=target_dates[-1],
        )
        ph_count = placeholders.count()
        if args.dry_run:
            print(f"[DRY RUN] Would delete {ph_count} @discovered.* placeholders", flush=True)
        else:
            deleted = placeholders.delete()[0]
            print(f"Cleaned {deleted} @discovered.* placeholders", flush=True)

    if args.clean_only:
        return

    # Step 2: Read creators Excel
    try:
        import openpyxl
    except ImportError:
        os.system(f'"{sys.executable}" -m pip install openpyxl')
        import openpyxl

    if not os.path.exists(CREATORS_XLSX):
        print(f"ERROR: Creators file not found: {CREATORS_XLSX}", flush=True)
        print("Run export_syncly_clean.py first to generate the Excel files.", flush=True)
        return

    print(f"Reading {CREATORS_XLSX}...", flush=True)
    wb = openpyxl.load_workbook(CREATORS_XLSX, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    headers = [str(h or "") for h in rows[0]]
    data_rows = rows[1:]
    print(f"  Total rows: {len(data_rows)}", flush=True)

    # Build header index
    def col_idx(name):
        for i, h in enumerate(headers):
            if name in h:
                return i
        return -1

    idx_platform = col_idx("Platform")
    idx_collab = col_idx("\uc81c\ud734 \uc0c1\ud0dc")  # 제휴 상태
    if idx_collab < 0:
        idx_collab = col_idx("제휴 상태")
    idx_blacklist = col_idx("Blacklist")
    idx_username = col_idx("Username")
    idx_email = col_idx("Email")
    idx_discovery = col_idx("\ucd5c\ucd08 \ubc1c\uacac")  # 최초 발견 일자
    if idx_discovery < 0:
        idx_discovery = col_idx("발견")

    print(f"  Column indices: platform={idx_platform} collab={idx_collab} blacklist={idx_blacklist} username={idx_username} email={idx_email} discovery={idx_discovery}", flush=True)

    # Step 3: Filter to target week
    target_date_set = set(target_dates)
    matched = []
    for row in data_rows:
        disc_raw = str(row[idx_discovery] or "") if idx_discovery >= 0 and idx_discovery < len(row) else ""
        disc_date = parse_date(disc_raw)
        if disc_date and disc_date in target_date_set:
            matched.append(row)

    print(f"  Matched {len(matched)} rows for week {args.week}", flush=True)

    if not matched:
        print("No rows found for this week.", flush=True)
        return

    # Step 4: Build eligible list (already filtered by export_syncly_clean.py, but double-check)
    eligible = []
    skip_collab = 0
    skip_no_email = 0
    skip_invalid = 0

    for row in matched:
        def cell(idx):
            return str(row[idx] or "").strip() if 0 <= idx < len(row) else ""

        username = cell(idx_username).lstrip("@").lower()
        email_val = cell(idx_email)
        collab = cell(idx_collab)
        platform_val = cell(idx_platform)
        disc_raw = cell(idx_discovery)

        if not username or not re.match(r'^[a-zA-Z0-9._]+$', username):
            skip_invalid += 1
            continue

        if collab:
            skip_collab += 1
            continue

        if not email_val or "@" not in email_val or "@discovered." in email_val.lower():
            skip_no_email += 1
            continue

        eligible.append({
            "username": username,
            "email": email_val,
            "platform": platform_val,
            "discovery_date": parse_date(disc_raw),
        })

    print(f"\nEligible: {len(eligible)}", flush=True)
    print(f"  Skipped (collab): {skip_collab}, no email: {skip_no_email}, invalid: {skip_invalid}", flush=True)

    if not DJANGO_OK or args.dry_run:
        for e in eligible[:10]:
            print(f"  {e['username']} | {e['email']} | {e['platform']} | {e['discovery_date']}", flush=True)
        if len(eligible) > 10:
            print(f"  ... and {len(eligible) - 10} more", flush=True)
        if args.dry_run:
            print("\n[DRY RUN] No DB changes made", flush=True)
        return

    # Step 5: Import to DB
    ht_follower_min = 50000
    ht_threshold = 100000
    try:
        cfg = PipelineConfig.objects.order_by('-date').first()
        if cfg and cfg.ht_threshold:
            ht_threshold = cfg.ht_threshold
        if cfg and cfg.ht_follower_min:
            ht_follower_min = cfg.ht_follower_min
    except Exception:
        pass

    created = 0
    updated = 0
    dupes = 0

    for e in eligible:
        handle = e["username"]
        email_val = e["email"]
        plat = "TikTok" if "tiktok" in (e["platform"] or "").lower() else "Instagram"
        ig_handle = handle if plat == "Instagram" else ""
        tiktok_handle = handle if plat == "TikTok" else ""
        disc_date = e["discovery_date"] or target_dates[0]

        existing = PipelineCreator.objects.filter(ig_handle__iexact=handle).first() or \
                   PipelineCreator.objects.filter(tiktok_handle__iexact=handle).first()

        if existing:
            if "@discovered." in (existing.email or ""):
                if not PipelineCreator.objects.filter(email=email_val).exclude(id=existing.id).exists():
                    existing.email = email_val
                    if not existing.initial_discovery_date:
                        existing.initial_discovery_date = disc_date
                    existing.save()
                    updated += 1
                else:
                    dupes += 1
            continue

        if PipelineCreator.objects.filter(email=email_val).exists():
            dupes += 1
            continue

        try:
            PipelineCreator.objects.create(
                email=email_val,
                ig_handle=ig_handle,
                tiktok_handle=tiktok_handle,
                full_name=handle,
                platform=plat,
                pipeline_status="Not Started",
                outreach_type="LT",
                source="syncly",
                initial_discovery_date=disc_date,
                notes="Syncly batch import (real email)",
            )
            created += 1
        except Exception:
            dupes += 1

    print(f"\nResult: Created={created}, Updated={updated}, Dupes={dupes}", flush=True)

    # Show final count for this week
    if DJANGO_OK:
        week_count = PipelineCreator.objects.filter(
            pipeline_status="Not Started",
            initial_discovery_date__gte=target_dates[0],
            initial_discovery_date__lte=target_dates[-1],
        ).count()
        week_email = PipelineCreator.objects.filter(
            pipeline_status="Not Started",
            initial_discovery_date__gte=target_dates[0],
            initial_discovery_date__lte=target_dates[-1],
        ).exclude(email__icontains="@discovered.").exclude(email="").count()
        print(f"Week {args.week}: {week_count} total Not Started, {week_email} with real email", flush=True)


if __name__ == "__main__":
    main()
