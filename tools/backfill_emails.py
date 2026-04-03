"""Backfill v2: update existing + create missing creators from Syncly sheet."""
import csv, io, urllib.request, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'export_calculator.settings.production')

import django
django.setup()

from onzenna.models import PipelineCreator
from django.db import IntegrityError
from datetime import date

url = "https://docs.google.com/spreadsheets/d/1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o/export?format=csv&gid=522613099"
data = urllib.request.urlopen(url, timeout=60).read().decode('utf-8')
reader = csv.DictReader(io.StringIO(data))

updated = 0
created = 0
skipped = 0
dupes = 0

for row in reader:
    username = (row.get("Username (id)") or "").strip().lstrip("@")
    email = (row.get("Email") or "").strip()
    platform = (row.get("Platform") or "").strip()
    discovery_raw = (row.get("\uc5d1\uce34 \ubc1c\uacac \uc77c\uc790") or row.get("최초 발견 일자") or "").strip()
    followers_raw = (row.get("Followers") or "0").replace(",", "").strip()
    location = (row.get("Location") or "").strip()
    language = (row.get("Language") or "").strip()

    if not username:
        continue
    handle = username.lower()
    has_email = bool(email and "@" in email and "@discovered." not in email)

    # Parse discovery date (format: YYMMDD or YYYY-MM-DD)
    disc_date = None
    try:
        if len(discovery_raw) == 6:
            disc_date = date(2000 + int(discovery_raw[:2]), int(discovery_raw[2:4]), int(discovery_raw[4:6]))
        elif "-" in discovery_raw:
            parts = discovery_raw.split("-")
            if len(parts[0]) == 4:
                disc_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                disc_date = date(2000 + int(parts[0]), int(parts[1]), int(parts[2]))
    except:
        pass

    followers = 0
    try:
        followers = int(float(followers_raw))
    except:
        pass

    # Determine platform
    plat = "TikTok" if "tiktok" in platform.lower() else "Instagram"
    ig_handle = handle if plat == "Instagram" else ""
    tiktok_handle = handle if plat == "TikTok" else ""

    # HT/LT
    est_r30d = int(followers * (0.15 if plat == "TikTok" else 0.08))
    is_ht = followers >= 50000 and est_r30d >= 100000
    outreach_type = "HT" if is_ht else "LT"

    # Find existing
    existing = PipelineCreator.objects.filter(ig_handle__iexact=handle).first() or \
               PipelineCreator.objects.filter(tiktok_handle__iexact=handle).first()

    if existing:
        if has_email and "@discovered." in (existing.email or ""):
            # Update placeholder email with real one
            if PipelineCreator.objects.filter(email=email).exclude(id=existing.id).exists():
                dupes += 1
                continue
            try:
                existing.email = email
                if location:
                    existing.country = location
                existing.save(update_fields=["email", "country"])
                updated += 1
            except IntegrityError:
                dupes += 1
        else:
            skipped += 1
    else:
        # Create new
        if not has_email:
            email = f"{handle.replace('.', '_')}@discovered.syncly"
        if PipelineCreator.objects.filter(email=email).exists():
            dupes += 1
            continue
        try:
            PipelineCreator.objects.create(
                email=email,
                ig_handle=ig_handle,
                tiktok_handle=tiktok_handle,
                full_name=username,
                platform=plat,
                pipeline_status="Not Started",
                outreach_type=outreach_type,
                source="syncly",
                followers=followers,
                avg_views=est_r30d,
                initial_discovery_date=disc_date or date.today(),
                country=location,
                notes=f"Syncly sheet import",
            )
            created += 1
        except IntegrityError:
            dupes += 1

print(f"Done! Updated: {updated}, Created: {created}, Skipped: {skipped}, Dupes: {dupes}")
